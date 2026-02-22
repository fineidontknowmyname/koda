"""
api/dependencies.py
--------------------
FastAPI dependency-injection providers for shared service singletons.

All providers are synchronous functions (no async needed since each just
returns a cached singleton) and are safe to use in both sync and async
endpoint handlers.

Available dependencies
──────────────────────
get_orchestrator()          → PlanOrchestrator
get_db()                    → AsyncSession          (re-exported from db.session)
get_ollama_client()         → OllamaClient
get_vision_model()          → ModelRegistry         (Keras model registry)
get_body_composition()      → BodyCompositionService
get_summarizer()            → SummarizerService
get_youtube_service()       → YouTubeService
get_settings()              → Settings              (re-exported from config)

Usage
─────
    from api.dependencies import get_ollama_client
    from integrations.ollama_client import OllamaClient

    async def my_endpoint(client: OllamaClient = Depends(get_ollama_client)):
        text = await client.generate_text("Hello")
"""

from __future__ import annotations

# ── Re-export db dependency so endpoints only need to import from here ─────────

from db.session import get_db as get_db  # noqa: F401 (re-export)


# ── Orchestrator ────────────────────────────────────────────────────────────────

from core.orchestrator import plan_orchestrator, PlanOrchestrator


def get_orchestrator() -> PlanOrchestrator:
    """Return the module-level PlanOrchestrator singleton."""
    return plan_orchestrator


# ── Ollama client ───────────────────────────────────────────────────────────────

from integrations.ollama_client import ollama_client, OllamaClient


def get_ollama_client() -> OllamaClient:
    """
    Return the shared OllamaClient singleton.

    The client is stateless and safe to share across requests; it holds no
    per-request state and uses httpx internally with connection pooling.
    """
    return ollama_client


# ── Vision model registry ───────────────────────────────────────────────────────

from services.vision.model_loader import model_registry, ModelRegistry


def get_vision_model() -> ModelRegistry:
    """
    Return the singleton ModelRegistry.

    The first call to ``model_registry.body_composition`` triggers a lazy
    load of the .keras weights; subsequent calls hit the in-memory cache.
    """
    return model_registry


# ── Body composition service ────────────────────────────────────────────────────

from services.vision.body_composition import (
    body_composition_service,
    BodyCompositionService,
)


def get_body_composition() -> BodyCompositionService:
    """Return the BodyCompositionService singleton (wraps MobileNetV2 + MediaPipe)."""
    return body_composition_service


# ── Summarizer ──────────────────────────────────────────────────────────────────

from services.intelligence.summarizer import summarizer_service, SummarizerService


def get_summarizer() -> SummarizerService:
    """Return the SummarizerService singleton (classify + extract via Ollama)."""
    return summarizer_service


# ── YouTube service ─────────────────────────────────────────────────────────────

from services.intelligence.youtube import youtube_service, YouTubeService


def get_youtube_service() -> YouTubeService:
    """Return the YouTubeService singleton (multi-URL parallel transcript fetch)."""
    return youtube_service


# ── Settings ────────────────────────────────────────────────────────────────────

from config.settings import get_settings, Settings  # noqa: F401 (re-export)
