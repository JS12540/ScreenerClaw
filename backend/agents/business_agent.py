"""
ScreenerClaw — Business Understanding Agent (Step 1)
Builds a comprehensive 5-dimension business profile:
  1. Business Model (revenue model, customers, distribution)
  2. Competitive Advantage / Moat (Porter's 5 forces, moat types)
  3. Revenue Deep Dive (segments, pricing power, concentration)
  4. Cost Structure & Raw Materials
  5. Management Quality

Uses web search to fetch annual report excerpts, management commentary,
and recent news before reasoning about the business.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from backend.llm_client import LLMClient
from backend.data.web_search import WebSearchClient, build_business_search_queries, build_news_search_queries
from backend.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are an expert business analyst with deep experience analysing Indian listed companies.
You combine Graham-style value investing with Porter's competitive analysis and Greenwald's asset-based framework.
You are BRUTALLY HONEST — your job is to protect investor capital first, generate returns second.
You call out value traps, fake moats, management red flags, and cyclical peaks disguised as secular growth.
You never sugarcoat. A business with mediocre returns on capital earns that description, not a polite "moderate."
If a business doesn't deserve capital, say so plainly.
Respond ONLY with valid JSON. No markdown, no preamble."""

BUSINESS_PROMPT = """## Company Financial & Business Data
{data_summary}

## Web Research Context (from live search)
{search_context}

## Task: Complete 5-Dimension Business Profile

Produce a comprehensive business analysis in this exact JSON structure:

{{
  "company_name": "string",
  "industry": "string",
  "one_line_verdict": "string (20 words max — honest, direct)",

  "business_model": {{
    "what_they_sell": "string — products/services, B2B/B2C/Gov/Export",
    "how_they_reach_customers": "string — direct/distributor/platform/tender",
    "revenue_model": "transactional|subscription|project|annuity|mixed",
    "is_revenue_recurring": true or false,
    "geography_mix": "string — domestic vs export, key markets",
    "value_chain_summary": "string",
    "primary_business_type": "commodity_processor|brand_play|specialty_niche|services|technology|hybrid",
    "margin_creation_point": "string — where in value chain does margin come from"
  }},

  "moat_analysis": {{
    "advantages": [
      {{
        "moat_type": "cost_advantage|switching_costs|network_effects|intangible_assets|efficient_scale",
        "present": true or false,
        "strength": "strong|moderate|weak|none",
        "durability_5yr": "durable|stable|eroding|vulnerable",
        "evidence": "string — specific evidence from the business, not assertions",
        "rationale": "string"
      }}
    ],
    "overall_moat_verdict": "string — honest 2-3 sentence assessment",
    "replacement_cost_estimate": "string — e.g. Rs 8,000-10,000 Cr to replicate",
    "replacement_cost_vs_mcap": "string — e.g. Current MCap 2.2-2.75x replacement cost",
    "binding_constraint_for_new_entrant": "capital|time|relationships|regulatory|brand|technology"
  }},

  "revenue_deep_dive": {{
    "segments": [
      {{
        "name": "string",
        "revenue_pct": number or null,
        "growth_driver": "string",
        "revenue_quality": "cash|deferred|lumpy|annuity",
        "pricing_power": "strong|moderate|weak|none"
      }}
    ],
    "customer_concentration_risk": "low|medium|high",
    "seasonality": "string — which quarter is strongest and why",
    "receivables_trend": "improving|stable|deteriorating"
  }},

  "cost_structure": {{
    "fixed_vs_variable": "string — operating leverage implications",
    "key_inputs": [
      {{
        "input_name": "string",
        "cost_pct_of_revenue": number or null,
        "price_volatility": "low|medium|high",
        "passthrough_ability": "full|partial|none",
        "china_exposure": "high|medium|low|none"
      }}
    ],
    "operating_margin_trend": "expanding|stable|compressing",
    "energy_cost_sensitivity": "high|medium|low",
    "labour_cost_sensitivity": "high|medium|low"
  }},

  "management_quality": {{
    "promoter_holding_pct": number or null,
    "promoter_holding_trend": "increasing|stable|decreasing",
    "promoter_pledge_pct": number or null,
    "pledge_assessment": "string",
    "rpt_as_pct_revenue": number or null,
    "governance_red_flags": ["string"],
    "capital_allocation_track_record": "excellent|good|average|poor",
    "management_remuneration_fairness": "fair|high|excessive",
    "track_record_vs_guidance": "consistently beats|meets|misses",
    "overall_management_score": number  // 0-100
  }},

  "raw_materials": [
    {{
      "input_name": "string",
      "category": "primary_rm|energy|packaging|logistics|technology|labour",
      "availability_risk": "low|medium|high",
      "passthrough_ability": "full|partial|none"
    }}
  ],

  "key_business_factors": [
    {{
      "factor": "string",
      "why_it_matters": "string",
      "sensitivity": "low|medium|high|critical",
      "management_control": "controllable|partially_controllable|external",
      "current_status": "string"
    }}
  ],

  "risk_matrix": [
    {{
      "risk_name": "string",
      "description": "string",
      "category": "input_cost|demand|regulatory|competitive|operational|financial|governance",
      "probability": "low|medium|high",
      "impact": "low|medium|high|severe",
      "risk_type": "structural|cyclical",
      "mitigant": "string"
    }}
  ],

  "strategic_opportunities": [
    {{
      "opportunity": "string",
      "rationale": "string",
      "timeline": "string",
      "key_execution_risk": "string"
    }}
  ],

  "analyst_summary": "string — 200-250 word plain English business profile for investment committee. Include: what does this business do, how does it make money, what protects it from competition, key risks, and one honest line on whether the business is worth investigating further."
}}

Provide 4-6 items for key_business_factors, 4-6 for risk_matrix, 2-3 for strategic_opportunities.
Be specific — cite actual products, segments, and evidence. Avoid generic statements."""


