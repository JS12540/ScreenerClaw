"""
ScreenerClaw — Unified LLM Client
Supports Anthropic, OpenAI (including reasoning models), and Groq.
Task-type based routing: reasoning | execution | fast

Routing:
  reasoning  → gpt-5-mini (deep analysis, valuation, reports)
  execution  → gpt-4.1-mini (data fetch, classification, summaries)
  fast       → groq llama-3.3-70b (alerts, routing, quick tasks)
"""
from __future__ import annotations

from typing import Optional

from backend.logger import get_logger

logger = get_logger(__name__)

# ─── Reasoning Models (special API handling) ──────────────────────────────────
# These models do not accept temperature; use max_completion_tokens.

REASONING_MODELS = frozenset({
    "o1", "o1-mini", "o1-preview",
    "o3", "o3-mini",
    "o4-mini", "o4",
    # GPT-5 series — same API restrictions as o-series:
    # requires max_completion_tokens, no temperature, developer role preferred
    "gpt-5", "gpt-5-mini",
})


def is_reasoning_model(model: str) -> bool:
    return model in REASONING_MODELS or any(
        model.startswith(r + "-") for r in ("o1", "o3", "o4", "gpt-5")
    )


# ─── Provider Catalogue ───────────────────────────────────────────────────────

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "display_name": "Anthropic Claude",
        "models": [
            "claude-sonnet-4-6",
            "claude-opus-4-6",
            "claude-haiku-4-5-20251001",
        ],
        "default_model": "claude-sonnet-4-6",
        "env_key": "ANTHROPIC_API_KEY",
    },
    "openai": {
        "display_name": "OpenAI",
        "models": [
            "gpt-5-mini",
            "gpt-4.1-mini",
            "gpt-4.1",
            "o4-mini",
            "gpt-4o",
            "gpt-4o-mini",
        ],
        "default_model": "gpt-4.1-mini",
        "env_key": "OPENAI_API_KEY",
    },
    "groq": {
        "display_name": "Groq",
        "models": [
            "llama-3.3-70b-versatile",
            "compound-beta-mini",
            "compound-beta",
            "llama-3.1-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
        ],
        "default_model": "llama-3.3-70b-versatile",
        "env_key": "GROQ_API_KEY",
    },
}


def list_providers() -> list[dict]:
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


# ─── Task-Type Based LLM Resolver ────────────────────────────────────────────

TASK_TYPE_ROUTING = {
    # task_type → (provider_setting, model_setting)
    "reasoning":           ("reasoning_provider",  "reasoning_model"),
    "business_analysis":   ("reasoning_provider",  "reasoning_model"),
    "valuation":           ("reasoning_provider",  "reasoning_model"),
    "report":              ("reasoning_provider",  "reasoning_model"),
    "macro_analysis":      ("reasoning_provider",  "reasoning_model"),
    "execution":           ("execution_provider",  "execution_model"),
    "data_fetch":          ("execution_provider",  "execution_model"),
    "classification":      ("execution_provider",  "execution_model"),
    "scoring":             ("execution_provider",  "execution_model"),
    "fast":                ("fast_provider",       "fast_model"),
    "routing":             ("fast_provider",       "fast_model"),
    "alert":               ("fast_provider",       "fast_model"),
}


def resolve_task_llm(task_type: str = "execution") -> tuple[str, str]:
    """Return (provider, model) for a given task type."""
    from backend.config import settings

    routing = TASK_TYPE_ROUTING.get(task_type, ("execution_provider", "execution_model"))
    provider = getattr(settings, routing[0], settings.execution_provider)
    model = getattr(settings, routing[1], settings.execution_model)

    # Fallback to groq if provider not configured
    if provider == "openai" and not settings.openai_api_key:
        if settings.groq_api_key:
            return "groq", settings.fast_model
        elif settings.anthropic_api_key:
            return "anthropic", "claude-sonnet-4-6"

    return provider, model


# ─── Unified LLM Client ───────────────────────────────────────────────────────


