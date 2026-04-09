"""
ScreenerClaw — Slack Channel
Uses slack-bolt (async). Requires SLACK_BOT_TOKEN + SLACK_SIGNING_SECRET in .env.
Listens for app_mentions and direct messages.
"""
from __future__ import annotations

import asyncio

from backend.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.logger import get_logger

logger = get_logger(__name__)


class SlackChannel(BaseChannel):
    """
    Slack channel via slack-bolt async adapter.
    Responds to @mentions in channels and direct messages.
    """

    def __init__(self, bot_token: str, signing_secret: str, port: int = 3001) -> None:
        super().__init__("slack")
        self._token = bot_token
        self._secret = signing_secret
        self._port = port
        self._app = None
        self._handler = None

    async def start(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp
            from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        except ImportError:
            raise RuntimeError(
                "slack-bolt not installed. Run: pip install slack-bolt>=1.18.0"
            )

        self._app = AsyncApp(token=self._token, signing_secret=self._secret)

        app = self._app

        async def _process_message(event, say, text):
            user_id = event.get("user", "unknown")

            await say("Analysing... this may take 3-5 minutes.")

            msg = InboundMessage(
                channel="slack",
                user_id=user_id,
                session_id=f"slack-{user_id}",
                text=text,
                metadata={"channel": event.get("channel")},
            )

            try:
                response = await self.dispatch(msg)
                if response:
                    for chunk in self._chunk_text(response.text, max_len=3000):
                        await say(chunk)
            except Exception as exc:
                logger.error("Slack handler error: %s", exc)
                await say(f"Error: {exc}")

        async def _handle(body, say, ack):
            await ack()
            event = body.get("event", {})
            text = event.get("text", "").strip()
            # Strip bot mention prefix (<@BOTID>)
            if text.startswith("<@"):
                text = text.split(">", 1)[-1].strip()

            if not text:
                await say("Ask me about an Indian stock! e.g. 'Analyse Infosys'")
                return

            await _process_message(event, say, text)

        async def _handle_dm(body, say, ack):
            await ack()
            event = body.get("event", {})
            # Only process DMs (channel_type == "im")
            if event.get("channel_type") != "im":
                return
            # Skip bot messages
            if event.get("bot_id"):
                return
            text = event.get("text", "").strip()
            if not text:
                return
            await _process_message(event, say, text)

        app.event("app_mention")(_handle)
        app.event("message")(_handle_dm)

        from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
        logger.info("Slack bot starting on socket mode...")
        # Socket mode uses SLACK_APP_TOKEN; HTTP mode uses port
        try:
            from backend.config import settings
            if hasattr(settings, "slack_app_token") and settings.slack_app_token:
                handler = AsyncSocketModeHandler(app, settings.slack_app_token)
                await handler.start_async()
                return
        except Exception:
            pass

        # Fallback: HTTP mode
        from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
        logger.warning("No SLACK_APP_TOKEN — using HTTP mode on port %d", self._port)
        self._handler = AsyncSlackRequestHandler(app)

    async def stop(self) -> None:
        pass  # slack-bolt handles cleanup internally

    async def send(self, msg: OutboundMessage) -> None:
        if self._app:
            channel = msg.metadata.get("channel") or msg.user_id
            for chunk in self._chunk_text(msg.text, max_len=3000):
                await self._app.client.chat_postMessage(channel=channel, text=chunk)
