"""
ScreenerClaw — Stock Universe Cache

Downloads and caches the complete list of NSE and BSE equity listings.
Used for accurate ticker resolution — avoids relying on LLM abbreviations.

Sources:
  NSE: archives.nseindia.com/content/equities/EQUITY_L.csv  (EQ series only)
  BSE: api.bseindia.com  ListofScripData (Equity, Active)

Cache:
  data/nse_stocks.json  — [{symbol, name, name_normalized, isin}]
  data/bse_stocks.json  — [{code, name, name_normalized, isin}]
  Refreshed automatically if older than CACHE_TTL_SECONDS (24h).

Search:
  search_universe(query)  returns list of (symbol, name, score, exchange)
  Matching strategy (in priority order):
    1. Space-collapsed exact match  "arrowgreentech" == "arrowgreentech" (from "Arrow Greentech Ltd")
    2. Normalized exact match
    3. Every word in query found in company name
    4. Starts-with on normalized name
    5. difflib ratio >= 0.72
"""
from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import httpx

from backend.logger import get_logger

logger = get_logger(__name__)

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent.parent.parent / "data"
NSE_CACHE = DATA_DIR / "nse_stocks.json"
BSE_CACHE = DATA_DIR / "bse_stocks.json"

CACHE_TTL = 24 * 3600  # 24 hours

# ── Download URLs ─────────────────────────────────────────────────────────────
NSE_CSV_URL = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
# BSE equity list — two fallback URLs tried in order
BSE_URLS = [
    "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w?Group=&Scripcode=&industry=&segment=Equity&status=Active",
    "https://www.bseindia.com/corporates/List_Scrips.aspx",
]

# ── Normalization ─────────────────────────────────────────────────────────────
# Only strip pure corporate/legal designators — NOT industry words like "bank", "tech", "finance".
# Stripping meaningful words causes companies to normalize to empty strings, breaking search.
_STRIP_WORDS = {
    "limited", "ltd", "private", "pvt", "public",
    "company", "co", "corporation", "corp",
    "incorporated", "inc",
    "the",
}


def _normalize(text: str) -> str:
    """
    Lowercase, strip punctuation, remove common corporate suffixes.
    'Arrow Greentech Limited' → 'arrow greentech'
    """
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", " ", t)
    tokens = [w for w in t.split() if w not in _STRIP_WORDS]
    return " ".join(tokens).strip()


# ── In-memory cache ───────────────────────────────────────────────────────────
_universe: list[dict] = []          # combined NSE + BSE entries
_loaded_at: float = 0.0


# ── Download helpers ──────────────────────────────────────────────────────────

async def _fetch_nse(client: httpx.AsyncClient) -> list[dict]:
    """Download NSE EQUITY_L.csv and return list of stock dicts (EQ series only)."""
    try:
        resp = await client.get(NSE_CSV_URL, timeout=30.0, follow_redirects=True)
        resp.raise_for_status()
        # NSE CSV headers have leading spaces: ' SERIES', ' ISIN NUMBER' etc.
        # Strip all header keys to normalize them.
        raw_reader = csv.DictReader(io.StringIO(resp.text))
        stocks = []
        for row in raw_reader:
            stripped = {k.strip(): v.strip() for k, v in row.items()}
            symbol = stripped.get("SYMBOL", "")
            name = stripped.get("NAME OF COMPANY", "")
            series = stripped.get("SERIES", "")
            isin = stripped.get("ISIN NUMBER", "")
            if symbol and name and series == "EQ":
                stocks.append({
                    "symbol": symbol,
                    "name": name,
                    "name_normalized": _normalize(name),
                    "isin": isin,
                    "exchange": "NSE",
                })
        logger.info("NSE universe downloaded", extra={"count": len(stocks)})
        return stocks
    except Exception as exc:
        logger.warning("NSE universe download failed", extra={"error": str(exc)})
        return []


