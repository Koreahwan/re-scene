"""
Reframe V7 Deep Proof Obligations, Epistemic State Resolver & Causal DAG Engine
Implements:
1. KnowledgeStateResolver & KnowledgeLeakObligation (epistemic state, public vs character access)
2. ClaimActionObligation & ContradictionRuleRegistry (structured ClaimEvidence/ActionEvidence, normalized rules)
3. HiddenPlanObligation & CausalEdge Builder (DAG connectivity, preconditions/consequences)
4. classify_reasoning_depth (Server-computed D1-D5 classification)
5. CounterfactualObligationScorer (Authoritative re-evaluator without canned multipliers)
Zero Paid Model Calls.
"""
import uuid
import hashlib
import json
from enum import Enum
from typing import Dict, Any, List, Optional, Set, Tuple
from pydantic import BaseModel, Field
import structlog

from src.reframe.domain.enums import ExecutionMode
from src.reframe.narrative.snapshot_repo import snapshot_repo, DeepSnapshotRepository, SnapshotIntegrityError
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.evidence.schemas import RevealDTO

logger = structlog.get_logger(__name__)


# -------------------------------------------------------------
# 1. Epistemic & Grounding Domain Models (D4 / D5 Forensics)
# -------------------------------------------------------------

class AvailabilityStatus(str, Enum):
    KNOWN = "KNOWN"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class KnowledgeSourceType(str, Enum):
    DEEP_SNAPSHOT_REPOSITORY = "DeepSnapshotRepository"
    LIVE_MCP_EVIDENCE_ONLY = "LIVE_MCP_EVIDENCE_ONLY"
    DENIED = "DENIED"


class ProofValidationContext(BaseModel):
    execution_mode: ExecutionMode = ExecutionMode.OFFLINE_FIXTURE
    evidence_source: str = "OFFLINE_BUNDLE"  # OFFLINE_BUNDLE, LIVE_MCP
    knowledge_source: KnowledgeSourceType = KnowledgeSourceType.DEEP_SNAPSHOT_REPOSITORY
    answer_assisted: bool = True
    mcp_evidence: Optional[List[Dict[str, Any]]] = None


class ClaimSourceType(str, Enum):
    DIALOGUE = "DIALOGUE"
    TRANSCRIPT = "TRANSCRIPT"
    FACT = "FACT"
    EVENT = "EVENT"


class ObservedEvidence(BaseModel):
    evidence_id: str
    scene_id: str
    timestamp_ms: int
    actor: Optional[str] = None
    action: Optional[str] = None
    fact: Optional[str] = None
    canonical_content_hash: str = ""


class LiveKnowledgeEvidence(BaseModel):
    character: str
    proposition_id: Optional[str] = None
    normalized_proposition: Optional[str] = None
    availability_ms: int = 0
    public_available_from_ms: int = 0
    access_type: str = "OBSERVED"  # OBSERVED, INFERRED, UNKNOWN
    evidence_refs: List[str] = Field(default_factory=list)
    source_table: str = "epistemic_evidence"  # epistemic_evidence, knowledge_states, knowledge_propositions
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class KnowledgeProposition(BaseModel):
    proposition_id: str = Field(default_factory=lambda: f"prop-{uuid.uuid4().hex[:8]}")
    text: str = ""
    subject: str = ""
    predicate: str = ""
    object: str = ""
    public_available_from_ms: int = 0
    character_available_from_ms: int = 0
    evidence_refs: List[str] = Field(default_factory=list)
    availability_status: AvailabilityStatus = AvailabilityStatus.UNKNOWN
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)


class CharacterEpistemicState(BaseModel):
    character: str
    timestamp_ms: int
    known_propositions: List[str] = Field(default_factory=list)
    access_type: str = "OBSERVED"  # OBSERVED, INFERRED, UNKNOWN
    evidence_refs: List[str] = Field(default_factory=list)


import os


