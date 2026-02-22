"""
services/vision/body_composition.py
--------------------------------------
MobileNetV2 body composition inference service.

Accepts up to three images of the same person (e.g. front, side, back views)
and returns a populated BodyComposition Pydantic model.  All expensive
operations (model inference, OpenCV decode, MediaPipe pose) run in a thread
pool so the FastAPI event loop is never blocked.

Pipeline for each image
────────────────────────
  1. Decode bytes → BGR numpy array (OpenCV)
  2. Validate size / presence of a person (basic heuristic)
  3. Run MobileNetV2 feature extraction (via model_registry.body_composition)
  4. Run MediaPipe pose → RFM body-fat formula + V-taper ratio + posture
  5. Fuse outputs across all provided images → ensemble average

Multi-image fusion
───────────────────
When multiple images are supplied the per-image scalars are averaged and the
qualitative categories (muscle level, body type) are determined by majority
vote.  This improves robustness for the common 3-view photography workflow.

Fallback behaviour
───────────────────
When TensorFlow / the .keras weights are unavailable, inference falls back
to landmark-only estimation (RFM + V-taper from MediaPipe), which still
yields all scalar fields — only the deep-feature-derived categories degrade.

Usage
─────
    from services.vision.body_composition import body_composition_service

    result = await body_composition_service.analyze(
        images=[front_bytes, side_bytes, back_bytes],
        user_height_cm=178.0,
        gender="male",
    )
    # result is a BodyComposition Pydantic model
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import Counter
from typing import List, Optional, Tuple

import cv2
import numpy as np

from schemas.common import MuscleLevel, BodyType
from schemas.vision import BodyComposition, SWRCategory
from services.vision.model_loader import model_registry
from services.vision.landmarks import (
    Landmark,
    calculate_shoulder_waist_ratio,
)

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

_MOBILENET_INPUT_SIZE   = (224, 224)
_MIN_IMAGE_DIMENSION    = 80          # pixels
_MIN_DETECTION_CONF     = 0.50        # MediaPipe threshold
_CRITICAL_LANDMARK_IDX  = [11, 12, 23, 24, 27, 28]

# MobileNetV2 feature-score → MuscleLevel thresholds
_MUSCLE_SCORE_BANDS: List[Tuple[float, MuscleLevel]] = [
    (0.70, MuscleLevel.very_high),
    (0.52, MuscleLevel.high),
    (0.34, MuscleLevel.moderate),
    (0.00, MuscleLevel.low),
]

# V-taper ratio → BodyType heuristic
_VTAPER_BODY_TYPE: List[Tuple[float, BodyType]] = [
    (1.35, BodyType.mesomorph),   # broad shoulders, proportionate hips
    (1.10, BodyType.ectomorph),   # narrower frame
    (0.00, BodyType.endomorph),   # wider hips relative to shoulders
]


# ─────────────────────────────────────────────────────────────────────────────
# Per-image result (internal)
# ─────────────────────────────────────────────────────────────────────────────

class _ImageResult:
    """Raw scalars extracted from a single image."""
    fat_pct:            Optional[float] = None
    v_taper:            Optional[float] = None
    muscle_score:       float           = 0.0
    muscle_level:       Optional[MuscleLevel] = None
    body_type:          Optional[BodyType]    = None
    posture:            Optional[str]         = None
    confidence:         float                  = 0.0
    is_valid:           bool                   = False
    # SWR fields
    shoulder_width_px:  float                  = 0.0
    waist_width_px:     float                  = 0.0
    swr:                float                  = 1.1
    swr_category:       SWRCategory            = SWRCategory.BALANCED


# ─────────────────────────────────────────────────────────────────────────────
# Inference engine (synchronous — called from asyncio.to_thread)
# ─────────────────────────────────────────────────────────────────────────────

class _InferenceEngine:
    """All CPU-bound inference logic; designed to run in a thread pool."""

    def __init__(self) -> None:
        self._mp_pose = None   # lazy mediapipe handle

    # ── MediaPipe lazy init ───────────────────────────────────────────────────

    def _get_pose(self):
        if self._mp_pose is not None:
            return self._mp_pose
        try:
            import mediapipe as mp
            self._mp_pose = mp.solutions.pose.Pose(
                static_image_mode=True,
                model_complexity=1,
                min_detection_confidence=_MIN_DETECTION_CONF,
            )
            log.info("MediaPipe Pose initialised (body_composition pipeline)")
        except ImportError:
            log.warning("mediapipe not installed — landmark-based metrics unavailable")
            self._mp_pose = None
        return self._mp_pose

    # ── Preprocess image ──────────────────────────────────────────────────────

    def _decode(self, image_bytes: bytes) -> Optional[np.ndarray]:
        nparr = np.frombuffer(image_bytes, np.uint8)
        img   = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        if h < _MIN_IMAGE_DIMENSION or w < _MIN_IMAGE_DIMENSION:
            log.debug("Image too small (%dx%d) — skipping", w, h)
            return None
        return img

    def _preprocess_mobilenet(self, img_bgr: np.ndarray) -> np.ndarray:
        """Resize to 224×224 and apply MobileNetV2 pixel scaling [-1, 1]."""
        try:
            import tensorflow as tf
            rgb     = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            resized = cv2.resize(rgb, _MOBILENET_INPUT_SIZE).astype(np.float32)
            return tf.keras.applications.mobilenet_v2.preprocess_input(resized)
        except ImportError:
            return np.zeros((*_MOBILENET_INPUT_SIZE, 3), dtype=np.float32)

    # ── MobileNetV2 feature extraction ────────────────────────────────────────

    def _extract_features(self, img_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        Run image through MobileNetV2 feature extractor (global avg pool).
        Returns 1280-dim feature vector or None when the model is unavailable.
        """
        model = model_registry.body_composition
        if model is None:
            return None

        try:
            tensor   = self._preprocess_mobilenet(img_bgr)
            batch    = np.expand_dims(tensor, axis=0)
            features = model.predict(batch, verbose=0)[0]   # (1280,)
            return features.astype(np.float32)
        except Exception as exc:
            log.warning("MobileNetV2 feature extraction failed: %s", exc)
            return None

    def _features_to_muscle(
        self, features: np.ndarray
    ) -> Tuple[MuscleLevel, float]:
        """Map feature vector → (MuscleLevel, confidence)."""
        hi = float(np.mean(np.abs(features[640:])))
        lo = float(np.mean(np.abs(features[:640])))
        score = hi / max(hi + lo, 1e-9)

        level = MuscleLevel.low
        for threshold, cat in _MUSCLE_SCORE_BANDS:
            if score >= threshold:
                level = cat
                break

        return level, round(min(1.0, score * 1.5), 3)

    # ── MediaPipe landmark metrics ────────────────────────────────────────────

    def _landmark_metrics(
        self,
        img_bgr: np.ndarray,
        user_height_cm: float,
        gender: str,
    ) -> Tuple[
        Optional[float], Optional[float], Optional[str], float,
        float, float, float, SWRCategory,
    ]:
        """
        Returns (body_fat_pct, v_taper_ratio, posture_str, landmark_confidence,
                 shoulder_width_px, waist_width_px, swr, swr_category).
        Any field is None / default when landmarks are insufficient.
        """
        _swr_defaults = (0.0, 0.0, 1.1, SWRCategory.BALANCED)

        pose_handle = self._get_pose()
        if pose_handle is None:
            return None, None, None, 0.0, *_swr_defaults

        rgb     = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        results = pose_handle.process(rgb)
        if not results.pose_landmarks:
            return None, None, None, 0.0, *_swr_defaults

        lms = results.pose_landmarks.landmark
        critical = [lms[i] for i in _CRITICAL_LANDMARK_IDX if i < len(lms)]
        conf = sum(getattr(lm, "visibility", 1.0) for lm in critical) / max(len(critical), 1)
        if conf < _MIN_DETECTION_CONF:
            return None, None, None, conf, *_swr_defaults

        def _xy(idx: int) -> Tuple[float, float]:
            lm = lms[idx]
            return lm.x, lm.y

        l_sh = _xy(11); r_sh = _xy(12)
        l_hp = _xy(23); r_hp = _xy(24)
        l_ak = _xy(27); r_ak = _xy(28)

        def _dist(a: Tuple, b: Tuple) -> float:
            return math.hypot(a[0] - b[0], a[1] - b[1])

        # Height in normalised px for cal
        sh_mid = ((l_sh[0] + r_sh[0]) / 2, (l_sh[1] + r_sh[1]) / 2)
        ak_mid = ((l_ak[0] + r_ak[0]) / 2, (l_ak[1] + r_ak[1]) / 2)
        height_norm = _dist(sh_mid, ak_mid)
        if height_norm < 1e-6:
            return None, None, None, conf, *_swr_defaults

        ppc          = height_norm / max(user_height_cm, 1.0)  # norm-px per cm
        shoulder_cm  = _dist(l_sh, r_sh) / ppc
        hip_cm       = _dist(l_hp, r_hp) / ppc

        # Waist: midpoint between shoulder and hip
        l_waist = ((l_sh[0] + l_hp[0]) / 2, (l_sh[1] + l_hp[1]) / 2)
        r_waist = ((r_sh[0] + r_hp[0]) / 2, (r_sh[1] + r_hp[1]) / 2)
        waist_circ = (_dist(l_waist, r_waist) / ppc) * math.pi

        # RFM body fat (Woolcott & Bergman 2018)
        rfm_k    = 64.0 if gender.lower() == "male" else 76.0
        fat_pct  = rfm_k - (20.0 * (user_height_cm / max(waist_circ, 1.0)))
        fat_pct  = max(3.0, min(50.0, fat_pct))

        # V-taper
        v_taper = shoulder_cm / max(hip_cm, 1.0)

        # Posture heuristic (shoulder tilt)
        tilt = abs(l_sh[1] - r_sh[1])
        if tilt > 0.05:
            posture = "Lateral shoulder tilt detected"
        elif abs(l_sh[0] - r_sh[0]) < 0.02:
            posture = "Good upright alignment"
        else:
            posture = "Slight forward lean"

        # ── SWR from the same landmarks ───────────────────────────────────────
        h, w = img_bgr.shape[:2]
        lm_list = [
            Landmark(x=lm.x, y=lm.y, z=lm.z, visibility=lm.visibility)
            for lm in lms
        ]
        sh_w_px, wa_w_px, swr_val, swr_cat = calculate_shoulder_waist_ratio(
            lm_list, w, h,
        )

        return (fat_pct, v_taper, posture, round(conf, 3),
                sh_w_px, wa_w_px, swr_val, swr_cat)

    # ── Per-image analysis ────────────────────────────────────────────────────

    def analyse_one(
        self,
        image_bytes: bytes,
        user_height_cm: float,
        gender: str,
    ) -> _ImageResult:
        r = _ImageResult()

        img = self._decode(image_bytes)
        if img is None:
            r.posture = "Invalid or too-small image"
            return r

        r.is_valid = True

        # 1. MobileNetV2 features → muscle category
        features = self._extract_features(img)
        if features is not None:
            r.muscle_level, r.confidence = self._features_to_muscle(features)
            r.muscle_score = r.confidence
        else:
            r.muscle_level = MuscleLevel.moderate   # heuristic default
            r.confidence   = 0.0

        # 2. Landmark metrics → fat, v-taper, posture, SWR
        (
            fat, v_taper, posture, lm_conf,
            sh_w_px, wa_w_px, swr_val, swr_cat,
        ) = self._landmark_metrics(img, user_height_cm, gender)

        r.fat_pct           = fat
        r.v_taper           = v_taper
        r.posture           = posture
        r.confidence        = round((r.confidence + lm_conf) / 2, 3)
        r.shoulder_width_px = sh_w_px
        r.waist_width_px    = wa_w_px
        r.swr               = swr_val
        r.swr_category      = swr_cat

        # 3. Body type from V-taper
        if v_taper is not None:
            r.body_type = BodyType.ectomorph   # default
            for threshold, bt in _VTAPER_BODY_TYPE:
                if v_taper >= threshold:
                    r.body_type = bt
                    break

        return r


