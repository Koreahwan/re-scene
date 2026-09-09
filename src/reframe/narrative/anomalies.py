"""
Reframe V6/V7 Blind Anomaly Ledger
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class NarrativeAnomalyType:
    KNOWLEDGE_LEAK = "KNOWLEDGE_LEAK"
    CLAIM_ACTION_CONFLICT = "CLAIM_ACTION_CONFLICT"
    DUAL_PURPOSE_ACTION = "DUAL_PURPOSE_ACTION"
    UNEXPLAINED_ACTION = "UNEXPLAINED_ACTION"
    ALIBI_GAP = "ALIBI_GAP"
    ACCESS_ANOMALY = "ACCESS_ANOMALY"


class NarrativeAnomaly(BaseModel):
    anomaly_id: str
    anomaly_type: str
    scene_id: str
    timestamp_ms: int
    actor_alias: str
    description: str
    evidence_event_ids: List[str] = Field(default_factory=list)
    initial_confidence: float = 0.8
    unresolved_without_reveal: bool = True
