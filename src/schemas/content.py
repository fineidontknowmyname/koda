from typing import List, Optional
from pydantic import BaseModel, Field
from src.schemas.common import Equipment, Injury, ExperienceLevel

class Exercise(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(min_length=10, max_length=500)
    instructions: List[str] = Field(min_length=1, max_length=20)
    benefits: List[str] = Field(default_factory=list, max_length=5)
    muscles_worked: List[str] = Field(default_factory=list, description="List of primary muscles")
    equipment_needed: List[Equipment] = Field(default_factory=list)
    difficulty: ExperienceLevel
    safety_warnings: List[str] = Field(default_factory=list, description="Crucial safety notes")

class ExerciseLibrary(BaseModel):
    exercises: List[Exercise]
