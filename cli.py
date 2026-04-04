"""
ScreenerClaw CLI entry point.

Usage:
    screenerclaw run                       # CLI channel (default)
    screenerclaw run --channel telegram
    screenerclaw run --channel slack
    screenerclaw run --channel discord
    screenerclaw run --channel whatsapp
    screenerclaw run --channel all
    screenerclaw api
    screenerclaw api --port 8080 --reload
"""
from __future__ import annotations

import asyncio
import click


@click.group()
@click.version_option(package_name="screener-claw")
def cli() -> None:
    """ScreenerClaw — AI-native Indian stock intelligence platform."""


@cli.command()
@click.option(
    "--channel",
    default="cli",
    show_default=True,
    type=click.Choice(["cli", "telegram", "slack", "discord", "whatsapp", "all"]),
    help="Channel to start.",
)
def run(channel: str) -> None:
    """Start the bot on the specified channel."""
    from run_bot import main as _main
    asyncio.run(_main(channel))


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
@click.option("--reload", is_flag=True, default=False, help="Enable auto-reload.")
def api(host: str, port: int, reload: bool) -> None:
    """Start the FastAPI backend."""
    import uvicorn
    uvicorn.run("backend.main:app", host=host, port=port, reload=reload, log_level="info")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
