"""
ScreenerClaw — 5-Step Intelligence Pipeline

Step 1: Business Understanding    (BusinessAgent — o4-mini)
Step 2: Macro & Geopolitical      (MacroAgent — o4-mini)
Step 3: Business Report & Outlook (ReportAgent — o4-mini)
Step 4: Adaptive Valuation        (ValuationEngine + AssumptionsAgent)
Step 5: Composite Scoring         (RankingAgent)

For screening mode: runs filter + quick scoring without the full 5-step pipeline.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Optional

from backend.config import settings
from backend.llm_client import LLMClient, resolve_task_llm
from backend.screener.auth import get_authenticated_client
from backend.screener.scraper import ScreenerScraper
from backend.screener.filter_scraper import ScreenerFilterScraper
from backend.agents.router import QueryRouter
from backend.agents.business_agent import BusinessAgent
from backend.agents.macro_agent import MacroAgent
from backend.agents.report_agent import ReportAgent
from backend.agents.assumptions_agent import AssumptionsAgent
from backend.agents.verdict_agent import VerdictAgent
from backend.agents.ranking_agent import RankingAgent
from backend.agents.query_generator import QueryGeneratorAgent
from backend.valuation.engine import ValuationEngine
from backend.valuation.classifier import classify_stock_type, get_valuation_methods, get_margin_of_safety
from backend.report_builder import build_report
from backend.logger import get_logger

logger = get_logger(__name__)


class ScreenerClawPipeline:
    """
    Main pipeline orchestrating the 5-step ScreenerClaw intelligence workflow.
    Uses task-type-based LLM routing:
      reasoning  → o4-mini  (Steps 1, 2, 3)
      execution  → gpt-4.1-mini (routing, assumptions)
      fast       → groq (quick tasks)
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        # Build LLM clients for different task types
        reasoning_provider, reasoning_model = resolve_task_llm("reasoning")
        execution_provider, execution_model = resolve_task_llm("execution")
        fast_provider, fast_model = resolve_task_llm("fast")

        # Allow override from request
        if provider and model:
            reasoning_provider = execution_provider = fast_provider = provider
            reasoning_model = execution_model = fast_model = model

        self.llm_reasoning = LLMClient(provider=reasoning_provider, model=reasoning_model)
        self.llm_execution = LLMClient(provider=execution_provider, model=execution_model)
        self.llm_fast = LLMClient(provider=fast_provider, model=fast_model)

        # Agents
        self.router = QueryRouter(self.llm_fast)
        self.scraper = ScreenerScraper()
        self.filter_scraper = ScreenerFilterScraper()

        # 5-step agents
        self.business_agent = BusinessAgent(self.llm_reasoning)
        self.macro_agent = MacroAgent(self.llm_reasoning)
        self.report_agent = ReportAgent(self.llm_reasoning)
        self.assumptions_agent = AssumptionsAgent(self.llm_execution)
        self.verdict_agent = VerdictAgent(self.llm_execution)
        self.ranking_agent = RankingAgent()
        self.query_generator = QueryGeneratorAgent(self.llm_execution)
        self.valuation_engine = ValuationEngine()

        logger.info(
            "Pipeline initialized",
            extra={
                "reasoning": f"{reasoning_provider}/{reasoning_model}",
                "execution": f"{execution_provider}/{execution_model}",
                "fast": f"{fast_provider}/{fast_model}",
            },
        )

    async def analyze(self, user_query: str) -> dict[str, Any]:
        """
        Main entry point. Routes query, runs appropriate pipeline.
        Returns comprehensive analysis dict with report_markdown.
        """
        start_ts = time.monotonic()
        logger.info("Pipeline.analyze starting", extra={"query": user_query[:80]})

        # Auth
        try:
            client = await get_authenticated_client()
        except Exception as exc:
            logger.error("Auth failed", extra={"error": str(exc)})
            return {"error": f"Screener.in authentication failed: {exc}", "mode": "error"}

        # Route query
        try:
            routing = await self.router.route(user_query)
        except Exception as exc:
            logger.error("Routing failed", extra={"query": user_query[:80], "error": str(exc)})
            routing = {"mode": "single_stock", "ticker": user_query.strip().upper()}

        mode = routing.get("mode", "single_stock")
        logger.info(
            "Query routed",
            extra={"mode": mode, "ticker": routing.get("ticker"), "query": user_query[:60]},
        )

        if mode == "screening":
            return await self._run_screening(client, routing, start_ts)
        return await self._run_single_stock(client, routing, user_query, start_ts)

    # ── Screening Mode ────────────────────────────────────────────────────────

    async def _run_screening(
        self, client, routing: dict, start_ts: float
    ) -> dict[str, Any]:
        screener_query = routing.get("screener_query") or (
            "Return on capital employed > 20 AND Debt to equity < 0.5"
        )
        logger.info("Running screen", extra={"query": screener_query[:120]})

        try:
            results, site_total = await self.filter_scraper.run_filter(client, screener_query)
        except Exception as exc:
            logger.error("Screening failed", extra={"query": screener_query[:80], "error": str(exc)})
            results, site_total = [], 0

        # Quick score each result
        intent = routing.get("intent", "default")
        from backend.scoring.engine import score_for_screening
        for r in results:
            try:
                scored = score_for_screening(r, intent=intent)
                r["score"] = scored.get("composite_score")
                r["verdict"] = scored.get("verdict")
                r["verdict_emoji"] = scored.get("verdict_emoji")
            except Exception:
                pass

        # Sort by score
        results.sort(key=lambda x: x.get("score") or 0, reverse=True)

        elapsed = time.monotonic() - start_ts
        return {
            "mode": "screening",
            "query": routing.get("company_name") or screener_query,
            "screener_query_used": screener_query,
            "result_count": site_total or len(results),
            "results": results,
            "execution_time_seconds": round(elapsed, 2),
        }

    # ── Single Stock 5-Step Pipeline ──────────────────────────────────────────

    async def _run_single_stock(
        self, client, routing: dict, user_query: str, start_ts: float
    ) -> dict[str, Any]:
        ticker = routing.get("ticker") or user_query.strip()

        # Smart ticker resolution — handles names, BSE codes, misspellings
        try:
            from backend.screener.ticker_resolver import resolve_ticker
            resolved_ticker, resolve_method = await resolve_ticker(
                ticker, client, company_name=routing.get("company_name")
            )
            if resolved_ticker != ticker.upper():
                logger.info(
                    "Ticker resolved",
                    extra={"input": ticker, "resolved": resolved_ticker, "method": resolve_method},
                )
            ticker = resolved_ticker
        except ValueError as exc:
            logger.warning("Ticker resolution failed: %s", exc)
            # Fall back to simple extraction
            import re as _re2
            match = _re2.search(r"\b([A-Z]{2,15})\b", ticker.upper())
            ticker = match.group(1) if match else ticker.strip().upper()
        except Exception as exc:
            logger.warning("Ticker resolver error: %s", exc)
            ticker = ticker.strip().upper()

        # ── Scrape Screener.in ────────────────────────────────────────────────
        logger.info("Scraping company", extra={"ticker": ticker})
        try:
            raw_data = await self.scraper.scrape(client, ticker)
        except Exception as exc:
            logger.error("Scraping failed", extra={"ticker": ticker, "error": str(exc)})
            return {"mode": "single_stock", "ticker": ticker, "error": f"Scrape failed: {exc}"}

        if raw_data.get("error") == "not_found":
            return {"mode": "single_stock", "ticker": ticker, "error": f"'{ticker}' not found on Screener.in"}

        logger.info(
            "Scrape complete",
            extra={
                "company": raw_data.get("company_name"),
                "price": raw_data.get("current_price"),
                "sector": raw_data.get("sector"),
            },
        )

        # Classify stock type
        stock_type = classify_stock_type(raw_data)
        recommended_methods = get_valuation_methods(stock_type)
        mos_pct = get_margin_of_safety(stock_type, raw_data.get("sector", ""))
        logger.info(
            "Stock classified",
            extra={"ticker": ticker, "stock_type": stock_type, "mos_pct": round(mos_pct * 100, 0)},
        )

        # ── Load prior memory context ─────────────────────────────────────────
        prior_context = ""
        try:
            from backend.memory_manager import MemoryManager
            mm = MemoryManager()
            prior_context = mm.read_all_context(ticker, raw_data.get("sector", ""))
            if prior_context:
                raw_data["prior_memory_context"] = prior_context
                logger.info(
                    "Prior memory loaded",
                    extra={"ticker": ticker, "chars": len(prior_context)},
                )
        except Exception as exc:
            logger.warning("Memory read failed", extra={"error": str(exc)})

        # ── Generate smart search queries (once, shared by Steps 1 + 2) ──────────────
        logger.info("Generating search queries", extra={"ticker": ticker})
        generated_queries: dict = {}
        try:
            generated_queries = await self._safe(
                self.query_generator.generate(raw_data), "query_generation"
            )
        except Exception as exc:
            logger.warning("Query generation failed — using fallback queries", extra={"error": str(exc)})

        # ── Steps 1 & 2 in parallel ───────────────────────────────────────────────────
        logger.info("Steps 1+2 starting (parallel)", extra={"ticker": ticker})
        business_analysis, macro_analysis = await asyncio.gather(
            self._safe(self.business_agent.analyze(raw_data, queries=generated_queries.get("business_queries") or generated_queries.get("news_queries", [])), "business_analysis"),
            self._safe(self.macro_agent.analyze(raw_data, queries=generated_queries.get("macro_queries")), "macro_analysis"),
        )

        # ── Step 3: Report & Outlook ──────────────────────────────────────────
        logger.info("Step 3 starting", extra={"ticker": ticker, "step": "report_outlook"})
        report_outlook = await self._safe(
            self.report_agent.generate(raw_data, business_analysis, macro_analysis),
            "report_outlook",
        )

        # ── Step 4: Valuation ─────────────────────────────────────────────────
        logger.info(
            "Step 4 starting",
            extra={"ticker": ticker, "stock_type": stock_type, "methods": recommended_methods},
        )
        try:
            assumptions = await self._safe(self.assumptions_agent.derive(raw_data), "assumptions")
            valuations = self.valuation_engine.compute(raw_data, assumptions, methods=recommended_methods)
            valuation_table = self.valuation_engine.build_table(
                valuations, raw_data.get("current_price") or 0
            )
            logger.info(
                "Step 4 complete",
                extra={"ticker": ticker, "valuation_rows": len(valuation_table)},
            )
        except Exception as exc:
            logger.error("Valuation step failed", extra={"ticker": ticker, "error": str(exc)})
            assumptions = {}
            valuations = {}
            valuation_table = []

        # Compute MOS prices from table
        mos_prices = self._compute_mos_prices(valuation_table, mos_pct)

        # ── Step 5: Composite Scoring ─────────────────────────────────────────
        logger.info("Step 5 starting", extra={"ticker": ticker, "step": "scoring"})
        outlook = report_outlook.get("outlook", {}) if report_outlook else {}
        scoring = self.ranking_agent.score(
            raw_data=raw_data,
            business_analysis=business_analysis,
            macro_analysis=macro_analysis,
            valuation_table=valuation_table,
            outlook=outlook,
        )

        # ── Verdict (legacy + enhanced) ───────────────────────────────────────
        try:
            verdict = await self._safe(
                self.verdict_agent.synthesize(raw_data, assumptions, valuation_table, business_analysis),
                "verdict",
            )
        except Exception as exc:
            logger.warning("VerdictAgent failed", extra={"ticker": ticker, "error": str(exc)})
            verdict = {}

        # ── Build Markdown Report ─────────────────────────────────────────────
        logger.info("Building final report", extra={"ticker": ticker})
        try:
            report_md = build_report(
                raw_data=raw_data,
                assumptions=assumptions,
                valuations=valuations,
                valuation_table=valuation_table,
                business_analysis=business_analysis,
                verdict=verdict,
                macro_analysis=macro_analysis,
                report_outlook=report_outlook,
                scoring=scoring,
                stock_type=stock_type,
                mos_prices=mos_prices,
            )
        except Exception as exc:
            logger.error("Report builder failed", extra={"ticker": ticker, "error": str(exc)})
            report_md = f"# Report Error\n\n{exc}"

        elapsed = time.monotonic() - start_ts
        logger.info(
            "Pipeline complete",
            extra={"ticker": ticker, "elapsed_s": round(elapsed, 1)},
        )

        result = {
            "mode": "single_stock",
            "ticker": ticker,
            "company_name": raw_data.get("company_name"),
            "sector": raw_data.get("sector"),
            "industry": raw_data.get("industry"),
            "stock_type": stock_type,
            "current_price": raw_data.get("current_price"),
            "market_cap": raw_data.get("market_cap"),
            "pe": raw_data.get("pe"),
            "roce": raw_data.get("roce"),
            "roe": raw_data.get("roe"),

            # 5-step structured outputs
            "raw_data": raw_data,
            "business_analysis": business_analysis,
            "macro_analysis": macro_analysis,
            "report_outlook": report_outlook,
            "assumptions": assumptions,
            "valuations": valuations,
            "valuation_table": valuation_table,
            "mos_prices": mos_prices,
            "verdict": verdict,
            "scoring": scoring,

            # Final report
            "report_markdown": report_md,

            # Meta
            "execution_time_seconds": round(elapsed, 2),
            "llm_reasoning": f"{self.llm_reasoning.provider}/{self.llm_reasoning.model}",
            "llm_execution": f"{self.llm_execution.provider}/{self.llm_execution.model}",
        }

        # Write learnings to persistent memory
        try:
            from backend.memory_manager import MemoryManager
            mm = MemoryManager()
            mm.extract_and_save_learnings(
                ticker=ticker,
                sector=raw_data.get("sector", ""),
                pipeline_result=result,
            )
        except Exception as exc:
            logger.warning("Memory write failed", extra={"error": str(exc)})

        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def _safe(self, coro, name: str) -> dict:
        """Run a coroutine safely, returning empty dict on failure."""
        try:
            return await coro
        except Exception as exc:
            logger.error("Step failed", extra={"step": name, "error": str(exc)})
            return {}

    def _compute_mos_prices(
        self, valuation_table: list[dict], mos_pct: float
    ) -> dict[str, float]:
        """Compute margin-of-safety buy prices from valuation table."""
        if not valuation_table:
            return {}

        values = [
            r["value_per_share"]
            for r in valuation_table
            if r.get("value_per_share") and r["value_per_share"] > 0
        ]
        if not values:
            return {}

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        p25 = sorted_vals[n // 4]
        p50 = sorted_vals[n // 2]
        p75 = sorted_vals[3 * n // 4]

        return {
            "bear_intrinsic":   round(p25, 0),
            "base_intrinsic":   round(p50, 0),
            "bull_intrinsic":   round(p75, 0),
            "mos_buy_price":    round(p50 * (1 - mos_pct), 0),
            "mos_pct_applied":  round(mos_pct * 100, 0),
        }


# ── Module-level singleton ────────────────────────────────────────────────────

_pipeline: Optional[ScreenerClawPipeline] = None


def get_pipeline(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> ScreenerClawPipeline:
    global _pipeline
    if _pipeline is None or provider or model:
        _pipeline = ScreenerClawPipeline(provider=provider, model=model)
    return _pipeline


# ── Backwards compat alias ────────────────────────────────────────────────────
InvestmentPipeline = ScreenerClawPipeline
