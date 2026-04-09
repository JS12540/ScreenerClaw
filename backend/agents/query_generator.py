"""
ScreenerClaw — Smart Query Generator Agent
Reads Screener.in raw_data and uses a reasoning LLM to generate targeted,
company-specific web search queries that replace dumb hardcoded templates.

Output: {"business_queries": [...6], "macro_queries": [...4], "news_queries": [...2]}
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.llm_client import LLMClient
from backend.logger import get_logger

logger = get_logger(__name__)


SYSTEM_PROMPT = """You are a senior equity research analyst creating DuckDuckGo/Google search queries.
Your queries will be run on a search engine — they must return real news articles, filings, and data.
You generate keyword-based factual lookup queries, NOT analytical questions.
Respond ONLY with valid JSON."""


QUERY_GEN_PROMPT = """You are generating DuckDuckGo search queries to research an Indian listed company.

## Company Data (from Screener.in)
Company: {company_name} ({symbol})
Sector: {sector} | Industry: {industry}
Business: {about_snippet}
Key Metrics: {key_metrics}
Screener Pros: {pros_text}
Screener Cons: {cons_text}
Listed Peers: {peers_text}
Sector Flags: Pharma={is_pharma} | Tech/IT={is_tech} | Chemicals={is_chemical} | FMCG={is_fmcg} | Export-Heavy={is_export_heavy}

---

## CRITICAL — What makes a GOOD vs BAD search query

BAD queries — DO NOT generate these (return zero useful results on DuckDuckGo):
  BAD: "{company_name} SWOT analysis vulnerabilities"
  BAD: "{company_name} structural risks red flags"
  BAD: "{company_name} overhyped competitive advantage"
  BAD: "India {sector} sector macro headwinds tailwinds"
  BAD: "{company_name} management quality track record"

GOOD queries — these return real news articles, filings, price data:
  GOOD: "{company_name} PVC compound masterbatch revenue FY2024 annual report"
  GOOD: "{company_name} promoter SEBI order insider trading pledge 2024"
  GOOD: "naphtha ethylene price India 2025 petrochemical feedstock import"
  GOOD: "{company_name} Plastiblends India market share plastic additives 2024"
  GOOD: "{company_name} Q3 FY2025 earnings results concall management"
  GOOD: "{company_name} US FDA warning letter import alert 2024"

The rule: GOOD queries contain SPECIFIC NOUNS — product names, raw material names,
competitor names, regulator names, filing types, fiscal years.
BAD queries contain analytical adjectives — "structural", "SWOT", "red flags", "competitive advantage".
Read the Business and Peers fields above and extract real nouns to build your queries.

---

## Output — generate exactly this JSON, no other text:

{{
  "business_queries": ["q1", "q2", "q3", "q4", "q5", "q6"],
  "macro_queries": ["q1", "q2", "q3", "q4"],
  "news_queries": ["q1", "q2"]
}}

---

## How to build business_queries (6 queries):

Query 1 — PRODUCTS & REVENUE MIX:
  Look at the Business description above. Extract the actual product/service names.
  Search for what those specific products earn and how revenue is split.
  Pattern: [company_name] [product_name_from_description] revenue segment FY2024 annual report

Query 2 — COMPETITORS & MARKET DATA:
  Use the peer names from "Listed Peers" above in the query.
  Search for market share comparison or head-to-head data.
  Pattern: [company_name] vs [peer1] [peer2] [product_category] market share India 2024

Query 3 — PROMOTER & MANAGEMENT FACTS:
  Search for concrete events: SEBI orders, promoter pledging, buybacks, acquisitions, governance issues.
  Pattern: [company_name] promoter SEBI pledge shareholding change 2023 2024

Query 4 — CUSTOMERS & CONTRACTS:
  Search for named customers, government orders, export buyers, contract wins/losses.
  Pattern: [company_name] [end_market_sector] customer order contract 2024

Query 5 — RAW MATERIAL & INPUT COSTS:
  Extract the main input/raw material from the Business description.
  Search for its price trend — this is a factual lookup, not an analysis request.
  Pattern: [raw_material_from_description] price India 2024 2025 import [company_name]

