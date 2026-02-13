from typing import List, Optional
from pydantic import BaseModel, Field
from src.schemas.content import Exercise

class WorkoutSet(BaseModel):
    reps: int = Field(ge=1, le=100)
    weight_kg: float = Field(ge=0.0, le=500.0, default=0.0)
    rest_sec: int = Field(ge=0, le=300, default=60)
    notes: Optional[str] = None

class WorkoutExercise(BaseModel):
    exercise: Exercise
    sets: List[WorkoutSet] = Field(min_length=1)

class WorkoutSession(BaseModel):
    day_name: str = Field(description="e.g. 'Monday', 'Day 1'")
    exercises: List[WorkoutExercise] = Field(default_factory=list)
    duration_min: int = Field(ge=5, le=180)

class WeeklySchedule(BaseModel):
    week_number: int = Field(ge=1, le=52)
    sessions: List[WorkoutSession] = Field(min_length=1, max_length=7)

class FitnessPlan(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    weeks: List[WeeklySchedule] = Field(min_length=1, max_length=12)

from src.schemas.user import UserProfile

class GeneratePlanRequest(BaseModel):
    user_profile: UserProfile
    transcript_text: str = Field(min_length=50, max_length=100000, description="YouTube video transcript")
