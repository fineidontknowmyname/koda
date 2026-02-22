from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache
from typing import Optional
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
# src/config/settings.py -> src/config -> src -> root
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"


class Settings(BaseSettings):
    # ── Ollama (active LLM backend) ───────────────────────────────────────────
    OLLAMA_HOST: str = Field(
        default="http://localhost:11434",
        description="Base URL of the running Ollama server (alias: OLLAMA_BASE_URL)",
    )
    # Keep OLLAMA_BASE_URL as a read-only alias so existing .env files keep working
    OLLAMA_BASE_URL: Optional[str] = Field(
        default=None,
        description="Alias for OLLAMA_HOST — prefer OLLAMA_HOST in new .env files",
    )
    OLLAMA_MODEL: str = Field(
        default="llama3.2",
        description="Default text-generation model tag served by Ollama",
    )
    OLLAMA_VISION_MODEL: str = Field(
        default="llava",
        description="Multimodal / vision model tag served by Ollama",
    )

    # ── On-device vision model ────────────────────────────────────────────────
    MODEL_PATH: str = Field(
        default="models/body_composition.keras",
        description=(
            "Path to the MobileNetV2-based body composition .keras model file. "
            "Relative paths are resolved from the project root."
        ),
    )

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: Optional[str] = Field(
        default=None,
        description=(
            "Async-driver DB URL.  "
            "Not set → sqlite+aiosqlite:///./koda.db (zero-config default).  "
            "Postgres example: postgresql+asyncpg://user:pass@host:5432/koda"
        ),
    )

    # ── Redis / Celery ────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL used as the Celery broker",
    )
    CELERY_BROKER_URL: Optional[str] = Field(
        default=None,
        description="Celery broker URL (defaults to REDIS_URL when not set)",
    )
    CELERY_RESULT_BACKEND: Optional[str] = Field(
        default=None,
        description="Celery result backend URL (defaults to REDIS_URL on DB 1 when not set)",
    )

    # ── Application ────────────────────────────────────────────────────────────
    ENVIRONMENT: str = Field(
        default="local",
        description="Deployment environment: local | dev | staging | prod",
    )
    DEBUG: bool = Field(
        default=False,
        description="Enable verbose SQL logging and debug tracebacks",
    )

    # Model config — read from .env file
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,  # allow field name OR alias in .env
    )

    # ── Derived helpers ────────────────────────────────────────────────────────

    @property
    def effective_ollama_host(self) -> str:
        """Return OLLAMA_HOST, falling back to OLLAMA_BASE_URL for legacy .env files."""
        return self.OLLAMA_HOST or self.OLLAMA_BASE_URL or "http://localhost:11434"

    @property
    def effective_broker_url(self) -> str:
        return self.CELERY_BROKER_URL or self.REDIS_URL

    @property
    def effective_backend_url(self) -> str:
        if self.CELERY_RESULT_BACKEND:
            return self.CELERY_RESULT_BACKEND
        # Use Redis DB 1 for results to avoid colliding with broker on DB 0
        base = self.REDIS_URL.rstrip("/")
        if base.endswith("/0"):
            return base[:-2] + "/1"
        return base + "/1" if not base[-1].isdigit() else base


@lru_cache()
def get_settings() -> Settings:
    """
    Returns a cached (process-lifetime) Settings instance.
    Use as a FastAPI dependency::

        from config.settings import get_settings, Settings
        from fastapi import Depends

        def my_endpoint(cfg: Settings = Depends(get_settings)):
            ...
    """
    return Settings()


settings = get_settings()
