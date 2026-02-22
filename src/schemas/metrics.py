from pydantic import BaseModel, Field
from typing import Optional

class BodyMetrics(BaseModel):
    """
    Computed health and nutrition metrics derived from UserProfile.
    Produced by the TDEE/nutrition service and stored alongside a plan.
    """

    # ── Body Composition Indices ───────────────────────────────────────────────
    bmi: float = Field(
        ge=10.0, le=70.0,
        description="Body Mass Index (weight_kg / height_m²)"
    )
    ideal_weight_kg: float = Field(
        ge=30.0, le=200.0,
        description="Devine formula ideal weight in kg"
    )

    # ── Energy Expenditure ─────────────────────────────────────────────────────
    bmr: float = Field(
        ge=500.0, le=6000.0,
        description="Basal Metabolic Rate in kcal/day (Mifflin-St Jeor)"
    )
    activity_multiplier: float = Field(
        ge=1.0, le=2.5,
        description="PAL factor applied to BMR to get TDEE (1.2=sedentary … 1.9=very active)"
    )
    tdee: float = Field(
        ge=800.0, le=10000.0,
        description="Total Daily Energy Expenditure in kcal/day (BMR × activity_multiplier)"
    )
    calorie_target: float = Field(
        ge=800.0, le=10000.0,
        description="Goal-adjusted daily calorie target (deficit / surplus applied to TDEE)"
    )

    # ── Macronutrient Targets ──────────────────────────────────────────────────
    protein_g: float = Field(
        ge=0.0,
        description="Daily protein target in grams"
    )
    carbs_g: float = Field(
        ge=0.0,
        description="Daily carbohydrate target in grams"
    )
    fat_g: float = Field(
        ge=0.0,
        description="Daily fat target in grams"
    )

    # ── Optional Notes ─────────────────────────────────────────────────────────
    notes: Optional[str] = Field(
        None, max_length=300,
        description="e.g. 'High protein due to muscle gain goal'"
    )