def _load_system_prompt() -> str:
    """Load system prompt from SKILL.md if available, else use hardcoded default."""
    from pathlib import Path
    skill_file = Path(__file__).parent.parent.parent / "agent_skills" / "business_agent" / "SKILL.md"
    if skill_file.exists():
        content = skill_file.read_text(encoding="utf-8")
        # Extract the # System Prompt section
        match = re.search(r"^# System Prompt\s*\n(.*?)(?=^# |\Z)", content, re.MULTILINE | re.DOTALL)
        if match:
            return match.group(1).strip()
    return SYSTEM_PROMPT  # fallback to hardcoded


def _make_data_summary(data: dict) -> str:
    lines = []
    name = data.get("company_name") or data.get("symbol", "")
    lines.append(f"Company: {name} ({data.get('symbol', '')})")
    lines.append(f"Sector: {data.get('sector')} | Industry: {data.get('industry')}")
    lines.append(f"Price: ₹{data.get('current_price')} | MCap: ₹{data.get('market_cap')} Cr")
    lines.append(f"P/E: {data.get('pe')} | ROCE: {data.get('roce')}% | ROE: {data.get('roe')}%")
    lines.append(f"D/E: {data.get('debt_to_equity')} | OPM: {data.get('opm')}%")
    lines.append("")

    about = data.get("about")
    if about:
        lines.append(f"Business: {about[:600]}")
        lines.append("")

    pros = data.get("pros", [])
    cons = data.get("cons", [])
    if pros:
        lines.append("Strengths: " + " | ".join(str(p) for p in pros[:6]))
    if cons:
        lines.append("Concerns: " + " | ".join(str(c) for c in cons[:6]))
    lines.append("")

    # P&L trend
    sales = [x for x in data.get("pl_sales", []) if isinstance(x, dict)]
    profits = [x for x in data.get("pl_net_profit", []) if isinstance(x, dict)]
    if sales and profits:
        lines.append("Revenue & Profit (Rs Cr):")
        for s, p in zip(sales[-7:], profits[-7:]):
            lines.append(f"  {s.get('year')}: Rev={s.get('value')} | PAT={p.get('value')}")

    sc = data.get("sales_growth_cagr", {})
    pc = data.get("profit_growth_cagr", {})
    if sc:
        lines.append(
            f"CAGR — Rev: 3yr={sc.get('3_years')}% 5yr={sc.get('5_years')}%"
            f" | PAT: 3yr={pc.get('3_years')}% 5yr={pc.get('5_years')}%"
        )
    lines.append("")

    # Balance sheet
    bs = data.get("balance_sheet", {})
    borrows = [x for x in bs.get("borrowings", []) if isinstance(x, dict)]
    if borrows:
        lines.append(f"Borrowings (latest): ₹{borrows[-1].get('value')} Cr")

    # Cash flow
    cf = data.get("cash_flow", {})
    ops = [x for x in cf.get("operating", []) if isinstance(x, dict)]
    if ops:
        avg_ops = sum(x.get("value", 0) or 0 for x in ops[-3:]) / max(len(ops[-3:]), 1)
        lines.append(f"Avg Op CF (3yr): ₹{avg_ops:.0f} Cr")

    # Shareholding — values can be flat floats or dicts with 'latest' key
    sh = data.get("shareholding", {})
    if sh:
        def _sh_val(v):
            if isinstance(v, dict):
                return v.get("latest")
            return v
        lines.append(f"Promoter holding: {_sh_val(sh.get('promoters'))}%")
        lines.append(
            f"FII: {_sh_val(sh.get('fii') or sh.get('fiis'))}% "
            f"| DII: {_sh_val(sh.get('dii') or sh.get('diis'))}%"
        )

    # Peers
    peers = data.get("peers", [])
    if peers:
        lines.append("\nPeer Comparison:")
        for p in peers[:5]:
            if not isinstance(p, dict):
                continue
            lines.append(
                f"  {p.get('name')}: MCap={p.get('market_cap')} P/E={p.get('pe')} ROCE={p.get('roce')}%"
            )

    return "\n".join(lines)


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


