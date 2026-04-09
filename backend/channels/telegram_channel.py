"""
ScreenerClaw — Telegram Channel
Uses python-telegram-bot v20+ (async). Requires TELEGRAM_BOT_TOKEN in .env.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from backend.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.logger import get_logger

logger = get_logger(__name__)


class TelegramChannel(BaseChannel):
    """
    Telegram bot channel. Each user gets their own session_id based on chat_id.
    Long reports are split into chunks to respect Telegram's 4096-char message limit.
    In groups, only responds when the bot is @mentioned.
    """

    def __init__(self, token: str) -> None:
        super().__init__("telegram")
        self._token = token
        self._app = None
        self._stop_event = None

    async def start(self) -> None:
        try:
            from telegram.ext import Application, MessageHandler, filters
        except ImportError:
            raise RuntimeError(
                "python-telegram-bot not installed. Run: pip install python-telegram-bot>=20.0"
            )

        self._app = (
            Application.builder()
            .token(self._token)
            .build()
        )

        async def _on_message(update, context):
            if not update.message or not update.message.text:
                return

            chat_id = str(update.message.chat_id)
            text = update.message.text.strip()

            # In groups, only respond when bot is @mentioned
            if update.message.chat.type in ("group", "supergroup"):
                bot_username = context.bot.username
                if f"@{bot_username}" not in text:
                    return
                # Strip the mention from the text
                text = text.replace(f"@{bot_username}", "").strip()

            if text.startswith("/start"):
                await update.message.reply_text(
                    "Welcome to ScreenerClaw!\n\n"
                    "Ask me anything about Indian stocks:\n"
                    "- 'Analyse TCS'\n"
                    "- 'Find undervalued pharma midcaps'\n"
                    "- 'Best compounders in FMCG'"
                )
                return

            await update.message.reply_text("Analysing... this may take 3-5 minutes.")

            msg = InboundMessage(
                channel="telegram",
                user_id=chat_id,
                session_id=f"tg-{chat_id}",
                text=text,
                metadata={"chat_id": chat_id},
            )

            try:
                response = await self.dispatch(msg)
                if response:
                    pipeline_result = response.metadata.get("pipeline_result", {})
                    if pipeline_result and pipeline_result.get("mode") == "single_stock" and not pipeline_result.get("error"):
                        await self._send_pdf(context.bot, chat_id, pipeline_result)
                    elif pipeline_result and pipeline_result.get("screening_pdf_bytes"):
                        await self._send_screening_pdf(context.bot, chat_id, pipeline_result, response.text)
                    else:
                        for chunk in self._chunk_text(response.text, max_len=4000):
                            await context.bot.send_message(
                                chat_id=chat_id,
                                text=chunk,
                                parse_mode="Markdown",
                            )
            except Exception as exc:
                logger.error("Telegram handler error: %s", exc)
                await update.message.reply_text(f"Error: {exc}")

        from telegram.ext import MessageHandler, filters
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _on_message))
        self._app.add_handler(
            MessageHandler(filters.Command(["start", "help"]), _on_message)
        )

        logger.info("Telegram bot starting...")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()
        logger.info("Telegram bot polling.")

        # start_polling() is non-blocking — keep this coroutine alive
        # so gateway.start_all() (asyncio.gather) doesn't exit immediately.
        self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    async def _send_pdf(self, bot, chat_id: str, pipeline_result: dict) -> None:
        import io
        from datetime import date
        ticker = pipeline_result.get("ticker", "Report")
        company = pipeline_result.get("company_name", ticker)
        score = (pipeline_result.get("scoring") or {}).get("composite_score", "—")
        verdict = (pipeline_result.get("scoring") or {}).get("verdict", "—")
        today = date.today().isoformat()
        caption = f"*{company} ({ticker})* — ScreenerClaw\nScore: {score}/100 | {verdict}\n_{today}_"
        try:
            from backend.pdf_generator import generate_report_pdf
            pdf_bytes = generate_report_pdf(pipeline_result)
            pdf_file = io.BytesIO(pdf_bytes)
            pdf_file.name = f"{ticker}_ScreenerClaw_{today}.pdf"
            await bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                filename=f"{ticker}_ScreenerClaw_{today}.pdf",
                caption=caption,
                parse_mode="Markdown",
            )
            logger.info("Telegram PDF sent", extra={"ticker": ticker, "chat_id": chat_id})
        except Exception as exc:
            logger.error("Telegram PDF failed, falling back to text", extra={"error": str(exc)})
            for chunk in self._chunk_text(pipeline_result.get("report_markdown", str(exc)), max_len=4000):
                await bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")

    async def _send_screening_pdf(self, bot, chat_id: str, pipeline_result: dict, text: str) -> None:
        import io
        from datetime import date
        pdf_bytes = pipeline_result.get("screening_pdf_bytes")
        total = pipeline_result.get("result_count", len(pipeline_result.get("results", [])))
        fetched = len(pipeline_result.get("results", []))
        today = date.today().isoformat()
        # Completely plain-text caption — no Markdown, no special chars from query
        caption = f"ScreenerClaw Screening Results\n{fetched} stocks fetched ({total} total on Screener)\n{today}\nReply with a number or company name for full analysis."
        try:
            pdf_file = io.BytesIO(pdf_bytes)
            pdf_file.name = f"ScreenerClaw_Screen_{today}.pdf"
            await bot.send_document(
                chat_id=chat_id,
                document=pdf_file,
                filename=f"ScreenerClaw_Screen_{today}.pdf",
                caption=caption,
            )
            logger.info("Telegram screening PDF sent", extra={"chat_id": chat_id, "total": total})
        except Exception as exc:
            logger.error("Telegram screening PDF failed", extra={"error": str(exc)})
            # Fallback: stripped plain-text summary (no Markdown at all)
            summary = (
                f"Screening Results: {fetched} stocks fetched ({total} total on Screener)\n"
                f"PDF could not be sent. Reply with a stock name or number for full analysis."
            )
            await bot.send_message(chat_id=chat_id, text=summary)

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()  # unblock start()
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()

    async def send(self, msg: OutboundMessage) -> None:
        if self._app:
            chat_id = msg.metadata.get("chat_id") or msg.user_id
            pipeline_result = msg.metadata.get("pipeline_result", {})
            if pipeline_result and pipeline_result.get("mode") == "single_stock" and not pipeline_result.get("error"):
                await self._send_pdf(self._app.bot, chat_id, pipeline_result)
            elif pipeline_result and pipeline_result.get("screening_pdf_bytes"):
                await self._send_screening_pdf(self._app.bot, chat_id, pipeline_result, msg.text)
            else:
                for chunk in self._chunk_text(msg.text, max_len=4000):
                    await self._app.bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="Markdown",
                    )
