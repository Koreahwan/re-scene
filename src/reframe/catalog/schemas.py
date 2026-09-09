"""
Reframe V7 Film & Reveal Catalog Schemas
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class FilmSummaryDTO(BaseModel):
    movie_id: str
    edition_id: str
    title: str
    year: int
    synopsis_safe: str
    runtime_ms: int
    rights_status: str = "UNCONFIRMED"
    poster_path: Optional[str] = None
    analysis_status: str = "PREPARING"
    available_modes: List[str] = Field(default_factory=lambda: ["STRICT_CANON", "DEEP_READING", "THEORY_LAB"])


class FilmDetailDTO(FilmSummaryDTO):
    directors: List[Any] = Field(default_factory=list)
    cast: List[Any] = Field(default_factory=list)
    genres: List[str] = Field(default_factory=list)
    canonical_asset_sha256: Optional[str] = None
    dataset_version: str
    reveals_count: int
    scenes_count: int
    viewer_progress_ms: int = 0
    viewer_state: str = "NOT_STARTED"


class RevealSummaryDTO(BaseModel):
    reveal_id: str
    work_id: str
    edition_id: str
    title: str
    timestamp_ms: int
    spoiler_cutoff_ms: int
    severity: str = "MAJOR"
    safe_title: Optional[str] = None
    visibility: str = "VISIBLE"  # VISIBLE, MASKED, LOCKED
    is_locked: bool = False
    safe_preview: Optional[Dict[str, Any]] = None


class RevealDetailDTO(RevealSummaryDTO):
    description: Optional[str] = None
    proof_types: List[str] = Field(default_factory=list)
    proof_count: int = 0