Query 6 — SECTOR-SPECIFIC MANDATORY QUERY:
  Use whichever sector flag is True. If none are True, use the capacity/capex pattern.
  Pharma=True    → [company_name] [drug_name] patent expiry ANDA FDA approval 2024 2025
  Tech=True      → [company_name] client attrition deal win H1B visa offshore 2024
  Chemicals=True → [company_name] [chemical_name] China anti-dumping duty India 2024
  FMCG=True      → [company_name] [brand_name] market share distribution 2024
  Export=True    → [company_name] export USD EUR buyer country [product] FY2024
  None=True      → [company_name] capacity expansion capex order book FY2025

---

## How to build macro_queries (4 queries):

These are about the SECTOR environment — real policy, real prices, real trade events.
Reference actual government schemes, regulators, commodity names. No generic phrases.

Query 1 — GOVERNMENT POLICY specific to {sector}:
  What scheme or regulation is actively affecting {sector} right now?
  Chemicals example: "BIS quality control order plastics India import 2024"
  Pharma example:    "NPPA drug price ceiling NLEM 2024 India pharma"
  IT example:        "US H1B visa cap India IT companies 2025"

Query 2 — RAW MATERIAL PRICES for the main input of {sector}:
  What commodity or input does this sector buy? Search its actual price trend.
  Chemicals example: "naphtha crude ethylene price 2025 India petrochemical"
  Pharma example:    "China API bulk drug price India import 2024"
  FMCG example:      "palm oil wheat sugar price India 2025 FMCG input cost"

Query 3 — END-MARKET DEMAND for what {sector} sells into:
  Who buys from this sector? Search for demand data for that buyer market.
  Chemicals example: "India auto production sales 2025 plastic demand"
  IT example:        "BFSI healthcare IT spending India US 2025"

Query 4 — GLOBAL TRADE / IMPORT COMPETITION for {sector}:
  Is China or another country dumping goods into this sector?
  Chemicals example: "China polymer PVC compound import India anti-dumping 2024 2025"
  Pharma example:    "China India generic drug competition pricing 2024"

---

## news_queries (2 queries — recent factual events only):

Query 1: [company_name] [symbol] quarterly results Q3 Q4 FY2025 earnings revenue profit
Query 2: [company_name] [symbol] analyst downgrade target price cut 2025

---

