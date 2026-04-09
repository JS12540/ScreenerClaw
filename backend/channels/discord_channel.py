"""
ScreenerClaw — Discord Channel
Uses discord.py. Requires DISCORD_BOT_TOKEN in .env.
Responds to messages in guilds and DMs when the bot is mentioned or in DMs.
"""
from __future__ import annotations

from backend.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.logger import get_logger

logger = get_logger(__name__)


class DiscordChannel(BaseChannel):
    """
    Discord channel via discord.py client.
    Responds to direct messages and @mentions in servers.
    """

    def __init__(self, token: str) -> None:
        super().__init__("discord")
        self._token = token
        self._client = None

    async def start(self) -> None:
        try:
            import discord
        except ImportError:
            raise RuntimeError(
                "discord.py not installed. Run: pip install discord.py>=2.3.2"
            )

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = discord.Client(intents=intents)
        client = self._client

        @client.event
        async def on_ready():
            logger.info("Discord bot ready: %s", client.user)

        @client.event
        async def on_message(message):
            if message.author.bot:
                return

            # Respond in DMs or when mentioned
            is_dm = isinstance(message.channel, discord.DMChannel)
            is_mention = client.user in message.mentions if client.user else False

            logger.info("Discord message received: is_dm=%s is_mention=%s text=%s", is_dm, is_mention, message.content[:60])

            if not (is_dm or is_mention):
                return

            text = message.content.strip()
            # Remove mention prefix
            if client.user:
                text = text.replace(f"<@{client.user.id}>", "").strip()
                text = text.replace(f"<@!{client.user.id}>", "").strip()

            if not text:
                await message.reply("Ask me about an Indian stock! e.g. 'Analyse Reliance'")
                return

            await message.reply("Analysing... this may take 3-5 minutes.")

            user_id = str(message.author.id)
            msg = InboundMessage(
                channel="discord",
                user_id=user_id,
                session_id=f"discord-{user_id}",
                text=text,
                metadata={"channel_id": str(message.channel.id)},
            )

            try:
                response = await self.dispatch(msg)
                if response:
                    pipeline_result = response.metadata.get("pipeline_result", {})
                    if pipeline_result and pipeline_result.get("mode") == "single_stock" and not pipeline_result.get("error"):
                        await self._send_pdf(message.channel, pipeline_result)
                    elif pipeline_result and pipeline_result.get("screening_pdf_bytes"):
                        await self._send_screening_pdf(message.channel, pipeline_result, response.text)
                    else:
                        for chunk in self._chunk_text(response.text, max_len=2000):
                            await message.channel.send(chunk)
            except Exception as exc:
                logger.error("Discord handler error: %s", exc)
                await message.reply(f"Error: {exc}")

    async def _send_pdf(self, channel, pipeline_result: dict) -> None:
        import io
        import discord
        from datetime import date
        ticker = pipeline_result.get("ticker", "Report")
        company = pipeline_result.get("company_name", ticker)
        score = (pipeline_result.get("scoring") or {}).get("composite_score", "—")
        verdict = (pipeline_result.get("scoring") or {}).get("verdict", "—")
        today = date.today().isoformat()
        try:
            from backend.pdf_generator import generate_report_pdf
            pdf_bytes = generate_report_pdf(pipeline_result)
            pdf_file = io.BytesIO(pdf_bytes)
            file = discord.File(fp=pdf_file, filename=f"{ticker}_ScreenerClaw_{today}.pdf")
            await channel.send(
                content=f"**{company} ({ticker})** — Score: {score}/100 | {verdict}",
                file=file,
            )
            logger.info("Discord PDF sent", extra={"ticker": ticker})
        except Exception as exc:
            logger.error("Discord PDF failed, falling back to text", extra={"error": str(exc)})
            for chunk in self._chunk_text(pipeline_result.get("report_markdown", str(exc)), max_len=2000):
                await channel.send(chunk)

    async def _send_screening_pdf(self, channel, pipeline_result: dict, text: str) -> None:
        import io
        import discord
        from datetime import date
        pdf_bytes = pipeline_result.get("screening_pdf_bytes")
        query = pipeline_result.get("screener_query_used") or pipeline_result.get("query", "Screen")
        total = pipeline_result.get("result_count", len(pipeline_result.get("results", [])))
        today = date.today().isoformat()
        try:
            preview = text[:1500] if len(text) > 1500 else text
            await channel.send(preview)
            pdf_file = io.BytesIO(pdf_bytes)
            file = discord.File(fp=pdf_file, filename=f"ScreenerClaw_Screen_{today}.pdf")
            await channel.send(
                content=f"**Screening Results** — {total} stocks | `{query[:80]}`",
                file=file,
            )
            logger.info("Discord screening PDF sent", extra={"total": total})
        except Exception as exc:
            logger.error("Discord screening PDF failed", extra={"error": str(exc)})
            for chunk in self._chunk_text(text, max_len=2000):
                await channel.send(chunk)

    async def stop(self) -> None:
        if self._client:
            await self._client.close()

    async def send(self, msg: OutboundMessage) -> None:
        if self._client:
            channel_id = msg.metadata.get("channel_id")
            if channel_id:
                channel = self._client.get_channel(int(channel_id))
                if channel:
                    for chunk in self._chunk_text(msg.text, max_len=2000):
                        await channel.send(chunk)
