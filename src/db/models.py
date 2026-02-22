"""
db/models.py
-------------
SQLAlchemy ORM models for Koda.

Tables
──────
user_records         Authenticated user account + profile blob
user_profiles        Legacy profile table (backward compat — kept for existing rows)
fitness_plan_records Generated fitness plans linked to a user + Celery job

Design choices
──────────────
* Rich nested schemas (UserProfile, FitnessPlan) are stored as JSON blobs.
  This avoids a large migration burden when the Pydantic schema evolves and
  keeps all business logic in Python / Pydantic, not in SQL constraints.
* Timestamps use server_default=func.now() so they are set by the DB,
  not by the Python process clock (avoids timezone drift in multi-worker env).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from db.base import Base


# ── User account record ────────────────────────────────────────────────────────

class UserRecord(Base):
    """
    Authenticated user account.

    ``profile_json`` stores the full ``UserProfile.model_dump()`` so the
    Pydantic schema can evolve without DB migrations.
    """

    __tablename__ = "user_records"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Public-facing stable identifier (e.g. "1", "42", or a UUID string)
    user_id      = Column(String(64), unique=True, nullable=False, index=True)

    # Optional auth fields — populate when JWT / auth layer is wired
    email        = Column(String(255), unique=True, nullable=True, index=True)
    hashed_password = Column(String(256), nullable=True)
    is_active    = Column(Boolean, default=True, nullable=False)

    # Full Pydantic UserProfile stored as JSON
    profile_json = Column(JSON, nullable=True,
                          comment="Serialised UserProfile (biometrics, goals, etc.)")

    # Vision consent — mirrors UserProfile.analysis_consent
    analysis_consent = Column(Boolean, default=False, nullable=False)

    created_at   = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at   = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One user → many plans
    plans = relationship(
        "FitnessPlanRecord",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<UserRecord id={self.id} user_id={self.user_id!r} email={self.email!r}>"


# ── Fitness plan record ────────────────────────────────────────────────────────

class FitnessPlanRecord(Base):
    """
    A generated fitness plan tied to a user and a Celery job.

    ``plan_json`` stores ``FitnessPlan.model_dump()``; status tracks the
    async Celery pipeline so the poll endpoint can reflect progress.
    """

    __tablename__ = "fitness_plan_records"

    id           = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Celery task ID — also the public job_id returned to the client
    job_id       = Column(String(64), unique=True, nullable=False, index=True)

    # FK to the user who requested the plan
    user_id      = Column(
        String(64),
        ForeignKey("user_records.user_id", ondelete="CASCADE"),
        nullable=True,   # Nullable so plans can be generated without an account
        index=True,
    )

    # ── Pipeline state ──────────────────────────────────────────────────────────
    # Mirrors Celery task states: pending | running | done | failed
    status       = Column(String(16), default="pending", nullable=False, index=True)

    # Input snapshot (de-normalised for audit / replay)
    request_json = Column(JSON, nullable=True,
                          comment="Serialised GeneratePlanRequest sent by the client")

    # Output
    plan_json    = Column(JSON, nullable=True,
                          comment="Serialised FitnessPlan — populated when status=done")

    # Error message when status=failed
    error_detail = Column(Text, nullable=True)

    # Source YouTube URLs (convenience column for analytics)
    youtube_urls = Column(JSON, nullable=True,
                          comment="List of YouTube URLs used to generate this plan")

    created_at   = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship back to the user
    user = relationship("UserRecord", back_populates="plans")

    def __repr__(self) -> str:
        return (
            f"<FitnessPlanRecord id={self.id} job_id={self.job_id!r} "
            f"status={self.status!r} user_id={self.user_id!r}>"
        )


# ── Legacy alias (backward compat with users.py which imports UserProfileModel) ─

UserProfileModel = UserRecord
