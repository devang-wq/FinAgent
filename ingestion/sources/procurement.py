"""USASpending.gov connector.

Fetches federal contract awards for defence / tech / finance sectors.
No API key required.
"""
from __future__ import annotations

import asyncio

import aiohttp

from observability.circuit_breakers import procurement_breaker

_API = "https://api.usaspending.gov/api/v2/search/spending_by_award/"
_RATE = asyncio.Semaphore(5)

_KEYWORDS = [
    "cybersecurity intelligence",
    "financial technology",
    "sanctions monitoring",
    "data analytics intelligence",
    "compliance screening",
]

_AWARD_TYPES = ["A", "B", "C", "D"]    # procurement contract types


@procurement_breaker
async def fetch_contracts(max_docs: int = 500) -> list[dict]:
    docs: list[dict] = []

    async with aiohttp.ClientSession() as session:
        for keyword in _KEYWORDS:
            if len(docs) >= max_docs:
                break
            batch = await _search(session, keyword, limit=max_docs // len(_KEYWORDS) + 10)
            docs.extend(batch)

    seen: set[str] = set()
    deduped = []
    for d in docs:
        if d["document_id"] not in seen:
            seen.add(d["document_id"])
            deduped.append(d)

    return deduped[:max_docs]


async def _search(
    session: aiohttp.ClientSession,
    keyword: str,
    limit: int = 100,
) -> list[dict]:
    payload = {
        "filters": {
            "keywords": [keyword],
            "award_type_codes": _AWARD_TYPES,
        },
        "fields": [
            "Award ID",
            "Recipient Name",
            "Awarding Agency",
            "Award Amount",
            "Start Date",
            "End Date",
            "Description",
            "Place of Performance State Code",
        ],
        "page": 1,
        "limit": min(limit, 100),
        "sort": "Award Amount",
        "order": "desc",
    }

    async with _RATE:
        try:
            async with session.post(
                _API,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
        except Exception:
            return []

    docs: list[dict] = []
    for award in data.get("results", []):
        award_id   = award.get("Award ID", "")
        recipient  = award.get("Recipient Name", "Unknown")
        agency     = award.get("Awarding Agency", "")
        amount     = award.get("Award Amount", 0)
        start      = award.get("Start Date", "")
        desc       = award.get("Description", "")

        if not award_id:
            continue

        text = (
            f"Federal contract award.\n"
            f"Vendor: {recipient}\n"
            f"Awarding agency: {agency}\n"
            f"Contract value: ${amount:,.0f} USD\n"
            f"Start date: {start}\n"
            f"Description: {desc}\n"
            f"Keyword match: {keyword}"
        ).strip()

        state = award.get("Place of Performance State Code", "")
        docs.append({
            "document_id": f"procurement:{award_id}",
            "title": f"{recipient} — {agency}",
            "author": agency,
            "jurisdiction": state or "US",
            "text": text,
            "date": start[:10] if start else "",
        })

    return docs
