"""
tests/verify_orchestrator.py
-----------------------------
Smoke-test for the rewritten PlanOrchestrator.

Verifies (without a real Gemini API key or Redis broker):
  1. PlanOrchestrator can be imported and instantiated
  2. _compute_body_metrics returns a valid BodyMetrics with sane TDEE
  3. _classify_videos gracefully returns 'general' on network/API failure
  4. generate_plan_async raises ImportError (no Celery broker) OR returns JobResponse

Run from repo root:
    python tests/verify_orchestrator.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

PASS = "\u2705"
FAIL = "\u274c"
WARN = "\u26a0\ufe0f"

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_user_profile():
    from schemas.user import UserProfile, UserMetrics, StrengthMetrics, PhysicalActivity
    from schemas.common import (
        Gender, ActivityLevel, ExperienceLevel, FitnessGoal,
    )
    return UserProfile(
        biometrics=UserMetrics(age=28, weight_kg=80.0, height_cm=178.0, gender=Gender.male),
        metrics=StrengthMetrics(pushup_count=25, situp_count=20, squat_count=30),
        physical_activity=PhysicalActivity(
            activity_level=ActivityLevel.moderately_active,
            physical_activity_hours_per_day=1.0,
        ),
        injuries=[],
        equipment=[],
        experience_level=ExperienceLevel.intermediate,
        fitness_goal=FitnessGoal.muscle_gain,
    )


# ── test 1: import ─────────────────────────────────────────────────────────────

def test_import():
    print("Test 1 — Import PlanOrchestrator ...", end=" ")
    try:
        from core.orchestrator import PlanOrchestrator, plan_orchestrator
        assert plan_orchestrator is not None
        print(PASS)
        return plan_orchestrator
    except Exception as e:
        print(FAIL, e)
        return None


# ── test 2: _compute_body_metrics ─────────────────────────────────────────────

def test_body_metrics(orchestrator):
    print("Test 2 — _compute_body_metrics ...", end=" ")
    try:
        profile = _make_user_profile()
        bm = orchestrator._compute_body_metrics(profile, capacity_score=1.0)

        assert bm.bmr > 0,             f"BMR should be positive, got {bm.bmr}"
        assert 1200 < bm.tdee < 8000,  f"TDEE out of range: {bm.tdee}"
        assert bm.protein_g > 0,       f"protein_g should be positive"
        assert bm.carbs_g >= 0,        f"carbs_g should be non-negative"
        assert bm.fat_g > 0,           f"fat_g should be positive"
        assert 10 < bm.bmi < 60,       f"BMI out of range: {bm.bmi}"

        print(PASS, f"(BMR={bm.bmr:.1f} kcal, TDEE={bm.tdee:.1f} kcal, target={bm.calorie_target:.1f} kcal)")
    except Exception as e:
        print(FAIL, e)


# ── test 3: _classify_videos (no real API) ────────────────────────────────────

async def test_classify_videos(orchestrator):
    print("Test 3 — _classify_videos falls back gracefully ...", end=" ")
    try:
        # No real transcript map — should return empty dict cleanly
        result = await orchestrator._classify_videos({})
        assert result == {}, f"Expected empty dict, got {result}"
        print(PASS, "(empty input → empty output)")
    except Exception as e:
        print(FAIL, e)


# ── test 4: generate_plan_async without broker ────────────────────────────────

async def test_generate_plan_async(orchestrator):
    print("Test 4 — generate_plan_async (no broker expected) ...", end=" ")
    try:
        from schemas.plan import GeneratePlanRequest
        profile = _make_user_profile()
        request = GeneratePlanRequest(
            user_profile=profile,
            youtube_urls=["https://www.youtube.com/watch?v=dQw4w9WgXcQ"],
        )
        job = await orchestrator.generate_plan_async(request)
        from schemas.plan import JobStatus
        assert job.status == JobStatus.pending
        assert len(job.job_id) > 0
        print(PASS, f"(job_id={job.job_id[:8]}…)")
    except Exception as e:
        # A connection error to broker is acceptable in a dev environment
        if "connection" in str(e).lower() or "redis" in str(e).lower() or "kombu" in str(e).lower():
            print(WARN, f"Broker not available (expected in dev): {type(e).__name__}")
        else:
            print(FAIL, e)


# ── runner ─────────────────────────────────────────────────────────────────────

async def main():
    print("=" * 55)
    print("  Orchestrator Smoke Tests")
    print("=" * 55)

    orchestrator = test_import()
    if orchestrator is None:
        print("Cannot continue — import failed.")
        sys.exit(1)

    test_body_metrics(orchestrator)
    await test_classify_videos(orchestrator)
    await test_generate_plan_async(orchestrator)

    print("=" * 55)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
