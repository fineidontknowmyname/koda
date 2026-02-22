import math

import mediapipe as mp
import cv2
import numpy as np
from typing import NamedTuple, List, Optional, Tuple

from schemas.vision import SWRCategory

class Landmark(NamedTuple):
    x: float
    y: float
    z: float
    visibility: float

class LandmarkDetector:
    def __init__(self, static_image_mode: bool = False, model_complexity: int = 1):
        self.mp_pose = None
        self.pose = None
        self._init_error = None

        try:
            # Legacy MediaPipe API path.
            self.mp_pose = mp.solutions.pose
        except AttributeError:
            try:
                # Some wheels expose solutions only via mediapipe.python.
                from mediapipe.python.solutions import pose as mp_pose  # type: ignore
                self.mp_pose = mp_pose
            except Exception as exc:
                self._init_error = (
                    "MediaPipe Pose API is unavailable in this environment. "
                    "Install a MediaPipe build that includes `solutions.pose`."
                )
                self.pose = None
                return

        self.pose = self.mp_pose.Pose(
            static_image_mode=static_image_mode,
            model_complexity=model_complexity,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        )

    def detect(self, frame: np.ndarray) -> Optional[List[Landmark]]:
        """
        Processes a BGR image frame and returns a list of normalized landmarks.
        Returns None if no pose is detected.
        """
        if self.pose is None:
            raise RuntimeError(self._init_error or "Landmark detector is not initialized")

        # MediaPipe expects RGB
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.pose.process(image_rgb)

        if not results.pose_landmarks:
            return None

        landmarks = []
        for lm in results.pose_landmarks.landmark:
            landmarks.append(Landmark(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility))
        
        return landmarks

    def draw_landmarks(self, frame: np.ndarray, landmarks_list) -> np.ndarray:
        """
        Helper to draw landmarks on the frame for visualization.
        Note: landmarks_list argument here expects the raw MediaPipe results object
        or we need to reconstruct it. For simplicity, we'll let the user handle raw drawing
        via mp.solutions.drawing_utils if needed, or implement simple drawing here.
        """
        # Re-implementation of drawing utils is complex; 
        # standard usage usually passes the original results.pose_landmarks.
        # This is a placeholder for custom drawing logic.
        return frame

def calculate_shoulder_waist_ratio(
    landmarks: List[Landmark],
    image_width: int,
    image_height: int,
) -> Tuple[float, float, float, SWRCategory]:
    """
    Compute Shoulder-to-Waist Ratio from MediaPipe pose landmarks.

    Uses landmarks 11/12 (left/right shoulder) and 23/24 (left/right hip,
    used as a waist proxy) to derive pixel-space widths and their ratio.

    Parameters
    ----------
    landmarks      33-element list of normalised Landmark tuples.
    image_width    Original image width in pixels.
    image_height   Original image height in pixels.

    Returns
    -------
    (shoulder_width_px, waist_width_px, swr, swr_category)
    """
    l_sh = landmarks[11]   # left shoulder
    r_sh = landmarks[12]   # right shoulder
    l_hp = landmarks[23]   # left hip (waist proxy)
    r_hp = landmarks[24]   # right hip (waist proxy)

    # Convert normalised → pixel coordinates
    shoulder_width_px = math.hypot(
        (l_sh.x - r_sh.x) * image_width,
        (l_sh.y - r_sh.y) * image_height,
    )
    waist_width_px = math.hypot(
        (l_hp.x - r_hp.x) * image_width,
        (l_hp.y - r_hp.y) * image_height,
    )

    # Guard against division by zero
    if waist_width_px < 1e-6:
        return (shoulder_width_px, 0.0, 1.1, SWRCategory.BALANCED)

    swr = shoulder_width_px / waist_width_px

    # Classify
    if swr < 1.0:
        category = SWRCategory.OVERFAT
    elif swr > 1.2:
        category = SWRCategory.ATHLETIC
    else:
        category = SWRCategory.BALANCED

    return (round(shoulder_width_px, 2), round(waist_width_px, 2),
            round(swr, 3), category)


landmark_detector = LandmarkDetector()
