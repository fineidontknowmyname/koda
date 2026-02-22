"""
exceptions.py
--------------
Domain exception hierarchy for Koda.

All application-level errors subclass ``DomainBaseError`` so callers can
catch them at the appropriate level of granularity:

    except DomainBaseError:          # catch any business-logic error
    except ValidationError:          # catch only input validation failures
    except ExternalServiceError:     # catch only third-party failures

FastAPI exception handlers
───────────────────────────
Register these in ``main.py`` to return consistent JSON error responses:

    from fastapi import Request
    from fastapi.responses import JSONResponse
    from exceptions import DomainBaseError

    @app.exception_handler(DomainBaseError)
    async def domain_error_handler(request: Request, exc: DomainBaseError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": exc.code, "detail": exc.detail},
        )

Exception taxonomy
───────────────────

DomainBaseError
├── ValidationError              — bad input from the caller
│   ├── AgeOutOfRangeError       — age not in 15–60
│   ├── InvalidURLError          — malformed YouTube URL
│   └── ConsentRequiredError     — user hasn't given vision consent
├── NotFoundError                — requested resource doesn't exist
│   ├── UserNotFoundError
│   └── PlanNotFoundError
├── ExternalServiceError         — third-party call failed
│   ├── OllamaUnavailableError   — Ollama server unreachable/timeout
│   ├── TranscriptFetchError     — YouTube transcript unavailable
│   └── VisionModelError         — MobileNetV2/MediaPipe inference failed
├── PipelineError                — orchestrator / job failure
│   ├── PlanGenerationError      — orchestrator pipeline error
│   └── JobDispatchError         — Celery task dispatch failed
└── ConfigurationError           — missing or invalid server config
"""

from __future__ import annotations

from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────

class DomainBaseError(Exception):
    """
    Root of the Koda domain exception hierarchy.

    Attributes
    ----------
    detail      Human-readable error message (safe to send to clients).
    code        Machine-readable error code (snake_case string).
    http_status Default HTTP status code for FastAPI exception handlers.
    context     Optional dict of additional debugging context (never sent to clients).
    """

    http_status: int = 500
    code: str = "internal_error"

    def __init__(
        self,
        detail: str = "An unexpected error occurred.",
        *,
        code: str | None = None,
        http_status: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail     = detail
        self.code       = code or self.__class__.code
        self.http_status = http_status or self.__class__.http_status
        self.context    = context or {}

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, detail={self.detail!r})"


# ─────────────────────────────────────────────────────────────────────────────
# Validation errors  (4xx — caller's fault)
# ─────────────────────────────────────────────────────────────────────────────

class ValidationError(DomainBaseError):
    """Input from the caller failed domain validation."""
    http_status = 422
    code = "validation_error"


class AgeOutOfRangeError(ValidationError):
    """User age is outside the accepted range of 15–60 years."""
    code = "age_out_of_range"

    def __init__(self, age: int) -> None:
        super().__init__(
            detail=f"Age {age} is outside the accepted range (15–60 years).",
            context={"age": age, "min": 15, "max": 60},
        )


class InvalidURLError(ValidationError):
    """A supplied URL is not a valid YouTube video URL."""
    code = "invalid_url"

    def __init__(self, url: str) -> None:
        super().__init__(
            detail=f"Could not extract a valid YouTube video ID from URL: {url!r}",
            context={"url": url},
        )


class ConsentRequiredError(ValidationError):
    """Body-image analysis requires explicit user consent."""
    http_status = 451   # Unavailable For Legal Reasons
    code = "consent_required"

    def __init__(self) -> None:
        super().__init__(
            detail=(
                "Body image analysis requires explicit consent. "
                "Include the header 'X-Vision-Consent: true' in your request."
            ),
        )


# ─────────────────────────────────────────────────────────────────────────────
# Not found errors  (404)
# ─────────────────────────────────────────────────────────────────────────────

class NotFoundError(DomainBaseError):
    """Requested resource does not exist."""
    http_status = 404
    code = "not_found"


class UserNotFoundError(NotFoundError):
    """No user was found for the given identifier."""
    code = "user_not_found"

    def __init__(self, user_id: str) -> None:
        super().__init__(
            detail=f"User '{user_id}' not found.",
            context={"user_id": user_id},
        )


class PlanNotFoundError(NotFoundError):
    """No fitness plan / job was found for the given identifier."""
    code = "plan_not_found"

    def __init__(self, job_id: str) -> None:
        super().__init__(
            detail=f"No plan found for job ID '{job_id}'.",
            context={"job_id": job_id},
        )


# ─────────────────────────────────────────────────────────────────────────────
# External service errors  (502 / 503)
# ─────────────────────────────────────────────────────────────────────────────

class ExternalServiceError(DomainBaseError):
    """A call to a third-party service failed."""
    http_status = 502
    code = "external_service_error"


class OllamaUnavailableError(ExternalServiceError):
    """Ollama server is unreachable or returned an unexpected response."""
    http_status = 503
    code = "ollama_unavailable"

    def __init__(self, url: str, reason: str = "") -> None:
        super().__init__(
            detail=f"Ollama server at {url!r} is unavailable. {reason}".strip(),
            context={"url": url, "reason": reason},
        )


class TranscriptFetchError(ExternalServiceError):
    """YouTube transcript could not be retrieved for the given video."""
    code = "transcript_fetch_error"

    def __init__(self, url: str, reason: str = "") -> None:
        super().__init__(
            detail=f"Could not fetch transcript for {url!r}. {reason}".strip(),
            context={"url": url, "reason": reason},
        )


class VisionModelError(ExternalServiceError):
    """On-device vision model (MobileNetV2 / MediaPipe) inference failed."""
    http_status = 500
    code = "vision_model_error"

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            detail=f"Vision model inference failed. {reason}".strip(),
            context={"reason": reason},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline / job errors  (500 / 503)
# ─────────────────────────────────────────────────────────────────────────────

class PipelineError(DomainBaseError):
    """The orchestrator or background job pipeline encountered an error."""
    http_status = 500
    code = "pipeline_error"


class PlanGenerationError(PipelineError):
    """Plan orchestrator failed to produce a valid FitnessPlan."""
    code = "plan_generation_error"

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            detail=f"Fitness plan generation failed. {reason}".strip(),
            context={"reason": reason},
        )


class JobDispatchError(PipelineError):
    """Failed to dispatch a background task to Celery."""
    http_status = 503
    code = "job_dispatch_error"

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            detail=f"Could not queue plan generation job. {reason}".strip(),
            context={"reason": reason},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Configuration errors  (500)
# ─────────────────────────────────────────────────────────────────────────────

class ConfigurationError(DomainBaseError):
    """A required server configuration value is missing or invalid."""
    http_status = 500
    code = "configuration_error"

    def __init__(self, setting: str, reason: str = "") -> None:
        super().__init__(
            detail=f"Server misconfiguration: '{setting}'. {reason}".strip(),
            context={"setting": setting, "reason": reason},
        )
