"""
core/exercise_scorer.py
-----------------------
Score and rank every exercise in a master pool so the orchestrator can
cherry-pick only the best-fit movements for a given user.

The 5 scoring factors
──────────────────────
  1. Difficulty match    — penalty when exercise difficulty diverges from the
                           user's experience level.
  2. Equipment fit       — bonus for each piece of the user's equipment that
                           the exercise actually uses.
  3. Muscle coverage     — bonus for exercises that target multiple distinct
                           muscle groups (compound movements score higher).
  4. Goal alignment      — exercises that are semantically aligned with the
                           user's fitness goal receive a bonus.
  5. Safety headroom     — exercises with fewer / no safety warnings score
                           higher (lower risk).

Default weights sum to 1.0 so the final score lives in [0, 1].  Weights are
configurable via ``ExerciseScorer(weights=...)``.

Public API
──────────
exercise_scorer.score_and_rank(exercises, user_profile, top_n=None)
    -> List[ScoredExercise]          # descending by score
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from schemas.content import Exercise
from schemas.user import UserProfile
from schemas.common import ExperienceLevel, FitnessGoal, Equipment


# ── Experience level → numeric tier ───────────────────────────────────────────

_EXP_TIER: dict[ExperienceLevel, int] = {
    ExperienceLevel.beginner:     0,
    ExperienceLevel.intermediate: 1,
    ExperienceLevel.advanced:     2,
}

_DIFFICULTY_TIER: dict[str, int] = {
    "beginner":     0,
    "intermediate": 1,
    "advanced":     2,
}

# ── Goal → relevant keyword clusters ──────────────────────────────────────────
# These keyword sets are matched against exercise names, descriptions, and
# muscles_worked to determine semantic goal alignment.

_GOAL_KEYWORDS: dict[FitnessGoal, set[str]] = {
    FitnessGoal.weight_loss: {
        "cardio", "circuit", "hiit", "jump", "burpee", "metabolic",
        "interval", "sprint", "full body", "plyometric",
    },
    FitnessGoal.muscle_gain: {
        "press", "curl", "row", "pull", "push", "squat", "deadlift",
        "bench", "hypertrophy", "compound", "chest", "back", "bicep",
        "tricep", "shoulder", "leg",
    },
    FitnessGoal.strength_gain: {
        "deadlift", "squat", "bench", "overhead", "press", "clean",
        "snatch", "powerlifting", "compound", "heavy", "barbell",
    },
    FitnessGoal.endurance_gain: {
        "run", "jog", "cycle", "swim", "row", "cardio", "aerobic",
        "stamina", "long", "distance", "zone 2",
    },
    FitnessGoal.flexibility_gain: {
        "stretch", "yoga", "mobility", "hip flexor", "hamstring",
        "pigeon", "twist", "flex", "range of motion",
    },
    FitnessGoal.general_fitness: {
        "functional", "core", "balance", "stability", "mobility",
        "full body", "compound",
    },
}

# ── Default factor weights ─────────────────────────────────────────────────────

DEFAULT_WEIGHTS = {
    "difficulty_match": 0.30,
    "equipment_fit":    0.20,
    "muscle_coverage":  0.20,
    "goal_alignment":   0.20,
    "safety_headroom":  0.10,
}


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass(order=True)
class ScoredExercise:
    """
    An exercise paired with its composite score and individual factor scores.

    Attributes
    ----------
    score               Weighted composite score in [0, 1].  Higher is better.
    exercise            The original Exercise schema object.
    factor_scores       Dict of individual factor name → raw score (each in [0, 1]).
    """
    score: float = field(compare=True)
    exercise: Exercise = field(compare=False)
    factor_scores: dict[str, float] = field(compare=False, default_factory=dict)

    def __repr__(self) -> str:
        return f"ScoredExercise(score={self.score:.3f}, name={self.exercise.name!r})"


# ── Engine ─────────────────────────────────────────────────────────────────────

class ExerciseScorer:
    """
    Score a pool of exercises against a UserProfile and return a ranked list.

    Parameters
    ----------
    weights     Dict overriding one or more of the DEFAULT_WEIGHTS. Missing
                keys fall back to defaults.  Values are re-normalised so they
                always sum to 1.0.
    """

    def __init__(self, weights: Optional[dict[str, float]] = None):
        w = {**DEFAULT_WEIGHTS, **(weights or {})}
        total = sum(w.values()) or 1.0
        self.weights = {k: v / total for k, v in w.items()}

    # ── Public API ─────────────────────────────────────────────────────────────

    def score_and_rank(
        self,
        exercises: List[Exercise],
        user_profile: UserProfile,
        top_n: Optional[int] = None,
    ) -> List[ScoredExercise]:
        """
        Score every exercise and return them sorted best-first.

        Parameters
        ----------
        exercises       Master pool (post-safety-filter recommended).
        user_profile    Used for experience level, equipment, and goal.
        top_n           If given, return only the top N results.

        Returns
        -------
        List[ScoredExercise] sorted descending by composite score.
        """
        scored = [self._score_one(ex, user_profile) for ex in exercises]
        scored.sort(reverse=True)
        return scored[:top_n] if top_n is not None else scored

    # ── Per-exercise scoring ───────────────────────────────────────────────────

    def _score_one(self, ex: Exercise, profile: UserProfile) -> ScoredExercise:
        factors = {
            "difficulty_match": self._difficulty_match(ex, profile),
            "equipment_fit":    self._equipment_fit(ex, profile),
            "muscle_coverage":  self._muscle_coverage(ex),
            "goal_alignment":   self._goal_alignment(ex, profile.fitness_goal),
            "safety_headroom":  self._safety_headroom(ex),
        }
        composite = sum(self.weights[k] * v for k, v in factors.items())
        return ScoredExercise(
            score=round(composite, 4),
            exercise=ex,
            factor_scores={k: round(v, 4) for k, v in factors.items()},
        )

    # ── Factor implementations ─────────────────────────────────────────────────

    @staticmethod
    def _difficulty_match(ex: Exercise, profile: UserProfile) -> float:
        """
        Score 1.0 for an exact match, decreasing by 0.35 per tier of distance.
        A beginner given an advanced exercise scores 0.30; the reverse is 0.65
        (too-easy exercises are less harmful than too-hard ones).
        """
        user_tier = _EXP_TIER.get(profile.experience_level, 1)
        ex_tier   = _DIFFICULTY_TIER.get(
            getattr(ex, "difficulty", "intermediate").lower(), 1
        )
        diff = abs(user_tier - ex_tier)
        return max(0.0, 1.0 - diff * 0.35)

    @staticmethod
    def _equipment_fit(ex: Exercise, profile: UserProfile) -> float:
        """
        Ratio of the exercise's required equipment that the user actually owns.
        Bodyweight requirements are always satisfied (score +).
        Returns 1.0 when no equipment is needed (bodyweight only).
        """
        needed: List[Equipment] = getattr(ex, "equipment_needed", [])
        non_bw = [e for e in needed if e != Equipment.bodyweight]
        if not non_bw:
            return 1.0     # purely bodyweight — always achievable
        owned = set(profile.equipment)
        matched = sum(1 for e in non_bw if e in owned)
        return matched / len(non_bw)

    @staticmethod
    def _muscle_coverage(ex: Exercise) -> float:
        """
        Compound movements hit more muscles → higher score.
        Scores are mapped from muscle count using a soft-cap curve:
          1 muscle → 0.30
          2 muscles → 0.55
          3 muscles → 0.75
          4+ muscles → 0.90 (capped, isolation extremes not rewarded)
        """
        muscles: List[str] = getattr(ex, "muscles_worked", [])
        n = len(muscles)
        if n == 0:
            return 0.20
        elif n == 1:
            return 0.30
        elif n == 2:
            return 0.55
        elif n == 3:
            return 0.75
        else:
            return min(0.90, 0.75 + (n - 3) * 0.05)

    @staticmethod
    def _goal_alignment(ex: Exercise, goal: FitnessGoal) -> float:
        """
        Keyword intersection between exercise text and goal-specific keywords.
        Full match across multiple keywords → 1.0; no match → 0.0.
        """
        keywords = _GOAL_KEYWORDS.get(goal, set())
        if not keywords:
            return 0.5   # neutral when no keywords defined

        # Build a searchable text blob from the exercise
        blob = " ".join([
            ex.name,
            getattr(ex, "description", ""),
            " ".join(getattr(ex, "muscles_worked", [])),
        ]).lower()

        hits = sum(1 for kw in keywords if kw in blob)
        # Soft-cap: 3 keyword hits → full alignment score
        return min(1.0, hits / 3.0)

    @staticmethod
    def _safety_headroom(ex: Exercise) -> float:
        """
        Exercises with no safety warnings score 1.0.
        Each warning reduces by 0.20, floored at 0.20.
        """
        warnings: List[str] = getattr(ex, "safety_warnings", [])
        return max(0.20, 1.0 - len(warnings) * 0.20)


# Module-level singleton with default weights
exercise_scorer = ExerciseScorer()
