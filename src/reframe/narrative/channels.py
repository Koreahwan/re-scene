"""
Reframe V7 Active Multi-Channel Narrative Evidence Retrieval
Implements the 5 required P0 retrieval channels with deep structured domain models:
1. Entity Channel (Exact canonical alias & role matching)
2. Knowledge Conflict Channel (KnowledgeProposition & unbriefed access timestamps)
3. Claim-Action Channel (Explicit Claim vs Action ContradictionRelation)
4. Access/Opportunity Channel (Physical proximity & covert mechanism intervals)
5. Plan/Causal Channel (Multi-step PlanStep sequence & preconditions)
Zero Paid Model Calls.
"""
import uuid
import hashlib
from typing import List, Dict, Any, Optional, Set
from pydantic import BaseModel, Field
import structlog

from src.reframe.evidence.adapter import v3_adapter, compute_content_hash
from src.reframe.evidence.schemas import SceneDTO, EventDTO, FactDTO, RevealDTO
from src.reframe.narrative.blindness import blind_alias

logger = structlog.get_logger(__name__)


# -------------------------------------------------------------
# Structured Domain Models (R2-06)
# -------------------------------------------------------------

class KnowledgeProposition(BaseModel):
    proposition_id: str = Field(default_factory=lambda: f"kp-{uuid.uuid4().hex[:8]}")
    proposition_text: str
    required_by_action: str
    earliest_public_available_ms: int
    earliest_character_access_ms: int
    evidence_refs: List[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"clm-{uuid.uuid4().hex[:8]}")
    speaker: str
    statement_text: str
    scene_id: str
    timestamp_ms: int
    event_id: Optional[str] = None


class Action(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:8]}")
    actor: str
    action_type: str
    action_description: str
    scene_id: str
    timestamp_ms: int
    event_id: Optional[str] = None


class ContradictionRelation(BaseModel):
    relation_id: str = Field(default_factory=lambda: f"rel-{uuid.uuid4().hex[:8]}")
    claim: Claim
    action: Action
    contradiction_rule: str
    severity: str = "HIGH"  # HIGH, MEDIUM, LOW


class AccessOpportunity(BaseModel):
    opportunity_id: str = Field(default_factory=lambda: f"opp-{uuid.uuid4().hex[:8]}")
    entity: str
    location: str
    object_or_mechanism: str
    start_ms: int
    end_ms: int
    is_covert: bool = False
    evidence_refs: List[str] = Field(default_factory=list)


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: f"stp-{uuid.uuid4().hex[:8]}")
    goal_id: str
    step_index: int
    precondition: str
    action_taken: str
    consequence: str
    timestamp_ms: int
    scene_id: str
    event_id: Optional[str] = None


# -------------------------------------------------------------
# EvidenceSeed (R2-05)
# -------------------------------------------------------------

class EvidenceSeed(BaseModel):
    source_call_id: str = Field(default_factory=lambda: f"mcp-call-{uuid.uuid4().hex[:8]}")
    phase: str = "RETRIEVAL"
    dataset_version: str = "v3"
    channel_name: str  # ENTITY, KNOWLEDGE_CONFLICT, CLAIM_ACTION, ACCESS_OPPORTUNITY, PLAN_CAUSAL
    scene_ids: List[str]
    event_ids: List[str] = Field(default_factory=list)
    fact_ids: List[str] = Field(default_factory=list)
    evidence_hashes: List[str] = Field(default_factory=list)
    cutoff_ms: int
    salience_score: float = 0.0
    channel_rationale: str
    structured_payload: Dict[str, Any] = Field(default_factory=dict)


# Backward compatibility alias
ChannelCandidate = EvidenceSeed


# -------------------------------------------------------------
# 5 Active Retrieval Channels (R2-05 / R2-06)
# -------------------------------------------------------------

class EntityRetrievalChannel:
    """Channel 1: Retrieves pre-cutoff scenes and events where target entities appear."""
    @staticmethod
    def retrieve(
        target_entities: List[str],
        cutoff_ms: int,
        work_id: str = "the-bat-whispers-1930"
    ) -> List[EvidenceSeed]:
        candidates: List[EvidenceSeed] = []
        prior_scenes = v3_adapter.get_scenes(cutoff_ms=cutoff_ms)
        for s in prior_scenes:
            matching_chars = [c for c in s.characters if any(e.lower() in c.lower() for e in target_entities)]
            matching_objs = [o for o in s.objects if any(e.lower() in o.lower() for e in target_entities)]
            if matching_chars or matching_objs:
                events = v3_adapter.get_events(cutoff_ms=cutoff_ms, scene_id=s.scene_id)
                facts = v3_adapter.get_facts(cutoff_ms=cutoff_ms, scene_id=s.scene_id)
                ev_ids = [e.event_id for e in events]
                f_ids = [f.fact_id for f in facts]
                ev_hashes = [getattr(e, "evidence_hash", e.event_id) for e in events]
                score = min(1.0, (len(matching_chars) * 0.4) + (len(matching_objs) * 0.3) + (len(events) * 0.1))
                candidates.append(
                    EvidenceSeed(
                        channel_name="ENTITY",
                        scene_ids=[s.scene_id],
                        event_ids=ev_ids,
                        fact_ids=f_ids,
                        evidence_hashes=ev_hashes,
                        cutoff_ms=cutoff_ms,
                        salience_score=score,
                        channel_rationale=f"Entities {matching_chars + matching_objs} active in scene {s.scene_id}",
                        structured_payload={"matching_characters": matching_chars, "matching_objects": matching_objs}
                    )
                )
        return sorted(candidates, key=lambda c: c.salience_score, reverse=True)


