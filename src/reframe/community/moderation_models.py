"""Durable comment inspection outbox and conservative spend liabilities."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid
from src.reframe.shared.database import Base


class CommentModerationJob(Base):
    __tablename__ = 'comment_moderation_jobs'
    __table_args__ = (UniqueConstraint('comment_id', 'version_no', name='uq_comment_moderation_version'),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    comment_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False, index=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default='PENDING', nullable=False, index=True)
    reserved_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_micros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CommentModerationBudget(Base):
    __tablename__ = 'comment_moderation_budgets'
    bucket: Mapped[str] = mapped_column(String(32), primary_key=True)
    liability_micros: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
