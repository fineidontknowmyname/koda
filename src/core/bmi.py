"""
core/bmi.py
-----------
BMI computation, WHO category classification, Devine ideal weight, and a
``PlanSignal`` that the orchestrator can use to adapt plan generation.

WHO BMI categories (adults ≥ 18)
──────────────────────────────────
< 16.0          Severe thinness
16.0 – 16.99    Moderate thinness
17.0 – 18.49    Mild thinness
18.5 – 24.99    Normal weight          ← green zone
25.0 – 29.99    Pre-obesity (overweight)
30.0 – 34.99    Obese class I
35.0 – 39.99    Obese class II
≥ 40.0          Obese class III

Ideal weight — Devine formula (1974)
─────────────────────────────────────
Male  : 50.0 kg + 2.3 kg per inch over 5 ft
Female: 45.5 kg + 2.3 kg per inch over 5 ft

PlanSignal
──────────
The engine maps each BMI category to one of three signals that the orchestrator
can act on:

  GREEN    — proceed normally
  CAUTION  — mild thinness / pre-obesity; note in plan, lighter starting loads
  WARNING  — anything more extreme; recommend medical consultation in plan notes

Public API
──────────
bmi_engine.compute(weight_kg, height_cm, gender) -> BMIResult
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from schemas.common import Gender


# ── WHO category enum ─────────────────────────────────────────────────────────

class BMICategory(str, Enum):
    severe_thinness    = "Severe thinness"
    moderate_thinness  = "Moderate thinness"
    mild_thinness      = "Mild thinness"
    normal             = "Normal weight"
    pre_obesity        = "Pre-obesity"
    obese_class_i      = "Obese class I"
    obese_class_ii     = "Obese class II"
    obese_class_iii    = "Obese class III"


# ── Plan signal enum ──────────────────────────────────────────────────────────

class PlanSignal(str, Enum):
    """
    Action signal derived from BMI category for use by the orchestrator.

    GREEN  : BMI is in a healthy range — generate plan without modifications.
    CAUTION: Mild deviation — generate plan but reduce starting loads / note risk.
    WARNING: Significant deviation — strongly recommend medical clearance in plan.
    """
    green   = "green"
    caution = "caution"
    warning = "warning"


# ── Category → PlanSignal map ─────────────────────────────────────────────────

_SIGNAL_MAP: dict[BMICategory, PlanSignal] = {
    BMICategory.severe_thinness:   PlanSignal.warning,
    BMICategory.moderate_thinness: PlanSignal.warning,
    BMICategory.mild_thinness:     PlanSignal.caution,
    BMICategory.normal:            PlanSignal.green,
    BMICategory.pre_obesity:       PlanSignal.caution,
    BMICategory.obese_class_i:     PlanSignal.caution,
    BMICategory.obese_class_ii:    PlanSignal.warning,
    BMICategory.obese_class_iii:   PlanSignal.warning,
}

# ── Advisory notes per signal ─────────────────────────────────────────────────

_SIGNAL_NOTES: dict[PlanSignal, str] = {
    PlanSignal.green: (
        "BMI is within the healthy range. No adjustments required."
    ),
    PlanSignal.caution: (
        "BMI is outside the optimal range. Starting loads have been kept "
        "conservative. Monitor progress and consult a healthcare professional "
        "if unsure."
    ),
    PlanSignal.warning: (
        "BMI indicates a significant health deviation. It is strongly recommended "
        "to seek medical clearance before beginning this training programme."
    ),
}


# ── WHo category thresholds ───────────────────────────────────────────────────
# Stored as (upper_exclusive_bound, BMICategory) sorted ascending.

_THRESHOLDS: list[tuple[float, BMICategory]] = [
    (16.00, BMICategory.severe_thinness),
    (17.00, BMICategory.moderate_thinness),
    (18.50, BMICategory.mild_thinness),
    (25.00, BMICategory.normal),
    (30.00, BMICategory.pre_obesity),
    (35.00, BMICategory.obese_class_i),
    (40.00, BMICategory.obese_class_ii),
    (float("inf"), BMICategory.obese_class_iii),
]


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class BMIResult:
    """
    Output of BMIEngine.compute().

    Attributes
    ----------
    bmi              Body Mass Index (weight_kg / height_m²).
    category         WHO category string.
    ideal_weight_kg  Devine formula ideal weight in kg.
    weight_delta_kg  Difference from ideal (negative = underweight vs. ideal).
    plan_signal      GREEN / CAUTION / WARNING signal for plan generation.
    advisory         Human-readable recommendation derived from plan_signal.
    """
    bmi:              float
    category:         BMICategory
    ideal_weight_kg:  float
    weight_delta_kg:  float      # current_weight − ideal (positive = above ideal)
    plan_signal:      PlanSignal
    advisory:         str


# ── Engine ─────────────────────────────────────────────────────────────────────

class BMIEngine:
    """
    Derive BMI, WHO category, Devine ideal weight, and a plan signal.

    Thread-safe / async-safe — all methods are pure functions with no
    mutable state.
    """

    def compute(
        self,
        weight_kg: float,
        height_cm: float,
        gender: Gender,
    ) -> BMIResult:
        """
        Parameters
        ----------
        weight_kg   User's body weight in kilograms.
        height_cm   User's height in centimetres.
        gender      Gender enum (male | female) — used for Devine formula.

        Returns
        -------
        BMIResult   Full breakdown ready for orchestrator / plan enrichment.
        """
        bmi = self._bmi(weight_kg, height_cm)
        category = self._category(bmi)
        ideal = self._ideal_weight(height_cm, gender)
        delta = round(weight_kg - ideal, 2)
        signal = _SIGNAL_MAP[category]
        advisory = _SIGNAL_NOTES[signal]

        return BMIResult(
            bmi=round(bmi, 2),
            category=category,
            ideal_weight_kg=round(ideal, 2),
            weight_delta_kg=delta,
            plan_signal=signal,
            advisory=advisory,
        )

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _bmi(weight_kg: float, height_cm: float) -> float:
        """BMI = weight_kg / height_m²."""
        height_m = height_cm / 100.0
        if height_m <= 0:
            raise ValueError(f"height_cm must be positive, got {height_cm}")
        return weight_kg / (height_m ** 2)

    @staticmethod
    def _category(bmi: float) -> BMICategory:
        """Map a BMI value to the corresponding WHO category."""
        for upper_bound, cat in _THRESHOLDS:
            if bmi < upper_bound:
                return cat
        return BMICategory.obese_class_iii  # unreachable but satisfies type checker

    @staticmethod
    def _ideal_weight(height_cm: float, gender: Gender) -> float:
        """
        Devine formula (1974).

        Base weights:
          Male   → 50.0 kg for 152.4 cm (5 ft), +2.3 kg per inch above.
          Female → 45.5 kg for 152.4 cm (5 ft), +2.3 kg per inch above.

        For users shorter than 152.4 cm the formula can return low values;
        we clamp at 30 kg as a practical floor.
        """
        base_height_cm = 152.4   # 5 feet in cm
        inches_over    = max(0.0, height_cm - base_height_cm) / 2.54

        if gender == Gender.male:
            ideal = 50.0 + 2.3 * inches_over
        else:
            ideal = 45.5 + 2.3 * inches_over

        return max(30.0, ideal)


# Module-level singleton
bmi_engine = BMIEngine()
