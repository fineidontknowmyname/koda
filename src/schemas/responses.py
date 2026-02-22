"""
schemas/responses.py
--------------------
Standardised HTTP response envelopes returned by all Koda API endpoints.

Three dedicated response models are defined here:

  • JobResponse            — immediate acknowledgement when an async job is queued
  • JobStatusResponse      — polling response for a running / completed / failed job
  • BodyCompositionResponse — result of the Gemini vision body-composition analysis
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from schemas.common import MuscleLevel, BodyType
from schemas.plan import JobStatus


# ── Async Job Responses ────────────────────────────────────────────────────────

class JobResponse(BaseModel):
    """
    Returned immediately (HTTP 202) when an async plan-generation job is
    dispatched to Celery.  The client should store ``job_id`` and start
    polling ``GET /plans/job/{job_id}``.
    """

    job_id: str = Field(
        description="Celery task ID — use this to poll for results"
    )
    status: JobStatus = Field(
        default=JobStatus.pending,
        description="Always 'pending' at dispatch time"
    )
    message: str = Field(
        default="Plan generation queued. Poll /plans/job/{job_id} for status.",
        description="Human-readable status hint"
    )


class JobStatusResponse(BaseModel):
    """
    Returned by ``GET /plans/job/{job_id}`` while polling for an async job.

    * ``status == 'pending'``  → job is queued but not yet started
    * ``status == 'running'``  → worker is actively processing
    * ``status == 'done'``     → ``result`` contains the serialised FitnessPlan
    * ``status == 'failed'``   → ``error`` contains the failure detail
    """

    job_id: str = Field(description="Celery task ID")
    status: JobStatus = Field(description="Current state of the async job")
    result: Optional[Any] = Field(
        default=None,
        description=(
            "Populated with FitnessPlan JSON when status='done'; "
            "None otherwise"
        ),
    )
    error: Optional[str] = Field(
        default=None,
        description="Error detail when status='failed'; None otherwise"
    )


# ── Vision / Body-Composition Response ────────────────────────────────────────

class BodyCompositionResponse(BaseModel):
    """
    HTTP response envelope wrapping the Gemini vision body-composition
    analysis.  Returned by ``POST /vision/analyze``.

    Fat percentage is expressed as a low/high range to reflect the inherent
    uncertainty of a visual estimate.  All fields are optional so that a
    partial or low-confidence response is still well-formed.
    """

    # ── Validity & Confidence ─────────────────────────────────────────────────
    is_valid_person: bool = Field(
        default=True,
        description="False when no clear full-body shot was detected in the image"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Overall model confidence in this analysis (0 = low, 1 = high)"
    )

    # ── Body Fat Estimate ─────────────────────────────────────────────────────
    fat_pct_low: Optional[float] = Field(
        default=None, ge=2.0, le=60.0,
        description="Lower bound of estimated body fat percentage"
    )
    fat_pct_high: Optional[float] = Field(
        default=None, ge=2.0, le=60.0,
        description="Upper bound of estimated body fat percentage"
    )

    # ── Qualitative Assessments ───────────────────────────────────────────────
    muscle_level: Optional[MuscleLevel] = Field(
        default=None,
        description="Estimated muscle mass level: low | moderate | high | very_high"
    )
    body_type: Optional[BodyType] = Field(
        default=None,
        description="Estimated somatotype: ectomorph | mesomorph | endomorph"
    )

    # ── Structural Ratios ─────────────────────────────────────────────────────
    v_taper_ratio: Optional[float] = Field(
        default=None, ge=0.5, le=3.0,
        description="Estimated shoulder-width / waist-width ratio (V-taper)"
    )

    # ── Posture ───────────────────────────────────────────────────────────────
    posture_assessment: Optional[str] = Field(
        default=None, max_length=200,
        description="Brief posture note e.g. 'Slight anterior pelvic tilt'"
    )

    # ── Narrative ─────────────────────────────────────────────────────────────
    summary: Optional[str] = Field(
        default=None, max_length=500,
        description="One-paragraph plain-English summary of the analysis"
    )