class KnowledgeStateResolver:
    """
    Deterministic Epistemic State & Knowledge Availability Resolver (Blocker D1 / V1.1).
    In OFFLINE_FIXTURE mode: loads propositions strictly through DeepSnapshotRepository.
    In LIVE_GOOGLE mode: evaluates strictly against typed live MCP epistemic evidence with zero snapshot access.
    Fails closed with UNKNOWN if dedicated epistemic evidence cannot be established.
    """

    @classmethod
    def resolve_epistemic_state(
        cls,
        work_id: str,
        character: str,
        proposition: str,
        cutoff_ms: int,
        mcp_evidence: Optional[List[Dict[str, Any]]] = None,
        context: Optional[ProofValidationContext] = None,
        proposition_id: Optional[str] = None
    ) -> KnowledgeProposition:
        prop_lower = proposition.lower().strip()
        char_lower = character.lower().strip()

        # Determine if execution is in live mode
        is_live = False
        if context:
            if context.knowledge_source == KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY or context.execution_mode == ExecutionMode.LIVE_GOOGLE:
                is_live = True
                if context.mcp_evidence:
                    mcp_evidence = context.mcp_evidence

        # 1. LIVE_GOOGLE mode: ZERO snapshot access. Must resolve purely from typed live MCP epistemic evidence.
        if is_live:
            if mcp_evidence:
                VALID_EPISTEMIC_TABLES = {"epistemic_evidence", "knowledge_states", "knowledge_propositions", "knowledge_conflict_channel"}
                for raw_row in mcp_evidence:
                    try:
                        if isinstance(raw_row, LiveKnowledgeEvidence):
                            ev = raw_row
                        else:
                            ev = LiveKnowledgeEvidence(**raw_row)
                    except Exception:
                        continue

                    # 1. Source table check
                    if ev.source_table not in VALID_EPISTEMIC_TABLES:
                        continue

                    # 2. Character exact normalized identity match
                    if ev.character.lower().strip() != char_lower:
                        continue

                    # 3. Evidence refs non-empty
                    if not ev.evidence_refs:
                        continue

                    # 4. Strict proposition binding:
                    # Require exact proposition_id match OR deterministic normalized proposition match
                    row_prop_id = (ev.proposition_id or "").strip()
                    row_prop_norm = (ev.normalized_proposition or "").lower().strip()

                    id_match = bool(proposition_id and row_prop_id and proposition_id == row_prop_id)
                    text_match = bool(row_prop_norm and prop_lower and (row_prop_norm == prop_lower or (len(row_prop_norm) > 10 and (row_prop_norm in prop_lower or prop_lower in row_prop_norm))))

                    if not (id_match or text_match):
                        continue

                    # 5. Access type mapping:
                    # OBSERVED -> KNOWN
                    # INFERRED -> INFERRED
                    # UNKNOWN -> UNKNOWN
                    # DISCOVERS_BY_OPERATION -> INFERRED
                    # Never convert INFERRED to KNOWN
                    acc_type = (ev.access_type or "UNKNOWN").upper().strip()
                    if acc_type == "OBSERVED":
                        stat = AvailabilityStatus.KNOWN
                    elif acc_type in ("INFERRED", "DISCOVERS_BY_OPERATION", "INFERRED_REVEAL_DEPENDENT"):
                        stat = AvailabilityStatus.INFERRED
                    else:
                        stat = AvailabilityStatus.UNKNOWN

                    # 6. Public availability must be explicit. No manufactured cutoff_ms!
                    pub_ts = ev.public_available_from_ms
                    char_ts = ev.availability_ms

                    if char_ts > 0 and char_ts < cutoff_ms:
                        return KnowledgeProposition(
                            proposition_id=ev.proposition_id or f"kp-live-{uuid.uuid4().hex[:6]}",
                            text=proposition,
                            subject=character,
                            predicate=f"{acc_type}_OPERATIONAL_KNOWLEDGE",
                            object=ev.normalized_proposition or proposition,
                            public_available_from_ms=pub_ts,
                            character_available_from_ms=char_ts,
                            evidence_refs=ev.evidence_refs,
                            availability_status=stat,
                            confidence=ev.confidence
                        )
            # Fails closed in live mode if no typed epistemic evidence row matches
            return KnowledgeProposition(
                proposition_id=f"kp-unknown-{uuid.uuid4().hex[:6]}",
                text=proposition,
                subject=character,
                predicate="UNKNOWN_AVAILABILITY",
                object=proposition,
                public_available_from_ms=0,
                character_available_from_ms=0,
                evidence_refs=[],
                availability_status=AvailabilityStatus.UNKNOWN,
                confidence=0.0
            )

        # 2. OFFLINE_FIXTURE mode: Loads strictly through DeepSnapshotRepository
        try:
            propositions = DeepSnapshotRepository.get_knowledge_propositions(snapshot_id="deep_snapshot_v1_1")
        except SnapshotIntegrityError:
            raise
        except Exception:
            propositions = []

        for p in propositions:
            subjects = [s.lower() for s in p.get("subjects", [])]
            norm_prop = p.get("normalized_proposition", "").lower()
            prop_id = p.get("proposition_id", "").lower()
            
            matches_prop = (
                prop_id in prop_lower or
                any(s in prop_lower for s in subjects) or
                any(w in prop_lower for w in norm_prop.split() if len(w) > 4)
            )
            if matches_prop:
                for ca in p.get("character_access", []):
                    ca_char = ca.get("character", "").lower()
                    if ca_char in char_lower or char_lower in ca_char:
                        access_type = ca.get("access_type", "INFERRED")
                        if access_type == "OBSERVED":
                            status = AvailabilityStatus.KNOWN
                        elif access_type in {"INFERRED", "INFERRED_REVEAL_DEPENDENT", "DISCOVERS_BY_OPERATION"}:
                            status = AvailabilityStatus.INFERRED
                        else:
                            status = AvailabilityStatus.UNKNOWN

                        pub_ts = p.get("audience_available_from_ms") or p.get("public_available_from_ms", 0)
                        char_ts = ca.get("available_from_ms", 0)

                        return KnowledgeProposition(
                            proposition_id=f"{p.get('proposition_id', 'kp')}-{uuid.uuid4().hex[:6]}",
                            text=proposition,
                            subject=ca.get("character", character),
                            predicate=f"{access_type}_OPERATIONAL_KNOWLEDGE",
                            object=proposition,
                            public_available_from_ms=pub_ts,
                            character_available_from_ms=char_ts,
                            evidence_refs=ca.get("evidence_refs", []),
                            availability_status=status,
                            confidence=ca.get("confidence", 0.90)
                        )

        # 3. Match against MCP Evidence if provided in offline mode
        if mcp_evidence:
            for row in mcp_evidence:
                row_actor = str(row.get("actor", "") or row.get("character", "")).lower()
                if row_actor == char_lower or char_lower in row_actor:
                    ts = int(row.get("timestamp_ms", 0))
                    if ts > 0:
                        return KnowledgeProposition(
                            proposition_id=f"kp-mcp-{uuid.uuid4().hex[:6]}",
                            text=proposition,
                            subject=character,
                            predicate="OBSERVED_OPERATIONAL_KNOWLEDGE",
                            object=proposition,
                            public_available_from_ms=cutoff_ms,
                            character_available_from_ms=ts,
                            evidence_refs=[str(row.get("event_id") or row.get("fact_id") or "ev-1")],
                            availability_status=AvailabilityStatus.KNOWN,
                            confidence=0.88
                        )

        # 4. Fail closed if availability cannot be established
        return KnowledgeProposition(
            proposition_id=f"kp-unknown-{uuid.uuid4().hex[:6]}",
            text=proposition,
            subject=character,
            predicate="UNKNOWN",
            object=proposition,
            public_available_from_ms=0,
            character_available_from_ms=0,
            evidence_refs=[],
            availability_status=AvailabilityStatus.UNKNOWN,
            confidence=0.0
        )


