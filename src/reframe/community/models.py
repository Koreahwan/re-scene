"""
Reframe V7 Community Models (Posts, Versions, Claims, Comments, Counterclaims, Reactions)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Any
from sqlalchemy import String, Integer, DateTime, ForeignKey, Text, UniqueConstraint, Boolean, CheckConstraint, Float, JSON, event
from sqlalchemy.orm import Mapped, mapped_column, relationship, Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.evidence.models import EvidenceCatalog


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        CheckConstraint(
            "content_type = 'MAGAZINE_ARTICLE' OR (work_id IS NOT NULL AND edition_id IS NOT NULL)",
            name="ck_post_work_edition_scope"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    work_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    edition_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    content_type: Mapped[str] = mapped_column(String(32), default="FAN_THEORY", nullable=False)  # DISCOVERY, FAN_THEORY, QUESTION, REWATCH_GUIDE, EVIDENCE_NOTE
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", nullable=False, index=True)  # DRAFT, PUBLISHED, NEEDS_EVIDENCE, DISPUTED, ENGINE_SUPPORTED, CANON_VERIFIED, CONTRADICTED, RETRACTED, REMOVED
    spoiler_scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("spoiler_scopes.id", ondelete="SET NULL"), nullable=True)
    ai_disclosure: Mapped[str] = mapped_column(String(32), default="HUMAN", nullable=False)  # HUMAN, AI_ASSISTED, AI_DRAFT_HUMAN_EDITED, ENGINE_GENERATED_DISCOVERY
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    versions: Mapped[list["PostVersion"]] = relationship("PostVersion", back_populates="post", cascade="all, delete-orphan", foreign_keys="[PostVersion.post_id]")
    claims: Mapped[list["Claim"]] = relationship("Claim", back_populates="post", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship("Comment", back_populates="post", cascade="all, delete-orphan")
    counterclaims: Mapped[list["Counterclaim"]] = relationship("Counterclaim", back_populates="post", cascade="all, delete-orphan")


@event.listens_for(Session, "before_flush")
def validate_post_scope_before_flush(session, flush_context, instances):
    for obj in session.new:
        if isinstance(obj, Post):
            if obj.content_type != "MAGAZINE_ARTICLE" and (obj.work_id is None or obj.edition_id is None):
                raise IntegrityError(
                    "CHECK constraint failed: ck_post_work_edition_scope (Non-magazine post requires work_id and edition_id)",
                    params={"content_type": obj.content_type, "work_id": obj.work_id, "edition_id": obj.edition_id},
                    orig=Exception("Non-magazine post requires work_id and edition_id")
                )


class PostVersion(Base):
    __tablename__ = "post_versions"
    __table_args__ = (
        UniqueConstraint("post_id", "version_no", name="uq_post_version_no"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    body_sanitized_html: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    author_cutoff_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contains_spoilers: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    inspection_status: Mapped[str] = mapped_column(String(64), default="UNVERIFIED_CALLS_DISABLED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    post: Mapped["Post"] = relationship("Post", back_populates="versions", foreign_keys=[post_id])
    evidence_links: Mapped[list["PostEvidenceLink"]] = relationship("PostEvidenceLink", back_populates="post_version", cascade="all, delete-orphan")


class FilmReviewSlot(Base):
    """A durable unique slot serializes review creation across workers and retries."""
    __tablename__ = "film_review_slots"
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    work_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    post_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("posts.id", ondelete="SET NULL"), nullable=True)


class Claim(Base):
    __tablename__ = "claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)

    post: Mapped["Post"] = relationship("Post", back_populates="claims")
    versions: Mapped[list["ClaimVersion"]] = relationship("ClaimVersion", back_populates="claim", cascade="all, delete-orphan")


class ClaimVersion(Base):
    __tablename__ = "claim_versions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    classification: Mapped[str] = mapped_column(String(32), default="STRONG_INTERPRETATION", nullable=False)  # CANON_CLUE, ENGINE_SUPPORTED, STRONG_INTERPRETATION, PLAUSIBLE, SPECULATIVE, DISPUTED
    confidence_label: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    claim: Mapped["Claim"] = relationship("Claim", back_populates="versions")


class PostEvidenceLink(Base):
    __tablename__ = "post_evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_version_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("post_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    claim_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("claim_versions.id", ondelete="SET NULL"), nullable=True)
    evidence_catalog_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_catalog.id", ondelete="RESTRICT"), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), default="SUPPORTS", nullable=False)  # SUPPORTS, REFUTES, CONTEXT, ALTERNATIVE
    annotation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    post_version: Mapped["PostVersion"] = relationship("PostVersion", back_populates="evidence_links")


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    parent_comment_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("comments.id", ondelete="CASCADE"), nullable=True)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    comment_type: Mapped[str] = mapped_column(String(32), default="COMMENT", nullable=False)  # COMMENT, QUESTION, EVIDENCE_ADD, CORRECTION, OTHER_INTERPRETATION
    body_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    body_sanitized_html: Mapped[str] = mapped_column(Text, nullable=False)
    spoiler_scope_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("spoiler_scopes.id", ondelete="SET NULL"), nullable=True)
    author_cutoff_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    contains_spoilers: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    inspection_status: Mapped[str] = mapped_column(String(64), default="UNVERIFIED_CALLS_DISABLED", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="PUBLISHED", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    post: Mapped["Post"] = relationship("Post", back_populates="comments")


class Counterclaim(Base):
    __tablename__ = "counterclaims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    target_claim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("claims.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    challenged_premise: Mapped[str] = mapped_column(Text, nullable=False)
    alternative_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", nullable=False)  # OPEN, SUPPORTED, RESOLVED, WITHDRAWN
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    post: Mapped["Post"] = relationship("Post", back_populates="counterclaims")
    evidence_links: Mapped[list["CounterclaimEvidenceLink"]] = relationship("CounterclaimEvidenceLink", back_populates="counterclaim", cascade="all, delete-orphan")


class CounterclaimEvidenceLink(Base):
    __tablename__ = "counterclaim_evidence_links"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    counterclaim_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("counterclaims.id", ondelete="CASCADE"), nullable=False)
    evidence_catalog_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("evidence_catalog.id", ondelete="RESTRICT"), nullable=False)
    relation: Mapped[str] = mapped_column(String(32), default="SUPPORTS_COUNTERCLAIM", nullable=False)  # SUPPORTS_COUNTERCLAIM, REFUTES_ORIGINAL, CONTEXT

    counterclaim: Mapped["Counterclaim"] = relationship("Counterclaim", back_populates="evidence_links")


class Reaction(Base):
    __tablename__ = "reactions"
    __table_args__ = (
        UniqueConstraint("subject_type", "subject_id", "user_id", "reaction_type", name="uq_reactions_subject_user_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # POST, COMMENT, COUNTERCLAIM
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    reaction_type: Mapped[str] = mapped_column(String(32), nullable=False)  # FUN, NEW_INSIGHT, WELL_SUPPORTED, REWATCH, OTHER_INTERPRETATION, NEEDS_EVIDENCE
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ContentInspectionRecord(Base):
    __tablename__ = "content_inspection_records"
    __table_args__ = (
        UniqueConstraint("content_type", "content_id", "version_no", name="uq_inspection_type_id_ver"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)  # "POST" or "COMMENT"
    content_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(64), default="UNVERIFIED_CALLS_DISABLED", nullable=False)
    detected_cutoff_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    effective_cutoff_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    spoiler_flags: Mapped[Optional[Any]] = mapped_column(JSON, default=list, nullable=True)
    paid_model_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    analysis_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
