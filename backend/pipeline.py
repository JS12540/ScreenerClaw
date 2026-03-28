"""
Investment Research Pipeline — Phases 0 through 8
Orchestrates the complete analysis workflow:

  Phase 0: Screener.in login
  Phase 1: Query routing (single stock vs screening)
  Phase 2A: Screening mode — filter & list
  Phase 2B: Single stock — comprehensive data extraction
  Phase 3: LLM reasoning for valuation assumptions
  Phase 4: Valuation engine (7 methods)
  Phase 5: Combined valuation table
  Phase 6: Business analysis
  Phase 7: Final verdict & buy ranges
  Phase 8: Markdown report generation
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from backend.config import settings
from backend.llm_client import LLMClient, default_model_for
from backend.screener.auth import get_authenticated_client
from backend.screener.scraper import ScreenerScraper
from backend.screener.filter_scraper import ScreenerFilterScraper
from backend.agents.router import QueryRouter
from backend.agents.assumptions_agent import AssumptionsAgent
from backend.agents.business_agent import BusinessAgent
from backend.agents.verdict_agent import VerdictAgent
from backend.valuation.engine import ValuationEngine
from backend.report_builder import build_report

logger = logging.getLogger(__name__)


class InvestmentPipeline:

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        _provider = provider or settings.default_llm_provider
        _model = model or settings.default_llm_model or default_model_for(_provider)

        self.llm = LLMClient(provider=_provider, model=_model)
        self.router = QueryRouter(self.llm)
        self.scraper = ScreenerScraper()
        self.filter_scraper = ScreenerFilterScraper()
        self.assumptions_agent = AssumptionsAgent(self.llm)
        self.business_agent = BusinessAgent(self.llm)
        self.verdict_agent = VerdictAgent(self.llm)
        self.valuation_engine = ValuationEngine()

        logger.info(
            "InvestmentPipeline initialized — provider=%s model=%s",
            self.llm.provider,
            self.llm.model,
        )

    async def analyze(self, user_query: str) -> dict[str, Any]:
        """
        Main entry point. Routes query and runs the full analysis pipeline.
        Returns a comprehensive analysis dict with report_markdown.
        """
        start_ts = time.monotonic()
        logger.info("Pipeline.analyze started | query=%r", user_query)

        # ── Phase 0: Get authenticated Screener client ───────────────────────
        try:
            client = await get_authenticated_client()
        except Exception as exc:
            logger.error("Auth failed: %s", exc)
            return {"error": f"Screener.in authentication failed: {exc}", "mode": "error"}

        # ── Phase 1: Route query ─────────────────────────────────────────────
        try:
            routing = await self.router.route(user_query)
        except Exception as exc:
            logger.error("Routing failed: %s", exc)
            routing = {"mode": "single_stock", "ticker": user_query.strip().upper()}

        mode = routing.get("mode", "single_stock")
        logger.info("Routed to mode=%s ticker=%s", mode, routing.get("ticker"))

        if mode == "screening":
            return await self._run_screening(client, routing, start_ts)
        else:
            return await self._run_single_stock(client, routing, user_query, start_ts)

    # ─── Phase 2A: Screening ──────────────────────────────────────────────────

    async def _run_screening(
        self, client, routing: dict, start_ts: float
    ) -> dict[str, Any]:
        """Run screening mode and return results list."""
        screener_query = routing.get("screener_query") or (
            "Return on capital employed > 20 AND Debt to equity < 0.5"
        )
        logger.info("Running screen: %s", screener_query)

        try:
            results = await self.filter_scraper.run_filter(client, screener_query)
        except Exception as exc:
            logger.error("Screening failed: %s", exc)
            results = []

        elapsed = time.monotonic() - start_ts
        return {
            "mode": "screening",
            "query": routing.get("company_name") or screener_query,
            "screener_query_used": screener_query,
            "result_count": len(results),
            "results": results,
            "execution_time_seconds": round(elapsed, 2),
        }

    # ─── Phase 2B–8: Single Stock Analysis ───────────────────────────────────

    async def _run_single_stock(
        self, client, routing: dict, user_query: str, start_ts: float
    ) -> dict[str, Any]:
        """Run full 8-phase analysis for a single stock."""
        ticker = routing.get("ticker")
        if not ticker:
            # Try to extract from query directly
            import re
            match = re.search(r"\b([A-Z]{2,10})\b", user_query.upper())
            ticker = match.group(1) if match else user_query.strip().upper()

        # ── Phase 2B: Scrape ─────────────────────────────────────────────────
        logger.info("Phase 2B: Scraping %s from Screener.in", ticker)
        try:
            raw_data = await self.scraper.scrape(client, ticker)
        except Exception as exc:
            logger.error("Scraping failed for %s: %s", ticker, exc)
            return {
                "mode": "single_stock",
                "ticker": ticker,
                "error": f"Failed to scrape data: {exc}",
            }

        if raw_data.get("error") == "not_found":
            return {
                "mode": "single_stock",
                "ticker": ticker,
                "error": f"Symbol '{ticker}' not found on Screener.in",
            }

        logger.info("Scraped: %s | Price=₹%s", raw_data.get("company_name"), raw_data.get("current_price"))

        # ── Phase 3: Assumptions ─────────────────────────────────────────────
        logger.info("Phase 3: Deriving valuation assumptions")
        try:
            assumptions = await self.assumptions_agent.derive(raw_data)
        except Exception as exc:
            logger.error("Assumptions agent error: %s", exc)
            assumptions = {}

        # ── Phase 4 & 5: Valuations ──────────────────────────────────────────
        logger.info("Phase 4-5: Computing valuations")
        try:
            valuations = self.valuation_engine.compute(raw_data, assumptions)
            valuation_table = self.valuation_engine.build_table(
                valuations, raw_data.get("current_price") or 0
            )
        except Exception as exc:
            logger.error("Valuation error: %s", exc)
            valuations = {}
            valuation_table = []

        # ── Phase 6: Business Analysis ───────────────────────────────────────
        logger.info("Phase 6: Business analysis")
        try:
            business_analysis = await self.business_agent.analyze(raw_data)
        except Exception as exc:
            logger.error("Business agent error: %s", exc)
            business_analysis = {}

        # ── Phase 7: Verdict ─────────────────────────────────────────────────
        logger.info("Phase 7: Final verdict")
        try:
            verdict = await self.verdict_agent.synthesize(
                raw_data, assumptions, valuation_table, business_analysis
            )
        except Exception as exc:
            logger.error("Verdict agent error: %s", exc)
            verdict = {}

        # ── Phase 8: Report ──────────────────────────────────────────────────
        logger.info("Phase 8: Building report")
        try:
            report_md = build_report(
                raw_data=raw_data,
                assumptions=assumptions,
                valuations=valuations,
                valuation_table=valuation_table,
                business_analysis=business_analysis,
                verdict=verdict,
            )
        except Exception as exc:
            logger.error("Report builder error: %s", exc)
            report_md = f"# Report Generation Error\n\n{exc}"

        elapsed = time.monotonic() - start_ts
        logger.info("Pipeline complete for %s in %.1fs", ticker, elapsed)

        return {
            "mode": "single_stock",
            "ticker": ticker,
            "company_name": raw_data.get("company_name"),
            "sector": raw_data.get("sector"),
            "industry": raw_data.get("industry"),
            "current_price": raw_data.get("current_price"),
            "market_cap": raw_data.get("market_cap"),
            "pe": raw_data.get("pe"),
            "roce": raw_data.get("roce"),
            "roe": raw_data.get("roe"),
            "book_value": raw_data.get("book_value"),
            "eps_ttm": raw_data.get("eps_ttm"),

            # Structured outputs
            "raw_data": raw_data,
            "assumptions": assumptions,
            "valuations": valuations,
            "valuation_table": valuation_table,
            "business_analysis": business_analysis,
            "verdict": verdict,

            # Phase 8: The full report
            "report_markdown": report_md,

            "execution_time_seconds": round(elapsed, 2),
            "llm_provider": self.llm.provider,
            "llm_model": self.llm.model,
        }


# Module-level singleton
_pipeline: Optional[InvestmentPipeline] = None


def get_pipeline(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> InvestmentPipeline:
    global _pipeline
    if _pipeline is None or provider or model:
        _pipeline = InvestmentPipeline(provider=provider, model=model)
    return _pipeline
