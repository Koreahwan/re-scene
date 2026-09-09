"""
Reframe V6/V7 Typed Narrative Graph & Path Traversal
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class TypedNarrativeEdge(BaseModel):
    edge_id: str
    source_id: str  # event_id, fact_id, or anomaly_id
    target_id: str
    edge_type: str  # CAUSES, ENABLES, PREVENTS, MOTIVATES, EXPLAINS, CONTRADICTS, REQUIRES_KNOWLEDGE_OF, REQUIRES_ACCESS_TO, SATISFIES_PLAN_STEP
    evidence_event_ids: List[str] = Field(default_factory=list)
    evidence_fact_ids: List[str] = Field(default_factory=list)
    evidence_frame_ids: List[str] = Field(default_factory=list)
    confidence: float = 0.95


class TypedGraphPath(BaseModel):
    path_id: str
    start_scene_id: str
    end_scene_id: str
    edges: List[TypedNarrativeEdge] = Field(default_factory=list)
    narrative_explanation: str