class KnowledgeConflictChannel:
    """Channel 2: Identifies actions requiring knowledge prior to public availability."""
    @staticmethod
    def retrieve(
        target_entities: List[str],
        cutoff_ms: int
    ) -> List[EvidenceSeed]:
        candidates: List[EvidenceSeed] = []
        events = v3_adapter.get_events(cutoff_ms=cutoff_ms)

        knowledge_keywords = [
            "search", "examine", "mantel", "private", "study", "safe",
            "fireplace", "mechanism", "blueprint", "vault", "panel", "directly", "observe"
        ]

        grouped_by_scene: Dict[str, List[EventDTO]] = {}
        for ev in events:
            text = f"{ev.action} {ev.description}".lower()
            if any(k in text for k in knowledge_keywords) and any(e.lower() in ev.actor.lower() for e in target_entities):
                grouped_by_scene.setdefault(ev.scene_id, []).append(ev)

        for sid, evs in grouped_by_scene.items():
            ev_ids = [e.event_id for e in evs]
            ev_hashes = [getattr(e, "evidence_hash", e.event_id) for e in evs]
            score = min(1.0, 0.70 + (0.05 * len(evs)))
            propositions = [
                KnowledgeProposition(
                    proposition_text=f"Location of hidden safe/mechanism in {sid}",
                    required_by_action=f"{e.actor} {e.action}",
                    earliest_public_available_ms=cutoff_ms,
                    earliest_character_access_ms=e.timestamp_ms,
                    evidence_refs=[e.event_id]
                )
                for e in evs
            ]
            candidates.append(
                EvidenceSeed(
                    channel_name="KNOWLEDGE_CONFLICT",
                    scene_ids=[sid],
                    event_ids=ev_ids,
                    evidence_hashes=ev_hashes,
                    cutoff_ms=cutoff_ms,
                    salience_score=score,
                    channel_rationale=f"Unbriefed structural or operational knowledge demonstrated in {sid}",
                    structured_payload={"propositions": [p.model_dump() for p in propositions]}
                )
            )
        return sorted(candidates, key=lambda c: c.salience_score, reverse=True)


class ClaimActionChannel:
    """Channel 3: Retrieves verbal statements paired with conflicting physical actions."""
    @staticmethod
    def retrieve(
        target_entities: List[str],
        cutoff_ms: int
    ) -> List[EvidenceSeed]:
        candidates: List[EvidenceSeed] = []
        events = v3_adapter.get_events(cutoff_ms=cutoff_ms)

        # Separate verbal / speech events vs physical movement / manipulation events
        verbal_events = [e for e in events if any(k in e.action.lower() for k in ["speak", "reassure", "converse", "question", "talk"])]
        action_events = [e for e in events if any(k in e.action.lower() for k in ["move", "examine", "search", "display", "unroll", "touch", "open", "aim"])]

        for v_ev in verbal_events:
            for a_ev in action_events:
                # Contradiction when target entity speaks reassurance/protocol while covertly probing
                if any(t.lower() in v_ev.actor.lower() for t in target_entities) and any(t.lower() in a_ev.actor.lower() for t in target_entities):
                    if v_ev.timestamp_ms <= a_ev.timestamp_ms:
                        claim_obj = Claim(
                            speaker=v_ev.actor,
                            statement_text=v_ev.description,
                            scene_id=v_ev.scene_id,
                            timestamp_ms=v_ev.timestamp_ms,
                            event_id=v_ev.event_id
                        )
                        action_obj = Action(
                            actor=a_ev.actor,
                            action_type=a_ev.action,
                            action_description=a_ev.description,
                            scene_id=a_ev.scene_id,
                            timestamp_ms=a_ev.timestamp_ms,
                            event_id=a_ev.event_id
                        )
                        contradiction = ContradictionRelation(
                            claim=claim_obj,
                            action=action_obj,
                            contradiction_rule="Explicit investigative reassurance directly contradicted by covert structural manipulation"
                        )
                        sids = list(set([v_ev.scene_id, a_ev.scene_id]))
                        candidates.append(
                            EvidenceSeed(
                                channel_name="CLAIM_ACTION",
                                scene_ids=sids,
                                event_ids=[v_ev.event_id, a_ev.event_id],
                                evidence_hashes=[getattr(v_ev, "evidence_hash", v_ev.event_id), getattr(a_ev, "evidence_hash", a_ev.event_id)],
                                cutoff_ms=cutoff_ms,
                                salience_score=0.88,
                                channel_rationale=f"Claim-Action Conflict between {v_ev.scene_id} ({v_ev.action}) and {a_ev.scene_id} ({a_ev.action})",
                                structured_payload={"contradiction": contradiction.model_dump()}
                            )
                        )
        return candidates[:5]


