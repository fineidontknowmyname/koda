from src.schemas.user import UserMetrics, StrengthMetrics, Gender
from typing import Dict

class CapacityEngine:
    def calculate_score(self, user_metrics: UserMetrics, strength_metrics: StrengthMetrics) -> float:
        """
        Calculates a capacity multiplier (0.5 to 1.5) based on user strength vs standards.
        """
        # Baseline standards (simplified for MVP)
        pushup_std = 20 if user_metrics.gender == Gender.male else 10
        squat_std = 30
        
        # Age adjustment
        if user_metrics.age > 40:
            pushup_std *= 0.8
            squat_std *= 0.8
            
        # Calculate ratios
        pushup_ratio = strength_metrics.pushup_count / max(pushup_std, 1)
        squat_ratio = strength_metrics.squat_count / max(squat_std, 1)
        
        # Cardio factor (inverse, lower time is better)
        # Standard: 6 mins for 1km
        run_std = 6.0
        if strength_metrics.run_time_min and strength_metrics.run_time_min > 0:
            cardio_ratio = run_std / strength_metrics.run_time_min
        else:
            cardio_ratio = 1.0 # Neutral if no run data
            
        # Weighted average
        raw_score = (pushup_ratio * 0.4) + (squat_ratio * 0.3) + (cardio_ratio * 0.3)
        
        # Clamp between 0.5 (beginner) and 1.5 (advanced)
        return max(0.5, min(raw_score, 1.5))

capacity_engine = CapacityEngine()