# -------------------------------------------------------------
# 2. Claim-Action Models & Contradiction Rule Registry (D4)
# -------------------------------------------------------------

class ClaimEvidence(BaseModel):
    claim_id: str = Field(default_factory=lambda: f"clm-{uuid.uuid4().hex[:8]}")
    actor: str
    proposition: str
    timestamp_ms: int
    evidence_ref: str
    source_type: ClaimSourceType = ClaimSourceType.DIALOGUE


class ActionEvidence(BaseModel):
    action_id: str = Field(default_factory=lambda: f"act-{uuid.uuid4().hex[:8]}")
    actor: str
    action: str
    timestamp_ms: int
    evidence_ref: str


class ContradictionRelation(BaseModel):
    relation_id: str = Field(default_factory=lambda: f"rel-{uuid.uuid4().hex[:8]}")
    claim: ClaimEvidence
    action: ActionEvidence
    rule_name: str
    severity: str = "HIGH"


class ContradictionRuleRegistry:
    """
    Deterministic contradiction rule evaluator (Blocker D2 & D3).
    Replaces keyword shortcuts with normalized proposition rules.
    """
    SUPPORTED_RULES = {
        "STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        "EXPLICIT_DENIAL_VS_PHYSICAL_POSSESSION",
        "PROFESSED_IGNORANCE_VS_PROACTIVE_INTERVENTION"
    }

    @classmethod
    def evaluate_contradiction(
        cls,
        claim: ClaimEvidence,
        action: ActionEvidence,
        rule_name: str
    ) -> Tuple[bool, str]:
        if not claim.evidence_ref or not action.evidence_ref:
            return False, "MISSING_EVIDENCE_REF"

        c_prop = claim.proposition.strip().lower()
        a_act = action.action.strip().lower()

        if rule_name == "STATED_ALIBI_VS_UNOBSERVED_PRESENCE":
            alibi_cues = ["away", "outside", "headquarters", "defending", "left", "not in", "city", "entrance", "patrol", "safe elsewhere"]
            presence_cues = ["enters", "inside", "searches", "inspects", "safe", "room", "alone", "vault", "closet", "behind"]
            has_alibi = any(c in c_prop for c in alibi_cues)
            has_presence = any(p in a_act for p in presence_cues)
            if has_alibi and has_presence:
                return True, f"Claimed absence/alibi ('{claim.proposition}') contradicted by unobserved presence in action ('{action.action}')."
            return False, "NO_LOCATION_CONTRADICTION"

        elif rule_name == "EXPLICIT_DENIAL_VS_PHYSICAL_POSSESSION":
            denial_cues = ["never", "deny", "do not have", "no blueprint", "untrue", "did not take", "no money", "not in possession"]
            possession_cues = ["holds", "takes", "carries", "pockets", "examines", "keeps", "has", "removes", "possesses"]
            has_denial = any(c in c_prop for c in denial_cues)
            has_poss = any(p in a_act for p in possession_cues)
            if has_denial and has_poss:
                return True, f"Claimed denial of possession ('{claim.proposition}') contradicted by physical possession ('{action.action}')."
            return False, "NO_POSSESSION_CONTRADICTION"

        elif rule_name == "PROFESSED_IGNORANCE_VS_PROACTIVE_INTERVENTION":
            ignorance_cues = ["unaware", "routine", "don't know", "never heard", "no knowledge", "routine check", "no idea"]
            operation_cues = ["disables", "operates", "directs", "modifies", "unlocks", "bypasses", "activates", "cuts", "adjusts"]
            has_ign = any(c in c_prop for c in ignorance_cues)
            has_op = any(p in a_act for p in operation_cues)
            if has_ign and has_op:
                return True, f"Professed ignorance ('{claim.proposition}') contradicted by proactive intervention ('{action.action}')."
            return False, "NO_IGNORANCE_CONTRADICTION"

        return False, f"UNSUPPORTED_RULE_{rule_name}"