async def _fetch_bse(client: httpx.AsyncClient) -> list[dict]:
    """
    Download BSE equity list.
    Tries two BSE API endpoints; returns empty list if both fail.
    BSE codes are stored as "symbol" so 6-digit lookups work.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.bseindia.com/",
        "Accept": "application/json, text/plain, */*",
    }
    for url in BSE_URLS:
        try:
            resp = await client.get(url, timeout=30.0, headers=headers, follow_redirects=True)
            resp.raise_for_status()
            data = resp.json()

            # Response can be {"Table": [...]} or a direct list
            if isinstance(data, dict):
                rows = data.get("Table", data.get("data", []))
            elif isinstance(data, list):
                rows = data
            else:
                continue

            stocks = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                # Try multiple field name variants across BSE API versions
                code = str(
                    row.get("SCRIP_CD") or row.get("scripCode") or row.get("Scrip_Code") or ""
                ).strip()
                name = str(
                    row.get("Issuer_Name") or row.get("scrip_name") or row.get("ISSUER_NAME") or ""
                ).strip()
                isin = str(
                    row.get("ISIN_NUMBER") or row.get("isinno") or row.get("ISIN") or ""
                ).strip()
                if code and name and re.match(r"^\d{6}$", code):
                    stocks.append({
                        "symbol": code,
                        "name": name,
                        "name_normalized": _normalize(name),
                        "isin": isin,
                        "exchange": "BSE",
                    })

            if stocks:
                logger.info("BSE universe downloaded", extra={"count": len(stocks), "url": url})
                return stocks

        except Exception as exc:
            logger.warning("BSE URL failed", extra={"url": url, "error": str(exc)})
            continue

    logger.warning("BSE universe download failed — all URLs failed (non-fatal, NSE data still active)")
    return []


# ── Build & persist ───────────────────────────────────────────────────────────

async def build_universe() -> None:
    """
    Download NSE + BSE listings, save to JSON cache files, update in-memory universe.
    Called once at startup; subsequent calls are no-ops if cache is fresh.
    """
    global _universe, _loaded_at

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient() as client:
        nse_stocks, bse_stocks = await asyncio.gather(
            _fetch_nse(client),
            _fetch_bse(client),
        )

    if nse_stocks:
        NSE_CACHE.write_text(
            json.dumps({"updated_at": time.time(), "stocks": nse_stocks}, ensure_ascii=False),
            encoding="utf-8",
        )

    if bse_stocks:
        BSE_CACHE.write_text(
            json.dumps({"updated_at": time.time(), "stocks": bse_stocks}, ensure_ascii=False),
            encoding="utf-8",
        )

    _universe = nse_stocks + bse_stocks
    _loaded_at = time.time()
    logger.info(
        "Stock universe built",
        extra={"nse": len(nse_stocks), "bse": len(bse_stocks), "total": len(_universe)},
    )


def _load_from_cache() -> list[dict]:
    """Load universe from JSON cache files. Returns empty list if files missing."""
    stocks: list[dict] = []
    for cache_file in (NSE_CACHE, BSE_CACHE):
        if cache_file.exists():
            try:
                payload = json.loads(cache_file.read_text(encoding="utf-8"))
                stocks.extend(payload.get("stocks", []))
            except Exception as exc:
                logger.warning("Cache read failed", extra={"file": str(cache_file), "error": str(exc)})
    return stocks


def _cache_is_fresh() -> bool:
    """True if NSE cache exists and is younger than CACHE_TTL. BSE is best-effort."""
    if not NSE_CACHE.exists():
        return False
    try:
        payload = json.loads(NSE_CACHE.read_text(encoding="utf-8"))
        return (time.time() - payload.get("updated_at", 0)) < CACHE_TTL
    except Exception:
        return False


async def ensure_universe() -> None:
    """
    Called at startup. Loads universe from cache if fresh, otherwise re-downloads.
    Non-blocking: if download fails, falls back to stale cache or empty list.
    """
    global _universe, _loaded_at

    if _universe and (time.time() - _loaded_at) < CACHE_TTL:
        return  # already loaded in this process

    if _cache_is_fresh():
        _universe = _load_from_cache()
        _loaded_at = time.time()
        logger.info("Stock universe loaded from cache", extra={"total": len(_universe)})
        return

    logger.info("Stock universe cache stale or missing — downloading...")
    try:
        await build_universe()
    except Exception as exc:
        logger.warning("Universe build failed, falling back to stale cache", extra={"error": str(exc)})
        _universe = _load_from_cache()
        _loaded_at = time.time()


# ── Search ────────────────────────────────────────────────────────────────────

def search_universe(query: str, limit: int = 5, exchange_filter: str = "NSE") -> list[dict]:
    """
    Search the universe for stocks matching query.

    Args:
        query:           Raw user input — company name, partial name, or NSE symbol.
        limit:           Max results to return.
        exchange_filter: "NSE" | "BSE" | "ALL"

    Returns:
        List of dicts: {symbol, name, score, exchange, match_type}
        Sorted by score descending. Empty list if universe not loaded.
    """
    if not _universe:
        return []

    q_raw = query.strip()
    q_norm = _normalize(q_raw)
    q_collapsed = q_norm.replace(" ", "")   # "arrowgreentech" for matching "arrow greentech"
    q_upper = q_raw.upper()

    pool = _universe if exchange_filter == "ALL" else [
        s for s in _universe if s["exchange"] == exchange_filter
    ]

    results: list[tuple[float, dict]] = []

    for stock in pool:
        sym = stock["symbol"]
        name_norm = stock["name_normalized"]
        name_collapsed = name_norm.replace(" ", "")
        score: float = 0.0
        match_type: str = ""

        # 1. Exact NSE symbol match
        if sym == q_upper:
            score = 1.0
            match_type = "symbol_exact"

        # 2. Space-collapsed exact match: "arrowgreentech" == "arrowgreentech"
        elif q_collapsed and q_collapsed == name_collapsed:
            score = 0.98
            match_type = "name_collapsed_exact"

        # 3. Normalized exact match
        elif q_norm and q_norm == name_norm:
            score = 0.96
            match_type = "name_exact"

        # 4. All query words found in company name
        elif q_norm:
            q_words = q_norm.split()
            if q_words and all(w in name_norm for w in q_words):
                # Score by coverage: longer name match = higher relevance
                score = 0.85 + 0.1 * (len(q_norm) / max(len(name_norm), 1))
                match_type = "name_all_words"

        # 5. Name starts with query (collapsed) — require query >= 4 chars to avoid "abc" matching "abcdef bank"
        if not score and q_collapsed and len(q_collapsed) >= 4 and name_collapsed.startswith(q_collapsed):
            score = 0.80
            match_type = "name_startswith"

        # 6. Query starts with a prefix of the name — guards: non-empty name, query >= 5 chars
        #    e.g. "arrowgreen" matches "arrow greentech" because collapsed prefix overlaps
        if (
            not score
            and q_collapsed
            and name_collapsed                           # never match empty-normalized names
            and len(q_collapsed) >= 5
            and len(name_collapsed) >= 4
            and q_collapsed.startswith(name_collapsed[:min(len(name_collapsed), len(q_collapsed))])
        ):
            score = 0.75
            match_type = "partial_prefix"

        # 7. difflib fuzzy on collapsed strings — require >= 6 chars to avoid short symbol noise
        if not score and q_collapsed and len(q_collapsed) >= 6:
            ratio = SequenceMatcher(None, q_collapsed, name_collapsed).ratio()
            if ratio >= 0.72:
                score = ratio * 0.70   # scale down so fuzzy < exact
                match_type = "fuzzy"

        if score > 0:
            results.append((score, {**stock, "score": round(score, 3), "match_type": match_type}))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results[:limit]]


def get_by_symbol(symbol: str) -> Optional[dict]:
    """Return the NSE stock entry for a given symbol, or None if not in universe."""
    sym = symbol.upper().strip()
    for stock in _universe:
        if stock["exchange"] == "NSE" and stock["symbol"] == sym:
            return stock
    return None


def is_valid_nse_symbol(symbol: str) -> bool:
    """Return True if symbol exists in the downloaded NSE universe."""
    if not _universe:
        return True   # universe not loaded yet — don't block resolver
    return get_by_symbol(symbol) is not None
