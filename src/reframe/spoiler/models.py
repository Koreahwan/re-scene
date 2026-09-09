"""
Reframe V7 Spoiler Scope Models
"""
import uuid
from typing import Optional, List
from sqlalchemy import String, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base


class SpoilerScope(Base):
    __tablename__ = "spoiler_scopes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    work_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    edition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    minimum_progress_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    required_season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    required_episode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    required_reveal_ids: Mapped[dict] = mapped_column(JSON, default=list, nullable=False)  # List of reveal_ids
    severity: Mapped[str] = mapped_column(String(32), default="MEDIUM", nullable=False)  # LOW, MEDIUM, MAJOR, ENDING
    safe_title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    safe_preview: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
