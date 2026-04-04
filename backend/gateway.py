"""
ScreenerClaw — Gateway (OpenClaw-inspired)
Manages all channel adapters, normalises messages, and routes to the pipeline.

Architecture:
  Channel adapters (Telegram/Slack/Discord/CLI)
      -> InboundMessage
      -> Gateway.handle_message()
      -> session state check (screening follow-up?)
      -> ScreenerClawPipeline.analyze()
      -> OutboundMessage
      -> Channel adapter sends reply

Features:
  - Per-user lane queuing (serial processing per session)
  - Session state: after screening, user can pick a stock by number/name
  - Typing/working indicators per channel
  - Graceful shutdown of all channels
"""
from __future__ import annotations

import asyncio
from typing import Optional

from backend.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.pipeline import get_pipeline
from backend.session_manager import get_session_manager
from backend.screener.result_formatter import format_screening_results, format_stock_selected_message
from backend.logger import get_logger

logger = get_logger(__name__)

MAX_RESPONSE_CHARS = 12_000


class ScreenerClawGateway:
    """
    Central gateway. Registers channel adapters and routes messages to the pipeline.
    Uses per-session asyncio.Lock for lane queuing (one request at a time per user).
    """

    def __init__(self) -> None:
        self._channels: list[BaseChannel] = []
        self._pipeline = get_pipeline()
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._sessions = get_session_manager()

    def add_channel(self, channel: BaseChannel) -> None:
        channel.set_handler(self.handle_message)
        self._channels.append(channel)
        logger.info("Gateway channel registered", extra={"channel": channel.name})

    async def handle_message(self, msg: InboundMessage) -> OutboundMessage:
        """
        Route an inbound message through the pipeline.
        Serialises requests per session_id.
        """
        lock = self._session_locks.setdefault(msg.session_id, asyncio.Lock())

        async with lock:
            logger.info(
                "Gateway routing message",
                extra={"channel": msg.channel, "user": msg.user_id, "query": msg.text[:80]},
            )

            # ── Check if user is picking a stock from previous screening results ──
            matched = self._sessions.resolve_stock_from_input(msg.session_id, msg.text)
            if matched:
                ticker = matched.get("ticker") or matched.get("symbol") or matched.get("company_name", "")
                confirm = format_stock_selected_message(matched)
                logger.info(
                    "Session stock pick resolved",
                    extra={"session": msg.session_id, "ticker": ticker},
                )
                # Run full single stock analysis on the matched ticker
                try:
                    result = await self._pipeline.analyze(ticker)
                except Exception as exc:
                    logger.error("Pipeline error on stock pick", extra={"ticker": ticker, "error": str(exc)})
                    return OutboundMessage(
                        text=f"Analysis failed for {ticker}: {exc}",
                        channel=msg.channel,
                        user_id=msg.user_id,
                        session_id=msg.session_id,
                        metadata=msg.metadata,
                    )

                text = self._format_response(result, msg.channel)
                return OutboundMessage(
                    text=text,
                    channel=msg.channel,
                    user_id=msg.user_id,
                    session_id=msg.session_id,
                    metadata={**msg.metadata, "pipeline_result": result},
                )

            # ── Normal pipeline routing ────────────────────────────────────────
            try:
                result = await self._pipeline.analyze(msg.text)
            except Exception as exc:
                logger.error(
                    "Pipeline error",
                    extra={"channel": msg.channel, "query": msg.text[:80], "error": str(exc)},
                )
                return OutboundMessage(
                    text=f"Analysis failed: {exc}",
                    channel=msg.channel,
                    user_id=msg.user_id,
                    session_id=msg.session_id,
                    metadata=msg.metadata,
                )

            # ── After screening: store results in session for follow-up ────────
            if result.get("mode") == "screening" and not result.get("error"):
                self._sessions.set_screening_result(
                    session_id=msg.session_id,
                    results=result.get("results", []),
                    query=result.get("screener_query_used") or result.get("query", ""),
                )
                # Generate screening PDF (all results)
                try:
                    from backend.pdf_generator import generate_screening_pdf
                    result["screening_pdf_bytes"] = generate_screening_pdf(
                        results=result.get("results", []),
                        query=result.get("screener_query_used") or result.get("query", ""),
                        total_count=result.get("result_count", 0),
                    )
                    logger.info(
                        "Screening PDF generated",
                        extra={"size_kb": round(len(result["screening_pdf_bytes"]) / 1024, 1)},
                    )
                except Exception as exc:
                    logger.warning("Screening PDF generation failed", extra={"error": str(exc)})

        text = self._format_response(result, msg.channel)
        return OutboundMessage(
            text=text,
            channel=msg.channel,
            user_id=msg.user_id,
            session_id=msg.session_id,
            metadata={**msg.metadata, "pipeline_result": result},
        )

    def _format_response(self, result: dict, channel: str) -> str:
        if result.get("error"):
            return f"Error: {result['error']}"

        mode = result.get("mode", "")

        if mode == "screening":
            return self._format_screening(result, channel)

        # single_stock
        report = result.get("report_markdown", "")
        if not report:
            name = result.get("company_name") or result.get("ticker", "?")
            price = result.get("current_price", "N/A")
            score = result.get("scoring", {}).get("composite_score", "N/A")
            verdict = result.get("verdict", {})
            report = f"**{name}** — Price: {price}\nScore: {score}\n{verdict.get('summary', '')}"

        if len(report) > MAX_RESPONSE_CHARS:
            report = report[:MAX_RESPONSE_CHARS] + "\n\n_(Report truncated — use the web UI for full analysis)_"

        return report

    def _format_screening(self, result: dict, channel: str) -> str:
        results = result.get("results", [])
        query = result.get("screener_query_used") or result.get("query", "")
        total = result.get("result_count", len(results))
        elapsed = result.get("execution_time_seconds")

        text = format_screening_results(
            results=results,
            query=query,
            total_count=total,
            channel=channel,
        )

        if elapsed:
            text += f"\n\n_Fetched in {elapsed:.1f}s_"

        return text

    async def start_all(self) -> None:
        if not self._channels:
            logger.warning("Gateway: no channels registered", extra={})
            return
        names = [ch.name for ch in self._channels]
        logger.info("Gateway starting channels", extra={"channels": names, "count": len(names)})
        await asyncio.gather(*[ch.start() for ch in self._channels])

    async def stop_all(self) -> None:
        await asyncio.gather(*[ch.stop() for ch in self._channels], return_exceptions=True)
        logger.info("Gateway: all channels stopped", extra={})
