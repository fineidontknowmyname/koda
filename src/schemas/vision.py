from enum import Enum

from pydantic import BaseModel, Field
from typing import Optional
from schemas.common import MuscleLevel, BodyType


class SWRCategory(str, Enum):
    """Shoulder-to-Waist Ratio classification."""
    OVERFAT  = "overfat"    # swr < 1.0  — waist wider than shoulders
    BALANCED = "balanced"   # 1.0 ≤ swr ≤ 1.2
    ATHLETIC = "athletic"   # swr > 1.2  — strong V-taper

class BodyComposition(BaseModel):
    """
    Rich body composition result from Gemini vision analysis.
    Fat percentage is expressed as a low/high range to reflect visual estimation uncertainty.
    """
    # Body fat range estimate
    fat_pct_low: Optional[float] = Field(
        None, ge=2.0, le=60.0,
        description="Lower bound of estimated body fat percentage"
    )
    fat_pct_high: Optional[float] = Field(
        None, ge=2.0, le=60.0,
        description="Upper bound of estimated body fat percentage"
    )

    # Qualitative assessments
    muscle_level: Optional[MuscleLevel] = Field(
        None, description="Estimated muscle mass level"
    )
    body_type: Optional[BodyType] = Field(
        None, description="Estimated somatotype: ectomorph | mesomorph | endomorph"
    )

    # V-Taper (shoulder-to-waist ratio)
    v_taper_ratio: Optional[float] = Field(
        None, ge=0.5, le=3.0,
        description="Estimated shoulder-width / waist-width ratio"
    )

    # Shoulder-to-Waist Ratio (SWR) — MediaPipe landmark-based
    shoulder_width_px: float = Field(
        default=0.0, ge=0.0,
        description="Pixel-space shoulder width (landmarks 11–12)"
    )
    waist_width_px: float = Field(
        default=0.0, ge=0.0,
        description="Pixel-space waist/hip width (landmarks 23–24)"
    )
    shoulder_waist_ratio: float = Field(
        default=1.1, ge=0.0,
        description="Shoulder width ÷ waist width"
    )
    swr_category: SWRCategory = Field(
        default=SWRCategory.BALANCED,
        description="Classification: overfat | balanced | athletic"
    )

    # Posture
    posture_assessment: Optional[str] = Field(
        None, max_length=200,
        description="Brief posture note e.g. 'Slight anterior pelvic tilt'"
    )

    # Validity & confidence
    is_valid_person: bool = Field(
        True,
        description="False if no clear full-body shot was detected"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Overall model confidence in this analysis (0 = low, 1 = high)"
    )

# Backward-compat alias so existing imports don't break
BodyAnalysisResult = BodyComposition