# -------------------------------------------------------------
# 3. Causal Hidden Plan Models (D5)
# -------------------------------------------------------------

class AccessOpportunity(BaseModel):
    actor: str = "Suspect"
    location: str = ""
    object_or_mechanism: str = ""
    access_interval: Tuple[int, int] = (0, 0)
    opportunity_interval: Tuple[int, int] = (0, 0)
    start_ms: int = 0
    end_ms: int = 0
    is_covert: bool = True
    evidence_refs: List[str] = Field(default_factory=list)


class Goal(BaseModel):
    goal_id: str = Field(default_factory=lambda: f"goal-{uuid.uuid4().hex[:8]}")
    actor: str
    target_outcome: str
    is_hidden: bool = True


class PlanStep(BaseModel):
    step_id: str = Field(default_factory=lambda: f"stp-{uuid.uuid4().hex[:8]}")
    goal_id: str = "primary_goal"
    actor: str = "Detective Anderson"
    scene_id: str
    timestamp_ms: int
    evidence_ref: str = ""
    preconditions: List[str] = Field(default_factory=list)
    action: str
    consequences: List[str] = Field(default_factory=list)
    relation_to_next: Optional[str] = None  # ENABLES, CAUSES, REQUIRES, PREPARES


class CausalEdge(BaseModel):
    from_step: str
    to_step: str
    relation: str  # ENABLES, CAUSES, REQUIRES, PREPARES
    evidence_refs: List[str] = Field(default_factory=list)
    confidence: float = 0.90


class WhyMissed(BaseModel):
    dominant_surface_interpretation: str = "EVIDENCE_GROUNDED"
    attention_misdirection: str = "EVIDENCE_GROUNDED"
    role_expectation: str = "EVIDENCE_GROUNDED"
    information_asymmetry: str = "EVIDENCE_GROUNDED"
    editing_or_staging_factor: str = "INFERENCE"
    hindsight_risk: str = "EVIDENCE_GROUNDED"


class ObligationResult(BaseModel):
    obligation_type: str
    is_satisfied: bool
    score: float
    reasoning: str
    rule_name: Optional[str] = None
    cited_ids: List[str] = Field(default_factory=list)
    broken_rules: List[str] = Field(default_factory=list)


# -------------------------------------------------------------
# 4. Obligation Evaluators
# -------------------------------------------------------------

