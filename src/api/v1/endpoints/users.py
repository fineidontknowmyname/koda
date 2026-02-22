"""
api/v1/endpoints/users.py
--------------------------
User profile CRUD backed by SQLAlchemy (replaces the former in-memory dict).

Validation
──────────
Age 15–60 is enforced by UserMetrics.age (ge=15, le=60) in the Pydantic schema.
Pydantic raises a 422 Unprocessable Entity automatically — no extra code needed.

Storage
───────
Profiles are stored as JSON blobs in the ``user_profiles`` table via the
``UserProfileModel`` ORM model.  This allows rich schema evolution without
DB migrations.  On SQLite (default dev setup) the table is created at startup
via ``create_all_tables()`` in ``main.py``.

Routes
──────
POST  /users/          Create profile   → UserProfile (201)
GET   /users/{id}      Read profile     → UserProfile (200)
PUT   /users/{id}      Replace profile  → UserProfile (200)
DELETE /users/{id}     Remove profile   → 204 No Content
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import UserProfileModel
from db.session import get_db
from schemas.user import UserProfile

log = logging.getLogger(__name__)

router = APIRouter()


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _fetch_or_404(user_id: str, db: AsyncSession) -> UserProfileModel:
    """Return the ORM row or raise HTTP 404."""
    result = await db.execute(
        select(UserProfileModel).where(UserProfileModel.user_id == user_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"User '{user_id}' not found")
    return row


def _next_id(row_count: int) -> str:
    """Simple monotonic ID — replace with UUID or auth-issued ID in production."""
    return str(row_count + 1)


# ── CREATE ─────────────────────────────────────────────────────────────────────

@router.post(
    "/",
    response_model=UserProfile,
    status_code=status.HTTP_201_CREATED,
    summary="Create a user profile",
)
async def create_user_profile(
    user_profile: UserProfile,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Persist a new user profile.

    Age (``biometrics.age``) must be **15–60**; Pydantic validates this
    automatically and returns HTTP 422 on violation.
    """
    # Count existing rows to derive next ID
    from sqlalchemy import func as sa_func
    count_result = await db.execute(select(sa_func.count(UserProfileModel.id)))
    count = count_result.scalar_one()

    user_id = _next_id(count)

    row = UserProfileModel(
        user_id=user_id,
        profile_json=user_profile.model_dump(),
    )
    db.add(row)
    await db.flush()   # get DB-assigned id without committing
    log.info("Created user profile  user_id=%s", user_id)
    return user_profile


# ── READ ───────────────────────────────────────────────────────────────────────

@router.get(
    "/{user_id}",
    response_model=UserProfile,
    summary="Get user profile",
)
async def get_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve a stored user profile by ID."""
    row = await _fetch_or_404(user_id, db)
    return UserProfile.model_validate(row.profile_json)


# ── UPDATE (full replace) ──────────────────────────────────────────────────────

@router.put(
    "/{user_id}",
    response_model=UserProfile,
    summary="Replace user profile",
)
async def update_user_profile(
    user_id: str,
    user_profile: UserProfile,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Fully replace an existing profile.

    Age validation (15–60) is enforced by the Pydantic schema.
    Returns 404 when the user ID does not exist.
    """
    row = await _fetch_or_404(user_id, db)
    row.profile_json = user_profile.model_dump()
    log.info("Updated user profile  user_id=%s", user_id)
    return user_profile


# ── DELETE ─────────────────────────────────────────────────────────────────────

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user profile",
)
async def delete_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a user profile. Returns 204 No Content on success."""
    row = await _fetch_or_404(user_id, db)
    await db.delete(row)
    log.info("Deleted user profile  user_id=%s", user_id)
