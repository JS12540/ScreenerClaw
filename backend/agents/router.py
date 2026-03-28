"""
Query Router — Phase 1
Sends user query to LLM to determine: single stock analysis or screening mode.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.llm_client import LLMClient

logger = logging.getLogger(__name__)

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
  "clarifications_needed": []
}}

For single_stock: extract ticker symbol (e.g. TCS, RELIANCE, HDFCBANK, INFY).
Handle company names too: "Tata Consultancy" → ticker "TCS", "Reliance Industries" → "RELIANCE".

For screening, translate NL to Screener.in query syntax using ONLY these exact field names:
- Return on capital employed > 20
- Return on equity > 15
- Price to Earning < 25
- Market Capitalization > 5000 (in Crores)
- Debt to equity < 0.5
- Dividend yield > 2
- Sales growth 5years > 15
- Profit growth 5years > 15
- Sales growth 3years > 15
- Profit growth 3years > 15
- Price to book value < 3
- Current ratio > 1.5
- EV/EBITDA < 15

DO NOT include sector/industry filters — they are not supported.

Examples:
- "low PE IT companies" → "Return on capital employed > 15 AND Price to Earning < 20"
- "high ROCE midcap compounders" → "Return on capital employed > 20 AND Market Capitalization > 5000 AND Market Capitalization < 20000 AND Sales growth 5years > 15"
- "debt free high growth" → "Debt to equity < 0.1 AND Sales growth 5years > 15 AND Profit growth 5years > 15"
- "quality dividend stocks" → "Return on capital employed > 20 AND Dividend yield > 2 AND Debt to equity < 0.5"
"""


class QueryRouter:

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def route(self, user_query: str) -> dict[str, Any]:
        """
        Route a user query.
        Returns dict with keys: mode, ticker, company_name, screener_query, clarifications_needed
        """
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
            logger.error("Router LLM call failed: %s", exc)
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
            "Routed query %r → mode=%s ticker=%s",
            user_query,
            result["mode"],
            result.get("ticker"),
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
        ticker = ticker_match.group(1) if ticker_match else None
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