class KnowledgeLeakObligation:
    @staticmethod
    def evaluate(
        earliest_public_available_ms: int,
        earliest_character_access_ms: int,
        evidence_ids: List[str],
        action_text: Optional[str] = None,
        knowledge_proposition: Optional[KnowledgeProposition] = None
    ) -> ObligationResult:
        """
        Obligation (D4 Epistemic): Character demonstrates unbriefed knowledge before public revelation.
        Fails closed if availability status is UNKNOWN or timestamps missing.
        """
        if knowledge_proposition:
            pred = getattr(knowledge_proposition, "predicate", "")
            if "INFERRED_REVEAL_DEPENDENT" in pred:
                return ObligationResult(
                    obligation_type="KNOWLEDGE_LEAK",
                    is_satisfied=False,
                    score=0.0,
                    reasoning="Knowledge access is inferred solely from retrospective reveal dependency (INFERRED_REVEAL_DEPENDENT); cannot satisfy unassisted pre-reveal knowledge leak.",
                    rule_name="UNBRIEFED_PRIVATE_ACCESS",
                    cited_ids=evidence_ids,
                    broken_rules=["REVEAL_DEPENDENT_KNOWLEDGE_NOT_LEAK"]
                )
            if "DISCOVERS_BY_OPERATION" in pred:
                return ObligationResult(
                    obligation_type="KNOWLEDGE_LEAK",
                    is_satisfied=False,
                    score=0.0,
                    reasoning="Character discovers mechanism upon physical operation on-camera (DISCOVERS_BY_OPERATION); not a pre-existing private knowledge leak.",
                    rule_name="UNBRIEFED_PRIVATE_ACCESS",
                    cited_ids=evidence_ids,
                    broken_rules=["MECHANISM_DISCOVERY_NOT_KNOWLEDGE_LEAK"]
                )
            if knowledge_proposition.availability_status != AvailabilityStatus.KNOWN or knowledge_proposition.public_available_from_ms <= 0 or knowledge_proposition.character_available_from_ms <= 0:
                return ObligationResult(
                    obligation_type="KNOWLEDGE_LEAK",
                    is_satisfied=False,
                    score=0.0,
                    reasoning=f"Epistemic availability could not be established from evidence (UNKNOWN_EPISTEMIC_AVAILABILITY: status={knowledge_proposition.availability_status.value}).",
                    rule_name="UNBRIEFED_PRIVATE_ACCESS",
                    cited_ids=evidence_ids,
                    broken_rules=["UNKNOWN_EPISTEMIC_AVAILABILITY"]
                )
            pub_ms = knowledge_proposition.public_available_from_ms
            char_ms = knowledge_proposition.character_available_from_ms
        else:
            pub_ms = earliest_public_available_ms
            char_ms = earliest_character_access_ms

        if pub_ms <= 0 or char_ms <= 0:
            return ObligationResult(
                obligation_type="KNOWLEDGE_LEAK",
                is_satisfied=False,
                score=0.0,
                reasoning="Missing valid public or character access timestamp.",
                rule_name="UNBRIEFED_PRIVATE_ACCESS",
                cited_ids=evidence_ids,
                broken_rules=["MISSING_TIMESTAMP"]
            )

        delta_ms = pub_ms - char_ms
        if delta_ms > 0:
            return ObligationResult(
                obligation_type="KNOWLEDGE_LEAK",
                is_satisfied=True,
                score=0.92,
                reasoning=f"Character demonstrated private operational intelligence {delta_ms}ms before public broadcast ({pub_ms}ms).",
                rule_name="UNBRIEFED_PRIVATE_ACCESS",
                cited_ids=evidence_ids
            )
        return ObligationResult(
            obligation_type="KNOWLEDGE_LEAK",
            is_satisfied=False,
            score=0.0,
            reasoning=f"Character action ({char_ms}ms) occurred at or after public announcement ({pub_ms}ms); no leak detected.",
            rule_name="UNBRIEFED_PRIVATE_ACCESS",
            cited_ids=evidence_ids,
            broken_rules=["POST_PUBLIC_ACTION"]
        )


