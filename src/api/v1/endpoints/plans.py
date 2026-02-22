"""
api/v1/endpoints/plans.py
--------------------------
Fitness plan generation endpoints.

Routes
──────
POST /plans/generate         Dispatch async Celery job → JobResponse
POST /plans/generate/pdf     Legacy synchronous PDF (kept for backward compat)
GET  /plans/job/{job_id}     Poll job status → JobStatusResponse
GET  /plans/job/{job_id}/pdf Download PDF once job is done

Legacy fix
──────────
Old routes called plan_orchestrator.generate_plan(transcript_text=...) which 
no longer matches the orchestrator signature.  All new calls use youtube_urls
and pass the full GeneratePlanRequest to the Celery task.
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import StreamingResponse

from schemas.plan import (
    GeneratePlanRequest,
    FitnessPlan,
    JobResponse,
    JobStatus,
    JobStatusResponse,
)

log = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_celery():
    """Lazy import so the module can be loaded without a running broker."""
    from tasks.plan_tasks import celery_app, generate_plan_task  # noqa: F401
    return celery_app, generate_plan_task


def _task_to_status(state: str) -> JobStatus:
    """Map Celery task state → JobStatus enum."""
    mapping = {
        "PENDING":  JobStatus.pending,
        "STARTED":  JobStatus.running,
        "RETRY":    JobStatus.running,
        "SUCCESS":  JobStatus.done,
        "FAILURE":  JobStatus.failed,
        "REVOKED":  JobStatus.failed,
    }
    return mapping.get(state.upper(), JobStatus.pending)


# ── POST /generate  (async dispatch) ──────────────────────────────────────────

@router.post(
    "/generate",
    response_model=JobResponse,
    status_code=202,
    summary="Dispatch async fitness plan generation",
    description=(
        "Queues plan generation as a background Celery task and immediately "
        "returns a `job_id`.  Poll `GET /plans/job/{job_id}` for results."
    ),
)
async def generate_plan(request: GeneratePlanRequest) -> JobResponse:
    """
    Dispatch plan generation to Celery and return a job handle.

    The request is serialised to JSON via `model_dump()` so it is broker-safe.
    """
    try:
        _, generate_plan_task = _get_celery()
        task = generate_plan_task.delay(request.model_dump())
        log.info("Dispatched generate_plan_task  job_id=%s", task.id)
        return JobResponse(job_id=task.id)

    except Exception as exc:
        log.exception("Failed to dispatch plan task: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to queue plan generation")


# ── GET /job/{job_id}  (poll) ──────────────────────────────────────────────────

@router.get(
    "/job/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll plan generation job status",
)
async def get_job_status(
    job_id: str = Path(..., description="Celery task ID returned by POST /generate"),
) -> JobStatusResponse:
    """
    Returns the current status of a queued plan generation job.

    When `status == "done"`, `result` contains the full `FitnessPlan` JSON.
    When `status == "failed"`, `error` contains the exception message.
    """
    try:
        celery_app, _ = _get_celery()
        result_obj = celery_app.AsyncResult(job_id)
        state      = result_obj.state

        status = _task_to_status(state)

        if state == "SUCCESS":
            return JobStatusResponse(
                job_id=job_id,
                status=status,
                result=result_obj.result,   # FitnessPlan dict
            )

        if state == "FAILURE":
            exc = result_obj.result
            return JobStatusResponse(
                job_id=job_id,
                status=status,
                error=str(exc) if exc else "Unknown error",
            )

        return JobStatusResponse(job_id=job_id, status=status)

    except Exception as exc:
        log.exception("Error polling job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail="Error retrieving job status")


# ── GET /job/{job_id}/pdf  (download PDF once done) ───────────────────────────

@router.get(
    "/job/{job_id}/pdf",
    summary="Download PDF for a completed plan job",
)
async def get_job_pdf(
    job_id: str = Path(..., description="Celery task ID"),
) -> StreamingResponse:
    """
    Renders and streams a PDF for a completed plan job.

    Returns 202 if the job is still running, 404 if the job ID is unknown,
    400 if the job failed.
    """
    try:
        celery_app, _ = _get_celery()
        result_obj = celery_app.AsyncResult(job_id)
        state      = result_obj.state

        if state in ("PENDING", "STARTED", "RETRY"):
            raise HTTPException(
                status_code=202,
                detail=f"Job {job_id} is still {_task_to_status(state).value}. Try again shortly.",
            )

        if state == "FAILURE":
            exc = result_obj.result
            raise HTTPException(status_code=400, detail=f"Job failed: {exc}")

        if state != "SUCCESS":
            raise HTTPException(status_code=404, detail=f"Unknown job state: {state}")

        # Reconstruct FitnessPlan and render PDF
        plan = FitnessPlan.model_validate(result_obj.result)
        from reporting.pdf_architect import pdf_architect
        pdf_bytes = pdf_architect.render_plan(plan)

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=koda_plan_{job_id[:8]}.pdf"},
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.exception("Error rendering PDF for job %s: %s", job_id, exc)
        raise HTTPException(status_code=500, detail="PDF rendering failed")


# ── POST /generate/pdf  (legacy synchronous) ──────────────────────────────────

@router.post(
    "/generate/pdf",
    summary="[Legacy] Synchronous plan generation + PDF download",
    description=(
        "Runs plan generation synchronously in the request lifecycle. "
        "Prefer `POST /generate` + `GET /job/{job_id}/pdf` for production use."
    ),
)
async def generate_plan_pdf_legacy(request: GeneratePlanRequest) -> Any:
    """
    Kept for backward compatibility with existing clients.

    Generates a plan and returns a PDF inline.  Times out for complex requests;
    prefer the async dispatch route in production.
    """
    try:
        from core.orchestrator import plan_orchestrator
        from reporting.pdf_architect import pdf_architect

        plan = await plan_orchestrator.generate_plan(
            user_profile=request.user_profile,
            youtube_urls=request.youtube_urls or [],
            transcript_text=request.transcript_text,
        )
        pdf_bytes = pdf_architect.render_plan(plan)

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=koda_plan.pdf"},
        )

    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        log.exception("Legacy PDF generation error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal Server Error")
