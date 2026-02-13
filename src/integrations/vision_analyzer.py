import mediapipe as mp
import math
from typing import Dict, List, Tuple, Optional
import numpy as np

class VisionAnalyzer:
    def __init__(self):
        self.mp_pose = mp.solutions.pose
        self.pose = self.mp_pose.Pose(
            static_image_mode=True,
            model_complexity=2,
            enable_segmentation=False,
            min_detection_confidence=0.5
        )

    def analyze_pose(self, image_path: str) -> Dict[str, float]:
        """
        Analyzes a static image for biomechanical metrics.
        Returns a dictionary of angles and scores.
        """
        # In a real API, we would handle image loading from bytes.
        # For this module, we assume the file handler passes a valid cv2 image or path.
        # Since we don't want to depend on cv2 here if not needed, we'll assume standard MP input.
        import cv2 # Import locally to avoid hard dependency if not used elsewhere
        
        image = cv2.imread(image_path)
        if image is None:
            raise ValueError(f"Could not load image from {image_path}")
            
        points = self._get_landmarks(image)
        if not points:
            return {"error": 1.0} # Indicator of failure

        metrics = {
            "knee_angle": self._calculate_angle(points[23], points[25], points[27]), # Hip, Knee, Ankle
            "hip_angle": self._calculate_angle(points[11], points[23], points[25]),  # Shoulder, Hip, Knee
            "confidence": 1.0
        }
        
        return metrics

    def _get_landmarks(self, image) -> Optional[List[Tuple[float, float]]]:
        results = self.pose.process(image)
        if not results.pose_landmarks:
            return None
            
        # Convert to list of (x, y) tuples
        h, w, _ = image.shape
        landmarks = []
        for lm in results.pose_landmarks.landmark:
            landmarks.append((lm.x * w, lm.y * h))
            
        return landmarks

    def _calculate_angle(self, a, b, c) -> float:
        """
        Calculates angle ABC in degrees.
        """
        ang = math.degrees(
            math.atan2(c[1] - b[1], c[0] - b[0]) - math.atan2(a[1] - b[1], a[0] - b[0])
        )
        return ang + 360 if ang < 0 else ang

vision_analyzer = VisionAnalyzer()
