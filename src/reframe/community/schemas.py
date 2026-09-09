"""
Reframe V7 Community Schemas & Request/Response Envelopes
"""
import uuid
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class PostEvidenceLinkInput(BaseModel):
    evidence_type: str  # scene, event, fact
    evidence_id: str
    relation: str = "SUPPORTS"  # SUPPORTS, REFUTES, CONTEXT, ALTERNATIVE
    annotation: Optional[str] = None


class CreatePostRequest(BaseModel):
    work_id: str = "the-bat-whispers-1930"
    edition_id: str = "tbw-fullscreen-archive"
    content_type: str = "FAN_THEORY"
    title: str = Field(min_length=1, max_length=255)
    body_markdown: str = Field(min_length=1, max_length=10000)
    rating: Optional[int] = Field(None, ge=1, le=5)
    author_cutoff_ms: Optional[int] = Field(None, ge=0)
    contains_spoilers: bool = False
    claim_text: Optional[str] = None
    claim_classification: Optional[str] = "STRONG_INTERPRETATION"
    evidence_links: List[PostEvidenceLinkInput] = Field(default_factory=list)
    tagged_reveal_ids: List[str] = Field(default_factory=list)
    ai_disclosure: str = "HUMAN"


class CreateCounterclaimRequest(BaseModel):
    target_claim_id: uuid.UUID
    challenged_premise: str
    alternative_explanation: str
    evidence_links: List[PostEvidenceLinkInput] = Field(default_factory=list)


class AddReactionRequest(BaseModel):
    reaction_type: str  # WELL_SUPPORTED, NEW_INSIGHT, FUN, REWATCH, NEEDS_EVIDENCE


class PostSummaryDTO(BaseModel):
    post_id: uuid.UUID
    work_id: str
    edition_id: str
    content_type: str
    title: str
    status: str
    visibility: str  # VISIBLE, MASKED, LOCKED
    rating: Optional[int] = None
    author_cutoff_ms: Optional[int] = None
    safe_preview: Optional[Dict[str, Any]] = None
    author_name: str
    evidence_count: int
    claims_count: int
    reactions_count: int
    published_at: Optional[datetime] = None


class PostDetailDTO(BaseModel):
    post_id: uuid.UUID
    work_id: str
    edition_id: str
    content_type: str
    title: str
    body_markdown: str
    body_sanitized_html: str
    status: str
    visibility: str
    rating: Optional[int] = None
    author_cutoff_ms: Optional[int] = None
    safe_preview: Optional[Dict[str, Any]] = None
    author_id: uuid.UUID
    author_name: str
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_links: List[Dict[str, Any]] = Field(default_factory=list)
    counterclaims: List[Dict[str, Any]] = Field(default_factory=list)
    reactions: Dict[str, int] = Field(default_factory=dict)
    published_at: Optional[datetime] = None
