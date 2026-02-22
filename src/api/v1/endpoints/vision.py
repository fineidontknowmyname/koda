"""
api/v1/endpoints/vision.py
---------------------------
Body composition analysis endpoint backed by on-device MobileNetV2
(via BodyCompositionService) instead of the deprecated Gemini vision API.

Endpoint
────────
POST /vision/analyze-body

  Accepts 1–3 images (front, side, back views) as multipart file uploads.
  Requires explicit user consent via the `X-Vision-Consent: true` header.
  Returns a BodyComposition Pydantic model.

Privacy & consent
──────────────────
Body image analysis is sensitive.  Callers MUST include the header:

    X-Vision-Consent: true

Requests without this header receive HTTP 451 (Unavailable For Legal Reasons).

All inference runs on-device (MediaPipe + MobileNetV2); no image bytes are
sent to any external service.
"""

from __future__ import annotations

import logging
from typing import Annotated, List

from fastapi import (
    APIRouter,
    File,
    Header,
    HTTPException,
    UploadFile,
    status,
)

from schemas.vision import BodyComposition
from services.vision.body_composition import body_composition_service

log = logging.getLogger(__name__)

router = APIRouter()

# ── Constants ──────────────────────────────────────────────────────────────────

_MAX_IMAGE_BYTES  = 10 * 1024 * 1024   # 10 MB per image
_ALLOWED_MIME     = {"image/jpeg", "image/jpg", "image/png", "image/webp"}
_CONSENT_HEADER   = "x-vision-consent"


# ── Consent guard ──────────────────────────────────────────────────────────────

def _require_consent(x_vision_consent: str | None) -> None:
    """Raise HTTP 451 if the caller hasn't sent the consent header."""
    if not x_vision_consent or x_vision_consent.strip().lower() != "true":
        raise HTTPException(
            status_code=status.HTTP_451_UNAVAILABLE_FOR_LEGAL_REASONS,
            detail=(
                "Body image analysis requires explicit consent. "
                "Include the header 'X-Vision-Consent: true' in your request."
            ),
        )


# ── Validation helper ──────────────────────────────────────────────────────────

async def _read_image(file: UploadFile) -> bytes:
    """
    Read and validate a single uploaded image file.

    Raises HTTP 400 for wrong MIME type or oversized files.
    """
    if file.content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{file.content_type}' for '{file.filename}'. "
                f"Accepted types: {', '.join(sorted(_ALLOWED_MIME))}"
            ),
        )

    data = await file.read()

    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Image '{file.filename}' exceeds the {_MAX_IMAGE_BYTES // (1024*1024)} MB limit."
            ),
        )

    if not data:
        raise HTTPException(
            status_code=400,
            detail=f"Image '{file.filename}' is empty.",
        )

    return data


# ── Endpoint ───────────────────────────────────────────────────────────────────

@router.post(
    "/analyze-body",
    response_model=BodyComposition,
    summary="Multi-view body composition analysis (on-device MobileNetV2)",
    description=(
        "Upload 1–3 photos (front, side, rear) for body composition analysis.\n\n"
        "Analysis runs entirely on-device (MobileNetV2 + MediaPipe Pose) — "
        "no image data leaves the server.\n\n"
        "**Required header:** `X-Vision-Consent: true`"
    ),
)
async def analyze_body(
    front: Annotated[UploadFile, File(description="Front-view image (required)")] = ...,
    side:  Annotated[UploadFile | None, File(description="Side-view image (optional)")] = None,
    back:  Annotated[UploadFile | None, File(description="Rear-view image (optional)")] = None,
    x_vision_consent: Annotated[
        str | None,
        Header(alias="X-Vision-Consent", description="Must be 'true' to consent to image analysis"),
    ] = None,
    user_height_cm: float = 175.0,
    gender: str = "male",
) -> BodyComposition:
    """
    Analyse up to three body images and return a `BodyComposition` result.

    Parameters
    ----------
    front           Front-view image (JPEG/PNG/WebP, ≤ 10 MB). Required.
    side            Side-view image. Optional but improves V-taper accuracy.
    back            Rear-view image. Optional.
    x_vision_consent Must be "true" (case-insensitive).
    user_height_cm  Known height used to calibrate pixel → cm scale.
    gender          "male" or "female" — influences the RFM body-fat constant.

    Returns
    -------
    BodyComposition
        `is_valid_person=False` when no clear full-body shot is detected.
    """
    # ── Consent gate ──────────────────────────────────────────────────────────
    _require_consent(x_vision_consent)

    # ── Validate & read images ────────────────────────────────────────────────
    images: List[bytes] = []

    front_bytes = await _read_image(front)
    images.append(front_bytes)

    if side is not None:
        images.append(await _read_image(side))

    if back is not None:
        images.append(await _read_image(back))

    log.info(
        "analyze-body: received %d image(s)  height=%.1f cm  gender=%s",
        len(images), user_height_cm, gender,
    )

    # ── Validate gender param ─────────────────────────────────────────────────
    if gender.lower() not in ("male", "female"):
        raise HTTPException(
            status_code=400,
            detail="'gender' must be 'male' or 'female'.",
        )

    # ── Run inference ─────────────────────────────────────────────────────────
    try:
        result = await body_composition_service.analyze(
            images=images,
            user_height_cm=user_height_cm,
            gender=gender.lower(),
        )
    except Exception as exc:
        log.exception("Body composition analysis failed: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Body composition analysis failed. Please try again.",
        )

    if not result.is_valid_person:
        raise HTTPException(
            status_code=422,
            detail=(
                "No clear full-body person detected in the provided image(s). "
                "Please upload well-lit, full-body photographs."
            ),
        )

    return result
