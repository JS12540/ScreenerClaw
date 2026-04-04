"""
ScreenerClaw — Multi-Channel Bot Entry Point

Starts the configured channels and routes messages through the pipeline.

Usage:
    python run_bot.py                    # CLI mode (default)
    python run_bot.py --channel cli
    python run_bot.py --channel telegram
    python run_bot.py --channel slack
    python run_bot.py --channel discord
    python run_bot.py --channel whatsapp # QR code scan on first run
    python run_bot.py --channel all      # start all configured channels
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from backend.logger import get_logger

logger = get_logger(__name__)


def build_gateway(channels_to_start: list[str]):
    from backend.config import settings
    from backend.gateway import ScreenerClawGateway

    gw = ScreenerClawGateway()

    if "cli" in channels_to_start:
        from backend.channels.cli_channel import CLIChannel
        gw.add_channel(CLIChannel())

    if "telegram" in channels_to_start:
        if not settings.telegram_bot_token:
            logger.error("TELEGRAM_BOT_TOKEN not set in .env — skipping Telegram")
        else:
            from backend.channels.telegram_channel import TelegramChannel
            gw.add_channel(TelegramChannel(token=settings.telegram_bot_token))

    if "slack" in channels_to_start:
        if not settings.slack_bot_token:
            logger.error("SLACK_BOT_TOKEN not set in .env — skipping Slack")
        else:
            from backend.channels.slack_channel import SlackChannel
            gw.add_channel(SlackChannel(
                bot_token=settings.slack_bot_token,
                signing_secret=settings.slack_signing_secret,
            ))

    if "discord" in channels_to_start:
        if not settings.discord_bot_token:
            logger.error("DISCORD_BOT_TOKEN not set in .env — skipping Discord")
        else:
            from backend.channels.discord_channel import DiscordChannel
            gw.add_channel(DiscordChannel(token=settings.discord_bot_token))

    if "whatsapp" in channels_to_start:
        from backend.channels.whatsapp_channel import WhatsAppChannel
        gw.add_channel(WhatsAppChannel(
            bridge_port=settings.whatsapp_bridge_port,
            webhook_port=settings.whatsapp_webhook_port,
        ))

    return gw


async def main(channel_arg: str) -> None:
    from backend.config import settings

    if channel_arg == "all":
        channels = ["telegram", "slack", "discord", "whatsapp"]
        if not settings.telegram_bot_token:
            channels.remove("telegram")
        if not settings.slack_bot_token:
            channels.remove("slack")
        if not settings.discord_bot_token:
            channels.remove("discord")
        # WhatsApp is always attempted in 'all' mode (uses QR, no pre-configured token)
    else:
        channels = [channel_arg]

    if not channels:
        logger.error("No channels to start", extra={"hint": "check .env configuration"})
        sys.exit(1)

    gw = build_gateway(channels)

    logger.info("Starting ScreenerClaw gateway", extra={"channels": channels})
    try:
        await gw.start_all()
    except KeyboardInterrupt:
        logger.info("Shutting down by KeyboardInterrupt", extra={})
    finally:
        await gw.stop_all()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ScreenerClaw Bot")
    parser.add_argument(
        "--channel",
        default="cli",
        choices=["cli", "telegram", "slack", "discord", "whatsapp", "all"],
        help="Channel to start (default: cli)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.channel))
