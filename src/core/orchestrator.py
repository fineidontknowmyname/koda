from typing import List
from src.schemas.user import UserProfile
from src.schemas.plan import FitnessPlan, WeeklySchedule, WorkoutSession, WorkoutExercise, WorkoutSet
from src.schemas.content import ExerciseLibrary
from src.integrations.gemini_client import gemini_client
from src.core.capacity import capacity_engine
from src.core.safety import safety_engine
from src.core.progression import progression_engine

class PlanOrchestrator:
    async def generate_plan(self, user_profile: UserProfile, transcript_text: str) -> FitnessPlan:
        # 1. Calculate Capacity
        capacity_score = capacity_engine.calculate_score(user_profile.biometrics, user_profile.metrics)
        
        # 2. Extract Exercises using Gemini
        exercise_lib = await gemini_client.extract_exercises(transcript_text)
        
        # 3. Filter for Safety
        safe_exercises = safety_engine.filter_exercises(
            exercise_lib.exercises, 
            user_profile.injuries, 
            user_profile.equipment
        )
        
        if not safe_exercises:
            # Fallback if everything is filtered out
            raise ValueError("No safe exercises found matching criteria.")
        
        # 4. Build Base Template (Simple Round Robin for MVP)
        # Create a single base week with 3 sessions (Mon, Wed, Fri)
        base_sessions = []
        days = ["Monday", "Wednesday", "Friday"]
        
        # Distribute exercises across days
        chunk_size = max(1, len(safe_exercises) // 3)
        
        for i, day in enumerate(days):
            day_exercises = safe_exercises[i*chunk_size : (i+1)*chunk_size]
            workout_exercises = []
            
            for ex in day_exercises:
                # Default sets structure: 3 sets of 10 reps
                sets = [WorkoutSet(reps=10, weight_kg=10.0, rest_sec=60) for _ in range(3)]
                workout_exercises.append(WorkoutExercise(exercise=ex, sets=sets))
            
            base_sessions.append(WorkoutSession(
                day_name=day, 
                exercises=workout_exercises, 
                duration_min=45
            ))
            
        base_week = WeeklySchedule(week_number=1, sessions=base_sessions)
        
        # 5. Apply Progression for 4 Weeks
        weeks = progression_engine.apply_progression(base_week, total_weeks=4, capacity_score=capacity_score)
        
        return FitnessPlan(
            title=f"Koda 4-Week Plan for {user_profile.fitness_goal.value}",
            weeks=weeks
        )

plan_orchestrator = PlanOrchestrator()
