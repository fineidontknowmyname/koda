"""
core/orchestrator.py
--------------------
End-to-end plan generation pipeline.

Sync entry-point  → ``generate_plan(...)``  (coroutine, returns FitnessPlan)
Async entry-point → ``generate_plan_async(request)``  (returns JobResponse,
                    dispatches to Celery worker)

Pipeline stages
───────────────
  0. Resolve transcripts  — fetch multi-URL YouTube transcripts concurrently
  1. Classify videos      — Gemini labels each URL: workout|diet|motivation|general
  2. Extract exercises    — Gemini extracts ExerciseLibrary from workout transcripts
  3. Safety filter        — drop exercises that conflict with injuries / missing equipment
  4. Capacity score       — enriched by activity hours + BMI + muscle level (new capacity engine)
  5. BodyMetrics          — compute BMR / TDEE / macros from UserProfile
  6. Diet pipeline        — Gemini extracts diet guidance from diet-classified transcripts
  7. Build template       — round-robin exercise distribution across Mon / Wed / Fri
  8. Apply progression    — 4-week progressive overload via ProgressionEngine
"""

from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from schemas.user import UserProfile
from schemas.metrics import BodyMetrics
from schemas.plan import (
    FitnessPlan,
    GeneratePlanRequest,
    JobResponse,
    JobStatus,
    WeeklySchedule,
    WorkoutExercise,
    WorkoutSession,
    WorkoutSet,
)
from schemas.vision import BodyComposition
from schemas.common import ActivityLevel

from integrations.ollama_client import ollama_client
from core.capacity import capacity_engine
from core.safety import safety_engine
from core.progression import progression_engine
from services.intelligence.youtube import youtube_service

log = logging.getLogger(__name__)

# ── Video classification labels ───────────────────────────────────────────────
_WORKOUT_LABEL  = "workout"
_DIET_LABEL     = "diet"

# ── TDEE / macro constants ────────────────────────────────────────────────────
# Activity multipliers aligned with ActivityLevel enum
_PAL: dict[ActivityLevel, float] = {
    ActivityLevel.sedentary:          1.20,
    ActivityLevel.lightly_active:     1.375,
    ActivityLevel.moderately_active:  1.55,
    ActivityLevel.very_active:        1.725,
    ActivityLevel.extra_active:       1.90,
}

# Goal-based calorie adjustments (applied to TDEE)
_GOAL_DELTA: dict[str, float] = {
    "weight_loss":       -500.0,
    "muscle_gain":       +300.0,
    "strength_gain":     +200.0,
    "endurance_gain":      0.0,
    "flexibility_gain":    0.0,
    "general_fitness":     0.0,
}


# ── Orchestrator ──────────────────────────────────────────────────────────────

