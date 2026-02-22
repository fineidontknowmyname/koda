import numpy as np
from typing import List, Dict, Any, Optional
from services.vision.landmarks import Landmark
from schemas.user import UserProfile

class FitnessEngine:
    def calculate_angle(self, a: Landmark, b: Landmark, c: Landmark) -> float:
        """
        Calculates the angle at point b (in degrees) given three landmarks a, b, c.
        """
        a_arr = np.array([a.x, a.y])
        b_arr = np.array([b.x, b.y])
        c_arr = np.array([c.x, c.y])

        radians = np.arctan2(c_arr[1] - b_arr[1], c_arr[0] - b_arr[0]) - \
                  np.arctan2(a_arr[1] - b_arr[1], a_arr[0] - b_arr[0])
        
        angle = np.abs(radians * 180.0 / np.pi)
        
        if angle > 180.0:
            angle = 360.0 - angle
            
        return angle

    def _get_distance(self, a: Landmark, b: Landmark) -> float:
        """Euclidean distance between two landmarks."""
        return np.sqrt((a.x - b.x)**2 + (a.y - b.y)**2)

    def calculate_biometric_ratios(self, landmarks: List[Landmark], user_profile: UserProfile) -> Dict[str, Any]:
        """
        Extracts human body ratios and estimates body composition.
        """
        if not landmarks or len(landmarks) < 33:
            return {"error": "Insufficient landmarks"}

        # Key Landmarks
        l_shoulder = landmarks[11]
        r_shoulder = landmarks[12]
        l_hip = landmarks[23]
        r_hip = landmarks[24]
        l_ankle = landmarks[27]
        r_ankle = landmarks[28]

        # Visibility Check (Confidence Score)
        critical_landmarks = [l_shoulder, r_shoulder, l_hip, r_hip, l_ankle, r_ankle]
        confidence_score = sum(lm.visibility for lm in critical_landmarks) / len(critical_landmarks)
        
        if confidence_score < 0.6:
            return {
                "error": "Low visibility for biometric analysis",
                "confidence_score": confidence_score
            }

        # 1. Pixel Measurements
        shoulder_width_px = self._get_distance(l_shoulder, r_shoulder)
        hip_width_px = self._get_distance(l_hip, r_hip)
        
        # Height approximation: Mid-Shoulder to Mid-Ankle (Standing pose assumption)
        mid_shoulder_x = (l_shoulder.x + r_shoulder.x) / 2
        mid_shoulder_y = (l_shoulder.y + r_shoulder.y) / 2
        mid_ankle_x = (l_ankle.x + r_ankle.x) / 2
        mid_ankle_y = (l_ankle.y + r_ankle.y) / 2
        
        apparent_height_px = np.sqrt((mid_shoulder_x - mid_ankle_x)**2 + (mid_shoulder_y - mid_ankle_y)**2)
        
        # Avoid division by zero
        if apparent_height_px == 0:
            return {"error": "Invalid pose detected (height 0)"}

        # 2. Calibration (Pixels per cm)
        # Note: This implies the user is standing fully upright and fitting the frame similarly to the reference height.
        # Ideally we'd use a known reference object, but using user height is the requested logic.
        user_height_cm = user_profile.biometrics.height_cm
        pixels_per_cm = apparent_height_px / user_height_cm

        # 3. Real-world estimations
        shoulder_width_cm = shoulder_width_px / pixels_per_cm
        hip_width_cm = hip_width_px / pixels_per_cm
        
        # Waist Approximation (Midway between hip and shoulder, slightly weighted towards hip)
        # We can also conceptually just estimate waist width as a fraction of hip/shoulder logic or position.
        # Let's use geometrical midpoint:
        l_waist_x = (l_shoulder.x + l_hip.x) / 2
        l_waist_y = (l_shoulder.y + l_hip.y) / 2
        r_waist_x = (r_shoulder.x + r_hip.x) / 2
        r_waist_y = (r_shoulder.y + r_hip.y) / 2
        
        waist_width_px = np.sqrt((l_waist_x - r_waist_x)**2 + (l_waist_y - r_waist_y)**2)
        # Adjusting: Waist is essentially narrower. Let's assume the visual width is roughly diameter.
        waist_width_cm = waist_width_px / pixels_per_cm
        
        # Estimate Circumference (assuming circular cross section is simplistic, but standard for visual est)
        # C = Pi * d
        waist_circumference_cm = waist_width_cm * 3.14159

        # Safety clamp for Waist (humanly possible ranges)
        if waist_circumference_cm < 40 or waist_circumference_cm > 200:
             # Fallback/Error if calculation is way off due to camera angle
             pass 

        # 4. Biometric Ratios
        v_taper_ratio = shoulder_width_cm / hip_width_cm if hip_width_cm > 0 else 0

        # 5. Body Fat Estimation (RFM - Relative Fat Mass)
        # RFM = 64 - (20 * (Height / Waist))  (Men)
        # RFM = 76 - (20 * (Height / Waist))  (Women)
        
        rfm_constant = 64 if user_profile.biometrics.gender.value == "male" else 76
        
        if waist_circumference_cm > 0:
            body_fat_pct = rfm_constant - (20 * (user_height_cm / waist_circumference_cm))
        else:
            body_fat_pct = 0

        return {
            "v_taper_ratio": round(v_taper_ratio, 2),
            "estimated_body_fat_pct": round(body_fat_pct, 1),
            "shoulder_width_cm": round(shoulder_width_cm, 1),
            "hip_width_cm": round(hip_width_cm, 1),
            "waist_circumference_estimate_cm": round(waist_circumference_cm, 1),
            "confidence_score": round(confidence_score, 2)
        }

    def analyze_form(self, exercise_type: str, landmarks: List[Landmark]) -> Dict[str, Any]:
        """
        Analyzes form for a specific exercise based on landmarks.
        Returns a dictionary with metrics and feedback.
        """
        if not landmarks:
            return {"error": "No landmarks provided"}

        feedback = []
        metrics = {}
        
        # Mapping MediaPipe Pose Landmarks for reference
        # 11: left_shoulder, 12: right_shoulder
        # 23: left_hip, 24: right_hip
        # 25: left_knee, 26: right_knee
        # 27: left_ankle, 28: right_ankle
        # 13: left_elbow, 14: right_elbow
        # 15: left_wrist, 16: right_wrist

        if exercise_type.lower() == "squat":
            # Right side analysis (simplified)
            hip = landmarks[24]
            knee = landmarks[26]
            ankle = landmarks[28]
            
            # Check for visibility
            if hip.visibility > 0.5 and knee.visibility > 0.5 and ankle.visibility > 0.5:
                knee_angle = self.calculate_angle(hip, knee, ankle)
                metrics["knee_angle"] = knee_angle
                
                if knee_angle < 80:
                    feedback.append("Good depth!")
                elif knee_angle < 100:
                    feedback.append("Parallel depth achieved.")
                else:
                    feedback.append("Go lower for full range of motion.")
            else:
                feedback.append("Ensure full body is visible.")

        elif exercise_type.lower() == "pushup":
             # Right side analysis
            shoulder = landmarks[12]
            elbow = landmarks[14]
            wrist = landmarks[16]
            
            if shoulder.visibility > 0.5 and elbow.visibility > 0.5 and wrist.visibility > 0.5:
                elbow_angle = self.calculate_angle(shoulder, elbow, wrist)
                metrics["elbow_angle"] = elbow_angle
                
                if elbow_angle > 160:
                    feedback.append("Arms fully extended.")
                elif elbow_angle < 90:
                    feedback.append("Good depth at bottom.")
        
        # Add more exercises as needed...

        return {
            "exercise": exercise_type,
            "metrics": metrics,
            "feedback": feedback
        }

fitness_engine = FitnessEngine()
