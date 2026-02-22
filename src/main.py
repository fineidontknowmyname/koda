"""
main.py
--------
FastAPI application entry-point for Koda.

Startup sequence (lifespan)
─────────────────────────────
  1. Create / verify DB tables (SQLAlchemy declarative models)
  2. Pre-warm on-device vision model (MobileNetV2 weights into RAM)
  3. Check Ollama connectivity — warn but do not abort on failure
  4. Check Celery / Redis connectivity — warn but do not abort on failure

Exception handlers
───────────────────
  DomainBaseError subclasses → structured JSON  {"error": code, "detail": msg}
  RequestValidationError      → 422 with Pydantic field errors normalised
  Unhandled Exception         → 500 with opaque message (no stack leak)

Routes
───────
  /api/v1/*                   — versioned API (plans, vision, users)
  /generate-plan              — 307 redirect shim (legacy frontend compat)
  GET /health                 — liveness check (no DB dependency)
  GET /api/v1/health          — same, mounted under versioned prefix
  GET /api/v1/celery-health   — Celery / Redis broker ping
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router as legacy_router
from api.v1.api import api_router
from config.settings import settings
from exceptions import DomainBaseError

log = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


# ── Startup / shutdown ─────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Runs startup tasks before yielding control to the ASGI server, and
    shutdown tasks (if any) after the yield.
    """
    # 1. DB
    log.info("Startup: creating / verifying database tables …")
    try:
        # Import models first so their tables are registered with Base.metadata
        import db.models  # noqa: F401
        from db.session import create_all_tables
        await create_all_tables()
        log.info("Startup: database OK")
    except Exception as exc:
        log.error("Startup: DB init failed — %s", exc)

    # 2. Vision model pre-warm (non-blocking, best-effort)
    log.info("Startup: pre-warming vision model …")
    try:
        from services.vision.model_loader import model_registry
        await asyncio.to_thread(model_registry.prewarm)
        log.info("Startup: vision model OK")
    except Exception as exc:
        log.warning("Startup: vision model pre-warm skipped — %s", exc)

    # 3. Ollama connectivity check (warn only)
    log.info("Startup: checking Ollama connectivity at %s …", settings.OLLAMA_HOST)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"{settings.OLLAMA_HOST}/api/tags")
            r.raise_for_status()
        log.info("Startup: Ollama OK")
    except Exception as exc:
        log.warning("Startup: Ollama not reachable — %s (plan generation will fail)", exc)

    # 4. Celery / Redis connectivity check (warn only)
    log.info("Startup: checking Celery broker at %s …", settings.REDIS_URL)
    try:
        from workers.celery_app import celery_app
        # inspect().ping() with a short timeout is the canonical broker ping
        inspector = celery_app.control.inspect(timeout=3.0)
        await asyncio.to_thread(inspector.ping)
        log.info("Startup: Celery broker OK")
    except Exception as exc:
        log.warning("Startup: Celery broker not reachable — %s (async jobs will fail)", exc)

    yield   # ← application runs here

    # Shutdown (add cleanup here if needed)
    log.info("Shutdown: complete")


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Koda API",
    version="1.0.0",
    description="AI-powered personalised fitness plan generation API.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS ───────────────────────────────────────────────────────────────────────

_CORS_ORIGINS = ["*"] if settings.ENVIRONMENT == "local" else [
    # Add known frontend origins here for non-local environments
    # e.g. "https://app.koda.fit"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Exception handlers ─────────────────────────────────────────────────────────

@app.exception_handler(DomainBaseError)
async def domain_error_handler(request: Request, exc: DomainBaseError) -> JSONResponse:
    """
    Convert any DomainBaseError (and subclasses) into a consistent JSON response.

    Response body: {"error": "<code>", "detail": "<human message>"}
    """
    log.warning(
        "DomainBaseError  code=%s  status=%d  path=%s  detail=%s",
        exc.code, exc.http_status, request.url.path, exc.detail,
    )
    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.code, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """
    Normalise Pydantic v2 validation errors into the same envelope format.

    Response body: {"error": "validation_error", "detail": [...pydantic errors...]}
    """
    log.debug("RequestValidationError  path=%s  errors=%s", request.url.path, exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "validation_error", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for unexpected exceptions — returns 500 without leaking a stack trace.
    """
    log.exception("Unhandled exception  path=%s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "detail": "An unexpected error occurred."},
    )


# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(api_router, prefix="/api/v1")
app.include_router(legacy_router)   # /generate-plan → 307 redirect


# ── System endpoints ───────────────────────────────────────────────────────────

@app.get("/health", tags=["System"], summary="Liveness probe")
@app.get("/api/v1/health", tags=["System"], include_in_schema=False)
def health_check() -> dict:
    """Returns 200 OK — no DB or broker dependency (suitable for k8s liveness probe)."""
    return {"status": "ok", "environment": settings.ENVIRONMENT, "version": "1.0.0"}


@app.get("/api/v1/celery-health", tags=["System"], summary="Celery broker ping")
async def celery_health() -> dict:
    """
    Attempts a short-timeout ping to the Celery broker.

    Returns ``{"status": "ok"}`` when at least one worker responds,
    or ``{"status": "degraded", "reason": "..."}`` otherwise.
    """
    try:
        from workers.celery_app import celery_app
        inspector = celery_app.control.inspect(timeout=3.0)
        result = await asyncio.to_thread(inspector.ping)
        if result:
            workers = list(result.keys())
            return {"status": "ok", "workers": workers}
        return {"status": "degraded", "reason": "No active Celery workers responded"}
    except Exception as exc:
        return {"status": "degraded", "reason": str(exc)}


# ── Entry-point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=(settings.ENVIRONMENT == "local"),
        log_level="info",
    )
