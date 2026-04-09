"""
ScreenerClaw — Macro & Geopolitical Agent (Step 2)
Maps current India macro environment + global geopolitical factors
to specific earnings impact for the company being analysed.

Uses web search to fetch live macro data before asking the LLM
to make targeted, quantified assessments.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any, Optional

from backend.llm_client import LLMClient
from backend.data.web_search import WebSearchClient, build_macro_search_queries
from backend.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a senior macro strategist and equity analyst specialising in Indian markets.
You understand RBI policy cycles, INR dynamics, commodity cycles, India's PLI schemes,
and global geopolitical risks as they affect listed Indian companies.
You are BRUTALLY HONEST about macro headwinds — you quantify the earnings impact (in % EPS terms where possible)
rather than using vague language. If macro is a serious headwind to a thesis, say it plainly.
Do not be bullish by default — India's macro is complex and sector-specific impacts can be severe.
Respond ONLY with valid JSON. No markdown, no preamble, no explanation outside the JSON."""


MACRO_PROMPT = """## Company Context
Name: {company_name}
Sector: {sector}
Revenue mix: {revenue_mix}
Key cost drivers: {cost_drivers}
Export exposure: {export_pct}% of revenue
Import dependence: {import_dep}

## Live Macro & News Context (web search results)
{search_context}

## India Macro Factors to Assess
{macro_factors}

## Geopolitical Factors to Assess
{geo_factors}

## Task
Produce a targeted macro and geopolitical impact analysis in this exact JSON structure:

{{
  "macro_date_context": "string — brief note on current macro environment (1-2 sentences)",

  "india_macro_impacts": [
    {{
      "factor": "string — e.g. RBI Rate Cycle",
      "current_status": "string — what is actually happening right now",
      "direction": "tailwind|headwind|neutral",
      "earnings_impact": "string — specific quantified or qualified impact on THIS company",
      "magnitude": "low|moderate|high|critical",
      "time_horizon": "immediate|0-12months|1-3years"
    }}
  ],

  "geopolitical_impacts": [
    {{
      "factor": "string",
      "relevance": "high|medium|low|not_applicable",
      "direction": "tailwind|headwind|neutral",
      "earnings_impact": "string — specific impact on THIS company",
      "magnitude": "low|moderate|high|critical"
    }}
  ],

  "tailwinds_summary": ["string — top 3-4 specific tailwinds with magnitude"],
  "headwinds_summary": ["string — top 3-4 specific headwinds with magnitude"],

  "net_macro_verdict": "POSITIVE|NEUTRAL|NEGATIVE",
  "net_macro_explanation": "string — 3-4 sentence honest assessment",

  "key_macro_risks": [
    {{
      "risk": "string",
      "trigger": "string — what event triggers this risk",
      "probability": "low|medium|high",
      "eps_impact": "string — estimated EPS impact if triggered"
    }}
  ],

  "macro_score": number  // 0-100: 100=strong tailwinds, 50=neutral, 0=severe headwinds
}}

Only include macro factors with medium/high relevance to this specific company.
Skip factors with no meaningful connection to this business."""


