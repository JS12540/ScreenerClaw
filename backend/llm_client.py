"""
ScreenerClaw — Unified LLM Client
Abstracts Anthropic, OpenAI, and Groq behind a single async interface.

Usage:
    client = LLMClient(provider="anthropic", model="claude-sonnet-4-6")
    text = await client.complete(messages=[...], system="...", max_tokens=1024)
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider catalogue
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "display_name": "Anthropic Claude",
        "models": [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        "default_model": "claude-sonnet-4-6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "display_name": "OpenAI",
        "models": [
            "gpt-4o",
            "gpt-4o-mini",
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "o1-preview",
            "o1-mini",
        ],
        "default_model": "gpt-4o",
        "env_key": "OPENAI_API_KEY",
    },
    "groq": {
        "display_name": "Groq",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
            "llama3-70b-8192",
            "llama3-8b-8192",
        ],
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
}


def list_providers() -> list[dict]:
    """Return provider metadata for the API /llm/providers endpoint."""
    return [
        {
            "id": pid,
            "display_name": meta["display_name"],
            "models": meta["models"],
            "default_model": meta["default_model"],
        }
        for pid, meta in PROVIDERS.items()
    ]


def default_model_for(provider: str) -> str:
    return PROVIDERS.get(provider, {}).get("default_model", "")


# ---------------------------------------------------------------------------
# Unified client
# ---------------------------------------------------------------------------


class LLMClient:
    """
    Single async wrapper around Anthropic, OpenAI, and Groq.

    All three expose the same ``complete`` coroutine which returns the
    assistant's text response as a plain string.
    """

    def __init__(
        self,
        provider: str = "anthropic",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> None:
        provider = provider.lower()
        if provider not in PROVIDERS:
            raise ValueError(
                f"Unknown provider '{provider}'. Valid: {list(PROVIDERS)}"
            )

        self.provider = provider
        self.model = model or default_model_for(provider)
        self._api_key = api_key  # may be None → fall through to env / settings

        # Lazily-built SDK clients
        self._anthropic_client = None
        self._openai_client = None
        self._groq_client = None

        logger.info("LLMClient: provider=%s model=%s", self.provider, self.model)

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 2048,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> str:
        """
        Send a chat-completion request and return the assistant text.

        Parameters
        ----------
        messages   : list of {"role": "user"/"assistant", "content": str}
        system     : system prompt (handled natively by Anthropic; prepended
                     as a system message for OpenAI/Groq)
        max_tokens : upper token limit for the response
        temperature: sampling temperature (lower = more deterministic)
        json_mode  : when True, instructs OpenAI/Groq to return JSON object

        Returns
        -------
        str  — the assistant's text, stripped of leading/trailing whitespace
        """
        if self.provider == "anthropic":
            return await self._complete_anthropic(messages, system, max_tokens, temperature, json_mode)
        elif self.provider == "openai":
            return await self._complete_openai(messages, system, max_tokens, temperature, json_mode)
        elif self.provider == "groq":
            return await self._complete_groq(messages, system, max_tokens, temperature, json_mode)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    # ------------------------------------------------------------------
    # Provider-specific implementations
    # ------------------------------------------------------------------

    async def _complete_anthropic(
        self, messages: list[dict], system: str, max_tokens: int, temperature: float, json_mode: bool = False
    ) -> str:
        import asyncio
        import anthropic as _anthropic

        client = self._get_anthropic_client()
        # anthropic SDK is synchronous; run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
            ),
        )
        return response.content[0].text.strip()

    async def _complete_openai(
        self, messages: list[dict], system: str, max_tokens: int, temperature: float, json_mode: bool = False
    ) -> str:
        import openai as _openai

        client = self._get_openai_client()
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        response = await client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **({"response_format": {"type": "json_object"}} if json_mode else {}),
        )
        return response.choices[0].message.content.strip()

    async def _complete_groq(
        self, messages: list[dict], system: str, max_tokens: int, temperature: float, json_mode: bool = False
    ) -> str:
        import groq as _groq
        import asyncio

        client = self._get_groq_client()
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        # groq SDK is synchronous; run in executor
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                max_tokens=max_tokens,
                temperature=temperature,
                **({"response_format": {"type": "json_object"}} if json_mode else {}),
            ),
        )
        return response.choices[0].message.content.strip()

    # ------------------------------------------------------------------
    # Lazy SDK client factories
    # ------------------------------------------------------------------

    def _get_anthropic_client(self):
        if self._anthropic_client is None:
            import anthropic as _anthropic
            from backend.config import settings
            key = self._api_key or settings.anthropic_api_key
            if not key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY is not set. Add it to .env or pass api_key=..."
                )
            self._anthropic_client = _anthropic.Anthropic(api_key=key)
        return self._anthropic_client

    def _get_openai_client(self):
        if self._openai_client is None:
            import openai as _openai
            from backend.config import settings
            key = self._api_key or settings.openai_api_key
            if not key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set. Add it to .env or pass api_key=..."
                )
            self._openai_client = _openai.AsyncOpenAI(api_key=key)
        return self._openai_client

    def _get_groq_client(self):
        if self._groq_client is None:
            import groq as _groq
            from backend.config import settings
            key = self._api_key or settings.groq_api_key
            if not key:
                raise RuntimeError(
                    "GROQ_API_KEY is not set. Add it to .env or pass api_key=..."
                )
            self._groq_client = _groq.Groq(api_key=key)
        return self._groq_client

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"LLMClient(provider={self.provider!r}, model={self.model!r})"