class LLMClient:
    """
    Single async interface over Anthropic, OpenAI, and Groq.
    Handles o4-mini reasoning model quirks automatically.
    """

    def __init__(
        self,
        provider: str = "openai",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> None:
        if task_type:
            resolved_provider, resolved_model = resolve_task_llm(task_type)
            provider = resolved_provider
            model = model or resolved_model

        provider = provider.lower()
        if provider not in PROVIDERS:
            raise ValueError(f"Unknown provider '{provider}'. Valid: {list(PROVIDERS)}")

        self.provider = provider
        self.model = model or default_model_for(provider)
        self.is_reasoning = is_reasoning_model(self.model)
        self._api_key = api_key

        self._anthropic_client = None
        self._openai_client = None
        self._groq_client = None

        logger.debug("LLMClient: provider=%s model=%s reasoning=%s", self.provider, self.model, self.is_reasoning)

    @classmethod
    def for_task(cls, task_type: str) -> "LLMClient":
        """Factory: create client tuned for a specific task type."""
        provider, model = resolve_task_llm(task_type)
        return cls(provider=provider, model=model)

    async def complete(
        self,
        messages: list[dict],
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.1,
        json_mode: bool = False,
    ) -> str:
        if self.provider == "anthropic":
            return await self._complete_anthropic(messages, system, max_tokens, temperature)
        elif self.provider == "openai":
            return await self._complete_openai(messages, system, max_tokens, temperature, json_mode)
        elif self.provider == "groq":
            return await self._complete_groq(messages, system, max_tokens, temperature, json_mode)
        raise ValueError(f"Unsupported provider: {self.provider}")

    # ── Anthropic ─────────────────────────────────────────────────────────────

    async def _complete_anthropic(
        self, messages: list[dict], system: str, max_tokens: int, temperature: float
    ) -> str:
        import asyncio
        import anthropic as _anthropic

        client = self._get_anthropic_client()
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

    # ── OpenAI (handles both reasoning and standard models) ───────────────────

    async def _complete_openai(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
    ) -> str:
        client = self._get_openai_client()
        full_messages: list[dict] = []

        if system:
            if self.is_reasoning:
                # o-series: developer role for system-level instructions
                full_messages.append({"role": "developer", "content": system})
            else:
                full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict = {"model": self.model, "messages": full_messages}

        if self.is_reasoning:
            # Reasoning models: no temperature, use max_completion_tokens
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = temperature
            if json_mode:
                kwargs["response_format"] = {"type": "json_object"}

        response = await client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()

    # ── Groq ──────────────────────────────────────────────────────────────────

    async def _complete_groq(
        self,
        messages: list[dict],
        system: str,
        max_tokens: int,
        temperature: float,
        json_mode: bool = False,
    ) -> str:
        import groq as _groq
        import asyncio

        client = self._get_groq_client()
        full_messages: list[dict] = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs: dict = {
            "model": self.model,
            "messages": full_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(**kwargs),
        )
        return response.choices[0].message.content.strip()

    # ── SDK Factories ─────────────────────────────────────────────────────────

    def _get_anthropic_client(self):
        if self._anthropic_client is None:
            import anthropic as _anthropic
            from backend.config import settings
            key = self._api_key or settings.anthropic_api_key
            if not key:
                raise RuntimeError("ANTHROPIC_API_KEY not set")
            self._anthropic_client = _anthropic.Anthropic(api_key=key)
        return self._anthropic_client

    def _get_openai_client(self):
        if self._openai_client is None:
            import openai as _openai
            from backend.config import settings
            key = self._api_key or settings.openai_api_key
            if not key:
                raise RuntimeError("OPENAI_API_KEY not set")
            self._openai_client = _openai.AsyncOpenAI(api_key=key)
        return self._openai_client

    def _get_groq_client(self):
        if self._groq_client is None:
            import groq as _groq
            from backend.config import settings
            key = self._api_key or settings.groq_api_key
            if not key:
                raise RuntimeError("GROQ_API_KEY not set")
            self._groq_client = _groq.Groq(api_key=key)
        return self._groq_client

    def __repr__(self) -> str:
        return f"LLMClient(provider={self.provider!r}, model={self.model!r})"