def _load_system_prompt() -> str:
    """Load system prompt from SKILL.md if available, else use hardcoded default."""
    from pathlib import Path
    skill_file = Path(__file__).parent.parent.parent / "agent_skills" / "macro_agent" / "SKILL.md"
    if skill_file.exists():
        content = skill_file.read_text(encoding="utf-8")
        match = re.search(r"^# System Prompt\s*\n(.*?)(?=^# |\Z)", content, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return SYSTEM_PROMPT  # fallback to hardcoded


def _build_prompt(raw_data: dict, search_context: str) -> str:
    from backend.config import INDIA_MACRO_FACTORS, GEOPOLITICAL_FACTORS

    name = raw_data.get("company_name", "Company")
    sector = raw_data.get("sector", "Unknown")

    # Try to extract revenue mix info
    about = raw_data.get("about", "")
    peers = raw_data.get("peers", [])

    # Estimate export exposure from company description
    export_pct = "unknown"
    if "export" in (about or "").lower():
        export_pct = "significant (exact % unknown — see annual report)"

    revenue_mix = about[:300] if about else "Not available"
    cost_drivers = "Raw materials, employee costs, logistics"

    return MACRO_PROMPT.format(
        company_name=name,
        sector=sector,
        revenue_mix=revenue_mix[:200],
        cost_drivers=cost_drivers,
        export_pct=export_pct,
        import_dep="partially import-dependent" if sector in ("Pharmaceuticals", "Specialty Chemicals") else "primarily domestic inputs",
        search_context=search_context or "No live web data available — use general knowledge.",
        macro_factors="\n".join(f"  - {f}" for f in INDIA_MACRO_FACTORS),
        geo_factors="\n".join(f"  - {f}" for f in GEOPOLITICAL_FACTORS),
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


class MacroAgent:
    """
    Step 2 of the 5-step pipeline.
    Analyses India macro + geopolitical impact on the specific business.
    """

    def __init__(self, llm: LLMClient) -> None:
        self.llm = llm
        self.searcher = WebSearchClient()

    async def analyze(self, raw_data: dict, queries: Optional[list[str]] = None) -> dict[str, Any]:
        t0 = time.monotonic()
        company = raw_data.get("company_name", raw_data.get("symbol", "Company"))
        sector = raw_data.get("sector", "")

        logger.info(
            "MacroAgent starting",
            extra={"company": company, "sector": sector},
        )

        # Step 1: All search queries run in parallel across all backends
        search_context = ""
        try:
            if queries:
                search_queries = queries[:5]
            else:
                search_queries = build_macro_search_queries(company, sector)
            all_results = await self.searcher.search_many(search_queries, num_results=3)
            search_context = self.searcher.format_results_for_llm(all_results, max_chars=4000)
            logger.info(
                "MacroAgent web search done",
                extra={"company": company, "results": len(all_results)},
            )
        except Exception as exc:
            logger.warning(
                "MacroAgent web search failed",
                extra={"company": company, "error": str(exc)},
            )

        # Step 2: LLM analysis
        prior_context = raw_data.get("prior_memory_context", "")
        if prior_context:
            search_context = f"## Prior ScreenerClaw Sector Memory\n{prior_context}\n\n" + (search_context or "")
        prompt = _build_prompt(raw_data, search_context)
        try:
            raw = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_load_system_prompt(),
                max_tokens=6000,
                temperature=0.1,
                json_mode=True,
            )
            result = _parse_json(raw)
            logger.info(
                "MacroAgent LLM done",
                extra={"company": company, "elapsed_s": round(time.monotonic() - t0, 1)},
            )
        except Exception as exc:
            logger.error(
                "MacroAgent LLM failed",
                extra={"company": company, "error": str(exc)},
            )
            result = _fallback_macro(raw_data)

        # Ensure defaults
        result.setdefault("india_macro_impacts", [])
        result.setdefault("geopolitical_impacts", [])
        result.setdefault("tailwinds_summary", [])
        result.setdefault("headwinds_summary", [])
        result.setdefault("net_macro_verdict", "NEUTRAL")
        result.setdefault("net_macro_explanation", "Macro analysis not available.")
        result.setdefault("key_macro_risks", [])
        result.setdefault("macro_score", 50)

        return result


def _fallback_macro(raw_data: dict) -> dict:
    return {
        "macro_date_context": "Macro analysis unavailable",
        "india_macro_impacts": [],
        "geopolitical_impacts": [],
        "tailwinds_summary": ["Data not available"],
        "headwinds_summary": ["Data not available"],
        "net_macro_verdict": "NEUTRAL",
        "net_macro_explanation": "Macro analysis could not be generated.",
        "key_macro_risks": [],
        "macro_score": 50,
    }
