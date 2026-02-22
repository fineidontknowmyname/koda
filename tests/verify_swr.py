"""
tests/verify_swr.py
-------------------
Unit-level verification of the SWR (Shoulder-to-Waist Ratio) feature.

Tests:
  1. SWRCategory enum values
  2. BodyComposition SWR field defaults
  3. calculate_shoulder_waist_ratio — ATHLETIC case
  4. calculate_shoulder_waist_ratio — OVERFAT case
  5. calculate_shoulder_waist_ratio — division-by-zero guard
  6. CapacityEngine SWR adjustment for each category
  7. swr_weight_multiplier for ATHLETIC vs others
"""

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from schemas.vision import BodyComposition, SWRCategory
from services.vision.landmarks import Landmark, calculate_shoulder_waist_ratio
from core.capacity import capacity_engine

_PASS = 0
_FAIL = 0

def _check(label: str, condition: bool, detail: str = ""):
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  ✅ {label}")
    else:
        _FAIL += 1
        print(f"  ❌ {label}  {detail}")


def test_enum():
    print("\n── SWRCategory Enum ──")
    _check("OVERFAT value",  SWRCategory.OVERFAT.value == "overfat")
    _check("BALANCED value", SWRCategory.BALANCED.value == "balanced")
    _check("ATHLETIC value", SWRCategory.ATHLETIC.value == "athletic")


def test_defaults():
    print("\n── BodyComposition Defaults ──")
    bc = BodyComposition()
    _check("shoulder_width_px default",   bc.shoulder_width_px == 0.0)
    _check("waist_width_px default",      bc.waist_width_px == 0.0)
    _check("shoulder_waist_ratio default",bc.shoulder_waist_ratio == 1.1)
    _check("swr_category default",        bc.swr_category == SWRCategory.BALANCED)
    # Ensure existing fields still present
    _check("v_taper_ratio unchanged",     bc.v_taper_ratio is None)
    _check("confidence unchanged",        bc.confidence == 0.0)


def _make_landmarks(
    l_sh_x=0.3, r_sh_x=0.7,  # shoulder spread
    l_hp_x=0.4, r_hp_x=0.6,  # hip spread
    y_sh=0.3, y_hp=0.6,
):
    """Build a 33-landmark list with specified shoulder/hip x-positions."""
    blank = Landmark(x=0.5, y=0.5, z=0.0, visibility=0.9)
    lms = [blank] * 33
    lms[11] = Landmark(x=l_sh_x, y=y_sh, z=0.0, visibility=0.9)
    lms[12] = Landmark(x=r_sh_x, y=y_sh, z=0.0, visibility=0.9)
    lms[23] = Landmark(x=l_hp_x, y=y_hp, z=0.0, visibility=0.9)
    lms[24] = Landmark(x=r_hp_x, y=y_hp, z=0.0, visibility=0.9)
    return lms


def test_swr_athletic():
    print("\n── SWR Calculation (ATHLETIC) ──")
    # Shoulders much wider than hips → ratio > 1.2
    lms = _make_landmarks(l_sh_x=0.2, r_sh_x=0.8, l_hp_x=0.4, r_hp_x=0.6)
    sh, wa, swr, cat = calculate_shoulder_waist_ratio(lms, 640, 480)
    _check("shoulder_width_px > 0",   sh > 0)
    _check("waist_width_px > 0",      wa > 0)
    _check(f"swr={swr:.3f} > 1.2",    swr > 1.2, f"got {swr}")
    _check("category is ATHLETIC",    cat == SWRCategory.ATHLETIC, f"got {cat}")


def test_swr_overfat():
    print("\n── SWR Calculation (OVERFAT) ──")
    # Hips wider than shoulders → ratio < 1.0
    lms = _make_landmarks(l_sh_x=0.4, r_sh_x=0.6, l_hp_x=0.2, r_hp_x=0.8)
    sh, wa, swr, cat = calculate_shoulder_waist_ratio(lms, 640, 480)
    _check(f"swr={swr:.3f} < 1.0",    swr < 1.0, f"got {swr}")
    _check("category is OVERFAT",     cat == SWRCategory.OVERFAT, f"got {cat}")


def test_div_zero():
    print("\n── SWR Division-by-Zero Guard ──")
    # Hips at the same point → waist_width ≈ 0
    lms = _make_landmarks(l_hp_x=0.5, r_hp_x=0.5)
    sh, wa, swr, cat = calculate_shoulder_waist_ratio(lms, 640, 480)
    _check("waist_width_px is 0",     wa == 0.0)
    _check("swr fallback to 1.1",     swr == 1.1, f"got {swr}")
    _check("category fallback BALANCED", cat == SWRCategory.BALANCED)


def test_capacity_swr():
    print("\n── Capacity SWR Adjustment ──")
    bc_overfat = BodyComposition(swr_category=SWRCategory.OVERFAT, is_valid_person=True)
    bc_athletic = BodyComposition(swr_category=SWRCategory.ATHLETIC, is_valid_person=True)
    bc_balanced = BodyComposition(swr_category=SWRCategory.BALANCED, is_valid_person=True)

    _check("OVERFAT  → -0.05", capacity_engine._swr_adjustment(bc_overfat) == -0.05)
    _check("ATHLETIC → +0.05", capacity_engine._swr_adjustment(bc_athletic) == 0.05)
    _check("BALANCED →  0.00", capacity_engine._swr_adjustment(bc_balanced) == 0.0)


def test_weight_multiplier():
    print("\n── SWR Weight Multiplier ──")
    bc_ath = BodyComposition(swr_category=SWRCategory.ATHLETIC)
    bc_bal = BodyComposition(swr_category=SWRCategory.BALANCED)

    _check("ATHLETIC → 1.1",  capacity_engine.swr_weight_multiplier(bc_ath) == 1.1)
    _check("BALANCED → 1.0",  capacity_engine.swr_weight_multiplier(bc_bal) == 1.0)
    _check("None     → 1.0",  capacity_engine.swr_weight_multiplier(None) == 1.0)


if __name__ == "__main__":
    print("=" * 50)
    print("SWR Feature Verification")
    print("=" * 50)
    test_enum()
    test_defaults()
    test_swr_athletic()
    test_swr_overfat()
    test_div_zero()
    test_capacity_swr()
    test_weight_multiplier()
    print(f"\n{'=' * 50}")
    print(f"Results: {_PASS} passed, {_FAIL} failed")
    print("=" * 50)
    if _FAIL:
        sys.exit(1)
