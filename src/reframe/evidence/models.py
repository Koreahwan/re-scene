"""
Reframe V7 Evidence Catalog Models
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceCatalog(Base):
    __tablename__ = "evidence_catalog"
    __table_args__ = (
        UniqueConstraint("work_id", "edition_id", "dataset_version", "evidence_type", "evidence_id", name="uq_evidence_catalog_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    work_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    edition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)  # scene, event, fact, frame
    evidence_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correction_overlay_sha: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    screen_start_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    screen_end_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, SUPERSEDED, WITHDRAWN, CONFLICT
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    superseded_by: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
