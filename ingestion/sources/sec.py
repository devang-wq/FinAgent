"""SEC EDGAR connector.

Fetches recent 10-K / 10-Q / 8-K filings via EDGAR full-text search.
No API key required; rate-limited to 10 req/s per SEC fair-use policy.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta

import aiohttp
from bs4 import BeautifulSoup

from core.config import settings
from observability.circuit_breakers import sec_breaker

_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_FILING_URL = "https://www.sec.gov"
_RATE = asyncio.Semaphore(10)          # 10 concurrent requests max

_FORM_TYPES = ["10-K", "10-Q", "8-K"]
_SEARCH_TERMS = [
    "money laundering",
    "sanctions compliance",
    "politically exposed",
    "beneficial ownership",
    "anti-bribery",
    "OFAC",
]


@sec_breaker
async def fetch_sec_filings(
    days_back: int = 180,
    max_docs: int = 300,
) -> list[dict]:
    """Return a list of {document_id, title, text, date, source} dicts."""
    start = (datetime.utcnow() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    end = datetime.utcnow().strftime("%Y-%m-%d")

    filing_urls: list[tuple[str, str, str]] = []  # (url, title, date)

    async with aiohttp.ClientSession(
        headers={"User-Agent": settings.sec_user_agent}
    ) as session:
        for term in _SEARCH_TERMS:
            if len(filing_urls) >= max_docs:
                break
            hits = await _search(session, term, start, end)
            filing_urls.extend(hits)

        filing_urls = list({u: (u, t, d) for u, t, d in filing_urls}.values())[:max_docs]

        tasks = [_fetch_filing(session, url, title, date) for url, title, date in filing_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    docs = [r for r in results if isinstance(r, dict) and r.get("text")]
    return docs


async def _search(
    session: aiohttp.ClientSession,
    query: str,
    start: str,
    end: str,
) -> list[tuple[str, str, str]]:
    params = {
        "q": f'"{query}"',
        "dateRange": "custom",
        "startdt": start,
        "enddt": end,
        "forms": ",".join(_FORM_TYPES),
        "hits.hits.total.value": 20,
    }
    async with _RATE:
        try:
            async with session.get(_SEARCH_URL, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

    hits = data.get("hits", {}).get("hits", [])
    results = []
    for hit in hits:
        src = hit.get("_source", {})
        file_date = src.get("file_date", "")
        entity = src.get("entity_name", "")
        form = src.get("form_type", "")
        # build filing index URL
        accession = src.get("accession_no", "").replace("-", "")
        cik = str(src.get("entity_id", "")).zfill(10)
        if accession and cik:
            url = f"{_FILING_URL}/Archives/edgar/data/{int(cik)}/{accession}-index.htm"
            title = f"{entity} {form} {file_date}"
            results.append((url, title, file_date))
    return results


async def _fetch_filing(
    session: aiohttp.ClientSession,
    index_url: str,
    title: str,
    date: str,
) -> dict | None:
    async with _RATE:
        try:
            async with session.get(index_url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status != 200:
                    return None
                html = await resp.text(errors="replace")
        except Exception:
            return None

    # find the primary document link inside the filing index
    soup = BeautifulSoup(html, "lxml")
    doc_link = None
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".htm") and "-index" not in href:
            doc_link = _FILING_URL + href if href.startswith("/") else href
            break

    if not doc_link:
        return None

    async with _RATE:
        try:
            async with session.get(doc_link, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    return None
                content = await resp.text(errors="replace")
        except Exception:
            return None

    text = _strip_html(content)[:60_000]   # cap at 60 K chars per filing
    if len(text) < 200:
        return None

    return {
        "document_id": f"sec:{index_url.split('/')[-1]}",
        "title": title,
        "text": text,
        "date": date,
        "source": "sec",
    }


def _strip_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "table"]):
        tag.decompose()
    text = soup.get_text(separator=" ")
    return re.sub(r"\s{2,}", " ", text).strip()
