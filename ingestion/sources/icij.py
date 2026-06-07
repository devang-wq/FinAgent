"""ICIJ Offshore Leaks connector.

Downloads the ICIJ Offshore Leaks bulk CSV (Panama Papers, Paradise Papers,
Pandora Papers) and converts graph records into synthetic narrative documents
suitable for vector indexing.

The CSV archive is ~250 MB. It is downloaded once and cached at
ICIJ_DATA_DIR (default: /tmp/icij).
"""
from __future__ import annotations

import asyncio
import csv
import os
import zipfile
from pathlib import Path

import aiohttp

_BULK_URL = "https://offshoreleaks-data.icij.org/offshoreleaks/csv/full-oldb.LATEST.zip"
_CACHE_DIR = Path(os.getenv("ICIJ_DATA_DIR", "/tmp/icij"))

# CSV files inside the zip
_ENTITIES_CSV = "nodes-entities.csv"
_OFFICERS_CSV = "nodes-officers.csv"
_EDGES_CSV    = "relationships.csv"


async def fetch_icij_documents(max_docs: int = 5_000) -> list[dict]:
    await _ensure_downloaded()

    entities  = _load_csv(_CACHE_DIR / _ENTITIES_CSV)
    officers  = _load_csv(_CACHE_DIR / _OFFICERS_CSV)
    edges     = _load_csv(_CACHE_DIR / _EDGES_CSV)

    # Build a quick lookup: node_id → name
    name_map: dict[str, str] = {}
    for row in entities + officers:
        nid = row.get("node_id") or row.get("id", "")
        name = row.get("name", "")
        if nid and name:
            name_map[nid] = name

    # Build adjacency for officers (persons who own/control entities)
    officer_connections: dict[str, list[str]] = {}
    for edge in edges:
        src = edge.get("START_ID", "") or edge.get("_start", "")
        dst = edge.get("END_ID", "") or edge.get("_end", "")
        rel = edge.get("TYPE", "") or edge.get("type", "")
        if src in name_map and dst in name_map:
            officer_connections.setdefault(src, []).append(
                f"{rel} → {name_map[dst]}"
            )

    docs: list[dict] = []

    # Entity documents
    for row in entities[:max_docs // 2]:
        nid   = row.get("node_id") or row.get("id", "")
        name  = row.get("name", "")
        juri  = row.get("jurisdiction", "") or row.get("jurisdiction_description", "")
        incorp = row.get("incorporation_date", "")
        status = row.get("status", "")
        source = row.get("sourceID", "ICIJ")

        if not name:
            continue

        connections = officer_connections.get(nid, [])
        conn_text = "\n".join(f"  - {c}" for c in connections[:10])

        text = (
            f"Offshore entity: {name}\n"
            f"Jurisdiction: {juri}\n"
            f"Incorporation date: {incorp}\n"
            f"Status: {status}\n"
            f"Leak source: {source}\n"
            f"Connections:\n{conn_text}"
        ).strip()

        docs.append({
            "document_id": f"icij:entity:{nid}",
            "title": f"Offshore entity — {name}",
            "author": source,           # "Panama Papers", "Pandora Papers", etc.
            "jurisdiction": juri,       # country/territory from CSV
            "text": text,
            "date": incorp[:10] if incorp else "",
        })

    # Officer documents (persons with offshore holdings)
    for row in officers[: max_docs - len(docs)]:
        nid  = row.get("node_id") or row.get("id", "")
        name = row.get("name", "")
        if not name:
            continue

        connections = officer_connections.get(nid, [])
        conn_text = "\n".join(f"  - {c}" for c in connections[:10])

        text = (
            f"Individual with offshore connections: {name}\n"
            f"Connections:\n{conn_text}"
        ).strip()

        countries = row.get("countries", "") or row.get("country_codes", "")
        docs.append({
            "document_id": f"icij:officer:{nid}",
            "title": f"Individual — {name}",
            "jurisdiction": countries,
            "text": text,
            "date": "",
        })

    return docs[:max_docs]


async def _ensure_downloaded() -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if (_CACHE_DIR / _ENTITIES_CSV).exists():
        return  # already cached

    print("Downloading ICIJ Offshore Leaks data (~250 MB)…")
    zip_path = _CACHE_DIR / "full-oldb.zip"
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
        "Accept": "application/zip,application/octet-stream,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://offshoreleaks.icij.org/",
    }
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(
            _BULK_URL,
            allow_redirects=True,
            timeout=aiohttp.ClientTimeout(total=600),
        ) as resp:
            resp.raise_for_status()
            with zip_path.open("wb") as fh:
                async for chunk in resp.content.iter_chunked(65536):
                    fh.write(chunk)

    try:
        with zipfile.ZipFile(zip_path) as zf:
            for name in zf.namelist():
                if any(name.endswith(f) for f in [_ENTITIES_CSV, _OFFICERS_CSV, _EDGES_CSV]):
                    target = _CACHE_DIR / Path(name).name
                    target.write_bytes(zf.read(name))
    finally:
        zip_path.unlink(missing_ok=True)
    print("ICIJ data cached.")


def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        return list(csv.DictReader(f))
