from typing import List, Optional
from pydantic import BaseModel, Field
from schemas.common import Equipment, Injury, ExperienceLevel

# ── Exercise ──────────────────────────────────────────────────────────────────

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

# ── Nutrition ─────────────────────────────────────────────────────────────────

class MealIdea(BaseModel):
    name: str = Field(min_length=2, max_length=100, description="e.g. 'Grilled Chicken & Rice'")
    description: str = Field(min_length=5, max_length=300)
    approximate_calories: int = Field(ge=50, le=2000)
    protein_g: float = Field(ge=0.0, description="Protein in grams")
    carbs_g: float = Field(ge=0.0, description="Carbohydrates in grams")
    fat_g: float = Field(ge=0.0, description="Fat in grams")
    meal_type: str = Field(description="breakfast | lunch | dinner | snack")
    prep_time_min: Optional[int] = Field(None, ge=0, le=180, description="Prep time in minutes")
    tags: List[str] = Field(default_factory=list, description="e.g. ['high-protein', 'low-carb']")

class MealIdeaBank(BaseModel):
    """Collection of meal ideas extracted or generated for a user."""
    meals: List[MealIdea]
    daily_calorie_target: int = Field(ge=800, le=6000)
    daily_protein_target_g: float = Field(ge=0.0)

# ── Video Intelligence ────────────────────────────────────────────────────────

class VideoClassification(BaseModel):
    """Result of classifying a YouTube video by its transcript content."""
    video_url: str
    category: str = Field(
        description="strength | cardio | mobility | diet | general"
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Classification confidence score")
    key_topics: List[str] = Field(
        default_factory=list,
        description="Main topics detected in the transcript"
    )

# ── Diet Plan ─────────────────────────────────────────────────────────────────

class DietDay(BaseModel):
    """A single day's structured meal plan."""
    day_number: int = Field(ge=1, le=7, description="Day of the week (1=Monday)")
    meals: List[MealIdea] = Field(min_length=1, max_length=8)
    total_calories: int = Field(ge=0)
    total_protein_g: float = Field(ge=0.0)
    total_carbs_g: float = Field(ge=0.0)
    total_fat_g: float = Field(ge=0.0)
    notes: Optional[str] = Field(None, max_length=300, description="e.g. training day — eat more carbs")

class DietPlan(BaseModel):
    """A weekly diet plan returned alongside or separately from a fitness plan."""
    title: str = Field(min_length=3, max_length=100)
    days: List[DietDay] = Field(min_length=1, max_length=7)
    weekly_calorie_average: float = Field(ge=0.0)
    weekly_protein_average_g: float = Field(ge=0.0)
    generated_from_video: Optional[str] = Field(
        None, description="YouTube URL that sourced this diet plan, if any"
    )
