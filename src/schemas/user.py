from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from schemas.common import Gender, ExperienceLevel, Injury, Equipment, FitnessGoal, ActivityLevel


class UserMetrics(BaseModel):
    age: int = Field(ge=15, le=60, description="Age in years")
    weight_kg: float = Field(ge=30.0, le=200.0, description="Weight in kilograms")
    height_cm: float = Field(ge=95.0, le=250.0, description="Height in centimeters")
    gender: Gender  # male | female only

    @field_validator("age", mode="before")
    @classmethod
    def clamp_age(cls, v):  # noqa: N805
        """Clamp incoming age to 15–60 instead of rejecting it."""
        return max(15, min(60, int(v)))

    @field_validator("gender", mode="before")
    @classmethod
    def normalise_gender(cls, v):  # noqa: N805
        """Map unrecognised gender values to 'male' instead of rejecting."""
        return v if v in ("male", "female") else "male"


class StrengthMetrics(BaseModel):
    pushup_count: int = Field(ge=0, le=100, description="Max consecutive pushups")
    situp_count: int = Field(ge=0, le=100, description="Max consecutive situps")
    squat_count: int = Field(ge=0, le=100, description="Max consecutive bodyweight squats")
    run_time_min: Optional[float] = Field(None, ge=0.0, le=120.0, description="1km run time in minutes")
    run_distance_km: Optional[float] = Field(None, ge=0.0, le=42.0, description="Max run distance in km")


class PhysicalActivity(BaseModel):
    activity_level: ActivityLevel = Field(
        default=ActivityLevel.moderately_active,
        description="General daily activity level",
    )
    physical_activity_hours_per_day: float = Field(
        default=1.0, ge=0.0, le=16.0,
        description="Hours per day spent in deliberate physical activity (exercise, sport, etc.)",
    )


class UserProfile(BaseModel):
    biometrics: UserMetrics
    metrics: StrengthMetrics
    physical_activity: Optional[PhysicalActivity] = None
    injuries: List[Injury] = Field(default_factory=list)
    equipment: List[Equipment] = Field(default_factory=list)
    experience_level: ExperienceLevel
    fitness_goal: FitnessGoal
    analysis_consent: bool = Field(
        default=False,
        description="User consents to AI body composition analysis of uploaded images",
    )