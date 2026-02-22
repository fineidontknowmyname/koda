"""
core/protein.py
---------------
Goal-based protein target, CDC/WHO safety validation, and full macro split.

Protein philosophy
──────────────────
The engine uses a *goal-driven g/kg* approach anchored to ISSN (International
Society of Sports Nutrition) 2017 position paper:

  General fitness / maintenance  : 1.4 g/kg
  Weight loss (preserve muscle)  : 1.8 g/kg
  Endurance performance          : 1.6 g/kg
  Muscle gain / strength gain    : 2.0 g/kg

A capacity-score nudge (0.0 – 0.2 g/kg) is added to reward higher training
readiness.  The result is then validated against the CDC safe upper intake
(≈ 3.5 g/kg/day for healthy adults) and a physiological floor (0.8 g/kg).

Macro split (remaining calories after protein is fixed)
────────────────────────────────────────────────────────
  Fat  : 25 % of total calorie target  (→ grams = kcal × 0.25 / 9)
  Carbs: remainder                     (→ grams = leftover kcal / 4)

Public API
──────────
protein_engine.compute(weight_kg, fitness_goal, calorie_target, capacity_score)
    -> MacroResult
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas.common import FitnessGoal


# ── Goal-based protein targets (g/kg body weight) ─────────────────────────────

_PROTEIN_G_PER_KG: dict[FitnessGoal, float] = {
    FitnessGoal.weight_loss:       1.8,   # high protein to spare lean mass in deficit
    FitnessGoal.muscle_gain:       2.0,   # ISSN upper recommendation for hypertrophy
    FitnessGoal.strength_gain:     2.0,   # same — strength athletes need ample protein
    FitnessGoal.endurance_gain:    1.6,   # endurance athletes need slightly less
    FitnessGoal.flexibility_gain:  1.4,   # maintenance level
    FitnessGoal.general_fitness:   1.4,   # maintenance level
}

# ── CDC / WHO safety bounds (g/kg/day) ────────────────────────────────────────
_CDC_FLOOR_G_PER_KG  = 0.8    # RDA: minimum to prevent deficiency
_CDC_CEILING_G_PER_KG = 3.5   # Tolerable upper bound for healthy adults

# ── Macro energy constants ────────────────────────────────────────────────────
_KCAL_PER_G_PROTEIN = 4.0
_KCAL_PER_G_CARB    = 4.0
_KCAL_PER_G_FAT     = 9.0
_FAT_FRACTION       = 0.25    # fat supplies 25 % of total daily calories


# ── Result dataclass ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MacroResult:
    """
    Full macro breakdown produced by ProteinEngine.compute().

    Attributes
    ----------
    protein_g_per_kg   Final protein rate used (after CDC clamping + bonus).
    protein_g          Absolute daily protein target in grams.
    fat_g              Daily fat target in grams (25 % of calorie_target).
    carbs_g            Daily carb target in grams (remaining calories).
    calorie_from_protein  kcal contributed by protein.
    calorie_from_fat      kcal contributed by fat.
    calorie_from_carbs    kcal contributed by carbs.
    cdc_clamped        True when the raw target was reduced to meet CDC ceiling.
    floor_applied      True when the raw target was raised to meet CDC floor.
    notes              Human-readable explanation.
    """
    protein_g_per_kg:      float
    protein_g:             float
    fat_g:                 float
    carbs_g:               float
    calorie_from_protein:  float
    calorie_from_fat:      float
    calorie_from_carbs:    float
    cdc_clamped:           bool
    floor_applied:         bool
    notes:                 str


# ── Engine ─────────────────────────────────────────────────────────────────────

class ProteinEngine:
    """
    Derive daily protein and full macro split for a given goal.

    Parameters
    ----------
    weight_kg       User's body weight (used for g/kg calculation).
    fitness_goal    Determines the baseline g/kg target.
    calorie_target  Goal-adjusted daily calorie target from TDEEEngine.
    capacity_score  CapacityEngine output [0.50, 1.50]; scales the bonus.
    """

    def compute(
        self,
        weight_kg: float,
        fitness_goal: FitnessGoal,
        calorie_target: float,
        capacity_score: float = 1.0,
    ) -> MacroResult:

        # ── Step 1: baseline g/kg for goal ────────────────────────────────────
        base_rate = _PROTEIN_G_PER_KG.get(fitness_goal, 1.4)

        # ── Step 2: capacity bonus [0.00 – 0.20 g/kg] ─────────────────────────
        # An advanced athlete (score ≈ 1.5) needs more protein to support greater
        # training volume; a beginner (score ≈ 0.5) gets no bonus.
        bonus = max(0.0, (capacity_score - 0.5) * 0.20)   # maps 0.5→0.0, 1.5→0.20
        raw_rate = base_rate + bonus

        # ── Step 3: CDC safety clamping ────────────────────────────────────────
        cdc_clamped  = raw_rate > _CDC_CEILING_G_PER_KG
        floor_applied = raw_rate < _CDC_FLOOR_G_PER_KG
        final_rate = max(_CDC_FLOOR_G_PER_KG, min(raw_rate, _CDC_CEILING_G_PER_KG))

        protein_g = round(weight_kg * final_rate, 1)

        # ── Step 4: fat ────────────────────────────────────────────────────────
        fat_kcal = calorie_target * _FAT_FRACTION
        fat_g = round(fat_kcal / _KCAL_PER_G_FAT, 1)

        # ── Step 5: carbs (remainder) ──────────────────────────────────────────
        protein_kcal = protein_g * _KCAL_PER_G_PROTEIN
        carb_kcal    = max(0.0, calorie_target - protein_kcal - fat_kcal)
        carbs_g      = round(carb_kcal / _KCAL_PER_G_CARB, 1)

        # Recompute exact carb kcal after rounding
        carb_kcal_final = carbs_g * _KCAL_PER_G_CARB

        # ── Step 6: notes ──────────────────────────────────────────────────────
        parts = [
            f"Goal: {fitness_goal.value.replace('_', ' ')}",
            f"base {base_rate:.1f} g/kg + capacity bonus {bonus:.2f} g/kg = {final_rate:.2f} g/kg.",
        ]
        if cdc_clamped:
            parts.append(
                f"Rate clamped from {raw_rate:.2f} to CDC ceiling {_CDC_CEILING_G_PER_KG} g/kg."
            )
        if floor_applied:
            parts.append(
                f"Rate raised to CDC floor {_CDC_FLOOR_G_PER_KG} g/kg."
            )

        return MacroResult(
            protein_g_per_kg=round(final_rate, 3),
            protein_g=protein_g,
            fat_g=fat_g,
            carbs_g=carbs_g,
            calorie_from_protein=round(protein_kcal, 1),
            calorie_from_fat=round(fat_kcal, 1),
            calorie_from_carbs=round(carb_kcal_final, 1),
            cdc_clamped=cdc_clamped,
            floor_applied=floor_applied,
            notes=" ".join(parts),
        )

    # ── Convenience validator ──────────────────────────────────────────────────

    @staticmethod
    def is_within_cdc_range(protein_g: float, weight_kg: float) -> bool:
        """
        Quick boolean check: is the given protein amount within the CDC/WHO
        safe intake range for this user's body weight?
        """
        rate = protein_g / max(weight_kg, 1.0)
        return _CDC_FLOOR_G_PER_KG <= rate <= _CDC_CEILING_G_PER_KG


# Module-level singleton
protein_engine = ProteinEngine()