## Checklist before responding (verify each query meets this):
- Contains at least one specific noun from the Company Data above (product, peer name, raw material, scheme name, year)
- Does NOT contain: SWOT, vulnerability, red flag, structural risk, overhyped, competitive advantage, governance quality, headwind, tailwind
- macro_queries reference a specific commodity/scheme/regulator, not "India [sector] outlook"
- All 12 queries are on different topics with no duplication"""


def _build_query_gen_prompt(raw_data: dict) -> str:
    """Extract relevant fields from raw_data and format the prompt."""
    company_name = raw_data.get("company_name") or raw_data.get("symbol", "Company")
    symbol = raw_data.get("symbol", "")
    sector = raw_data.get("sector", "Unknown")
    industry = raw_data.get("industry", sector)
    about = raw_data.get("about", "") or ""
    about_snippet = about[:400].strip()

    # Key metrics string
    pe = raw_data.get("pe", "N/A")
    roce = raw_data.get("roce", "N/A")
    roe = raw_data.get("roe", "N/A")
    de = raw_data.get("debt_to_equity", "N/A")
    opm = raw_data.get("opm", "N/A")
    key_metrics = f"P/E: {pe} | ROCE: {roce}% | ROE: {roe}% | D/E: {de} | OPM: {opm}%"

    # Pros and cons (first 5)
    pros = raw_data.get("pros", []) or []
    cons = raw_data.get("cons", []) or []
    pros_text = "\n".join(f"  - {p}" for p in pros[:5]) or "  - None listed"
    cons_text = "\n".join(f"  - {c}" for c in cons[:5]) or "  - None listed"

    # Peers
    peers = raw_data.get("peers", []) or []
    peer_names = []
    for p in peers[:5]:
        if isinstance(p, dict) and p.get("name"):
            peer_names.append(p["name"])
    peers_text = ", ".join(peer_names) if peer_names else "No peers listed"

    # Sector-specific boolean flags
    is_pharma = sector in ("Pharmaceuticals", "Pharma")
    is_tech = sector in ("Information Technology", "Technology", "IT Services", "Software")
    is_chemical = "Chemical" in sector or "chemical" in sector.lower()
    is_fmcg = sector in ("FMCG", "Consumer Staples", "Fast Moving Consumer Goods", "Food & Beverages")
    is_export_heavy = "export" in about.lower()

    return QUERY_GEN_PROMPT.format(
        company_name=company_name,
        symbol=symbol,
        sector=sector,
        industry=industry,
        about_snippet=about_snippet,
        key_metrics=key_metrics,
        pros_text=pros_text,
        cons_text=cons_text,
        peers_text=peers_text,
        is_pharma=is_pharma,
        is_tech=is_tech,
        is_chemical=is_chemical,
        is_fmcg=is_fmcg,
        is_export_heavy=is_export_heavy,
    )


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"```(?:json)?\s*", "", text).strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def _fallback_queries(raw_data: dict) -> dict:
    """Fall back to the old hardcoded query templates from web_search.py."""
    from backend.data.web_search import (
        build_business_search_queries,
        build_macro_search_queries,
        build_news_search_queries,
    )
    company = raw_data.get("company_name", raw_data.get("symbol", ""))
    sector = raw_data.get("sector", "")
    return {
        "business_queries": build_business_search_queries(company, sector),
        "macro_queries": build_macro_search_queries(company, sector),
        "news_queries": build_news_search_queries(company),
    }


class QueryGeneratorAgent:
    """
    Generates targeted, company-specific web search queries using a reasoning LLM.
    Replaces dumb hardcoded templates in web_search.py.
    Used once per stock analysis run; output is shared by BusinessAgent and MacroAgent.
    """

    # Minimum lengths to accept LLM output
    _MIN_BUSINESS = 4
    _MIN_MACRO = 2
    _MIN_NEWS = 1

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client

    async def generate(self, raw_data: dict) -> dict[str, Any]:
        """
        Generate targeted search queries for a company from its Screener.in raw_data.

        Returns:
            {
                "business_queries": [...],  # 6 queries
                "macro_queries": [...],     # 4 queries
                "news_queries": [...],      # 2 queries
            }
        """
        t0 = time.monotonic()
        company = raw_data.get("company_name") or raw_data.get("symbol", "Company")

        logger.info("QueryGeneratorAgent starting", extra={"company": company})

        try:
            prompt = _build_query_gen_prompt(raw_data)
            raw_response = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=SYSTEM_PROMPT,
                max_tokens=1500,
                temperature=0.1,
                json_mode=True,
            )

            parsed = _parse_json(raw_response)

            # Validate structure
            result = self._validate(parsed, company)

            elapsed = round(time.monotonic() - t0, 2)
            total_queries = (
                len(result.get("business_queries", []))
                + len(result.get("macro_queries", []))
                + len(result.get("news_queries", []))
            )
            logger.info(
                "QueryGeneratorAgent done",
                extra={
                    "company": company,
                    "elapsed_s": elapsed,
                    "total_queries": total_queries,
                },
            )
            return result

        except Exception as exc:
            logger.warning(
                "QueryGeneratorAgent LLM failed — falling back to hardcoded templates",
                extra={"company": company, "error": str(exc)},
            )
            return _fallback_queries(raw_data)

    def _validate(self, parsed: dict, company: str) -> dict:
        """
        Validate that the LLM returned a sensible dict.
        Raises ValueError if minimum requirements not met (triggers fallback).
        """
        required_keys = ("business_queries", "macro_queries", "news_queries")
        for key in required_keys:
            if key not in parsed:
                raise ValueError(f"Missing key '{key}' in LLM query response for {company}")
            if not isinstance(parsed[key], list):
                raise ValueError(f"'{key}' must be a list, got {type(parsed[key])} for {company}")

        bq = parsed["business_queries"]
        mq = parsed["macro_queries"]
        nq = parsed["news_queries"]

        if len(bq) < self._MIN_BUSINESS:
            raise ValueError(
                f"business_queries too short: {len(bq)} < {self._MIN_BUSINESS} for {company}"
            )
        if len(mq) < self._MIN_MACRO:
            raise ValueError(
                f"macro_queries too short: {len(mq)} < {self._MIN_MACRO} for {company}"
            )
        if len(nq) < self._MIN_NEWS:
            raise ValueError(
                f"news_queries too short: {len(nq)} < {self._MIN_NEWS} for {company}"
            )

        return parsed
