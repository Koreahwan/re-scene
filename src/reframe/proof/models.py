"""
Reframe V7 Proof Domain Models
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Integer, Float, DateTime, Text, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from src.reframe.shared.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProofRecord(Base):
    __tablename__ = "proof_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    proof_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    work_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    edition_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(32), default="v3", nullable=False)
    reveal_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    proof_type: Mapped[str] = mapped_column(String(64), nullable=False)  # KNOWLEDGE_LEAK, CLAIM_ACTION_CONFLICT, HIDDEN_PLAN_CHAIN
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    blind_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    reveal_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_chain: Mapped[list] = mapped_column(JSON, nullable=False)
    observed_premises: Mapped[list] = mapped_column(JSON, nullable=False)
    alternative_explanations: Mapped[list] = mapped_column(JSON, nullable=False)
    counterfactual_results: Mapped[dict] = mapped_column(JSON, nullable=False)
    proof_strength: Mapped[float] = mapped_column(Float, default=0.9, nullable=False)
    fan_impact: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    human_review_status: Mapped[str] = mapped_column(String(32), default="NOT_REVIEWED", nullable=False)
    presentation_status: Mapped[str] = mapped_column(String(32), default="PUBLIC", nullable=False)
    trust_namespace: Mapped[str] = mapped_column(String(32), default="ENGINE_INFERENCE", nullable=False)
    trust_label: Mapped[str] = mapped_column(String(64), default="Engine-supported interpretation", nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(64), default="OFFLINE_CANONICAL_FIXTURE", nullable=False)
    asset_sha256: Mapped[str] = mapped_column(String(64), default="8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948", nullable=False)
    correction_overlay_sha: Mapped[str] = mapped_column(String(64), default="8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948", nullable=False)
    evidence_bundle_hash: Mapped[str] = mapped_column(String(64), default="default_evidence_bundle", nullable=False)
    model_id: Mapped[str] = mapped_column(String(64), default="gemini-2.5-flash", nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), default="prompt_v7_canonical", nullable=False)
    retrieval_config_hash: Mapped[str] = mapped_column(String(64), default="5channel_retrieval_v7", nullable=False)
    proof_schema_version: Mapped[str] = mapped_column(String(16), default="1.0.0", nullable=False)
    cache_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