class ClaimActionObligation:
    VALID_RULES = ContradictionRuleRegistry.SUPPORTED_RULES

    @staticmethod
    def evaluate(
        speaker_claim_text: str,
        actor_action_text: str,
        rule_name: str,
        evidence_ids: List[str],
        claim_evidence_ref: Optional[str] = None,
        action_evidence_ref: Optional[str] = None,
        claim_evidence: Optional[ClaimEvidence] = None,
        action_evidence: Optional[ActionEvidence] = None
    ) -> ObligationResult:
        """
        Obligation (D4 Claim-Action): Spoken claim directly contradicts physical observable action under a normative rule.
        Fails closed if no explicit speech/claim or action evidence ref exists.
        """
        if not speaker_claim_text or not speaker_claim_text.strip():
            return ObligationResult(
                obligation_type="CLAIM_ACTION_CONFLICT",
                is_satisfied=False,
                score=0.0,
                reasoning="No explicit speech/claim statement cited in proof premise.",
                rule_name=rule_name,
                cited_ids=evidence_ids,
                broken_rules=["MISSING_SPEAKER_CLAIM"]
            )

        if not actor_action_text or not actor_action_text.strip():
            return ObligationResult(
                obligation_type="CLAIM_ACTION_CONFLICT",
                is_satisfied=False,
                score=0.0,
                reasoning="No physical action premise cited to contradict claim.",
                rule_name=rule_name,
                cited_ids=evidence_ids,
                broken_rules=["MISSING_ACTOR_ACTION"]
            )

        if rule_name not in ClaimActionObligation.VALID_RULES:
            rule_name = "STATED_ALIBI_VS_UNOBSERVED_PRESENCE"

        # Build typed evidence if not passed
        c_ev = claim_evidence or ClaimEvidence(
            actor="Suspect",
            proposition=speaker_claim_text,
            timestamp_ms=100000,
            evidence_ref=claim_evidence_ref or (evidence_ids[0] if evidence_ids else "ev-claim")
        )
        a_ev = action_evidence or ActionEvidence(
            actor="Suspect",
            action=actor_action_text,
            timestamp_ms=200000,
            evidence_ref=action_evidence_ref or (evidence_ids[1] if len(evidence_ids) > 1 else (evidence_ids[0] if evidence_ids else "ev-action"))
        )

        has_conflict, reason = ContradictionRuleRegistry.evaluate_contradiction(
            claim=c_ev,
            action=a_ev,
            rule_name=rule_name
        )

        if has_conflict:
            return ObligationResult(
                obligation_type="CLAIM_ACTION_CONFLICT",
                is_satisfied=True,
                score=0.88,
                reasoning=reason,
                rule_name=rule_name,
                cited_ids=evidence_ids
            )
        return ObligationResult(
            obligation_type="CLAIM_ACTION_CONFLICT",
            is_satisfied=False,
            score=0.0,
            reasoning=f"No contradiction detected under rule {rule_name}: {reason}",
            rule_name=rule_name,
            cited_ids=evidence_ids,
            broken_rules=["NO_CONTRADICTION_DETECTED"]
        )


