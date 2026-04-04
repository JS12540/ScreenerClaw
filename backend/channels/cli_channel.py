"""
ScreenerClaw — CLI Channel
Rich terminal REPL. Run directly via `python run_bot.py --channel cli`.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from backend.channels.base import BaseChannel, InboundMessage, OutboundMessage
from backend.logger import get_logger

logger = get_logger(__name__)

_SESSION = "cli-session"
_USER = "cli-user"


class CLIChannel(BaseChannel):
    """
    Interactive terminal channel using Rich for formatted output.
    Reads stdin in an async loop, calls the handler, prints the result.
    """

    def __init__(self) -> None:
        super().__init__("cli")
        self._running = False

    async def start(self) -> None:
        self._running = True
        try:
            from rich.console import Console
            from rich.markdown import Markdown
            from rich.panel import Panel
            console = Console()
        except ImportError:
            import sys
            console = None  # type: ignore

        def _print(text: str) -> None:
            if console:
                from rich.markdown import Markdown
                from rich.panel import Panel
                console.print(Panel(Markdown(text), border_style="cyan"))
            else:
                print(text)

        def _banner() -> None:
            banner = (
                "\n[bold cyan]ScreenerClaw[/bold cyan] — AI Indian Stock Intelligence\n"
                "Type your query (e.g. 'Analyse TCS' or 'Find undervalued pharma midcaps')\n"
                "Type [bold]exit[/bold] or [bold]quit[/bold] to stop.\n"
            )
            if console:
                from rich.console import Console
                Console().print(banner)
            else:
                print("ScreenerClaw — AI Indian Stock Intelligence")
                print("Type your query. Type 'exit' to stop.\n")

        _banner()

        loop = asyncio.get_event_loop()

        while self._running:
            try:
                # Read input asynchronously
                raw = await loop.run_in_executor(None, lambda: input(">> "))
            except (EOFError, KeyboardInterrupt):
                break

            raw = raw.strip()
            if not raw:
                continue
            if raw.lower() in ("exit", "quit", "q"):
                break

            msg = InboundMessage(
                channel="cli",
                user_id=_USER,
                session_id=_SESSION,
                text=raw,
            )

            if console:
                from rich.console import Console
                Console().print("[dim]Analysing...[/dim]")
            else:
                print("Analysing...")

            try:
                response = await self.dispatch(msg)
                if response:
                    _print(response.text)
            except Exception as exc:
                logger.error("CLI handler error: %s", exc)
                print(f"Error: {exc}")

        self._running = False

    async def stop(self) -> None:
        self._running = False

    async def send(self, msg: OutboundMessage) -> None:
        # In CLI mode, output is handled inline in start()
        print(msg.text)
