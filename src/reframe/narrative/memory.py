"""
Reframe V6/V7 Memory Separation: Blind Narrative Memory vs Canonical Truth Memory
"""
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import structlog

from src.reframe.narrative.blindness import blind_alias
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.evidence.schemas import SceneDTO, EventDTO, FactDTO, RevealDTO

logger = structlog.get_logger(__name__)


class BlindSceneRecord(BaseModel):
    scene_id: str
    start_ms: int
    end_ms: int
    blind_summary: str
    anonymized_characters: List[str]
    anonymized_objects: List[str]
    unresolved_anomalies: List[str] = Field(default_factory=list)


class BlindNarrativeMemory:
    """
    Constructed strictly without knowledge of any future scenes or canonical reveal identities.
    Operates on anonymized entities and pre-cutoff timeline.
    """
    def __init__(self, cutoff_ms: int):
        self.cutoff_ms = cutoff_ms
        self.scenes: Dict[str, BlindSceneRecord] = {}
        self._build_blind_memory()

    def _build_blind_memory(self):
        prior_scenes = v3_adapter.get_scenes(cutoff_ms=self.cutoff_ms)
        for s in prior_scenes:
            blind_sum = blind_alias.anonymize_text(s.summary)
            blind_chars = [blind_alias.anonymize_text(c) for c in s.characters]
            blind_objs = [blind_alias.anonymize_text(o) for o in s.objects]

            self.scenes[s.scene_id] = BlindSceneRecord(
                scene_id=s.scene_id,
                start_ms=s.start_ms,
                end_ms=s.end_ms,
                blind_summary=blind_sum,
                anonymized_characters=blind_chars,
                anonymized_objects=blind_objs,
                unresolved_anomalies=[]
            )


class CanonicalTruthMemory:
    """
    Isolated memory space holding true confirmed identities, hidden goals, and full reveal programs.
    Never directly accessible by blind retrieval channels.
    """
    def __init__(self):
        self.reveals: Dict[str, RevealDTO] = {r.reveal_id: r for r in v3_adapter.get_reveals()}

    def get_canonical_reveal(self, reveal_id: str) -> Optional[RevealDTO]:
        return self.reveals.get(reveal_id)


canonical_memory = CanonicalTruthMemory()
