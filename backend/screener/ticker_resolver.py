"""
ScreenerClaw — Smart Ticker Resolver

Resolves user input to a valid Screener.in ticker symbol.
Handles:
  - Direct NSE symbols (TCS, INFY, RELIANCE)
  - BSE codes (500325, 532540)
  - Company names ("Tata Consultancy", "Reliance Industries")
  - Partial names ("Tata Cons", "Infosys Tech")
  - Common misspellings ("Infossys", "Relaince")
  - Mixed input ("Analyse hdfc bank" → "HDFCBANK")

Resolution order:
  1. Direct symbol attempt (if input looks like a symbol)
  2. Screener.in search API
  3. DuckDuckGo search as fallback
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
# (covers most frequently searched Indian stocks)
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
) -> tuple[str, str]:
    """
    Resolve user input to a Screener.in ticker symbol.

    Returns:
        (ticker, method) — e.g. ("TCS", "direct") or ("INFY", "screener_search")

    Raises:
        ValueError: if no ticker could be resolved
    """
    raw = user_input.strip()

    # ── Step 0: Extract ticker from natural language ──────────────────────────
    # e.g. "analyse TCS" → "TCS", "what is the value of Reliance" → "Reliance"
    cleaned = _extract_company_from_query(raw)
    logger.info("Ticker resolver: raw=%r cleaned=%r", raw, cleaned)

    # ── Step 1: Known aliases (instant, handles misspellings + common names) ──
    alias_result = _check_aliases(cleaned)
    if alias_result:
        logger.info("Ticker resolved via alias: %s → %s", cleaned, alias_result)
        return alias_result, "alias"

    # ── Step 2: Looks like a direct symbol or BSE code — try it directly ──────
    if _looks_like_symbol(cleaned):
        logger.info("Ticker resolved as direct symbol: %s", cleaned.upper())
        return cleaned.upper(), "direct"

    # ── Step 3: Screener.in search API ───────────────────────────────────────
    screener_result = await _screener_search(cleaned, http_client)
    if screener_result:
        logger.info("Ticker resolved via Screener.in search: %s → %s", cleaned, screener_result)
        return screener_result, "screener_search"

    # ── Step 4: DuckDuckGo fallback ───────────────────────────────────────────
    ddg_result = await _ddg_resolve(cleaned)
    if ddg_result:
        logger.info("Ticker resolved via DuckDuckGo: %s → %s", cleaned, ddg_result)
        return ddg_result, "duckduckgo"

    raise ValueError(
        f"Could not resolve '{cleaned}' to a known Indian stock ticker. "
        "Please use the NSE symbol (e.g. TCS, INFY, RELIANCE) or the company name."
    )


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
    # Exact match
    if key in KNOWN_ALIASES:
        return KNOWN_ALIASES[key]
    # Partial match — if input contains a known alias key
    for alias, ticker in KNOWN_ALIASES.items():
        if alias in key or key in alias:
            if len(alias) >= 4:  # avoid matching very short keys like "sbi" in "subsidiary"
                return ticker
    return None


def _looks_like_symbol(text: str) -> bool:
    """Return True if text looks like a direct NSE/BSE symbol or BSE code."""
    t = text.strip().upper()
    # BSE numeric code: 6 digits
    if re.match(r"^\d{6}$", t):
        return True
    # NSE symbol: 2-15 uppercase letters/digits/hyphens, no spaces
    if re.match(r"^[A-Z0-9&\-]{2,15}$", t) and " " not in t:
        return True
    return False


async def _screener_search(query: str, client: Optional[httpx.AsyncClient] = None) -> Optional[str]:
    """Search Screener.in's autocomplete API and return the best matching ticker."""
    url = SCREENER_SEARCH_URL.format(query=query.replace(" ", "+"))

    async def _do_search(c: httpx.AsyncClient) -> Optional[str]:
        try:
            resp = await c.get(url, timeout=8.0)
            if resp.status_code != 200:
                return None
            data = resp.json()
            # Response is a list of {id, name, url, ...} or similar
            if isinstance(data, list) and data:
                # First result is best match — extract ticker from url or name
                first = data[0]
                # URL format: /company/TCS/
                url_field = first.get("url", "")
                ticker_match = re.search(r"/company/([^/]+)/", url_field)
                if ticker_match:
                    return ticker_match.group(1).upper()
                # Fallback: use the 'name' field
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
            # Look for NSE: or BSE: patterns in results
            match = re.search(r"(?:NSE|BSE):\s*([A-Z]{2,15})", body)
            if match:
                return match.group(1)
            # Look for screener.in URL pattern
            url = r.get("href", "")
            ticker_match = re.search(r"screener\.in/company/([^/]+)/", url)
            if ticker_match:
                return ticker_match.group(1).upper()

        return None
    except Exception as exc:
        logger.warning("DuckDuckGo ticker resolve failed: %s", exc)
        return None
