"""
Query Router — Phase 1
Sends user query to LLM to determine: single stock analysis or screening mode.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.llm_client import LLMClient
from backend.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a query router for a stock research agent.
Your job is to classify whether the user wants:
1. SINGLE STOCK analysis (analyse a specific company)
2. SCREENING (find stocks matching criteria)

Respond ONLY with valid JSON, no extra text."""

ROUTER_PROMPT = """User query: "{query}"

Classify this query and extract relevant info.

Respond in JSON:
{{
  "mode": "single_stock" or "screening",
  "ticker": "SYMBOL or null",
  "company_name": "Full name or null",
  "screener_query": "Screener.in filter syntax or null",
  "intent": "quality|value|growth|dividend|momentum|default",
  "clarifications_needed": []
}}

For single_stock: extract ticker symbol (e.g. TCS, RELIANCE, HDFCBANK, INFY).
Handle company names too: "Tata Consultancy" → ticker "TCS", "Reliance Industries" → "RELIANCE".

For screening, translate natural language to Screener.in query syntax.
Use ONLY these exact field names (case-sensitive as shown):

QUALITY / PROFITABILITY:
  Return on capital employed, Return on equity, Return on assets,
  Profit growth 5Years, Profit growth 3Years, OPM, NPM,
  Average return on equity 5Years, Average return on capital employed 5Years,
  Profit after tax, Operating profit, EPS growth 5Years, Piotroski score

VALUATION:
  Price to Earning, Price to book value, EV/EBITDA, Price to Sales,
  Price to Free Cash Flow, PEG Ratio, Earnings yield, Graham Number,
  Industry PE, Enterprise Value, Market Capitalization

GROWTH:
  Sales growth 5Years, Sales growth 3Years, Sales growth 10Years,
  Profit growth 5Years, Profit growth 3Years, Profit growth 10Years,
  YOY Quarterly sales growth, YOY Quarterly profit growth,
  EPS growth 5Years, EPS growth 3Years, EBIDT growth 5Years

DEBT / SAFETY:
  Debt to equity, Current ratio, Interest Coverage Ratio,
  Quick ratio, Free cash flow last year, Cash from operations last year

DIVIDENDS:
  Dividend yield, Average 5years dividend

OWNERSHIP / GOVERNANCE:
  Promoter holding, Pledged percentage, Change in promoter holding,
  FII holding, DII holding, Change in FII holding

SIZE:
  Market Capitalization (in Crores)
  Smallcap: < 5000 | Midcap: 5000–20000 | Largecap: > 20000

MOMENTUM / PRICE:
  Return over 1year, Return over 3months, Return over 6months,
  Return over 3years, Return over 5years, DMA 50, DMA 200, RSI

CAPITAL EFFICIENCY:
  Debtor days, Working Capital Days, Cash Conversion Cycle,
  Inventory turnover ratio, Asset Turnover Ratio, Return on invested capital,
  Free cash flow 5years, Free cash flow 3years

OPERATORS: > < AND OR + - / *

DO NOT include sector/industry name filters — they are not directly supported.
Use AND to combine conditions. Do not use quotes around values.

Examples:
- "cheap high ROCE stocks" → "Return on capital employed > 22 AND Price to Earning < 15 AND Market Capitalization > 500"
- "high ROCE midcap compounders" → "Return on capital employed > 20 AND Market Capitalization > 5000 AND Market Capitalization < 20000 AND Sales growth 5Years > 15"
- "debt free high growth" → "Debt to equity < 0.1 AND Sales growth 5Years > 15 AND Profit growth 5Years > 15"
- "quality dividend stocks" → "Return on capital employed > 20 AND Dividend yield > 2 AND Debt to equity < 0.5"
- "strong momentum quality" → "Return over 1year > 30 AND Return on capital employed > 20 AND Market Capitalization > 1000"
- "net cash companies" → "Debt to equity < 0.1 AND Free cash flow last year > 0 AND Return on capital employed > 15"
- "undervalued PEG < 1" → "PEG Ratio < 1 AND Return on capital employed > 15 AND Market Capitalization > 500"
- "high piotroski score value" → "Piotroski score > 7 AND Price to Earning < 20 AND Market Capitalization > 500"
- "promoter buying" → "Change in promoter holding > 2 AND Return on capital employed > 15"
- "low pledge quality" → "Pledged percentage < 5 AND Return on capital employed > 20 AND Promoter holding > 50"
"""


class QueryRouter:

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def route(self, user_query: str) -> dict[str, Any]:
        """
        Route a user query.
        Returns dict with keys: mode, ticker, company_name, screener_query, clarifications_needed
        """
        t0 = time.monotonic()
        logger.info("QueryRouter starting", extra={"query": user_query[:80]})
        prompt = ROUTER_PROMPT.format(query=user_query)
        try:
            raw = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=512,
                temperature=0.0,
                json_mode=True,
            )
            result = _parse_json(raw)
        except Exception as exc:
            logger.error("Router LLM call failed", extra={"query": user_query[:80], "error": str(exc)})
            result = _fallback_route(user_query)

        # Validate / fix
        result.setdefault("mode", "single_stock")
        result.setdefault("ticker", None)
        result.setdefault("company_name", None)
        result.setdefault("screener_query", None)
        result.setdefault("clarifications_needed", [])

        # If ticker is given, clean it up
        if result.get("ticker"):
            result["ticker"] = result["ticker"].upper().strip()

        logger.info(
            "QueryRouter done",
            extra={
                "query": user_query[:80],
                "mode": result["mode"],
                "ticker": result.get("ticker"),
                "elapsed_s": round(time.monotonic() - t0, 2),
            },
        )
        return result


def _parse_json(text: str) -> dict:
    """Extract JSON from LLM response (may have markdown fences)."""
    text = text.strip()
    # Remove markdown code fences
    text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON object in text
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _fallback_route(query: str) -> dict:
    """Simple heuristic routing when LLM fails."""
    q = query.lower()
    screening_keywords = [
        "find", "screen", "list", "companies", "stocks", "filter",
        "top", "best", "search", "show me", "which",
    ]
    single_keywords = [
        "analyse", "analyze", "analysis", "report", "value", "valuation",
        "should i buy", "is it good",
    ]

    # Check for ticker-like pattern (2-10 uppercase letters)
    ticker_match = re.search(r"\b([A-Z]{2,10})\b", query.upper())

    is_screening = any(k in q for k in screening_keywords)
    is_single = any(k in q for k in single_keywords) or bool(ticker_match)

    if is_single and not is_screening:
        # If we can't extract a clean symbol, pass the raw query so the smart
        # ticker resolver in the pipeline can handle names/misspellings.
        ticker = ticker_match.group(1) if ticker_match else query.strip()
        return {
            "mode": "single_stock",
            "ticker": ticker,
            "company_name": None,
            "screener_query": None,
        }

    return {
        "mode": "screening",
        "ticker": None,
        "company_name": None,
        "screener_query": "Return on capital employed > 15 AND Debt to equity < 1",
    }
