from typing import Optional
from schemas.user import UserMetrics, StrengthMetrics, PhysicalActivity, Gender
from schemas.vision import BodyComposition, SWRCategory
from schemas.common import MuscleLevel


# ── Lookup tables ──────────────────────────────────────────────────────────────

# Activity bonus: extra capacity credit for deliberate exercise hours per day.
# Each bracket raises the multiplier ceiling slightly.
_ACTIVITY_BONUS: list[tuple[float, float]] = [
    # (hours_per_day_threshold, bonus)
    (0.0,  0.00),   # sedentary  — no bonus
    (0.5,  0.03),   # light      — brief walks / stretching
    (1.0,  0.06),   # moderate   — ~1 h structured exercise
    (1.5,  0.09),   # active     — 1.5 h training
    (2.0,  0.12),   # very active— 2 h+ sport / lifting
]

# Muscle-level credit: higher visible muscle mass suggests greater work capacity.
_MUSCLE_BONUS: dict[MuscleLevel, float] = {
    MuscleLevel.low:       -0.05,
    MuscleLevel.moderate:   0.00,
    MuscleLevel.high:       0.07,
    MuscleLevel.very_high:  0.12,
}


# ── Engine ─────────────────────────────────────────────────────────────────────

class CapacityEngine:
    """
    Produces a capacity multiplier used to scale training volume / intensity.

    Score range   Interpretation
    ──────────────────────────────
    0.50 – 0.79   Beginner / deconditioned
    0.80 – 1.09   Intermediate
    1.10 – 1.50   Advanced / elite

    Three optional signal layers can enrich the base strength score:
      1. Activity bonus     — from deliberate exercise hours per day
      2. BMI adjustment     — penalises very low (<17) or very high (>30) BMI
      3. Muscle-level bonus — from Gemini vision body-composition analysis
    """

    # ── Public API ─────────────────────────────────────────────────────────────

    def calculate_score(
        self,
        user_metrics: UserMetrics,
        strength_metrics: StrengthMetrics,
        physical_activity: Optional[PhysicalActivity] = None,
        body_composition: Optional[BodyComposition] = None,
    ) -> float:
        """
        Parameters
        ----------
        user_metrics        Core biometrics (age, weight, height, gender).
        strength_metrics    Pushup / squat / run performance.
        physical_activity   Optional; provides exercise hours/day for activity bonus.
        body_composition    Optional; Gemini vision result for muscle-level bonus.

        Returns
        -------
        float in [0.50, 1.50]
        """
        raw_score = self._strength_score(user_metrics, strength_metrics)

        # ── Layer 1: activity bonus ────────────────────────────────────────────
        if physical_activity is not None:
            raw_score += self._activity_bonus(
                physical_activity.physical_activity_hours_per_day
            )

        # ── Layer 2: BMI adjustment ────────────────────────────────────────────
        raw_score += self._bmi_adjustment(user_metrics)

        # ── Layer 3: muscle-level bonus ────────────────────────────────────────
        if body_composition is not None:
            raw_score += self._muscle_bonus(body_composition)

        # ── Layer 4: SWR adjustment ───────────────────────────────────────────
        if body_composition is not None:
            raw_score += self._swr_adjustment(body_composition)

        # Clamp: 0.50 (beginner) → 1.50 (advanced)
        return round(max(0.50, min(raw_score, 1.50)), 4)

    # ── Private helpers ────────────────────────────────────────────────────────

    def _strength_score(
        self,
        user_metrics: UserMetrics,
        strength_metrics: StrengthMetrics,
    ) -> float:
        """Baseline score derived from pushup / squat / cardio ratios."""

        # Gender-specific pushup standard
        pushup_std = 20.0 if user_metrics.gender == Gender.male else 10.0
        squat_std  = 30.0

        # Age adjustment: over-40 standards relaxed by 20 %
        if user_metrics.age > 40:
            pushup_std *= 0.8
            squat_std  *= 0.8

        pushup_ratio = strength_metrics.pushup_count / max(pushup_std, 1.0)
        squat_ratio  = strength_metrics.squat_count  / max(squat_std,  1.0)

        # Cardio: standard 1 km in 6 min; faster → ratio > 1
        run_std = 6.0
        if strength_metrics.run_time_min and strength_metrics.run_time_min > 0:
            cardio_ratio = run_std / strength_metrics.run_time_min
        else:
            cardio_ratio = 1.0  # neutral if no run data

        return (pushup_ratio * 0.40) + (squat_ratio * 0.30) + (cardio_ratio * 0.30)

    def _activity_bonus(self, hours_per_day: float) -> float:
        """
        Stepped bonus for deliberate daily exercise hours.

        Hours / day    Bonus
        ─────────────────────
        < 0.5          +0.00
        0.5 – 0.99     +0.03
        1.0 – 1.49     +0.06
        1.5 – 1.99     +0.09
        ≥ 2.0          +0.12
        """
        bonus = 0.0
        for threshold, value in reversed(_ACTIVITY_BONUS):
            if hours_per_day >= threshold:
                bonus = value
                break
        return bonus

    def _bmi_adjustment(self, user_metrics: UserMetrics) -> float:
        """
        Penalise extreme BMI values that limit safe training capacity.

        BMI bucket         Adjustment
        ──────────────────────────────
        < 17  (underweight)  −0.10
        17–18.4              −0.05
        18.5–29.9  (normal)   0.00
        30–34.9  (obese I)   −0.05
        ≥ 35   (obese II+)   −0.10
        """
        height_m = user_metrics.height_cm / 100.0
        bmi = user_metrics.weight_kg / (height_m ** 2)

        if bmi < 17.0:
            return -0.10
        elif bmi < 18.5:
            return -0.05
        elif bmi < 30.0:
            return 0.00
        elif bmi < 35.0:
            return -0.05
        else:
            return -0.10

    def _muscle_bonus(self, body_composition: BodyComposition) -> float:
        """
        Translate Gemini-estimated muscle level into a capacity bonus / penalty.
        Returns 0.0 when muscle_level is unavailable or confidence is too low.
        """
        # Ignore low-confidence or invalid analyses
        if not body_composition.is_valid_person:
            return 0.0
        if body_composition.confidence < 0.40:
            return 0.0
        if body_composition.muscle_level is None:
            return 0.0

        return _MUSCLE_BONUS.get(body_composition.muscle_level, 0.0)

    def _swr_adjustment(self, body_composition: BodyComposition) -> float:
        """
        Adjustment based on Shoulder-to-Waist Ratio category.

        OVERFAT  → −0.05  (waist wider than shoulders — prioritise core/cardio)
        ATHLETIC → +0.05  (strong V-taper — higher work capacity assumed)
        BALANCED →  0.00
        """
        if not body_composition.is_valid_person:
            return 0.0
        cat = body_composition.swr_category
        if cat == SWRCategory.OVERFAT:
            return -0.05
        if cat == SWRCategory.ATHLETIC:
            return 0.05
        return 0.0

    @staticmethod
    def swr_weight_multiplier(body_composition: Optional[BodyComposition]) -> float:
        """
        Baseline-weight scaling factor derived from SWR.

        ATHLETIC → 1.1×  (user can handle heavier loads)
        Others   → 1.0×
        """
        if body_composition is None:
            return 1.0
        if body_composition.swr_category == SWRCategory.ATHLETIC:
            return 1.1
        return 1.0


# Module-level singleton for import convenience
capacity_engine = CapacityEngine()