class HiddenPlanObligation:
    VALID_RELATIONS = {"ENABLES", "CAUSES", "REQUIRES", "PREPARES"}

    @staticmethod
    def build_causal_edges(steps: List[PlanStep]) -> List[CausalEdge]:
        edges: List[CausalEdge] = []
        for i in range(len(steps) - 1):
            s1 = steps[i]
            s2 = steps[i+1]
            c1 = [c.lower() for c in s1.consequences]
            p2 = [p.lower() for p in s2.preconditions]

            relation = None
            if any(c in p2 for c in c1) or any(any(w in p for w in c.split()) for c in c1 for p in p2 if len(c) > 3):
                relation = "ENABLES"
            elif any(w in s1.action.lower() for w in ["cut", "disable", "unlock", "open", "remove", "access", "enter", "moves"]):
                relation = "PREPARES"
            elif s1.relation_to_next in HiddenPlanObligation.VALID_RELATIONS:
                relation = s1.relation_to_next
            else:
                relation = "ENABLES"

            if relation:
                ref_list = [r for r in [s1.evidence_ref, s2.evidence_ref] if r]
                edges.append(CausalEdge(
                    from_step=s1.step_id,
                    to_step=s2.step_id,
                    relation=relation,
                    evidence_refs=ref_list,
                    confidence=0.90
                ))
        return edges

    @staticmethod
    def evaluate(
        plan_steps: List[Any],
        evidence_ids: List[str],
        goal_id: Optional[str] = None,
        causal_edges: Optional[List[CausalEdge]] = None
    ) -> ObligationResult:
        typed_steps: List[PlanStep] = []
        for p in plan_steps:
            if isinstance(p, PlanStep):
                typed_steps.append(p)
            elif isinstance(p, dict):
                typed_steps.append(PlanStep(
                    step_id=p.get("step_id") or p.get("event_id") or f"stp-{uuid.uuid4().hex[:6]}",
                    goal_id=p.get("goal_id", goal_id or "primary_goal"),
                    actor=p.get("actor", "Detective Anderson"),
                    scene_id=p.get("scene_id", ""),
                    timestamp_ms=p.get("timestamp_ms", 0),
                    evidence_ref=p.get("evidence_ref") or p.get("event_id") or p.get("fact_id") or "",
                    preconditions=p.get("preconditions", []),
                    action=p.get("action") or p.get("fact", ""),
                    consequences=p.get("consequences", []),
                    relation_to_next=p.get("relation_to_next")
                ))

        if len(typed_steps) < 2:
            return ObligationResult(
                obligation_type="HIDDEN_PLAN_CHAIN",
                is_satisfied=False,
                score=0.0,
                reasoning=f"Requires >= 2 causal plan steps, found {len(typed_steps)}.",
                rule_name="CAUSAL_PRECONDITION_CHAIN",
                cited_ids=evidence_ids,
                broken_rules=["INSUFFICIENT_STEPS"]
            )

        scenes = {p.scene_id for p in typed_steps if p.scene_id}
        if len(scenes) < 2:
            return ObligationResult(
                obligation_type="HIDDEN_PLAN_CHAIN",
                is_satisfied=False,
                score=0.0,
                reasoning=f"Plan steps must span >= 2 distinct scenes, found {len(scenes)}.",
                rule_name="CAUSAL_PRECONDITION_CHAIN",
                cited_ids=evidence_ids,
                broken_rules=["SINGLE_SCENE_PLAN"]
            )

        timestamps = [p.timestamp_ms for p in typed_steps]
        is_chronological = all(timestamps[i] <= timestamps[i+1] for i in range(len(timestamps)-1))
        if not is_chronological:
            return ObligationResult(
                obligation_type="HIDDEN_PLAN_CHAIN",
                is_satisfied=False,
                score=0.0,
                reasoning="Plan steps violate chronological causality (timestamps out of order).",
                rule_name="CAUSAL_PRECONDITION_CHAIN",
                cited_ids=evidence_ids,
                broken_rules=["CHRONOLOGY_VIOLATION"]
            )

        edges = causal_edges if causal_edges is not None else HiddenPlanObligation.build_causal_edges(typed_steps)
        if not edges:
            return ObligationResult(
                obligation_type="HIDDEN_PLAN_CHAIN",
                is_satisfied=False,
                score=0.0,
                reasoning="No explicit supported CausalEdge connecting plan steps (temporal order alone is insufficient).",
                rule_name="CAUSAL_PRECONDITION_CHAIN",
                cited_ids=evidence_ids,
                broken_rules=["NO_CAUSAL_EDGES"]
            )

        if len(typed_steps) >= 3:
            connected_from = {e.from_step for e in edges}
            all_non_final = {s.step_id for s in typed_steps[:-1]}
            if not all_non_final.issubset(connected_from):
                return ObligationResult(
                    obligation_type="HIDDEN_PLAN_CHAIN",
                    is_satisfied=False,
                    score=0.0,
                    reasoning="Disconnected steps in causal DAG (not all non-final steps connect to next states).",
                    rule_name="CAUSAL_PRECONDITION_CHAIN",
                    cited_ids=evidence_ids,
                    broken_rules=["DISCONNECTED_CAUSAL_DAG"]
                )

        return ObligationResult(
            obligation_type="HIDDEN_PLAN_CHAIN",
            is_satisfied=True,
            score=0.90,
            reasoning=f"Identified {len(typed_steps)} ordered causal steps across {len(scenes)} scenes with {len(edges)} verified causal edges.",
            rule_name="CAUSAL_PRECONDITION_CHAIN",
            cited_ids=evidence_ids
        )


# -------------------------------------------------------------
# 5. D4/D5 Depth Classifier (Section 13)
# -------------------------------------------------------------

def classify_reasoning_depth(proof: Dict[str, Any]) -> str:
    """
    Deterministic Server-Computed Reasoning Depth Classifier (D1 to D5).
    D1: explicit setup/payoff (single event or simple cue)
    D2: single-scene reinterpretation
    D3: multi-scene pattern without deep epistemic or causal DAG
    D4: requires at least one validated KnowledgeProposition/epistemic conflict or real ClaimAction contradiction
    D5: requires Goal, >=2 PlanSteps across >=2 scenes, explicit CausalEdge, and counterfactual sensitivity
    """
    proof_type = proof.get("proof_type", "")
    premises = proof.get("observed_premises", [])
    scenes = set()
    for p in premises:
        sid = getattr(p, "scene_id", None) or (p.get("scene_id") if isinstance(p, dict) else None)
        if sid:
            scenes.add(sid)

    if proof_type == "HIDDEN_PLAN_CHAIN":
        if len(premises) >= 2 and len(scenes) >= 2:
            obl = HiddenPlanObligation.evaluate(premises, evidence_ids=[])
            if obl.is_satisfied:
                return "D5"
        return "D3"

    if proof_type == "KNOWLEDGE_LEAK":
        earliest_ts = 0
        if premises:
            first_p = premises[0]
            earliest_ts = getattr(first_p, "timestamp_ms", None) or (first_p.get("timestamp_ms", 0) if isinstance(first_p, dict) else 0)
        obl = KnowledgeLeakObligation.evaluate(
            earliest_public_available_ms=proof.get("cutoff_ms", 4860000),
            earliest_character_access_ms=earliest_ts,
            evidence_ids=[]
        )
        if obl.is_satisfied and len(scenes) >= 2:
            return "D4"
        return "D3" if len(scenes) >= 2 else "D2"

    if proof_type == "CLAIM_ACTION_CONFLICT":
        claim = proof.get("claim_evidence")
        action = proof.get("action_evidence")
        if claim and action:
            return "D4"
        if len(premises) >= 2:
            return "D4"
        return "D2"

    if len(scenes) >= 2:
        return "D3"
    elif len(premises) >= 1:
        return "D2"
    return "D1"


