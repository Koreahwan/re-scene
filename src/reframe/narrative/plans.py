"""
Reframe V6/V7 Goal, Plan & Deception Models
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    step_id: str
    order: int
    scene_id: str
    timestamp_ms: int
    actor: str
    action: str
    apparent_surface_goal: str
    concealed_reveal_goal: str
    preconditions_met: List[str] = Field(default_factory=list)
    evidence_event_ids: List[str] = Field(default_factory=list)


class HiddenPlanChain(BaseModel):
    chain_id: str
    goal_name: str
    actor: str
    steps: List[PlanStep] = Field(default_factory=list)
    coherence_score: float = 0.90