class BusinessAgent:
    """Step 1 of the 5-step pipeline — deep business understanding with web research."""

    def __init__(self, llm_client: LLMClient) -> None:
        self.llm = llm_client
        self.searcher = WebSearchClient()

    async def analyze(self, raw_data: dict) -> dict[str, Any]:
        t0 = time.monotonic()
        company = raw_data.get("company_name", raw_data.get("symbol", "Company"))
        sector = raw_data.get("sector", "")

        logger.info(
            "BusinessAgent starting",
            extra={"company": company, "sector": sector},
        )

        # Step 1: All search queries run in parallel across all backends
        search_context = ""
        try:
            queries = (
                build_business_search_queries(company, sector)
                + build_news_search_queries(company)
            )[:4]
            all_results = await self.searcher.search_many(queries, num_results=3)
            search_context = self.searcher.format_results_for_llm(all_results, max_chars=5000)
            logger.info(
                "BusinessAgent web search done",
                extra={"company": company, "results": len(all_results)},
            )
        except Exception as exc:
            logger.warning(
                "BusinessAgent web search failed",
                extra={"company": company, "error": str(exc)},
            )
            search_context = "Web search unavailable — using Screener.in data only."

        # Step 2: Build prompt + call LLM
        data_summary = _make_data_summary(raw_data)
        prior_context = raw_data.get("prior_memory_context", "")
        prior_block = f"\n## Prior ScreenerClaw Analysis (from memory)\n{prior_context}\n" if prior_context else ""
        prompt = BUSINESS_PROMPT.format(
            data_summary=data_summary,
            search_context=(prior_block + search_context) if prior_block else search_context,
        )

        try:
            raw = await self.llm.complete(
                messages=[{"role": "user", "content": prompt}],
                system=_load_system_prompt(),
                max_tokens=8000,
                temperature=0.1,
                json_mode=True,
            )
            result = _parse_json(raw)
            logger.info(
                "BusinessAgent LLM done",
                extra={"company": company, "elapsed_s": round(time.monotonic() - t0, 1)},
            )
        except Exception as exc:
            logger.error(
                "BusinessAgent LLM failed",
                extra={"company": company, "error": str(exc)},
            )
            result = _fallback_analysis(raw_data)

        # Ensure required keys
        result.setdefault("company_name", company)
        result.setdefault("industry", raw_data.get("industry") or sector)
        result.setdefault("one_line_verdict", f"{company} — analysis pending")
        result.setdefault("business_model", {})
        result.setdefault("moat_analysis", {})
        result.setdefault("revenue_deep_dive", {})
        result.setdefault("cost_structure", {})
        result.setdefault("management_quality", {})
        result.setdefault("raw_materials", [])
        result.setdefault("key_business_factors", [])
        result.setdefault("risk_matrix", [])
        result.setdefault("strategic_opportunities", [])
        result.setdefault("analyst_summary", "")

        return result


def _fallback_analysis(data: dict) -> dict:
    name = data.get("company_name") or data.get("symbol", "Company")
    return {
        "company_name": name,
        "industry": data.get("industry") or data.get("sector"),
        "one_line_verdict": f"{name} — LLM analysis failed",
        "business_model": {"primary_business_type": "unknown"},
        "moat_analysis": {"advantages": [], "overall_moat_verdict": "Unable to assess"},
        "revenue_deep_dive": {},
        "cost_structure": {},
        "management_quality": {},
        "raw_materials": [],
        "key_business_factors": [],
        "risk_matrix": [],
        "strategic_opportunities": [],
        "analyst_summary": "Business analysis could not be generated. Please retry.",
    }