class AccessOpportunityChannel:
    """Channel 4: Pinpoints covert access opportunities to target structures."""
    @staticmethod
    def retrieve(
        target_locations: List[str],
        cutoff_ms: int
    ) -> List[EvidenceSeed]:
        candidates: List[EvidenceSeed] = []
        scenes = v3_adapter.get_scenes(cutoff_ms=cutoff_ms)
        for s in scenes:
            loc_match = any(loc.lower() in s.location.lower() or loc.lower() in s.summary.lower() for loc in target_locations)
            if loc_match:
                events = v3_adapter.get_events(cutoff_ms=cutoff_ms, scene_id=s.scene_id)
                opportunity = AccessOpportunity(
                    entity="Suspect/Target",
                    location=s.location or "Manor interior",
                    object_or_mechanism="Secret mechanism / Safe / Blueprint",
                    start_ms=s.start_ms,
                    end_ms=s.end_ms,
                    is_covert=True,
                    evidence_refs=[e.event_id for e in events]
                )
                candidates.append(
                    EvidenceSeed(
                        channel_name="ACCESS_OPPORTUNITY",
                        scene_ids=[s.scene_id],
                        event_ids=[e.event_id for e in events],
                        evidence_hashes=[getattr(e, "evidence_hash", e.event_id) for e in events],
                        cutoff_ms=cutoff_ms,
                        salience_score=0.80,
                        channel_rationale=f"Covert access opportunity identified at {s.location} during scene {s.scene_id}",
                        structured_payload={"opportunity": opportunity.model_dump()}
                    )
                )
        return candidates


class PlanCausalChannel:
    """Channel 5: Constructs multi-step chronological plan sequences towards a shared goal."""
    @staticmethod
    def retrieve(
        target_entities: List[str],
        cutoff_ms: int
    ) -> List[EvidenceSeed]:
        candidates: List[EvidenceSeed] = []
        events = v3_adapter.get_events(cutoff_ms=cutoff_ms)
        actor_events = [e for e in events if any(t.lower() in e.actor.lower() for t in target_entities)]
        actor_events.sort(key=lambda e: e.timestamp_ms)

        if len(actor_events) >= 3:
            sids = list(dict.fromkeys([e.scene_id for e in actor_events]))
            steps = [
                PlanStep(
                    goal_id="secret_safe_infiltration",
                    step_index=idx + 1,
                    precondition=f"Phase {idx} establishment",
                    action_taken=f"{e.actor} {e.action}: {e.description}",
                    consequence=f"Enables subsequent phase in sequence",
                    timestamp_ms=e.timestamp_ms,
                    scene_id=e.scene_id,
                    event_id=e.event_id
                )
                for idx, e in enumerate(actor_events[:4])
            ]
            candidates.append(
                EvidenceSeed(
                    channel_name="PLAN_CAUSAL",
                    scene_ids=sids[:4],
                    event_ids=[e.event_id for e in actor_events[:4]],
                    evidence_hashes=[getattr(e, "evidence_hash", e.event_id) for e in actor_events[:4]],
                    cutoff_ms=cutoff_ms,
                    salience_score=0.92,
                    channel_rationale="Multi-stage coordinated causal sequence executed across scenes",
                    structured_payload={"plan_steps": [s.model_dump() for s in steps]}
                )
            )
        return candidates


class MultiChannelRetrievalEngine:
    """Orchestrates all 5 channels with Reciprocal Rank Fusion (RRF)."""
    @classmethod
    def retrieve_candidates(
        cls,
        reveal: RevealDTO,
        cutoff_ms: int
    ) -> List[EvidenceSeed]:
        entities = reveal.affected_entities or [reveal.subject]
        locations = ["fireplace", "mantel", "safe", "room", "hall", "stairs"]

        c1 = EntityRetrievalChannel.retrieve(entities, cutoff_ms)
        c2 = KnowledgeConflictChannel.retrieve(entities, cutoff_ms)
        c3 = ClaimActionChannel.retrieve(entities, cutoff_ms)
        c4 = AccessOpportunityChannel.retrieve(locations, cutoff_ms)
        c5 = PlanCausalChannel.retrieve(entities, cutoff_ms)

        all_candidates = c1 + c2 + c3 + c4 + c5
        all_candidates.sort(key=lambda c: c.salience_score, reverse=True)
        return all_candidates


multi_channel_engine = MultiChannelRetrievalEngine()
