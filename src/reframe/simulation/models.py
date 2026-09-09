"""
Reframe V7 Synthetic Audience Lab & Demo Content Models
Grounded in Nemotron-Personas-USA dataset with strict pseudonymization and provenance.
Zero External Generative Model Calls.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import String, DateTime, ForeignKey, Text, Float, Boolean, JSON, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SyntheticPersona(Base):
    """
    Stores derived safe pseudonymized persona profiles for reproducibility sample,
    demo content authors, and cohort summaries.
    Full 1M+ streaming simulation does not populate raw DB rows for all personas.
    """
    __tablename__ = "synthetic_personas"

    __table_args__ = (
        UniqueConstraint(
            "source_persona_id_hash",
            name="uq_synthetic_persona_hash",
        ),
        UniqueConstraint(
            "demo_user_id",
            name="uq_synthetic_persona_demo_user_id",
        ),
        Index(
            "ix_synthetic_personas_hash",
            "source_persona_id_hash",
        ),
        Index(
            "ix_synthetic_personas_demo_user_id",
            "demo_user_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    source_dataset: Mapped[str] = mapped_column(String(128), default="nvidia/Nemotron-Personas-USA", nullable=False)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    source_persona_id_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), default="en_US", nullable=False)
    display_alias: Mapped[str] = mapped_column(String(64), nullable=False)
    demographic_context: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    fan_traits: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    sampling_weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    is_repro_sample: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    demo_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    provenances: Mapped[list["SyntheticContentProvenance"]] = relationship(
        "SyntheticContentProvenance", back_populates="persona", cascade="all, delete-orphan"
    )



class SyntheticContentProvenance(Base):
    """
    Authoritative deletion and disclosure boundary for all synthetic demo content.
    Tracks provenance back to a specific synthetic persona and simulation run.
    """
    __tablename__ = "synthetic_content_provenance"
    __table_args__ = (
        UniqueConstraint(
            "stable_content_key",
            name="uq_synthetic_content_stable_key",
        ),
        Index(
            "ix_synthetic_provenance_run_id",
            "simulation_run_id",
        ),
        Index(
            "ix_synthetic_provenance_persona_id",
            "persona_id",
        ),
        Index(
            "ix_synthetic_provenance_subject",
            "subject_type",
            "subject_id",
        ),
        Index(
            "ix_synthetic_provenance_key",
            "stable_content_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    simulation_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid, ForeignKey("analysis_runs.id", ondelete="SET NULL"), nullable=True
    )
    persona_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("synthetic_personas.id", ondelete="CASCADE"), nullable=False
    )
    subject_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # POST, COMMENT, COUNTERCLAIM, REACTION, MAGAZINE_ARTICLE
    subject_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    content_origin: Mapped[str] = mapped_column(String(32), default="SYNTHETIC_DEMO", nullable=False)
    generator_mode: Mapped[str] = mapped_column(
        String(64), default="DETERMINISTIC_TEMPLATE_V1", nullable=False
    )  # INTERACTIVE_GEMINI_CURATED_SEED, DETERMINISTIC_TEMPLATE_V1
    content_version: Mapped[str] = mapped_column(String(32), default="v1.0", nullable=False)
    stable_content_key: Mapped[str] = mapped_column(String(128), nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(128), default="nvidia/Nemotron-Personas-USA", nullable=False)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    persona: Mapped["SyntheticPersona"] = relationship("SyntheticPersona", back_populates="provenances")
