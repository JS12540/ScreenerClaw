"""
ScreenerClaw — FastAPI Application
Thin API layer over the 5-step ScreenerClaw intelligence pipeline.

Endpoints:
  POST /api/analyze       — Main: analyse query (single stock or screen)
  GET  /api/health        — Health check
  GET  /api/llm/providers — List available LLM providers
  POST /api/llm/test      — Test an LLM provider
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.pipeline import get_pipeline
from backend.llm_client import PROVIDERS, list_providers, resolve_task_llm
from backend.config import settings
from backend.logger import get_logger

logger = get_logger(__name__)

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="ScreenerClaw",
    description=(
        "AI-native Indian stock discovery and intelligence platform. "
        "5-step pipeline: Business Understanding → Macro Analysis → "
        "Report & Outlook → Adaptive Valuation → Composite Scoring."
    ),
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s — %d (%.0fms)",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


# ── Request Models ────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    query: str
    provider: Optional[str] = None
    model: Optional[str] = None


class LLMTestRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    prompt: str = "Say hello in one sentence."


# ── Startup / Shutdown ────────────────────────────────────────────────────────

async def _preload_universe() -> None:
    """Background task: download NSE + BSE listings on first startup."""
    try:
        from backend.screener.stock_universe import ensure_universe
        await ensure_universe()
    except Exception as exc:
        logger.warning("Stock universe preload failed (non-fatal): %s", exc)


@app.on_event("startup")
async def on_startup() -> None:
    reasoning_provider, reasoning_model = resolve_task_llm("reasoning")
    execution_provider, execution_model = resolve_task_llm("execution")
    fast_provider, fast_model = resolve_task_llm("fast")

    logger.info("=== ScreenerClaw v3.0 starting ===")
    logger.info("Reasoning LLM: %s/%s", reasoning_provider, reasoning_model)
    logger.info("Execution LLM: %s/%s", execution_provider, execution_model)
    logger.info("Fast LLM: %s/%s", fast_provider, fast_model)
    search_backends = []
    if settings.openai_api_key:
        search_backends.append("OpenAI")
    if settings.groq_api_key:
        search_backends.append("Groq")
    search_backends.append("DuckDuckGo")
    logger.info("Web search backends: %s", " + ".join(search_backends))
    logger.info(
        "Screener.in: %s",
        "configured" if settings.screener_username else "guest mode",
    )
    get_pipeline()
    # Pre-download NSE + BSE stock universe for accurate ticker resolution
    # Runs in background — does not block startup
    asyncio.ensure_future(_preload_universe())


@app.on_event("shutdown")
async def on_shutdown() -> None:
    from backend.screener.auth import close_session
    await close_session()
    logger.info("ScreenerClaw shutdown.")


# ── POST /api/analyze ─────────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> JSONResponse:
    """
    Main endpoint. Accepts any natural-language query:
    - "Analyse TCS" → full 5-step intelligence report
    - "Find undervalued pharma midcaps" → screened + scored list
    - "Best compounders in FMCG" → themed screening

    Optional: override provider/model for this request.
    """
    if not request.query or not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    pipeline = get_pipeline(provider=request.provider, model=request.model)

    try:
        result = await pipeline.analyze(request.query.strip())
    except Exception as exc:
        logger.exception("Pipeline failed for query %r: %s", request.query, exc)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {exc}") from exc

    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])

    return JSONResponse(content=result)


# ── GET /api/health ───────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check() -> JSONResponse:
    reasoning_provider, reasoning_model = resolve_task_llm("reasoning")
    return JSONResponse(content={
        "status": "ok",
        "version": "3.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reasoning_llm": f"{reasoning_provider}/{reasoning_model}",
        "web_search": "openai+groq+duckduckgo",
        "screener_credentials": bool(settings.screener_username),
    })


# ── GET /api/llm/providers ────────────────────────────────────────────────────

@app.get("/api/llm/providers")
async def get_llm_providers() -> JSONResponse:
    configured = {
        "anthropic": bool(settings.anthropic_api_key),
        "openai": bool(settings.openai_api_key),
        "groq": bool(settings.groq_api_key),
    }
    providers = list_providers()
    for p in providers:
        p["configured"] = configured.get(p["id"], False)

    reasoning_p, reasoning_m = resolve_task_llm("reasoning")
    execution_p, execution_m = resolve_task_llm("execution")

    return JSONResponse(content={
        "providers": providers,
        "routing": {
            "reasoning": f"{reasoning_p}/{reasoning_m}",
            "execution": f"{execution_p}/{execution_m}",
        },
    })


# ── POST /api/llm/test ────────────────────────────────────────────────────────

@app.post("/api/llm/test")
async def test_llm(request: LLMTestRequest) -> JSONResponse:
    from backend.llm_client import LLMClient

    if request.provider not in PROVIDERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider '{request.provider}'. Valid: {list(PROVIDERS)}",
        )
    try:
        client = LLMClient(provider=request.provider, model=request.model)
        t0 = time.monotonic()
        response = await client.complete(
            messages=[{"role": "user", "content": request.prompt}],
            system="You are a helpful assistant.",
            max_tokens=256,
        )
        return JSONResponse(content={
            "provider": request.provider,
            "model": client.model,
            "is_reasoning_model": client.is_reasoning,
            "response": response,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "status": "ok",
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM test failed: {exc}") from exc
