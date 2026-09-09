"""
Reframe V6/V7 Epistemic & Knowledge State Models
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class EpistemicStateType:
    KNOWS = "KNOWS"
    BELIEVES = "BELIEVES"
    SUSPECTS = "SUSPECTS"
    CLAIMS = "CLAIMS"
    DENIES = "DENIES"
    HAS_ACCESS_TO = "HAS_ACCESS_TO"
    HAS_OPPORTUNITY = "HAS_OPPORTUNITY"


class CharacterEpistemicState(BaseModel):
    character_alias: str
    state_type: str  # KNOWS, BELIEVES, CLAIMS, etc.
    proposition: str
    scene_id: str
    timestamp_ms: int
    evidence_event_ids: List[str] = Field(default_factory=list)
    is_conflicted_with_action: bool = False


class AudienceEpistemicState(BaseModel):
    apparent_belief: str
    scene_id: str
    timestamp_ms: int
    active_hypotheses: List[str] = Field(default_factory=list)
    misdirection_elements: List[str] = Field(default_factory=list)