class PlanOrchestrator:
    """
    Coordinates all pipeline stages to produce a complete FitnessPlan.

    Usage (sync / test)
    -------------------
    plan = await plan_orchestrator.generate_plan(
        user_profile   = ...,
        youtube_urls   = ["https://youtu.be/..."],
        transcript_text = None,
    )

    Usage (async / HTTP)
    --------------------
    job = await plan_orchestrator.generate_plan_async(request)
    # → JobResponse(job_id=..., status=pending)
    """

    # ── Public API ─────────────────────────────────────────────────────────────

    async def generate_plan(
        self,
        user_profile: UserProfile,
        youtube_urls: Optional[List[str]] = None,
        transcript_text: Optional[str] = None,
        body_composition: Optional[BodyComposition] = None,
    ) -> FitnessPlan:
        """
        Full synchronous pipeline. Returns a complete FitnessPlan.

        Parameters
        ----------
        user_profile
            Validated UserProfile (biometrics, metrics, goals, equipment …).
        youtube_urls
            Zero or more YouTube URLs. URLs are classified and fetched
            concurrently.  At least one URL *or* ``transcript_text`` is required.
        transcript_text
            Pre-fetched transcript text (used when no URLs are given or as a
            supplement).
        body_composition
            Optional Gemini vision result — forwarded to CapacityEngine for
            the muscle-level bonus.
        """
        youtube_urls = youtube_urls or []

        # ── Stage 0: resolve multi-URL transcripts ────────────────────────────
        url_transcript_map = await self._fetch_transcripts(youtube_urls)

        # Merge all text into one document for exercise extraction
        all_transcripts = list(url_transcript_map.values())
        if transcript_text:
            all_transcripts.append(transcript_text)

        if not all_transcripts:
            raise ValueError(
                "No content provided. Supply at least one YouTube URL or transcript_text."
            )

        # ── Stage 1: classify videos ──────────────────────────────────────────
        classifications = await self._classify_videos(url_transcript_map)
        log.info("Video classifications: %s", classifications)

        workout_text = self._collect_by_label(
            url_transcript_map, classifications, _WORKOUT_LABEL,
            fallback=transcript_text,
        )
        diet_transcripts = self._collect_by_label(
            url_transcript_map, classifications, _DIET_LABEL,
        )

        # ── Stage 2: extract exercises ────────────────────────────────────────
        if not workout_text:
            # Use the full merged corpus as a fallback
            workout_text = " ".join(all_transcripts)

        exercise_lib = await ollama_client.extract_exercises(workout_text)
        log.info("Extracted %d exercises", len(exercise_lib.exercises))

        # ── Stage 3: safety filter ────────────────────────────────────────────
        safe_exercises = safety_engine.filter_exercises(
            exercise_lib.exercises,
            user_profile.injuries,
            user_profile.equipment,
        )
        if not safe_exercises:
            raise ValueError(
                "No safe exercises found after filtering for injuries and equipment."
            )

        # ── Stage 4: capacity score ────────────────────────────────────────────
        capacity_score = capacity_engine.calculate_score(
            user_metrics=user_profile.biometrics,
            strength_metrics=user_profile.metrics,
            physical_activity=user_profile.physical_activity,
            body_composition=body_composition,
        )
        log.info("Capacity score: %.4f", capacity_score)

        # ── Stage 5: BodyMetrics ──────────────────────────────────────────────
        body_metrics = self._compute_body_metrics(user_profile, capacity_score)

        # ── Stage 6: diet pipeline ────────────────────────────────────────────
        diet_notes: Optional[str] = None
        if diet_transcripts:
            diet_notes = await self._extract_diet_guidance(diet_transcripts)
            log.info("Diet notes extracted (%d chars)", len(diet_notes or ""))

        # ── Stage 7: build base template ─────────────────────────────────────
        base_week = self._build_base_week(safe_exercises)

        # ── Stage 8: apply progression ────────────────────────────────────────
        weeks = progression_engine.apply_progression(
            base_week, total_weeks=4, capacity_score=capacity_score
        )

        return FitnessPlan(
            title=f"Koda 4-Week Plan — {user_profile.fitness_goal.value.replace('_', ' ').title()}",
            weeks=weeks,
            body_metrics=body_metrics,
            diet_notes=diet_notes,
        )

    async def generate_plan_async(self, request: GeneratePlanRequest) -> JobResponse:
        """
        Dispatch plan generation to a Celery worker and return immediately.

        Returns
        -------
        JobResponse
            Contains the Celery ``job_id`` and ``status=pending``.
        """
        from tasks.plan_tasks import generate_plan_task  # deferred — Celery optional

        task = generate_plan_task.delay(request.model_dump())
        log.info("Dispatched plan generation task  job_id=%s", task.id)

        return JobResponse(
            job_id=task.id,
            status=JobStatus.pending,
            message=f"Plan generation queued. Poll /plans/job/{task.id} for status.",
        )

    # ── Stage helpers ──────────────────────────────────────────────────────────

    async def _fetch_transcripts(
        self, urls: List[str]
    ) -> dict[str, str]:
        """
        Concurrently fetch transcripts for every URL via youtube_service.fetch_many.

        The token guard (12 000 chars) is applied inside fetch_many so each
        transcript is already budget-safe when it arrives here.
        Returns a dict mapping url → transcript_text; failed URLs are skipped.
        """
        return await youtube_service.fetch_many(urls, skip_failed=True)

    async def _classify_videos(
        self, url_transcript_map: dict[str, str]
    ) -> dict[str, str]:
        """
        Ask Gemini to classify each transcript as one of:
        workout | diet | motivation | general

        Returns a dict mapping ``url → label``.
        Falls back to ``"general"`` on error.
        """
        if not url_transcript_map:
            return {}

        async def _classify_one(url: str, text: str) -> tuple[str, str]:
            try:
                from services.intelligence.summarizer import summarizer_service
                category = await summarizer_service.classify_video(text)
                return url, category.value
            except Exception as exc:
                log.warning("Classification failed for %s: %s", url, exc)
                return url, "general"

        results = await asyncio.gather(
            *[_classify_one(u, t) for u, t in url_transcript_map.items()]
        )
        return dict(results)

    def _collect_by_label(
        self,
        url_transcript_map: dict[str, str],
        classifications: dict[str, str],
        label: str,
        fallback: Optional[str] = None,
    ) -> Optional[str]:
        """
        Concatenate transcripts for URLs that match ``label``.
        Returns ``fallback`` when no URLs match.
        """
        parts = [
            url_transcript_map[url]
            for url, lbl in classifications.items()
            if lbl == label and url in url_transcript_map
        ]
        if parts:
            return " ".join(parts)
        return fallback

    def _compute_body_metrics(
        self, user_profile: UserProfile, capacity_score: float
    ) -> BodyMetrics:
        """
        Derive TDEE, macros, and ideal weight from UserProfile using
        Mifflin-St Jeor BMR + PAL factor.
        """
        bio  = user_profile.biometrics
        goal = user_profile.fitness_goal.value

        # ── BMR (Mifflin-St Jeor) ──────────────────────────────────────────────
        if bio.gender.value == "male":
            bmr = (10.0 * bio.weight_kg) + (6.25 * bio.height_cm) - (5.0 * bio.age) + 5.0
        else:
            bmr = (10.0 * bio.weight_kg) + (6.25 * bio.height_cm) - (5.0 * bio.age) - 161.0

        # ── Activity multiplier ────────────────────────────────────────────────
        activity_multiplier = _PAL.get(
            user_profile.physical_activity.activity_level,
            1.375,
        )
        tdee = bmr * activity_multiplier

        # ── Goal-based calorie target ──────────────────────────────────────────
        delta = _GOAL_DELTA.get(goal, 0.0)
        calorie_target = max(1200.0, tdee + delta)

        # ── Macros ─────────────────────────────────────────────────────────────
        # Protein: 1.6–2.2 g/kg based on goal; capacity score nudges the upper end
        protein_factor = 1.6 + (0.6 * (capacity_score - 0.5))   # 1.6 @ score=0.5 → 2.2 @ score=1.5
        protein_g = round(max(50.0, bio.weight_kg * protein_factor), 1)

        fat_g    = round(calorie_target * 0.25 / 9.0, 1)  # 25 % of calories from fat
        carbs_g  = round(
            (calorie_target - (protein_g * 4.0) - (fat_g * 9.0)) / 4.0, 1
        )
        carbs_g  = max(0.0, carbs_g)

        # ── Ideal weight (Devine formula) ──────────────────────────────────────
        height_over_152 = max(0.0, bio.height_cm - 152.4)
        if bio.gender.value == "male":
            ideal_weight_kg = 50.0 + 2.3 * (height_over_152 / 2.54)
        else:
            ideal_weight_kg = 45.5 + 2.3 * (height_over_152 / 2.54)

        # ── BMI ────────────────────────────────────────────────────────────────
        height_m = bio.height_cm / 100.0
        bmi = bio.weight_kg / (height_m ** 2)

        return BodyMetrics(
            bmi=round(bmi, 2),
            ideal_weight_kg=round(ideal_weight_kg, 2),
            bmr=round(bmr, 2),
            activity_multiplier=round(activity_multiplier, 3),
            tdee=round(tdee, 2),
            calorie_target=round(calorie_target, 2),
            protein_g=protein_g,
            carbs_g=carbs_g,
            fat_g=fat_g,
            notes=f"Goal: {goal.replace('_', ' ')}; calorie delta {delta:+.0f} kcal applied to TDEE.",
        )

    async def _extract_diet_guidance(self, diet_text: str) -> str:
        """
        Ask Gemini to extract actionable diet guidance from diet-classified
        video transcripts.  Returns a plain-English summary string.
        """
        snippet = diet_text[:30000]
        prompt = (
            "You are a certified nutritionist reviewing a fitness video transcript.\n"
            "Extract the most specific, actionable diet recommendations from the text below.\n"
            "Format as a concise list of bullet-points (max 10 bullets).\n"
            "Do NOT include general advice — only content explicitly mentioned in the transcript.\n\n"
            f"Transcript:\n{snippet}"
        )
        try:
            return await ollama_client.generate_text(prompt)
        except Exception as exc:
            log.warning("Diet guidance extraction failed: %s", exc)
            return ""

    def _build_base_week(self, safe_exercises: list) -> WeeklySchedule:
        """
        Distribute safe exercises across Monday / Wednesday / Friday using a
        round-robin chunk.  Each exercise gets 3 × 10-rep sets to start.
        """
        days = ["Monday", "Wednesday", "Friday"]
        chunk_size = max(1, len(safe_exercises) // 3)
        sessions: List[WorkoutSession] = []

        for i, day in enumerate(days):
            day_exercises = safe_exercises[i * chunk_size: (i + 1) * chunk_size]
            workout_exercises = [
                WorkoutExercise(
                    exercise=ex,
                    sets=[WorkoutSet(reps=10, weight_kg=10.0, rest_sec=60) for _ in range(3)],
                )
                for ex in day_exercises
            ]
            sessions.append(
                WorkoutSession(day_name=day, exercises=workout_exercises, duration_min=45)
            )

        return WeeklySchedule(week_number=1, sessions=sessions)


# Module-level singleton
plan_orchestrator = PlanOrchestrator()
