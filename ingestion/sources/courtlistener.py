"""CourtListener connector.

Fetches financial-crime and AML-related court opinions via the free
CourtListener REST API. Provides 5 000 req/day unauthenticated; set
COURTLISTENER_TOKEN in .env for higher limits.
"""
from __future__ import annotations

import asyncio

import aiohttp

from core.config import settings
from observability.circuit_breakers import courtlistener_breaker

_BASE = "https://www.courtlistener.com/api/rest/v4"
_RATE = asyncio.Semaphore(5)

_QUERIES = [
    "money laundering AML",
    "sanctions OFAC violation",
    "politically exposed person bribery",
    "beneficial ownership shell company",
    "wire fraud financial crime",
    "SEC fraud enforcement",
]


@courtlistener_breaker
async def fetch_opinions(max_docs: int = 200) -> list[dict]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if settings.courtlistener_token:
        headers["Authorization"] = f"Token {settings.courtlistener_token}"

    opinion_ids: list[int] = []

    async with aiohttp.ClientSession(headers=headers) as session:
        for q in _QUERIES:
            if len(opinion_ids) >= max_docs:
                break
            ids = await _search(session, q, per_page=20)
            opinion_ids.extend(ids)

        opinion_ids = list(dict.fromkeys(opinion_ids))[:max_docs]

        tasks = [_fetch_opinion(session, oid) for oid in opinion_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return [r for r in results if isinstance(r, dict) and r.get("text")]


async def _search(
    session: aiohttp.ClientSession,
    query: str,
    per_page: int = 20,
) -> list[int]:
    params = {"search": query, "page_size": per_page, "format": "json"}
    async with _RATE:
        try:
            async with session.get(
                f"{_BASE}/opinions/",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

    return [int(r["id"]) for r in data.get("results", []) if "id" in r]


async def _fetch_opinion(session: aiohttp.ClientSession, opinion_id: int) -> dict | None:
    async with _RATE:
        try:
            async with session.get(
                f"{_BASE}/opinions/{opinion_id}/",
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            return None

    text = (
        data.get("plain_text")
        or data.get("html_with_citations")
        or data.get("html")
        or ""
    )
    if not text or len(text) < 100:
        return None

    # strip HTML tags if present
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()[:60_000]

    cluster = data.get("cluster", {})
    cluster_dict = cluster if isinstance(cluster, dict) else {}
    date_filed = cluster_dict.get("date_filed", "")
    case_name = cluster_dict.get("case_name", "") or f"Court Opinion {opinion_id}"
    court_id = (
        cluster_dict.get("court_id")
        or cluster_dict.get("court", "")
        or data.get("court_id", "")
        or ""
    )

    return {
        "document_id": f"court:{opinion_id}",
        "title": case_name,
        "author": court_id,
        "jurisdiction": court_id,
        "url": f"https://www.courtlistener.com/opinion/{opinion_id}/",
        "text": text,
        "date": date_filed or "",
    }
