"""
Reframe V7 Cost Tracking & Budget Reservation Models
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, Integer, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base
from src.reframe.jobs.models import ModelCallClaim


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UsageLedger(Base):
    __tablename__ = "usage_ledger"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    analysis_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=True, index=True)
    model_call_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)  # HYPOTHESIS, CRITIC, JUDGE, THEORY_CHECK
    input_text_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    input_image_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reasoning_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    pricing_version: Mapped[str] = mapped_column(String(32), default="2026-08-gemini", nullable=False)
    billing_reference: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(32), default="USER", nullable=False)  # USER, PROJECT
    reserved_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    released_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    consumed_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)  # ACTIVE, SETTLED, EXPIRED
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
