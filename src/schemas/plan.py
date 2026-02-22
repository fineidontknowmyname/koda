from typing import List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, model_validator
from schemas.content import Exercise
from schemas.metrics import BodyMetrics

# ── Workout Plan ──────────────────────────────────────────────────────────────

class WorkoutSet(BaseModel):
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0.0, le=500.0, default=0.0)
    rest_sec: int = Field(ge=0, le=300, default=60)
    notes: Optional[str] = None

class WorkoutExercise(BaseModel):
    exercise: Exercise
    sets: List[WorkoutSet] = Field(min_length=1)

class WorkoutSession(BaseModel):
    day_name: str = Field(description="e.g. 'Monday', 'Day 1'")
    exercises: List[WorkoutExercise] = Field(default_factory=list)
    duration_min: int = Field(ge=5, le=180)

class WeeklySchedule(BaseModel):
    week_number: int = Field(ge=1, le=52)
    sessions: List[WorkoutSession] = Field(min_length=1, max_length=7)

from schemas.vision import BodyComposition

class FitnessPlan(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    weeks: List[WeeklySchedule] = Field(min_length=1, max_length=12)
    # ── Enrichment (populated by orchestrator; optional so backward compat is preserved)
    body_metrics: Optional[BodyMetrics] = Field(
        default=None,
        description="Computed TDEE / macro targets for this plan"
    )
    diet_notes: Optional[str] = Field(
        default=None, max_length=2000,
        description="Gemini-extracted diet guidance from diet-classified videos"
    )
    body_composition: Optional[BodyComposition] = Field(
        default=None,
        description="Vision-derived body composition including SWR analysis"
    )

# ── Request ───────────────────────────────────────────────────────────────────

from schemas.user import UserProfile

class GeneratePlanRequest(BaseModel):
    user_profile: UserProfile

    # ── Multi-URL support ──────────────────────────────────────────────────────
    youtube_urls: Optional[List[str]] = Field(
        default=None,
        description="One or more YouTube video URLs (workout, diet, motivation, etc.)"
    )
    # Deprecated single-URL alias — kept for backward compat with existing API routes
    youtube_url: Optional[str] = Field(
        default=None,
        description="[Deprecated] Single YouTube URL; prefer youtube_urls."
    )
    transcript_text: Optional[str] = Field(
        default=None,
        description="Direct transcript text (used if no URLs are provided)"
    )

    @model_validator(mode="after")
    def _coerce_single_url(self) -> "GeneratePlanRequest":
        """Merge legacy youtube_url into youtube_urls so the orchestrator sees one list."""
        if self.youtube_url and not self.youtube_urls:
            self.youtube_urls = [self.youtube_url]
        return self

# ── Async Job (Celery) ────────────────────────────────────────────────────────

class JobStatus(str, Enum):
    pending  = "pending"   # task queued, not started
    running  = "running"   # worker has picked it up
    done     = "done"      # completed successfully
    failed   = "failed"    # terminated with error

class JobResponse(BaseModel):
    """Returned immediately when an async plan generation is dispatched."""
    job_id: str = Field(description="Celery task ID — use this to poll for results")
    status: JobStatus = JobStatus.pending
    message: str = Field(default="Plan generation queued. Poll /plans/job/{job_id} for status.")

class JobStatusResponse(BaseModel):
    """Returned when polling GET /plans/job/{job_id}."""
    job_id: str
    status: JobStatus
    result: Optional[Any] = Field(
        None,
        description="Populated with FitnessPlan JSON when status=done, error string when status=failed"
    )
    error: Optional[str] = Field(None, description="Error detail if status=failed")
