"""
Reframe V7 Identity & User Models
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, Text, UniqueConstraint, JSON, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint(
            "handle_normalized",
            name="uq_users_handle_normalized",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email_normalized: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    handle: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    handle_normalized: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, SUSPENDED, DELETED
    role: Mapped[str] = mapped_column(String(32), default="USER", nullable=False)  # USER, TRUSTED_REVIEWER, MODERATOR, ADMIN
    account_origin: Mapped[str] = mapped_column(String(32), default="HUMAN", nullable=False)  # HUMAN, SYNTHETIC_DEMO, SYSTEM
    auth_version: Mapped[int] = mapped_column(default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped[Optional["Profile"]] = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    credentials: Mapped[Optional["UserCredential"]] = relationship("UserCredential", back_populates="user", uselist=False, cascade="all, delete-orphan")
    watch_progress: Mapped[list["WatchProgress"]] = relationship("WatchProgress", back_populates="user", cascade="all, delete-orphan")
    spoiler_preferences: Mapped[Optional["SpoilerPreferences"]] = relationship("SpoilerPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    locale: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    fan_depth: Mapped[str] = mapped_column(String(32), default="REGULAR", nullable=False)  # CASUAL, REGULAR, DEEP_ANALYST, FILM_FORM, THEORY_EXPLORER
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="profile")


class WishlistEntry(Base):
    __tablename__ = "film_wishlist"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ProfilePhoto(Base):
    """Small sanitized PNGs live in the database, including multi-instance deployments."""
    __tablename__ = "profile_photos"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    png: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "work_id", "edition_id", name="uq_watch_progress_user_work_edition"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    work_id: Mapped[str] = mapped_column(String(64), nullable=False)
    edition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="NOT_STARTED", nullable=False)  # NOT_STARTED, WATCHING, COMPLETED, ALL_SPOILERS_ALLOWED
    progress_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    season: Mapped[Optional[int]] = mapped_column(nullable=True)
    episode: Mapped[Optional[int]] = mapped_column(nullable=True)
    completed_reveal_ids: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)  # List of reveal_id strings
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="watch_progress")


class SpoilerPreferences(Base):
    __tablename__ = "spoiler_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    default_mode: Mapped[str] = mapped_column(String(16), default="STRICT", nullable=False)  # STRICT, ASK, ALL
    mask_titles: Mapped[bool] = mapped_column(default=True, nullable=False)
    mask_thumbnails: Mapped[bool] = mapped_column(default=True, nullable=False)
    mask_comments: Mapped[bool] = mapped_column(default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="spoiler_preferences")


class UserCredential(Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_algorithm: Mapped[str] = mapped_column(String(32), default="argon2id", nullable=False)
    password_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    failed_attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="credentials")


class AuthOperation(Base):
    __tablename__ = "auth_operations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    operation_type: Mapped[str] = mapped_column(String(32), nullable=False)  # SIGNUP, PASSWORD_RESET
    email_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    ticket_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="STARTED", nullable=False)  # STARTED, TICKET_RESERVED, DB_COMMITTED, TICKET_CONSUMED, COMPLETED, RECONCILIATION_REQUIRED, FAILED
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


# Phase 1 Public Author Identity Constant
PUBLIC_AUTHOR_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000002")


class BrowserWatchProgress(Base):
    """Decoupled per-browser watch progress (Step 2/3 of Phase 1)."""
    __tablename__ = "browser_watch_progress"
    __table_args__ = (
        UniqueConstraint("session_id", "work_id", "edition_id", name="uq_browser_watch_progress_session_work_edition"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    work_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    edition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="NOT_STARTED", nullable=False)  # NOT_STARTED, WATCHING, COMPLETED
    progress_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    completed_reveal_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class BrowserContentUnlock(Base):
    """Decoupled per-browser content unlock for warning confirmation (Step 3 of Phase 1)."""
    __tablename__ = "browser_content_unlocks"
    __table_args__ = (
        UniqueConstraint("session_id", "content_type", "content_id", "version_no", name="uq_browser_content_unlocks"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)  # POST, COMMENT
    content_id: Mapped[uuid.UUID] = mapped_column(Uuid, index=True, nullable=False)
    version_no: Mapped[int] = mapped_column(default=1, nullable=False)
    unlocked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

