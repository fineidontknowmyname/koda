"""
tasks/plan_tasks.py
-------------------
Celery task definitions for async plan generation.

The broker URL is read from ``settings.CELERY_BROKER_URL``
(defaults to ``redis://localhost:6379/0`` if the env-var is absent).

Starting a worker:
    celery -A tasks.plan_tasks worker --loglevel=info

Checking results:
    celery -A tasks.plan_tasks result <task-id>
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from celery import Celery
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

# ── Celery application ────────────────────────────────────────────────────────
# Import settings lazily inside the task to avoid circular imports at module
# load time; the broker URL below is evaluated once when the module is first
# imported.

def _make_celery() -> Celery:
    try:
        from config.settings import settings
        broker = getattr(settings, "CELERY_BROKER_URL", "redis://localhost:6379/0")
        backend = getattr(settings, "CELERY_RESULT_BACKEND", broker)
    except Exception:  # settings not available (e.g. running tests without .env)
        broker = "redis://localhost:6379/0"
        backend = broker

    app = Celery(
        "koda",
        broker=broker,
        backend=backend,
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_acks_late=True,           # re-queue on worker crash
        worker_prefetch_multiplier=1,  # one task at a time per worker
    )
    return app


celery_app = _make_celery()


# ── Task ──────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.generate_plan",
    max_retries=2,
    soft_time_limit=180,   # 3 min soft kill → triggers SoftTimeLimitExceeded
    time_limit=240,        # 4 min hard kill
)
def generate_plan_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Celery task wrapper around ``PlanOrchestrator.generate_plan``.

    Parameters
    ----------
    payload
        JSON-serialisable dict matching ``GeneratePlanRequest.model_dump()``.

    Returns
    -------
    dict
        ``FitnessPlan.model_dump()`` on success.
        Celery stores this in the result backend keyed by ``self.request.id``.
    """
    # Deferred imports to keep module-level load fast
    from schemas.plan import GeneratePlanRequest
    from core.orchestrator import plan_orchestrator

    logger.info("generate_plan_task started  task_id=%s", self.request.id)

    try:
        # Validate payload into a typed request
        request = GeneratePlanRequest.model_validate(payload)

        # Run the async orchestrator in a fresh event loop
        plan = asyncio.run(
            plan_orchestrator.generate_plan(
                user_profile=request.user_profile,
                youtube_urls=request.youtube_urls or [],
                transcript_text=request.transcript_text,
            )
        )

        logger.info("generate_plan_task completed  task_id=%s", self.request.id)
        return plan.model_dump()

    except Exception as exc:
        logger.exception(
            "generate_plan_task failed  task_id=%s  error=%s",
            self.request.id, exc,
        )
        # Retry with exponential backoff (10 s, 20 s)
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))
