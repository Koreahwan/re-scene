"""
Reframe V7 Evidence & Dataset Version-Pinned DTO Schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class EvidenceRefDTO(BaseModel):
    work_id: str
    edition_id: str
    dataset_version: str
    evidence_type: str  # scene, event, fact, frame
    evidence_id: str
    evidence_content_hash: str
    correction_overlay_sha: Optional[str] = None


class SceneDTO(BaseModel):
    scene_id: str
    work_id: str
    edition_id: str
    dataset_version: str
    start_ms: int
    end_ms: int
    duration_ms: int
    summary: str
    location: Optional[str] = "Oakdale Manor"
    characters: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    evidence_hash: str


class EventDTO(BaseModel):
    event_id: str
    scene_id: str
    work_id: str
    edition_id: str
    dataset_version: str
    timestamp_ms: int
    evidence_start_ms: int
    evidence_end_ms: int
    actor: str
    action: str
    target: Optional[str] = None
    object: Optional[str] = None
    description: str
    evidence_frame_ids: List[str] = Field(default_factory=list)
    evidence_frame_timestamps_ms: List[int] = Field(default_factory=list)
    evidence_hash: str
    is_corrected: bool = False
    correction_overlay_sha: Optional[str] = None


class FactDTO(BaseModel):
    fact_id: str
    scene_id: str
    work_id: str
    edition_id: str
    dataset_version: str
    timestamp_ms: int
    subject: str
    predicate: str
    object: str
    confidence: float
    evidence_frame_ids: List[str] = Field(default_factory=list)
    evidence_hash: str


class EvidenceFrameDTO(BaseModel):
    frame_id: str
    scene_id: str
    work_id: str
    edition_id: str
    timestamp_ms: int
    canonical_asset_sha256: str
    file_sha256: Optional[str] = None


class RevealDTO(BaseModel):
    reveal_id: str
    work_id: str
    edition_id: str
    dataset_version: str
    title: str
    reveal_type: str
    timestamp_ms: int
    spoiler_cutoff_ms: int
    subject: str
    predicate: str
    previous_belief: str
    revealed_fact: str
    affected_entities: List[str] = Field(default_factory=list)
    evidence_scene_ids: List[str] = Field(default_factory=list)
    importance: float = 1.0
    canonical_asset_sha256: str


class CanonicalCorrectionDTO(BaseModel):
    target_type: str  # event, fact, scene
    target_id: str
    scene_id: str
    field: str
    original_value: Any
    corrected_value: Any
    description_corrected: Optional[str] = None
    entities_corrected: Optional[List[str]] = None
    validation_frame_ids: List[str] = Field(default_factory=list)
    timestamp_ms: int
    canonical_asset_sha256: str
    human_review_reason: str
    overlay_sha256: Optional[str] = None
