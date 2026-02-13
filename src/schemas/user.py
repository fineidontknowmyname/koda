from typing import List, Optional
from pydantic import BaseModel, Field
from src.schemas.common import Gender, ExperienceLevel, Injury, Equipment, FitnessGoal

class UserMetrics(BaseModel):
    age: int = Field(ge=12, le=90, description="Age in years")
    weight_kg: float = Field(ge=30.0, le=200.0, description="Weight in kilograms")
    height_cm: float = Field(ge=95.0, le=250.0, description="Height in centimeters")
    gender: Gender

class StrengthMetrics(BaseModel):
    pushup_count: int = Field(ge=0, le=100, description="Max consecutive pushups")
    situp_count: int = Field(ge=0, le=100, description="Max consecutive situps")
    squat_count: int = Field(ge=0, le=100, description="Max consecutive bodyweight squats")
    run_time_min: Optional[float] = Field(None, ge=0.0, le=120.0, description="1km run time in minutes")
    run_distance_km: Optional[float] = Field(None, ge=0.0, le=42.0, description="Max run distance in km")

class UserProfile(BaseModel):
    biometrics: UserMetrics
    metrics: StrengthMetrics
    injuries: List[Injury] = Field(default_factory=list)
    equipment: List[Equipment] = Field(default_factory=list)
    experience_level: ExperienceLevel
    fitness_goal: FitnessGoal
