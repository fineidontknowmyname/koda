from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from typing import Any
import cv2
import numpy as np
import json

from src.services.vision.landmarks import landmark_detector
from src.services.fitness.engine import fitness_engine
from src.schemas.vision import VisionAnalysisResult, BiometricAnalysis, LandmarkPoint
from src.schemas.user import UserProfile

router = APIRouter()

@router.post("/analyze-frame", response_model=VisionAnalysisResult, summary="Analyze a single image frame")
async def analyze_frame(
    file: UploadFile = File(...)
) -> Any:
    """
    Receives an image file, detects landmarks, and returns coordinates.
    """
    try:
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image data")

        landmarks = landmark_detector.detect(frame)
        
        if not landmarks:
            return VisionAnalysisResult(
                frame_timestamp=0.0,
                has_landmarks=False
            )
            
        # Convert to Schema
        landmark_points = [
            LandmarkPoint(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility) 
            for lm in landmarks
        ]
        
        return VisionAnalysisResult(
            frame_timestamp=0.0,
            has_landmarks=True,
            landmarks=landmark_points
        )

    except Exception as e:
        print(f"Vision Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error processing image")

@router.post("/biometrics", response_model=BiometricAnalysis, summary="Extract biometric ratios")
async def extract_biometrics(
    file: UploadFile = File(...),
    user_profile_json: str = Form(...)
) -> Any:
    """
    Extracts V-Taper, Body Fat, etc. requires image and user profile (for height calibration).
    user_profile_json expected as stringified JSON of UserProfile.
    """
    try:
        # Parse User Profile
        user_data = json.loads(user_profile_json)
        user_profile = UserProfile(**user_data)
        
        # Process Image
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(status_code=400, detail="Invalid image data")
            
        landmarks = landmark_detector.detect(frame)
        
        if not landmarks:
            raise HTTPException(status_code=400, detail="No person detected in image")
            
        # Analysis
        result = fitness_engine.calculate_biometric_ratios(landmarks, user_profile)
        
        if "error" in result:
             raise HTTPException(status_code=400, detail=result["error"])
             
        return BiometricAnalysis(**result)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON for user_profile_json")
    except Exception as e:
        print(f"Biometric Error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Error: {str(e)}")
