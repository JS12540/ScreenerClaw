"""
ScreenerClaw — Smart Ticker Resolver

Resolves user input to a valid Screener.in ticker symbol.

Resolution order:
  1. Known aliases        (instant hardcoded map for top ~80 stocks)
  2. Local NSE universe   (downloaded CSV → JSON cache, fuzzy name search)
  3. BSE code → NSE       (6-digit BSE code → Screener.in search → extract NSE symbol)
  4. Screener.in search API
  5. DuckDuckGo fallback

Key fix over previous version:
  - resolve_ticker() accepts `company_name` (from QueryRouter) as a second query
    so that even if the LLM abbreviates "arrowgreentech" → "AGT", we can still
    fuzzy-match "arrowgreentech" against the full NSE listing.
  - "Direct symbol" fallback now verifies the symbol exists in the NSE universe
    before accepting it blindly.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

import httpx

from backend.logger import get_logger

logger = get_logger(__name__)

SCREENER_SEARCH_URL = "https://www.screener.in/api/company/search/?q={query}&v=3&fts=1"

# Common company name → NSE symbol mappings for instant resolution
KNOWN_ALIASES: dict[str, str] = {
    # Tata Group
    "tcs": "TCS", "tata consultancy": "TCS", "tata consultancy services": "TCS",
    "tata motors": "TATAMOTORS", "tata steel": "TATASTEEL",
    "tata power": "TATAPOWER", "tata chemicals": "TATACHEMICALS",
    "tata consumer": "TATACONSUM", "titan": "TITAN", "tanishq": "TITAN",
    "tata comm": "TATACOMM", "tata communications": "TATACOMM",
    # Reliance
    "reliance": "RELIANCE", "ril": "RELIANCE", "reliance industries": "RELIANCE",
    "jio": "RELIANCE",
    # HDFC Group
    "hdfc bank": "HDFCBANK", "hdfc": "HDFCBANK",
    "hdfc life": "HDFCLIFE", "hdfc amc": "HDFCAMC",
    "hdfcamc": "HDFCAMC",
    # Infosys
    "infosys": "INFY", "infy": "INFY", "infossys": "INFY", "infosis": "INFY",
    # ICICI Group
    "icici bank": "ICICIBANK", "icici": "ICICIBANK",
    "icici prudential": "ICICIPRULI", "icici lombard": "ICICIGI",
    # Wipro
    "wipro": "WIPRO",
    # HCL
    "hcl tech": "HCLTECH", "hcl technologies": "HCLTECH", "hcltech": "HCLTECH",
    # Axis Bank
    "axis bank": "AXISBANK", "axis": "AXISBANK",
    # SBI
    "sbi": "SBIN", "state bank": "SBIN", "state bank of india": "SBIN",
    # Kotak
    "kotak": "KOTAKBANK", "kotak mahindra": "KOTAKBANK", "kotak bank": "KOTAKBANK",
    # Bajaj
    "bajaj finance": "BAJFINANCE", "bajaj finserv": "BAJAJFINSV",
    "bajaj auto": "BAJAJ-AUTO",
    # Maruti
    "maruti": "MARUTI", "maruti suzuki": "MARUTI",
    # Asian Paints
    "asian paints": "ASIANPAINT", "asian paint": "ASIANPAINT",
    # Hindustan Unilever
    "hul": "HINDUNILVR", "hindustan unilever": "HINDUNILVR", "unilever india": "HINDUNILVR",
    # ITC
    "itc": "ITC",
    # L&T
    "l&t": "LT", "larsen": "LT", "larsen and toubro": "LT", "larsen & toubro": "LT",
    # Sun Pharma
    "sun pharma": "SUNPHARMA", "sun pharmaceutical": "SUNPHARMA",
    # Dr Reddy
    "dr reddy": "DRREDDY", "dr. reddy": "DRREDDY", "drreddys": "DRREDDY",
    # Cipla
    "cipla": "CIPLA",
    # Divis
    "divis": "DIVISLAB", "divis lab": "DIVISLAB", "divi's": "DIVISLAB",
    # Power Grid
    "power grid": "POWERGRID",
    # NTPC
    "ntpc": "NTPC",
    # Coal India
    "coal india": "COALINDIA",
    # Adani
    "adani ports": "ADANIPORTS", "adani enterprises": "ADANIENT",
    "adani green": "ADANIGREEN", "adani power": "ADANIPOWER",
    # Zomato
    "zomato": "ZOMATO",
    # Paytm
    "paytm": "PAYTM", "one97": "PAYTM",
    # Nykaa
    "nykaa": "NYKAA", "fss": "NYKAA",
    # Indigo
    "indigo": "INDIGO", "interglobe": "INDIGO",
    # M&M
    "mahindra": "M&M", "m&m": "M&M", "mahindra and mahindra": "M&M",
    # Hero
    "hero motocorp": "HEROMOTOCO", "hero moto": "HEROMOTOCO",
    # Nestle
    "nestle": "NESTLEIND", "nestle india": "NESTLEIND",
    # Pidilite
    "pidilite": "PIDILITIND", "fevicol": "PIDILITIND",
    # Dmart
    "dmart": "DMART", "avenue supermarts": "DMART", "avenue": "DMART",
    # Havells
    "havells": "HAVELLS",
    # Dixon
    "dixon": "DIXON",
    # Muthoot
    "muthoot": "MUTHOOTFIN", "muthoot finance": "MUTHOOTFIN",
    # Godrej
    "godrej consumer": "GODREJCP", "godrej properties": "GODREJPROP",
}


async def resolve_ticker(
    user_input: str,
    http_client: Optional[httpx.AsyncClient] = None,
    company_name: Optional[str] = None,
) -> tuple[str, str]:
    """
    Resolve user input to a Screener.in ticker symbol.

    Args:
        user_input:   Ticker or company name extracted by QueryRouter LLM.
                      May be an abbreviation like "AGT" even for "arrowgreentech".
        http_client:  Optional shared httpx client.
        company_name: Full company name from QueryRouter (e.g. "Arrow Greentech").
                      Used as a fallback query when user_input is a short abbreviation
                      that doesn't match anything in the universe.

    Returns:
        (ticker, method) — e.g. ("ARROWGREEN", "universe_name")

    Raises:
        ValueError: if no ticker could be resolved.
    """
    raw = user_input.strip()
    cleaned = _extract_company_from_query(raw)
    logger.info("Ticker resolver: raw=%r cleaned=%r company_name=%r", raw, cleaned, company_name)

    # ── Step 1: Known aliases ─────────────────────────────────────────────────
    for candidate in _candidates(cleaned, company_name):
        alias = _check_aliases(candidate)
        if alias:
            logger.info("Ticker resolved via alias: %s → %s", candidate, alias)
            return alias, "alias"

    # ── Step 2: Local NSE universe (name search) ──────────────────────────────
    # Try every candidate string: the extracted ticker/name AND the company_name.
    # This catches "AGT" passed from LLM but "arrowgreentech" found via company_name.
    universe_result = _universe_search(cleaned, company_name)
    if universe_result:
        logger.info(
            "Ticker resolved via universe: query=%r → %s (match_type=%s, score=%s)",
            universe_result["_query"],
            universe_result["symbol"],
            universe_result["match_type"],
            universe_result["score"],
        )
        return universe_result["symbol"], f"universe_{universe_result['match_type']}"

    # ── Step 3: BSE 6-digit code ──────────────────────────────────────────────
    if re.match(r"^\d{6}$", cleaned.strip()):
        screener_result = await _screener_search(cleaned.strip(), http_client)
        if screener_result:
            logger.info("BSE code resolved via Screener.in: %s → %s", cleaned, screener_result)
            return screener_result, "bse_code"

    # ── Step 4: Direct symbol — only accept if verified in universe ───────────
    if _looks_like_symbol(cleaned):
        from backend.screener.stock_universe import is_valid_nse_symbol
        if is_valid_nse_symbol(cleaned):
            logger.info("Ticker resolved as verified direct symbol: %s", cleaned.upper())
            return cleaned.upper(), "direct_verified"
        else:
            logger.info(
                "Symbol %r not in NSE universe — skipping direct fallback, trying Screener.in",
                cleaned.upper(),
            )

    # ── Step 5: Screener.in search API ───────────────────────────────────────
    for candidate in _candidates(cleaned, company_name):
        screener_result = await _screener_search(candidate, http_client)
        if screener_result:
            logger.info("Ticker resolved via Screener.in: %s → %s", candidate, screener_result)
            return screener_result, "screener_search"

    # ── Step 6: DuckDuckGo fallback ───────────────────────────────────────────
    for candidate in _candidates(cleaned, company_name):
        ddg_result = await _ddg_resolve(candidate)
        if ddg_result:
            logger.info("Ticker resolved via DuckDuckGo: %s → %s", candidate, ddg_result)
            return ddg_result, "duckduckgo"

    raise ValueError(
        f"Could not resolve '{cleaned}' to a known Indian stock ticker. "
        "Please use the NSE symbol (e.g. TCS, INFY, RELIANCE) or the full company name."
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _candidates(cleaned: str, company_name: Optional[str]) -> list[str]:
    """Return de-duplicated list of strings to try, cleaned first."""
    seen: set[str] = set()
    result: list[str] = []
    for s in filter(None, [cleaned, company_name]):
        key = s.lower().strip()
        if key not in seen:
            seen.add(key)
            result.append(s.strip())
    return result


def _universe_search(cleaned: str, company_name: Optional[str]) -> Optional[dict]:
    """
    Search the local NSE universe with all available candidate strings.
    Returns the best match dict (with added _query key) or None.
    Requires score >= 0.75 to avoid false positives.
    """
    from backend.screener.stock_universe import search_universe

    MIN_SCORE = 0.75

    best: Optional[dict] = None
    best_score: float = 0.0

    for query in _candidates(cleaned, company_name):
        matches = search_universe(query, limit=3, exchange_filter="NSE")
        if matches and matches[0]["score"] >= MIN_SCORE:
            if matches[0]["score"] > best_score:
                best_score = matches[0]["score"]
                best = {**matches[0], "_query": query}

    return best


def _extract_company_from_query(query: str) -> str:
    """Strip common analysis trigger words to isolate the company name/symbol."""
    patterns = [
        r"^(?:analyse|analyze|analysis of|check|research|tell me about|what about|"
        r"intrinsic value of|value of|price target for|evaluate|review|"
        r"should i buy|buy or sell|is it worth buying)\s+",
        r"\s+(?:stock|share|equity|ltd|limited|inc|corp|corporation)$",
    ]
    result = query.strip()
    for pattern in patterns:
        result = re.sub(pattern, "", result, flags=re.IGNORECASE).strip()
    return result


def _check_aliases(text: str) -> Optional[str]:
    """Check against known company name → ticker mappings."""
    key = text.lower().strip()
    if key in KNOWN_ALIASES:
        return KNOWN_ALIASES[key]
    for alias, ticker in KNOWN_ALIASES.items():
        if alias in key or key in alias:
            if len(alias) >= 4:
                return ticker
    return None


def _looks_like_symbol(text: str) -> bool:
    """Return True if text looks like a direct NSE symbol (no spaces, 2-15 chars)."""
    t = text.strip().upper()
    if re.match(r"^[A-Z0-9&\-]{2,15}$", t) and " " not in t:
        return True
    return False


async def _screener_search(query: str, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """Search Screener.in autocomplete API and return the best matching ticker."""
    url = SCREENER_SEARCH_URL.format(query=query.replace(" ", "+"))

    async def _do_search(c: httpx.AsyncClient) -> Optional[str]:
        try:
            resp = await c.get(url, timeout=8.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            if isinstance(data, list) and data:
                first = data[0]
                url_field = first.get("url", "")
                ticker_match = re.search(r"/company/([^/]+)/", url_field)
                if ticker_match:
                    return ticker_match.group(1).upper()
                name = first.get("name", "")
                if name:
                    return name.upper().split()[0]
            return None
        except Exception as exc:
            logger.warning("Screener.in search failed: %s", exc)
            return None

    if client:
        return await _do_search(client)
    else:
        async with httpx.AsyncClient() as c:
            return await _do_search(c)


async def _ddg_resolve(query: str) -> Optional[str]:
    """Use DuckDuckGo to find the NSE/BSE ticker for a company name."""
    try:
        from ddgs import DDGS
        search_query = f"{query} NSE BSE India stock ticker symbol screener.in"

        def _sync_search():
            with DDGS() as ddgs:
                return list(ddgs.text(search_query, max_results=5))

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _sync_search)

        for r in results:
            body = r.get("body", "") + " " + r.get("title", "")
            match = re.search(r"(?:NSE|BSE):\s*([A-Z]{2,15})", body)
            if match:
                return match.group(1)
            url = r.get("href", "")
            ticker_match = re.search(r"screener\.in/company/([^/]+)/", url)
            if ticker_match:
                return ticker_match.group(1).upper()

        return None
    except Exception as exc:
        logger.warning("DuckDuckGo ticker resolve failed: %s", exc)
        return None
