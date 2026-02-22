"""
integrations/vision_analyzer.py
---------------------------------
Unified vision analysis — two independent pipelines, one facade.

  Pipeline A — MediaPipe Pose
      Skeletal landmark extraction (33 key-points) for per-exercise
      form scoring and biometric ratio calculation.

  Pipeline B — MobileNetV2 (TensorFlow Keras)
      Deep visual feature extraction → muscle mass category + posture
      classification.  Supplements the landmark-derived RFM body-fat
      and V-taper metrics so no LLM / cloud call is required.

Architecture notes
──────────────────
* Both models are lazy-initialised on first use so FastAPI startup is fast.
* All blocking CV / ML calls are wrapped in asyncio.to_thread so the event
  loop is never held.
* Graceful degradation: if mediapipe or tensorflow is absent the code returns
  a valid (partial) result instead of crashing.

Public async API
────────────────
  vision_analyzer.analyze_pose(image_bytes)
      -> PoseResult

  vision_analyzer.analyze_body_composition(image_bytes, user_height_cm, gender)
      -> BodyCompositionResult

  vision_analyzer.analyze_form(exercise_type, image_bytes)
      -> FormResult

Install dependencies
────────────────────
  pip install mediapipe opencv-python-headless tensorflow
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

log = logging.getLogger(__name__)

# ── Lazy model singletons (set on first access) ───────────────────────────────
_mp_pose_handle  = None   # mediapipe Pose solution
_mobilenet_model = None   # tf.keras.Model


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Landmark:
    """Normalised image-space coordinate for a single pose landmark."""
    x:          float
    y:          float
    z:          float = 0.0
    visibility: float = 1.0


@dataclass
class PoseResult:
    landmarks:  List[Landmark] = field(default_factory=list)
    confidence: float          = 0.0
    is_valid:   bool           = False
    error:      Optional[str]  = None


@dataclass
class BodyCompositionResult:
    """Mirrors the fields consumed by BodyAnalysisResult / BodyComposition schemas."""
    body_fat_percentage:  float = 0.0
    v_taper_ratio:        float = 0.0
    muscle_mass_estimate: str   = "Unknown"   # Low | Moderate | High | Very High
    posture_assessment:   str   = "Unknown"
    is_valid_person:      bool  = False
    confidence:           float = 0.0
    method:               str   = "MobileNetV2 + RFM"


@dataclass
class FormResult:
    exercise: str
    metrics:  Dict[str, Any] = field(default_factory=dict)
    feedback: List[str]      = field(default_factory=list)
    is_valid: bool           = True
    error:    Optional[str]  = None


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline A — MediaPipe Pose
# ─────────────────────────────────────────────────────────────────────────────

_CRITICAL_LM_IDX = [11, 12, 23, 24, 27, 28]   # shoulders, hips, ankles
_MIN_CONFIDENCE  = 0.55


class PoseAnalyzer:
    """MediaPipe-based skeletal landmark extractor (static image mode)."""

    # ── lazy init ─────────────────────────────────────────────────────────────

    def _pose(self):
        global _mp_pose_handle
        if _mp_pose_handle is not None:
            return _mp_pose_handle
        try:
            import mediapipe as mp
            _mp_pose_handle = mp.solutions.pose.Pose(
                static_image_mode=True,
                model_complexity=1,
                enable_segmentation=False,
                min_detection_confidence=0.5,
            )
            log.info("MediaPipe Pose initialised (model_complexity=1)")
        except ImportError:
            log.warning("mediapipe not installed — pose analysis unavailable")
            _mp_pose_handle = None
        return _mp_pose_handle

    # ── public ────────────────────────────────────────────────────────────────

    def run(self, image_bytes: bytes) -> PoseResult:
        """Extract 33 landmarks from a raw image buffer."""
        pose = self._pose()
        if pose is None:
            return PoseResult(error="mediapipe not available")

        nparr = np.frombuffer(image_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return PoseResult(error="Could not decode image bytes")

        results = pose.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not results.pose_landmarks:
            return PoseResult(error="No person detected in image")

        lms = [
            Landmark(lm.x, lm.y, lm.z, getattr(lm, "visibility", 1.0))
            for lm in results.pose_landmarks.landmark
        ]
        critical   = [lms[i] for i in _CRITICAL_LM_IDX if i < len(lms)]
        confidence = sum(lm.visibility for lm in critical) / max(len(critical), 1)

        return PoseResult(
            landmarks=lms,
            confidence=round(confidence, 3),
            is_valid=confidence >= _MIN_CONFIDENCE,
            error=None if confidence >= _MIN_CONFIDENCE else "Low landmark confidence",
        )

    # ── joint angle helper ────────────────────────────────────────────────────

    @staticmethod
    def joint_angle(a: Landmark, b: Landmark, c: Landmark) -> float:
        """
        Angle at vertex B (rays B→A and B→C) in degrees [0, 180].
        Equivalent to FitnessEngine.calculate_angle for drop-in use.
        """
        ba = np.array([a.x - b.x, a.y - b.y])
        bc = np.array([c.x - b.x, c.y - b.y])
        cos_a = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-9)
        return float(np.degrees(np.arccos(np.clip(cos_a, -1.0, 1.0))))


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline B — MobileNetV2 body composition
# ─────────────────────────────────────────────────────────────────────────────

_MOBILENET_SIZE = (224, 224)

# Empirical thresholds on global-avg-pool feature magnitude → muscle category.
# Replace with a fine-tuned softmax head when labelled data is available.
_MUSCLE_THRESHOLDS: List[Tuple[float, str]] = [
    (0.70, "Very High"),
    (0.52, "High"),
    (0.34, "Moderate"),
    (0.00, "Low"),
]


class BodyCompositionAnalyzer:
    """
    Two-stage body composition inference:

      1. MediaPipe landmarks → V-taper, RFM body-fat %, posture (rule-based).
      2. MobileNetV2 global-avg-pool features → muscle mass category.
    """

    def __init__(self, pose_analyzer: PoseAnalyzer) -> None:
        self._pose = pose_analyzer

    # ── lazy MobileNetV2 ──────────────────────────────────────────────────────

    def _model(self):
        global _mobilenet_model
        if _mobilenet_model is not None:
            return _mobilenet_model
        try:
            import tensorflow as tf
            _mobilenet_model = tf.keras.applications.MobileNetV2(
                input_shape=(*_MOBILENET_SIZE, 3),
                include_top=False,
                pooling="avg",
                weights="imagenet",
            )
            _mobilenet_model.trainable = False
            log.info("MobileNetV2 feature extractor loaded (imagenet weights)")
        except ImportError:
            log.warning("tensorflow not installed — MobileNetV2 unavailable")
            _mobilenet_model = None
        return _mobilenet_model

    # ── public ────────────────────────────────────────────────────────────────

    def run(
        self,
        image_bytes: bytes,
        user_height_cm: float = 175.0,
        gender: str = "male",
    ) -> BodyCompositionResult:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return BodyCompositionResult(is_valid_person=False,
                                         posture_assessment="Invalid image")
        h, w = img.shape[:2]
        if h < 80 or w < 80:
            return BodyCompositionResult(is_valid_person=False,
                                         posture_assessment="Image too small")

        # Stage 1 — landmark-based scalars
        pose_res = self._pose.run(image_bytes)
        body_fat, v_taper, posture, pose_conf = self._landmark_scalars(
            pose_res, user_height_cm, gender
        )

        # Stage 2 — MobileNetV2 muscle category
        muscle_cat, net_conf = self._mobilenet_category(img)

        return BodyCompositionResult(
            body_fat_percentage=round(max(3.0, min(50.0, body_fat)), 1),
            v_taper_ratio=round(v_taper, 2),
            muscle_mass_estimate=muscle_cat,
            posture_assessment=posture,
            is_valid_person=pose_res.is_valid,
            confidence=round((pose_conf + net_conf) / 2, 3),
            method="MobileNetV2 + RFM",
        )

    # ── Stage 1 helpers ───────────────────────────────────────────────────────

    def _landmark_scalars(
        self,
        pose: PoseResult,
        height_cm: float,
        gender: str,
    ) -> Tuple[float, float, str, float]:
        """Returns (body_fat_pct, v_taper, posture_str, confidence)."""
        if not pose.is_valid or len(pose.landmarks) < 33:
            return 20.0, 1.0, "Pose inconclusive", 0.0

        lms = pose.landmarks

        def dist(a: Landmark, b: Landmark) -> float:
            return math.hypot(a.x - b.x, a.y - b.y)

        l_sh, r_sh   = lms[11], lms[12]
        l_hip, r_hip = lms[23], lms[24]
        l_ank, r_ank = lms[27], lms[28]

        # Pixel-space height for calibration
        sh_mid_x = (l_sh.x + r_sh.x) / 2; sh_mid_y = (l_sh.y + r_sh.y) / 2
        an_mid_x = (l_ank.x + r_ank.x) / 2; an_mid_y = (l_ank.y + r_ank.y) / 2
        height_px = math.hypot(sh_mid_x - an_mid_x, sh_mid_y - an_mid_y)
        if height_px < 1e-6:
            return 20.0, 1.0, "Pose measurement failed", 0.0

        ppc          = height_px / max(height_cm, 1.0)   # pixels per cm
        shoulder_cm  = dist(l_sh, r_sh)  / ppc
        hip_cm       = dist(l_hip, r_hip) / ppc

        # Waist: midpoint between shoulder and hip → diameter → circumference
        waist_px   = dist(
            Landmark((l_sh.x + l_hip.x) / 2, (l_sh.y + l_hip.y) / 2),
            Landmark((r_sh.x + r_hip.x) / 2, (r_sh.y + r_hip.y) / 2),
        )
        waist_circ = (waist_px / ppc) * math.pi

        # RFM body fat estimate (Woolcott & Bergman 2018 variant)
        rfm_k    = 64.0 if gender.lower() == "male" else 76.0
        body_fat = rfm_k - (20.0 * (height_cm / max(waist_circ, 1.0)))

        # V-taper
        v_taper  = shoulder_cm / max(hip_cm, 1.0)

        # Posture heuristic from shoulder tilt
        tilt = abs(l_sh.y - r_sh.y)
        if tilt > 0.05:
            posture = "Lateral tilt detected — shoulder imbalance"
        elif abs(l_sh.x - r_sh.x) < 0.02:
            posture = "Upright — good spinal alignment"
        else:
            posture = "Slight forward lean — check head position"

        return body_fat, v_taper, posture, pose.confidence

    # ── Stage 2 helper ────────────────────────────────────────────────────────

    def _mobilenet_category(self, img_bgr: np.ndarray) -> Tuple[str, float]:
        """MobileNetV2 feature extraction → muscle mass label + confidence."""
        model = self._model()
        if model is None:
            return "Moderate", 0.0
        try:
            import tensorflow as tf
            rgb      = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            resized  = cv2.resize(rgb, _MOBILENET_SIZE).astype(np.float32)
            scaled   = tf.keras.applications.mobilenet_v2.preprocess_input(resized)
            features = model.predict(np.expand_dims(scaled, 0), verbose=0)[0]  # (1280,)

            # Proxy: higher-layer activations correlate with structural complexity
            hi = float(np.mean(np.abs(features[640:])))
            lo = float(np.mean(np.abs(features[:640])))
            score = hi / max(hi + lo, 1e-9)

            category = "Low"
            for threshold, label in _MUSCLE_THRESHOLDS:
                if score >= threshold:
                    category = label
                    break

            return category, round(min(1.0, score * 1.4), 3)
        except Exception as exc:
            log.warning("MobileNetV2 inference error: %s", exc)
            return "Moderate", 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Form analysis registry
# ─────────────────────────────────────────────────────────────────────────────

FormHandler = Callable[[List[Landmark], PoseAnalyzer], Tuple[Dict, List[str]]]


def _squat(lms: List[Landmark], pa: PoseAnalyzer) -> Tuple[Dict, List[str]]:
    hip, knee, ankle = lms[24], lms[26], lms[28]
    if min(hip.visibility, knee.visibility, ankle.visibility) < 0.5:
        return {}, ["Ensure your full body (side view) is visible."]
    angle = pa.joint_angle(hip, knee, ankle)
    tips  = []
    if angle < 80:
        tips.append("Excellent — below-parallel depth achieved!")
    elif angle < 100:
        tips.append("Parallel depth achieved.")
    else:
        tips.append("Descend further for full range of motion.")
    if lms[26].x < lms[28].x - 0.04:
        tips.append("Knee valgus detected — push knees out over toes.")
    return {"knee_angle_deg": round(angle, 1)}, tips


def _pushup(lms: List[Landmark], pa: PoseAnalyzer) -> Tuple[Dict, List[str]]:
    sh, el, wr = lms[12], lms[14], lms[16]
    if min(sh.visibility, el.visibility, wr.visibility) < 0.5:
        return {}, ["Upper body must be clearly visible from the side."]
    angle = pa.joint_angle(sh, el, wr)
    tips  = []
    if angle > 160:
        tips.append("Arms fully locked out at the top.")
    elif angle < 90:
        tips.append("Good chest-to-floor depth at the bottom.")
    else:
        tips.append("Lower further — aim for 90° elbow flex at bottom.")
    return {"elbow_angle_deg": round(angle, 1)}, tips


def _deadlift(lms: List[Landmark], pa: PoseAnalyzer) -> Tuple[Dict, List[str]]:
    sh, hip, knee = lms[12], lms[24], lms[26]
    if min(sh.visibility, hip.visibility, knee.visibility) < 0.5:
        return {}, ["Stand side-on to camera for deadlift analysis."]
    angle = pa.joint_angle(sh, hip, knee)
    tips  = []
    if 150 <= angle <= 180:
        tips.append("Full hip extension — great lockout!")
    elif angle < 100:
        tips.append("Keep back straight; drive hips forward to lockout.")
    else:
        tips.append("Extend hips fully at the top.")
    return {"hip_angle_deg": round(angle, 1)}, tips


def _lunge(lms: List[Landmark], pa: PoseAnalyzer) -> Tuple[Dict, List[str]]:
    hip, knee, ankle = lms[24], lms[26], lms[28]
    if min(hip.visibility, knee.visibility, ankle.visibility) < 0.5:
        return {}, ["Full leg must be visible."]
    angle = pa.joint_angle(hip, knee, ankle)
    tips  = []
    if angle < 100:
        tips.append("Good lunge depth achieved.")
    else:
        tips.append("Lower back knee closer to the floor.")
    if lms[26].x > lms[28].x + 0.06:
        tips.append("Keep front knee directly over ankle — reduce forward lean.")
    return {"knee_angle_deg": round(angle, 1)}, tips


def _overhead_press(lms: List[Landmark], pa: PoseAnalyzer) -> Tuple[Dict, List[str]]:
    sh, el, wr = lms[12], lms[14], lms[16]
    if min(sh.visibility, el.visibility, wr.visibility) < 0.5:
        return {}, ["Face the camera at a slight angle for OHP analysis."]
    angle = pa.joint_angle(sh, el, wr)
    tips  = []
    if angle > 160:
        tips.append("Full arm extension achieved overhead.")
    elif angle < 90:
        tips.append("Bar at chin level — good start position.")
    else:
        tips.append("Press fully overhead for complete range of motion.")
    return {"elbow_angle_deg": round(angle, 1)}, tips


_FORM_REGISTRY: Dict[str, FormHandler] = {
    "squat":          _squat,
    "pushup":         _pushup,
    "push-up":        _pushup,
    "push_up":        _pushup,
    "deadlift":       _deadlift,
    "lunge":          _lunge,
    "overhead press": _overhead_press,
    "ohp":            _overhead_press,
}


# ─────────────────────────────────────────────────────────────────────────────
# Unified async facade
# ─────────────────────────────────────────────────────────────────────────────

class VisionAnalyzer:
    """
    Single async entry-point for all vision tasks.

    Every method wraps synchronous CPU work in asyncio.to_thread so the
    FastAPI event loop is never blocked.
    """

    def __init__(self) -> None:
        self._pose = PoseAnalyzer()
        self._body = BodyCompositionAnalyzer(self._pose)

    async def analyze_pose(self, image_bytes: bytes) -> PoseResult:
        """MediaPipe pose landmark detection from image bytes."""
        return await asyncio.to_thread(self._pose.run, image_bytes)

    async def analyze_body_composition(
        self,
        image_bytes: bytes,
        user_height_cm: float = 175.0,
        gender: str = "male",
    ) -> BodyCompositionResult:
        """
        MobileNetV2 + RFM body composition estimation.

        Parameters
        ----------
        image_bytes     Raw JPEG / PNG bytes.
        user_height_cm  Known height used for pixel-to-cm calibration.
        gender          "male" or "female" — affects RFM constant.
        """
        return await asyncio.to_thread(
            self._body.run, image_bytes, user_height_cm, gender
        )

    async def analyze_form(
        self,
        exercise_type: str,
        image_bytes: bytes,
    ) -> FormResult:
        """
        Per-exercise joint-angle form analysis.

        Supported exercises: squat, pushup / push-up, deadlift, lunge,
        overhead press / ohp.
        """
        def _run() -> FormResult:
            pose = self._pose.run(image_bytes)
            if not pose.is_valid:
                return FormResult(
                    exercise=exercise_type,
                    is_valid=False,
                    error=pose.error or "Pose detection failed",
                )
            key     = exercise_type.strip().lower()
            handler = _FORM_REGISTRY.get(key)
            if handler is None:
                supported = ", ".join(sorted(_FORM_REGISTRY))
                return FormResult(
                    exercise=exercise_type,
                    is_valid=False,
                    error=(
                        f"'{exercise_type}' is not yet supported. "
                        f"Supported: {supported}."
                    ),
                )
            metrics, feedback = handler(pose.landmarks, self._pose)
            return FormResult(exercise=exercise_type, metrics=metrics,
                              feedback=feedback, is_valid=True)

        return await asyncio.to_thread(_run)


# ── Module-level singleton ─────────────────────────────────────────────────────

vision_analyzer = VisionAnalyzer()
