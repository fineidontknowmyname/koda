"""
core/scheduler.py
-----------------
Split-based workout scheduler.

Replaces the hardcoded Monday / Wednesday / Friday round-robin in the
orchestrator with a configurable template that distributes scored exercises
across named training days according to the chosen split style.

Supported splits
────────────────
  FULL_BODY       3 days/week — each day trains every major muscle group.
  UPPER_LOWER     4 days/week — alternates upper-body and lower-body days.
  PUSH_PULL_LEGS  6 days/week (classic PPL) — push / pull / legs each twice.
  CUSTOM          Caller provides an explicit list of DayTemplate objects.

How sessions are built
─────────────────────
1. Exercises are pre-sorted by ExerciseScorer (caller should pass scored list).
2. Each DayTemplate declares which ``muscle_focus`` tags it targets.
3. Exercises whose ``muscles_worked`` contains any focus tag are routed to that
   day; remaining exercises are distributed round-robin.
4. Session duration is derived from exercise count and a per-set time estimate,
   then soft-capped by ``max_session_min``.
5. Capacity score scales the starting sets structure within each session.

Public API
──────────
scheduler.build_base_week(
    scored_exercises, user_profile, split=SplitType.FULL_BODY,
    capacity_score=1.0, custom_days=None
) -> WeeklySchedule
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence

from schemas.content import Exercise
from schemas.plan import WeeklySchedule, WorkoutSession, WorkoutExercise, WorkoutSet
from schemas.common import ExperienceLevel

# ScoredExercise is imported lazily to avoid circular import chains —
# the scheduler only needs .exercise from a ScoredExercise.


# ── Split types ───────────────────────────────────────────────────────────────

class SplitType(str, Enum):
    full_body       = "full_body"
    upper_lower     = "upper_lower"
    push_pull_legs  = "push_pull_legs"
    custom          = "custom"


# ── Day template ──────────────────────────────────────────────────────────────

@dataclass
class DayTemplate:
    """
    Blueprint for a single training day.

    Attributes
    ----------
    day_name        Human-readable name, e.g. "Monday", "Push Day".
    muscle_focus    Muscle-group keywords to route exercises to this day.
                    Case-insensitive substring match against muscles_worked.
                    Empty → accepts any exercise (used for full-body days).
    max_exercises   Hard cap on exercises per session.
    is_rest         If True this day is a rest day (no exercises assigned).
    """
    day_name:      str
    muscle_focus:  List[str] = field(default_factory=list)
    max_exercises: int = 6
    is_rest:       bool = False


# ── Built-in split templates ──────────────────────────────────────────────────

_FULL_BODY_DAYS: list[DayTemplate] = [
    DayTemplate("Monday",    muscle_focus=[], max_exercises=7),
    DayTemplate("Tuesday",   is_rest=True, day_name="Tuesday (Rest)"),
    DayTemplate("Wednesday", muscle_focus=[], max_exercises=7),
    DayTemplate("Thursday",  is_rest=True, day_name="Thursday (Rest)"),
    DayTemplate("Friday",    muscle_focus=[], max_exercises=7),
    DayTemplate("Saturday",  is_rest=True, day_name="Saturday (Rest)"),
    DayTemplate("Sunday",    is_rest=True, day_name="Sunday (Rest)"),
]

_UPPER_LOWER_DAYS: list[DayTemplate] = [
    DayTemplate("Monday (Upper)",    muscle_focus=["chest", "back", "shoulder", "bicep", "tricep"], max_exercises=6),
    DayTemplate("Tuesday (Lower)",   muscle_focus=["quad", "hamstring", "glute", "calf", "leg"],    max_exercises=6),
    DayTemplate("Wednesday (Rest)",  is_rest=True, day_name="Wednesday (Rest)"),
    DayTemplate("Thursday (Upper)",  muscle_focus=["chest", "back", "shoulder", "bicep", "tricep"], max_exercises=6),
    DayTemplate("Friday (Lower)",    muscle_focus=["quad", "hamstring", "glute", "calf", "leg"],    max_exercises=6),
    DayTemplate("Saturday (Rest)",   is_rest=True, day_name="Saturday (Rest)"),
    DayTemplate("Sunday (Rest)",     is_rest=True, day_name="Sunday (Rest)"),
]

_PUSH_PULL_LEGS_DAYS: list[DayTemplate] = [
    DayTemplate("Monday (Push A)",    muscle_focus=["chest", "shoulder", "tricep"],              max_exercises=6),
    DayTemplate("Tuesday (Pull A)",   muscle_focus=["back", "bicep", "rear delt"],               max_exercises=6),
    DayTemplate("Wednesday (Legs A)", muscle_focus=["quad", "hamstring", "glute", "calf"],       max_exercises=6),
    DayTemplate("Thursday (Push B)",  muscle_focus=["chest", "shoulder", "tricep"],              max_exercises=6),
    DayTemplate("Friday (Pull B)",    muscle_focus=["back", "bicep", "rear delt"],               max_exercises=6),
    DayTemplate("Saturday (Legs B)",  muscle_focus=["quad", "hamstring", "glute", "calf"],       max_exercises=6),
    DayTemplate("Sunday (Rest)",      is_rest=True, day_name="Sunday (Rest)"),
]

_SPLIT_TEMPLATES: dict[SplitType, list[DayTemplate]] = {
    SplitType.full_body:      _FULL_BODY_DAYS,
    SplitType.upper_lower:    _UPPER_LOWER_DAYS,
    SplitType.push_pull_legs: _PUSH_PULL_LEGS_DAYS,
}

# ── Per-set time estimates (seconds) ─────────────────────────────────────────

_SECONDS_PER_SET = 45      # avg work time
_REST_PER_SET    = 60      # avg rest between sets
_TIME_PER_SET    = (_SECONDS_PER_SET + _REST_PER_SET) / 60   # → 1.75 min/set

_MAX_SESSION_MIN = 90      # hard ceiling regardless of exercise count

# ── Sets-per-exercise by experience level ─────────────────────────────────────

_SETS_BY_LEVEL: dict[ExperienceLevel, int] = {
    ExperienceLevel.beginner:     2,
    ExperienceLevel.intermediate: 3,
    ExperienceLevel.advanced:     4,
}


# ── Engine ─────────────────────────────────────────────────────────────────────

class SchedulerEngine:
    """
    Build a WeeklySchedule from a ranked exercise list and a split template.

    The scheduler is the single source of truth for:
    - which day gets which exercises (via muscle-focus routing)
    - how many sets per exercise (from experience level + capacity nudge)
    - session duration estimate
    """

    def build_base_week(
        self,
        scored_exercises: Sequence,   # List[ScoredExercise] or List[Exercise]
        experience_level: ExperienceLevel,
        split: SplitType = SplitType.full_body,
        capacity_score: float = 1.0,
        custom_days: Optional[List[DayTemplate]] = None,
    ) -> WeeklySchedule:
        """
        Parameters
        ----------
        scored_exercises
                    Best-first ranked exercises (ScoredExercise or plain
                    Exercise objects; the .exercise attribute is used when
                    present, otherwise the object itself is treated as Exercise).
        experience_level
                    Determines the baseline sets-per-exercise.
        split       Split style; ignored when custom_days is provided.
        capacity_score
                    CapacityEngine output [0.50, 1.50] — adds up to +1 extra
                    set for very advanced users (score ≥ 1.30).
        custom_days List of DayTemplate objects when split=CUSTOM.

        Returns
        -------
        WeeklySchedule  week_number=1 base week ready for ProgressionEngine.
        """
        exercises = self._unwrap(scored_exercises)

        if split == SplitType.custom or custom_days is not None:
            templates = custom_days or []
        else:
            templates = _SPLIT_TEMPLATES.get(split, _FULL_BODY_DAYS)

        training_days = [t for t in templates if not t.is_rest]
        sets_per_ex   = self._sets_count(experience_level, capacity_score)

        # Route exercises to days
        day_exercise_map: dict[str, List[Exercise]] = {
            t.day_name: [] for t in training_days
        }
        unrouted: List[Exercise] = []

        for ex in exercises:
            routed = False
            for tmpl in training_days:
                if not tmpl.muscle_focus:
                    continue   # full-body days handled in round-robin below
                if self._matches_focus(ex, tmpl.muscle_focus):
                    bucket = day_exercise_map[tmpl.day_name]
                    if len(bucket) < tmpl.max_exercises:
                        bucket.append(ex)
                        routed = True
                        break
            if not routed:
                unrouted.append(ex)

        # Round-robin unrouted (or all, for full-body) exercises across days
        full_body_days = [t for t in training_days if not t.muscle_focus]
        target_days    = full_body_days or training_days   # fallback

        for idx, ex in enumerate(unrouted):
            tmpl  = target_days[idx % len(target_days)]
            bucket = day_exercise_map[tmpl.day_name]
            if len(bucket) < tmpl.max_exercises:
                bucket.append(ex)

        # Build WorkoutSession objects
        sessions: List[WorkoutSession] = []
        for tmpl in training_days:
            day_exercises = day_exercise_map.get(tmpl.day_name, [])
            if not day_exercises:
                continue   # skip empty training days

            workout_exercises = [
                WorkoutExercise(
                    exercise=ex,
                    sets=[
                        WorkoutSet(reps=10, weight_kg=0.0, rest_sec=60)
                        for _ in range(sets_per_ex)
                    ],
                )
                for ex in day_exercises
            ]

            duration = self._estimate_duration(len(day_exercises), sets_per_ex)

            sessions.append(WorkoutSession(
                day_name=tmpl.day_name,
                exercises=workout_exercises,
                duration_min=duration,
            ))

        if not sessions:
            raise ValueError(
                f"Scheduler produced zero sessions for split={split.value}. "
                "Ensure exercises are available after scoring and safety filtering."
            )

        return WeeklySchedule(week_number=1, sessions=sessions)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _unwrap(scored_exercises: Sequence) -> List[Exercise]:
        """Accept both ScoredExercise wrappers and plain Exercise objects."""
        result = []
        for item in scored_exercises:
            if hasattr(item, "exercise"):
                result.append(item.exercise)
            else:
                result.append(item)
        return result

    @staticmethod
    def _sets_count(level: ExperienceLevel, capacity_score: float) -> int:
        """
        Base sets from experience level + a +1 bonus for high capacity.
        Capped at 5 to keep sessions manageable.
        """
        base = _SETS_BY_LEVEL.get(level, 3)
        bonus = 1 if capacity_score >= 1.30 else 0
        return min(5, base + bonus)

    @staticmethod
    def _matches_focus(ex: Exercise, focus_tags: List[str]) -> bool:
        """
        True iff any muscle in the exercise overlaps with the day's focus tags
        (case-insensitive substring match).
        """
        muscles = [m.lower() for m in getattr(ex, "muscles_worked", [])]
        for tag in focus_tags:
            tag_lower = tag.lower()
            if any(tag_lower in m for m in muscles):
                return True
        return False

    @staticmethod
    def _estimate_duration(n_exercises: int, sets_per_ex: int) -> int:
        """
        Estimate session duration in whole minutes, capped at _MAX_SESSION_MIN.
        Adds a 10-min warm-up/cool-down buffer.
        """
        total_sets = n_exercises * sets_per_ex
        raw_min    = total_sets * _TIME_PER_SET + 10   # 10 min buffer
        return max(5, min(_MAX_SESSION_MIN, int(raw_min)))


# Module-level singleton
scheduler = SchedulerEngine()
