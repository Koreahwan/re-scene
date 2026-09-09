from __future__ import annotations
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from reframe.domain.enums import (
    RelationType,
    FactType,
    KnowledgeStatus,
    ReframeRunStatus,
    AbstainReason,
)


class Film(BaseModel):
    movie_id: str
    title: str
    year: int
    runtime_ms: int = 5119080
    language: str = "en"
    source_url: str = ""
    source_hash: str = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"
    rights_status: str = "APPROVED"
    subtitle_source: str = ""
    dataset_version: str = "the_bat_whispers_v3_gemini36"


class Scene(BaseModel):
    movie_id: str
    scene_id: str
    start_ms: int
    end_ms: int
    location: str
    characters: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    summary: str
    dialogue_summary: str = ""
    visual_events: List[str] = Field(default_factory=list)
    caption_segment_ids: List[str] = Field(default_factory=list)
    representative_frame_uris: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None
    source_chunk_id: str = ""
    extraction_version: str = "v3.0"
    dataset_version: str = "the_bat_whispers_v3_gemini36"

    @model_validator(mode="after")
    def validate_timestamps(self) -> Scene:
        if self.start_ms < 0:
            raise ValueError(f"start_ms ({self.start_ms}) must be non-negative")
        if self.end_ms <= self.start_ms:
            raise ValueError(f"end_ms ({self.end_ms}) must be greater than start_ms ({self.start_ms})")
        return self


class Event(BaseModel):
    event_id: str
    movie_id: str
    scene_id: str
    timestamp_ms: int
    actor: str
    action: str
    target: str = ""
    object: str = ""
    event_type: str = "ACTION"
    description: str
    entities: List[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_start_ms: int = 0
    evidence_end_ms: int = 0
    evidence_frame_ids: List[str] = Field(default_factory=list)
    evidence_frame_timestamps_ms: List[int] = Field(default_factory=list)
    dataset_version: str = "the_bat_whispers_v3_gemini36"

    @model_validator(mode="after")
    def populate_evidence_ranges(self) -> Event:
        if self.evidence_start_ms == 0:
            self.evidence_start_ms = self.timestamp_ms
        if self.evidence_end_ms == 0:
            self.evidence_end_ms = self.timestamp_ms
        return self


class Fact(BaseModel):
    fact_id: str
    movie_id: str
    scene_id: str
    timestamp_ms: int
    subject: str
    predicate: str
    object: str
    fact_type: FactType = FactType.OBSERVATION
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_start_ms: int = 0
    evidence_end_ms: int = 0
    evidence_event_ids: List[str] = Field(default_factory=list)
    evidence_frame_ids: List[str] = Field(default_factory=list)
    evidence_frame_timestamps_ms: List[int] = Field(default_factory=list)
    dataset_version: str = "the_bat_whispers_v3_gemini36"

    @model_validator(mode="after")
    def populate_evidence_ranges(self) -> Fact:
        if self.evidence_start_ms == 0:
            self.evidence_start_ms = self.timestamp_ms
        if self.evidence_end_ms == 0:
            self.evidence_end_ms = self.timestamp_ms
        return self


class KnowledgeState(BaseModel):
    knowledge_id: str
    movie_id: str
    subject: str
    predicate: str
    object: str
    status: KnowledgeStatus = KnowledgeStatus.BELIEVED
    valid_from_ms: int
    valid_until_ms: Optional[int] = None
    source_scene_id: str
    confidence: float = 1.0
    dataset_version: str = "the_bat_whispers_v3_gemini36"


class Reveal(BaseModel):
    reveal_id: str
    movie_id: str
    timestamp_ms: int
    timestamp_range: List[int] = Field(default_factory=list)
    title: str
    reveal_type: str = "IDENTITY"
    subject: str
    predicate: str
    previous_belief: str
    revealed_fact: str
    affected_entities: List[str] = Field(default_factory=list)
    importance: float = 1.0
    evidence_scene_ids: List[str] = Field(default_factory=list)
    review_status: str = "APPROVED"
    canonical_asset_sha256: str = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"
    validation_frame_ids: List[str] = Field(default_factory=list)
    human_validation_note: str = ""
    dataset_version: str = "the_bat_whispers_v3_gemini36"


class ReframeCandidate(BaseModel):
    reveal_id: str
    scene_id: str
    movie_id: str
    start_ms: int
    end_ms: int = 0
    evidence_start_ms: int = 0
    evidence_end_ms: int = 0
    summary: str
    dialogue_summary: str = ""
    characters: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    entity_rank: Optional[int] = None
    lexical_rank: Optional[int] = None
    semantic_rank: Optional[int] = None
    rrf_score: float = 0.0
    retrieval_reasons: List[str] = Field(default_factory=list)
    is_summary_pre_cutoff: bool = False
    pre_cutoff_summary: str = ""
    dataset_version: str = "the_bat_whispers_v3_gemini36"


class VerifiedReframe(BaseModel):
    reveal_id: str
    scene_id: str
    relation_type: RelationType
    before_meaning: str
    after_meaning: str
    evidence_event_ids: List[str] = Field(default_factory=list)
    evidence_fact_ids: List[str] = Field(default_factory=list)
    evidence_frame_ids: List[str] = Field(default_factory=list)
    verifier_score: float = Field(default=1.0, ge=0.0, le=1.0)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    unsupported_claims: List[str] = Field(default_factory=list)
    is_supported: bool = True


class ReframedMomentCard(BaseModel):
    scene_id: str
    start_ms: int
    end_ms: int
    location: str
    scene_summary: str
    relation_type: RelationType
    before_meaning: str
    after_meaning: str
    evidence_facts: List[str] = Field(default_factory=list)
    evidence_events: List[str] = Field(default_factory=list)
    evidence_frame_ids: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    representative_frames: List[str] = Field(default_factory=list)
    dataset_version: str = "the_bat_whispers_v3_gemini36"

    @model_validator(mode="after")
    def validate_relation(self) -> ReframedMomentCard:
        if not self.relation_type.is_user_presentable:
            raise ValueError(f"{self.relation_type} is not allowed on final user cards")
        return self


class RetrievalPlan(BaseModel):
    movie_id: str
    reveal_id: str
    spoiler_cutoff_ms: int
    target_entities: List[str]
    lexical_terms: List[str] = Field(default_factory=list)
    limit: int = 30


class ReframeResult(BaseModel):
    run_id: str
    movie_id: str
    reveal_id: str
    spoiler_cutoff_ms: int
    status: ReframeRunStatus
    cards: List[ReframedMomentCard] = Field(default_factory=list)
    abstain_reason: Optional[AbstainReason] = None
    dataset_version: str = "the_bat_whispers_v3_gemini36"
    agent_version: str = "v3.0"


class FanInsight(BaseModel):
    insight_id: str
    movie_id: str
    scene_id: str
    author: str
    title: str
    content: str
    timestamp_ms: int
    likes: int = 0
    created_at: str = "2026-08-18T00:00:00Z"


class ExecutionTrace(BaseModel):
    run_id: str
    movie_id: str
    reveal_id: str
    spoiler_cutoff_ms: int
    mcp_provider: str = "ClickHouse/mcp-clickhouse"
    tool_called: str = "run_query"
    template_id: str = "entity_candidates_sql"
    sql_query: str = ""
    parameters: Dict[str, Any] = Field(default_factory=dict)
    candidates_count: int
    verified_count: int
    latency_ms: float
    model_id: str = "gemini-3.6-flash"
    dataset_version: str = "the_bat_whispers_v3_gemini36"
    timestamp: str = "2026-08-18T00:00:00Z"