# ─────────────────────────────────────────────────────────────────────────────
# Public async service
# ─────────────────────────────────────────────────────────────────────────────

class BodyCompositionService:
    """
    Async wrapper that accepts 1–3 images and returns a fused BodyComposition.

    All heavy work runs in asyncio.to_thread (non-blocking for the event loop).
    """

    def __init__(self) -> None:
        self._engine = _InferenceEngine()

    async def analyze(
        self,
        images: List[bytes],
        user_height_cm: float = 175.0,
        gender: str = "male",
    ) -> BodyComposition:
        """
        Infer body composition from 1–3 images (e.g. front, side, rear).

        Parameters
        ----------
        images          List of raw JPEG/PNG byte strings. 1 to 3 images.
                        Extra images beyond 3 are ignored.
        user_height_cm  Known height for pixel-to-cm calibration.
        gender          "male" or "female" — affects RFM constant.

        Returns
        -------
        BodyComposition   Pydantic model with all fields populated.
                          is_valid_person=False when no valid image was decoded.
        """
        if not images:
            return BodyComposition(is_valid_person=False, confidence=0.0)

        # Process up to 3 images in parallel
        selected = images[:3]

        per_image: List[_ImageResult] = await asyncio.gather(
            *[
                asyncio.to_thread(
                    self._engine.analyse_one, img, user_height_cm, gender
                )
                for img in selected
            ]
        )

        valid = [r for r in per_image if r.is_valid]
        if not valid:
            return BodyComposition(
                is_valid_person=False,
                posture_assessment="No valid person detected in any image",
                confidence=0.0,
            )

        return self._fuse(valid)

    # ── Fusion helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _fuse(results: List[_ImageResult]) -> BodyComposition:
        """
        Ensemble-average scalar fields and majority-vote categorical fields
        across all valid per-image results.
        """
        # Scalars — average over images that have the value
        fat_vals    = [r.fat_pct  for r in results if r.fat_pct  is not None]
        vtaper_vals = [r.v_taper  for r in results if r.v_taper  is not None]
        conf_vals   = [r.confidence for r in results]

        avg_fat    = float(np.mean(fat_vals))    if fat_vals    else None
        avg_vtaper = float(np.mean(vtaper_vals)) if vtaper_vals else None
        avg_conf   = float(np.mean(conf_vals))

        # Uncertainty spread → fat_pct range  (±15 % of the estimate, min ±1)
        if avg_fat is not None:
            spread     = max(1.0, avg_fat * 0.15)
            fat_low    = round(max(3.0, avg_fat - spread), 1)
            fat_high   = round(min(50.0, avg_fat + spread), 1)
        else:
            fat_low = fat_high = None

        # Categorical — majority vote
        muscle_counter   = Counter(r.muscle_level for r in results if r.muscle_level)
        body_type_counter= Counter(r.body_type    for r in results if r.body_type)
        posture_vals     = [r.posture for r in results if r.posture]

        muscle_level = muscle_counter.most_common(1)[0][0] if muscle_counter else None
        body_type    = body_type_counter.most_common(1)[0][0] if body_type_counter else None
        posture      = posture_vals[-1] if posture_vals else None   # last (best angle)

        # SWR — average pixel widths and ratio; majority-vote category
        sh_px_vals  = [r.shoulder_width_px for r in results if r.shoulder_width_px > 0]
        wa_px_vals  = [r.waist_width_px    for r in results if r.waist_width_px > 0]
        swr_vals    = [r.swr               for r in results]
        swr_counter = Counter(r.swr_category for r in results)

        avg_sh_px  = float(np.mean(sh_px_vals)) if sh_px_vals else 0.0
        avg_wa_px  = float(np.mean(wa_px_vals)) if wa_px_vals else 0.0
        avg_swr    = float(np.mean(swr_vals))   if swr_vals   else 1.1
        swr_cat    = swr_counter.most_common(1)[0][0] if swr_counter else SWRCategory.BALANCED

        return BodyComposition(
            fat_pct_low=fat_low,
            fat_pct_high=fat_high,
            muscle_level=muscle_level,
            body_type=body_type,
            v_taper_ratio=round(avg_vtaper, 2) if avg_vtaper is not None else None,
            shoulder_width_px=round(avg_sh_px, 2),
            waist_width_px=round(avg_wa_px, 2),
            shoulder_waist_ratio=round(avg_swr, 3),
            swr_category=swr_cat,
            posture_assessment=posture,
            is_valid_person=True,
            confidence=round(avg_conf, 3),
        )


# ── Module-level singleton ─────────────────────────────────────────────────────

body_composition_service = BodyCompositionService()
