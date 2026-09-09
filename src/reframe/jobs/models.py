"""
Reframe V7 Durable Job Models (AnalysisRuns, RunSteps, RunEvents, Idempotency)
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import String, Integer, BigInteger, Float, Boolean, DateTime, ForeignKey, Text, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_type: Mapped[str] = mapped_column(String(32), default="REFRAME", nullable=False)  # REFRAME, THEORY_VALIDATION, EVALUATION
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    work_id: Mapped[str] = mapped_column(String(64), nullable=False)
    edition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    reveal_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="QUEUED", nullable=False, index=True)  # QUEUED, RUNNING, COMPLETED, FAILED, ABSTAINED
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proof_schema_version: Mapped[str] = mapped_column(String(16), default="1.0.0", nullable=False)
    cost_reserved_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    cost_actual_micros: Mapped[int] = mapped_column(
        BigInteger,
        default=0,
        nullable=False,
    )
    proof_ids: Mapped[Optional[list]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=True,
    )
    config_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_detail_redacted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    steps: Mapped[list["AnalysisRunStep"]] = relationship("AnalysisRunStep", back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list["AnalysisRunEvent"]] = relationship("AnalysisRunEvent", back_populates="run", cascade="all, delete-orphan")


class AnalysisRunStep(Base):
    __tablename__ = "analysis_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    step_type: Mapped[str] = mapped_column(String(64), nullable=False)  # RETRIEVAL, HYPOTHESIS, CRITIC, JUDGE, VALIDATION
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    output_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="PENDING", nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    worker_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    model_call_ids: Mapped[Optional[list]] = mapped_column(
        JSON,
        default=list,
        server_default="[]",
        nullable=True,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    artifact_uri: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    output_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)

    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="steps")



class AnalysisRunEvent(Base):
    __tablename__ = "analysis_run_events"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)  # status, step, completed, error
    safe_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    run: Mapped["AnalysisRun"] = relationship("AnalysisRun", back_populates="events")


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("principal_id", "route_key", "idempotency_key", name="uq_idempotency_principal_route_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    principal_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # user_id or client IP
    route_key: Mapped[str] = mapped_column(String(128), nullable=False)  # e.g. POST:/api/v1/reframe-runs
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body_ref: Mapped[str] = mapped_column(Text, nullable=False)  # JSON or artifact URI
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelCallClaim(Base):
    __tablename__ = "model_call_claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    model_call_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    analysis_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("analysis_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(64), default="REASONING", nullable=False)
    state: Mapped[str] = mapped_column(String(32), default="CLAIMED", nullable=False)  # CLAIMED, SUCCEEDED, FAILED, NEEDS_RECONCILIATION
    estimated_cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    actual_cost_micros: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class CounterfactualRunRecord(Base):
    __tablename__ = "counterfactual_run_records"

    __table_args__ = (
        UniqueConstraint(
            "experiment_id",
            name="uq_counterfactual_experiment_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    experiment_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    proof_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    proof_input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    experiment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    control_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    before_score: Mapped[float] = mapped_column(Float, nullable=False)
    after_score: Mapped[float] = mapped_column(Float, nullable=False)
    before_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)
    after_state: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)
    delta: Mapped[float] = mapped_column(Float, nullable=False)
    broken_obligations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    is_robust: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


