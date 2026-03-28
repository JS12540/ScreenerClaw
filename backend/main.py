"""
Screener Investment Research Agent — FastAPI Application
Thin API layer over the InvestmentPipeline.

Endpoints:
  POST /api/analyze      — Main endpoint: analyze a query (single stock or screen)
  GET  /api/health       — Health check
  GET  /api/llm/providers — List available LLM providers
  POST /api/llm/test     — Test an LLM provider
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.pipeline import get_pipeline
from backend.llm_client import PROVIDERS, list_providers, default_model_for
from backend.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ─── FastAPI app ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Screener Investment Research Agent",
    description="Autonomous AI agent for Indian stock analysis. Logs into Screener.in, scrapes all financial data, and produces multi-method valuation reports.",
    version="2.0.0",
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
    logger.info("%s %s — %d (%.0fms)", request.method, request.url.path, response.status_code, elapsed_ms)
    return response


# ─── Request models ───────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    query: str
    provider: Optional[str] = None   # Override LLM provider
    model: Optional[str] = None      # Override LLM model


class LLMTestRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    prompt: str = "Say hello in one sentence."


# ─── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def on_startup() -> None:
    logger.info("=== Screener Investment Research Agent starting ===")
    logger.info("Default LLM: provider=%s model=%s", settings.default_llm_provider, settings.default_llm_model or default_model_for(settings.default_llm_provider))
    logger.info("Screener credentials: %s", "configured" if settings.screener_username else "NOT configured (guest mode)")
    # Pre-warm the pipeline
    get_pipeline()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    from backend.screener.auth import close_session
    await close_session()
    logger.info("Agent shutdown.")


# ─── POST /api/analyze ───────────────────────────────────────────────────────

@app.post("/api/analyze")
async def analyze(request: AnalyzeRequest) -> JSONResponse:
    """
    Main endpoint. Accepts a natural-language query:
    - "Analyse TCS" → full 8-phase investment report
    - "Find low PE IT companies" → screening results

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


# ─── GET /api/health ─────────────────────────────────────────────────────────

@app.get("/api/health")
async def health_check() -> JSONResponse:
    provider = settings.default_llm_provider
    model = settings.default_llm_model or default_model_for(provider)
    return JSONResponse(content={
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "2.0.0",
        "default_provider": provider,
        "default_model": model,
        "screener_credentials": bool(settings.screener_username),
    })


# ─── GET /api/llm/providers ──────────────────────────────────────────────────

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
        p["is_default"] = p["id"] == settings.default_llm_provider

    return JSONResponse(content={
        "providers": providers,
        "default_provider": settings.default_llm_provider,
        "default_model": settings.default_llm_model or default_model_for(settings.default_llm_provider),
    })


# ─── POST /api/llm/test ──────────────────────────────────────────────────────

@app.post("/api/llm/test")
async def test_llm(request: LLMTestRequest) -> JSONResponse:
    """Test an LLM provider with a simple prompt."""
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
            "response": response,
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "status": "ok",
        })
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"LLM test failed: {exc}") from exc
