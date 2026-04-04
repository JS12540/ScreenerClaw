"""
ScreenerClaw — Base Channel abstractions (OpenClaw-inspired).
All channel adapters inherit from BaseChannel.
"""
from __future__ import annotations

import abc
import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional


@dataclass
class InboundMessage:
    """Normalised message received from any channel."""
    channel: str          # "telegram" | "slack" | "discord" | "cli"
    user_id: str
    session_id: str       # per-user session key for lane queuing
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class OutboundMessage:
    """Normalised message to send back via a channel."""
    text: str
    channel: str
    user_id: str
    session_id: str
    metadata: dict = field(default_factory=dict)


# Callback type: receives InboundMessage, returns OutboundMessage
MessageHandler = Callable[[InboundMessage], Awaitable[OutboundMessage]]


class BaseChannel(abc.ABC):
    """
    Abstract channel adapter.
    Each channel registers a message handler and manages its own lifecycle.
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._handler: Optional[MessageHandler] = None

    def set_handler(self, handler: MessageHandler) -> None:
        self._handler = handler

    async def dispatch(self, msg: InboundMessage) -> Optional[OutboundMessage]:
        """Send inbound message through the registered handler."""
        if self._handler is None:
            return None
        return await self._handler(msg)

    @abc.abstractmethod
    async def start(self) -> None:
        """Start the channel (connect, poll, listen)."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the channel."""

    @abc.abstractmethod
    async def send(self, msg: OutboundMessage) -> None:
        """Send a message out through this channel."""

    def _chunk_text(self, text: str, max_len: int = 4000) -> list[str]:
        """Split long text into chunks respecting max_len."""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            # Try to split at a newline boundary
            split_at = text.rfind("\n", 0, max_len)
            if split_at <= 0:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks
