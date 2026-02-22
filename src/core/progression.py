from copy import deepcopy
from typing import List
from schemas.plan import WeeklySchedule, WorkoutSession, WorkoutExercise, WorkoutSet
from schemas.content import Exercise

class ProgressionEngine:
    def apply_progression(self, base_week: WeeklySchedule, total_weeks: int, capacity_score: float) -> List[WeeklySchedule]:
        """
        Generates N weeks of workouts by scaling volume and intensity from the base week.
        """
        full_plan = []
        
        for week_num in range(1, total_weeks + 1):
            # Clone the base week structure
            current_week = deepcopy(base_week)
            current_week.week_number = week_num
            
            # Progression Factors
            # Volume: Increase reps by 10% each week
            volume_multiplier = 1.0 + ((week_num - 1) * 0.1)
            
            # Intensity: Initial weight scaling based on capacity
            # If capacity is high (1.5), start heavy. If low (0.5), start light.
            # We apply this base scalar to the "suggested" weights.
            intensity_scalar = capacity_score
            
            for session in current_week.sessions:
                for workout_exercise in session.exercises:
                    for wset in workout_exercise.sets:
                        # Scale Reps
                        wset.reps = int(wset.reps * volume_multiplier)
                        
                        # Scale Weight (if applicable)
                        if wset.weight_kg > 0:
                            # Add small progressive overload (2.5kg per week) if standardized
                            progressive_overload = (week_num - 1) * 2.5
                            wset.weight_kg = (wset.weight_kg * intensity_scalar) + progressive_overload
            
            full_plan.append(current_week)
            
        return full_plan

progression_engine = ProgressionEngine()
