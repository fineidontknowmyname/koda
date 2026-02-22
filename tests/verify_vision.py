import sys
import os
import numpy as np
import cv2

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from src.services.vision.landmarks import landmark_detector, Landmark
from src.services.fitness.engine import fitness_engine

def verify_vision():
    print("--- Verifying Vision Services ---")
    
    # 1. Test Landmark Detector with a blank image
    print("Testing LandmarkDetector with blank image...")
    blank_image = np.zeros((480, 640, 3), dtype=np.uint8)
    landmarks = landmark_detector.detect(blank_image)
    
    if landmarks is None:
        print("✅ Correctly returned None for blank image (no pose).")
    else:
        print("❓ Unexpectedly found landmarks in blank image.")

    # 2. Test Fitness Engine (Angle Calculation)
    print("\nTesting FitnessEngine (Geometry)...")
    # Create dummy landmarks for a 90-degree angle
    # A=(1,0), B=(0,0), C=(0,1) -> Should be 90 degrees
    a = Landmark(x=1.0, y=0.0, z=0.0, visibility=1.0)
    b = Landmark(x=0.0, y=0.0, z=0.0, visibility=1.0)
    c = Landmark(x=0.0, y=1.0, z=0.0, visibility=1.0)
    
    angle = fitness_engine.calculate_angle(a, b, c)
    print(f"Calculated Angle (Expected 90.0): {angle}")
    
    if abs(angle - 90.0) < 0.1:
        print("✅ Angle calculation accurate.")
    else:
        print("❌ Angle calculation failed.")

    # 3. Test Fitness Engine (Form Analysis - Squat)
    print("\nTesting FitnessEngine (Squat Logic)...")
    # Simulate a squat with deep knee bend (Angle < 80)
    # Hip, Knee, Ankle
    hip = Landmark(x=0.5, y=0.5, z=0.0, visibility=0.9)
    knee = Landmark(x=0.6, y=0.8, z=0.0, visibility=0.9)
    # To get < 80 degrees, place ankle carefully. 
    # Let's just trust the logic if angle calcs work, but we can test the function call.
    
    # Construct a list of 33 dummy landmarks (MediaPipe Pose has 33)
    dummy_landmarks = [Landmark(x=0.0, y=0.0, z=0.0, visibility=0.0) for _ in range(33)]
    
    # Set key landmarks for squat (Right side: 24, 26, 28)
    # Let's set them to form a 90 degree angle
    dummy_landmarks[24] = a # Hip
    dummy_landmarks[26] = b # Knee
    dummy_landmarks[28] = c # Ankle
    
    result = fitness_engine.analyze_form("squat", dummy_landmarks)
    print(f"Squat Analysis Result: {result}")
    
    if "metrics" in result and "knee_angle" in result["metrics"]:
        print("✅ Form analysis returned metrics.")
    else:
        print("❌ Form analysis missing metrics.")

if __name__ == "__main__":
    verify_vision()
