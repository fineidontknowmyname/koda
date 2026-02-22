"""
workers/tasks.py
-----------------
Celery task definitions for Koda background workers.

Tasks
──────
generate_plan_task(payload)   — Run the full orchestrator pipeline and persist
                                 the result to the FitnessPlanRecord table.

Execution model
───────────────
Celery tasks are *synchronous* functions; async orchestrator calls are
bridged via ``asyncio.run()``.  Each worker process gets its own event loop
so there is no loop-sharing issue.

Retry policy
────────────
  max_retries = 3
  Backoff:  10 s → 20 s → 30 s  (countdown * retry number)

Persistence
───────────
The task writes the plan result (or error) back to ``fitness_plan_records``
via a separate synchronous SQLAlchemy session so the poll endpoint can serve
results from the DB rather than querying Celery's result backend directly.
This decouples the frontend poll from Redis availability.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

from celery.utils.log import get_task_logger

from workers.celery_app import celery_app

log = get_task_logger(__name__)


# ── Helper: sync DB write (called inside synchronous task) ─────────────────────

def _persist_plan(job_id: str, status: str, plan_dict: dict | None, error: str | None) -> None:
    """
    Upsert a FitnessPlanRecord row with the final status.

    Uses a *synchronous* SQLAlchemy session (not the async one) because
    Celery tasks run in a regular thread, not an async event loop context.
    """
    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        # Build a sync URL from the same DATABASE_URL setting
        try:
            from config.settings import settings
            raw_url: str = settings.DATABASE_URL or "sqlite:///./koda.db"
        except Exception:
            raw_url = "sqlite:///./koda.db"

        # Convert async drivers → sync equivalents for the worker thread
        sync_url = (
            raw_url
            .replace("sqlite+aiosqlite://", "sqlite://")
            .replace("postgresql+asyncpg://", "postgresql+psycopg2://")
            .replace("postgresql://", "postgresql+psycopg2://")
            .replace("postgres://", "postgresql+psycopg2://")
        )

        engine = create_engine(sync_url, connect_args={"check_same_thread": False} if "sqlite" in sync_url else {})

        from db.models import FitnessPlanRecord

        with Session(engine) as session:
            row = session.execute(
                select(FitnessPlanRecord).where(FitnessPlanRecord.job_id == job_id)
            ).scalar_one_or_none()

            if row is None:
                row = FitnessPlanRecord(job_id=job_id)
                session.add(row)

            row.status       = status
            row.plan_json    = plan_dict
            row.error_detail = error
            if status in ("done", "failed"):
                row.completed_at = datetime.now(timezone.utc)

            session.commit()
            log.info("Persisted plan record  job_id=%s  status=%s", job_id, status)

    except Exception as exc:
        # Don't let a DB write failure mask the task result
        log.warning("Failed to persist plan record  job_id=%s  error=%s", job_id, exc)


# ── Task ───────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="workers.generate_plan",
    max_retries=3,
    soft_time_limit=180,   # 3 min → SoftTimeLimitExceeded → retry
    time_limit=240,        # 4 min hard kill
)
def generate_plan_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Run the full PlanOrchestrator pipeline and return a FitnessPlan dict.

    Parameters
    ----------
    payload
        JSON-serialisable dict produced by ``GeneratePlanRequest.model_dump()``.

    Returns
    -------
    dict
        ``FitnessPlan.model_dump()`` on success.
        Stored in the Celery result backend keyed by ``self.request.id``.

    Side-effects
    │── Updates ``fitness_plan_records`` row status → "running" on start.
    └── Updates row status → "done" | "failed" on completion.
    """
    job_id = self.request.id
    log.info("generate_plan_task START  job_id=%s  retry=%d", job_id, self.request.retries)

    # Mark as running
    _persist_plan(job_id, "running", None, None)

    try:
        # ── Validate payload ───────────────────────────────────────────────────
        from schemas.plan import GeneratePlanRequest
        request = GeneratePlanRequest.model_validate(payload)

        # ── Run async orchestrator in a fresh event loop ───────────────────────
        from core.orchestrator import plan_orchestrator

        plan = asyncio.run(
            plan_orchestrator.generate_plan(
                user_profile=request.user_profile,
                youtube_urls=request.youtube_urls or [],
                transcript_text=request.transcript_text,
            )
        )

        plan_dict = plan.model_dump()

        # ── Persist success ────────────────────────────────────────────────────
        _persist_plan(job_id, "done", plan_dict, None)
        log.info("generate_plan_task DONE  job_id=%s", job_id)

        return plan_dict

    except Exception as exc:
        log.exception(
            "generate_plan_task FAILED  job_id=%s  retry=%d  error=%s",
            job_id, self.request.retries, exc,
        )
        _persist_plan(job_id, "failed", None, str(exc))

        # Retry with linear backoff: 10 s, 20 s, 30 s
        raise self.retry(exc=exc, countdown=10 * (self.request.retries + 1))