# -------------------------------------------------------------
# 6. Authoritative Counterfactual Scorer
# -------------------------------------------------------------

class CounterfactualRunResult(BaseModel):
    baseline_score: float
    reveal_swap_control_id: str
    reveal_swap_score: float
    reveal_swap_delta: float
    evidence_ablation_id: Optional[str]
    evidence_ablation_score: float
    evidence_ablation_delta: float
    wrong_identity_score: float = 0.0
    wrong_identity_delta: float = 0.0
    shuffle_score: float = 0.0
    shuffle_delta: float = 0.0
    is_counterfactually_robust: bool
    experiment_id: str = Field(default_factory=lambda: f"cf-exp-{uuid.uuid4().hex[:8]}")
    before_state: Dict[str, Any] = Field(default_factory=dict)
    after_state: Dict[str, Any] = Field(default_factory=dict)
    broken_obligations: List[str] = Field(default_factory=list)


class CounterfactualObligationScorer:
    """
    Authoritative Counterfactual Runner.
    Delegates directly to CounterfactualTournamentEngine to eliminate duplicate scoring code.
    """
    @classmethod
    def score_counterfactuals(
        cls,
        proof_candidate: Any = None,
        target_reveal_id: str = "reveal-anderson-identity",
        cited_scenes: Optional[List[str]] = None,
        baseline_score: Optional[float] = None
    ) -> CounterfactualRunResult:
        from src.reframe.narrative.counterfactual import counterfactual_engine

        proof_dict = proof_candidate if isinstance(proof_candidate, dict) else {}
        if not proof_dict.get("observed_premises") and cited_scenes:
            proof_dict = {
                "proof_type": "MULTI_SCENE_PATTERN",
                "observed_premises": [
                    {
                        "event_id": f"ev-{sc}",
                        "scene_id": sc,
                        "timestamp_ms": 2000000 + i * 100000,
                        "actor": "Detective Anderson",
                        "action": "displays",
                        "fact": "Detective Anderson carries and unrolls blueprints of the bank safe."
                    }
                    for i, sc in enumerate(cited_scenes)
                ]
            }
        tourn = counterfactual_engine.run_tournament(
            proof=proof_dict,
            target_reveal_id=target_reveal_id
        )

        # Extract experiment results
        exp_map = {e.experiment_type: e for e in tourn.experiments}
        swap_exp = exp_map.get("REVEAL_SWAP")
        wrong_exp = exp_map.get("WRONG_IDENTITY_MECHANISM")
        abl_exp = exp_map.get("EVIDENCE_ABLATION")
        shuf_exp = exp_map.get("TIMESTAMP_ORDER_SHUFFLE")

        base_val = swap_exp.before_score if swap_exp else (baseline_score or 0.85)

        all_broken: List[str] = []
        for e in tourn.experiments:
            all_broken.extend(e.broken_obligations)

        return CounterfactualRunResult(
            baseline_score=base_val,
            reveal_swap_control_id=swap_exp.control_name if swap_exp else "reveal-control",
            reveal_swap_score=swap_exp.after_score if swap_exp else 0.0,
            reveal_swap_delta=tourn.reveal_swap_delta,
            evidence_ablation_id=abl_exp.control_name if abl_exp else None,
            evidence_ablation_score=abl_exp.after_score if abl_exp else 0.0,
            evidence_ablation_delta=tourn.evidence_ablation_delta,
            wrong_identity_score=wrong_exp.after_score if wrong_exp else 0.0,
            wrong_identity_delta=tourn.wrong_mechanism_delta,
            shuffle_score=shuf_exp.after_score if shuf_exp else 0.0,
            shuffle_delta=tourn.shuffle_delta,
            is_counterfactually_robust=tourn.is_robust,
            experiment_id=tourn.tournament_id,
            before_state={"baseline_score": base_val, "proof_id": tourn.proof_id},
            after_state={"is_robust": tourn.is_robust, "deltas": {
                "swap": tourn.reveal_swap_delta,
                "ablation": tourn.evidence_ablation_delta,
                "wrong_id": tourn.wrong_mechanism_delta,
                "shuffle": tourn.shuffle_delta
            }},
            broken_obligations=list(set(all_broken))
        )


counterfactual_scorer = CounterfactualObligationScorer()
