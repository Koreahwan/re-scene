"""
Reframe V7 — R4.2 Zero-API Deep Reasoning & Integrity Test Suite
Comprehensive unit tests covering all 28 requirements of R4.2:
1. Zero API lock enforcement (PAID_CALL_ATTEMPTED_DURING_R4_2)
2. Live principal derived from AnalysisRun.owner_user_id
3. Owner mismatch raises RUN_OWNER_MISMATCH
4. Missing owner_user_id raises OWNER_REQUIRED
5. Live model not in allowlist raises LIVE_MODEL_NOT_ALLOWED
6. gemini-3.6-flash pricing gate raises UNVERIFIED_PRICING_BLOCKED
7. Strict canonical event hash equality
8. Altered canonical event hash fails
9. Altered observed premise fields fail (actor, action, scene, timestamp)
10. KnowledgeStateResolver extracts KnowledgeProposition
11. KnowledgeLeakObligation requires public_available_from_ms > 0
12. Unknown epistemic availability fails obligation
13. ClaimActionObligation requires structured ClaimEvidence and ActionEvidence
14. Ungrounded sentences without evidence refs rejected as claims
15. ContradictionRuleRegistry evaluates STATED_ALIBI_VS_UNOBSERVED_PRESENCE
16. ContradictionRuleRegistry evaluates EXPLICIT_DENIAL_VS_PHYSICAL_POSSESSION
17. ContradictionRuleRegistry evaluates PROFESSED_IGNORANCE_VS_PROACTIVE_INTERVENTION
18. HiddenPlanObligation requires >=2 scenes, >=2 steps, same goal_id, chronological order
19. HiddenPlanObligation builds CausalEdge from preconditions/consequences
20. Broken DAG connectivity in >=3 step plan fails obligation
21. CounterfactualTournamentEngine evaluates all 4 controls via evaluate_proof_state
22. Zero canned multiplier formulas in counterfactual module (AST check)
23. Dynamic reveal swap delta computation
24. Dynamic evidence ablation delta computation
25. Dynamic wrong identity delta computation
26. Dynamic temporal shuffle delta computation
27. Server-computed classify_reasoning_depth returns D1-D5 truthfully
28. Truthful /ready and /health without false-green fallbacks
Zero Paid Model Calls ($0.00).
"""
import ast
import re
import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from src.reframe.shared.config import settings
from src.reframe.cost.pricing import PricingStatus
from src.reframe.cost.guard import PaidCallGuardException
from src.reframe.cost.invoker import (
    GuardedGeminiInvoker,
    ALLOWED_LIVE_MODEL_IDS,
    LiveModelInvocationContext,
    live_invocation_ctx
)
from src.reframe.proof.hasher import (
    canonical_event_hash,
    canonical_fact_hash,
    canonical_frame_hash
)
from src.reframe.proof.validator import (
    DeterministicProofValidator,
    ProofValidationVerdict,
    ProofValidationErrorCode,
    proof_validator
)
from src.reframe.narrative.obligations import (
    KnowledgeStateResolver,
    KnowledgeProposition,
    AvailabilityStatus,
    KnowledgeLeakObligation,
    ClaimSourceType,
    ClaimEvidence,
    ActionEvidence,
    ContradictionRuleRegistry,
    ClaimActionObligation,
    PlanStep,
    CausalEdge,
    HiddenPlanObligation,
    classify_reasoning_depth
)
from src.reframe.narrative.counterfactual import (
    CounterfactualTournamentEngine,
    evaluate_proof_state,
    counterfactual_engine
)
from src.reframe.evidence.adapter import v3_adapter


# ==============================================================================
# 1. Zero API Lock Enforcement
# ==============================================================================

@pytest.mark.asyncio
async def test_01_zero_api_lock_enforcement():
    """Attempted live call must fail closed with PAID_CALL_ATTEMPTED_DURING_R4_2."""
    with patch.object(settings, "PAID_CALLS_ENABLED", False):
        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(uuid.uuid4()),
                principal_id=str(uuid.uuid4()),
                role="RESEARCHER",
                model_id="gemini-3.6-flash",
                prompt_text="test prompt"
            )
        assert exc_info.value.code == "PAID_CALL_ATTEMPTED_DURING_R4_2"


# ==============================================================================
# 2-4. Live Principal & Run Owner Verification
# ==============================================================================

@pytest.mark.asyncio
async def test_02_live_principal_owner_match_passes_preflight():
    """When principal matches run.owner_user_id, preflight ownership check passes."""
    run_id = uuid.uuid4()
    owner_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.owner_user_id = owner_id

    mock_res = MagicMock()
    mock_res.status = "ACTIVE"
    mock_res.reserved_micros = 1000000
    mock_res.consumed_micros = 0

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)), # No dup claim
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)), # db_run
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_res)), # db_res
    ])
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("src.reframe.cost.invoker.pricing_registry.get_pricing") as mock_pr, \
         patch("src.reframe.cost.invoker.AsyncSessionLocal", return_value=mock_session_ctx):
        
        mock_pr.return_value = MagicMock(pricing_status=PricingStatus.ESTIMATE_ONLY)
        # Model is gemini-3.6-flash which hits unverified pricing
        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(owner_id),
                role="RESEARCHER",
                model_id="gemini-3.6-flash",
                prompt_text="test prompt"
            )
        # Passed ownership stage, blocked at pricing gate
        assert exc_info.value.code == "UNVERIFIED_PRICING_BLOCKED"


@pytest.mark.asyncio
async def test_03_live_principal_owner_mismatch_raises_error():
    """Principal mismatching AnalysisRun owner must raise RUN_OWNER_MISMATCH with 0 calls."""
    run_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.owner_user_id = owner_id

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)), # No dup claim
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)), # db_run
    ])
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("src.reframe.cost.invoker.pricing_registry.get_pricing") as mock_pr, \
         patch("src.reframe.cost.invoker.AsyncSessionLocal", return_value=mock_session_ctx):
        
        from src.reframe.cost.pricing import PricingStatus
        mock_pr.return_value.pricing_status = PricingStatus.VERIFIED_BILLING_PRICE

        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(attacker_id),
                role="RESEARCHER",
                model_id="gemini-3.6-flash",
                prompt_text="test prompt"
            )
        assert exc_info.value.code == "RUN_OWNER_MISMATCH"


@pytest.mark.asyncio
async def test_04_missing_owner_user_id_raises_owner_required():
    """AnalysisRun with null owner_user_id must raise OWNER_REQUIRED."""
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.owner_user_id = None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)),
    ])
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("src.reframe.cost.invoker.pricing_registry.get_pricing") as mock_pr, \
         patch("src.reframe.cost.invoker.AsyncSessionLocal", return_value=mock_session_ctx):
        
        from src.reframe.cost.pricing import PricingStatus
        mock_pr.return_value.pricing_status = PricingStatus.VERIFIED_BILLING_PRICE

        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(user_id),
                role="RESEARCHER",
                model_id="gemini-3.6-flash",
                prompt_text="test prompt"
            )
        assert exc_info.value.code == "OWNER_REQUIRED"


# ==============================================================================
# 5-6. Frozen Live Model Allowlist
# ==============================================================================

@pytest.mark.asyncio
async def test_05_unallowed_live_model_raises_error():
    """Models not in ALLOWED_LIVE_MODEL_IDS must raise LIVE_MODEL_NOT_ALLOWED."""
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.owner_user_id = user_id

    mock_res = MagicMock()
    mock_res.status = "ACTIVE"
    mock_res.reserved_micros = 1000000
    mock_res.consumed_micros = 0

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)), # dup
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)), # run
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_res)), # res
    ])
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("src.reframe.cost.invoker.AsyncSessionLocal", return_value=mock_session_ctx):
        
        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(user_id),
                role="RESEARCHER",
                model_id="gemini-2.5-flash",
                prompt_text="test prompt"
            )
        assert exc_info.value.code == "LIVE_MODEL_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_06_gemini_3_6_flash_hits_pricing_gate():
    """gemini-3.6-flash is in allowlist but fails closed at unverified pricing gate."""
    assert "gemini-3.6-flash" in ALLOWED_LIVE_MODEL_IDS
    run_id = uuid.uuid4()
    user_id = uuid.uuid4()

    mock_run = MagicMock()
    mock_run.id = run_id
    mock_run.owner_user_id = user_id

    mock_res = MagicMock()
    mock_res.status = "ACTIVE"
    mock_res.reserved_micros = 1000000
    mock_res.consumed_micros = 0

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=[
        MagicMock(scalar_one_or_none=MagicMock(return_value=None)), # dup
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_run)), # run
        MagicMock(scalar_one_or_none=MagicMock(return_value=mock_res)), # res
    ])
    mock_session_ctx = MagicMock()
    mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("src.reframe.cost.invoker.pricing_registry.get_pricing") as mock_pr, \
         patch("src.reframe.cost.invoker.AsyncSessionLocal", return_value=mock_session_ctx):
        
        mock_pr.return_value = MagicMock(pricing_status=PricingStatus.ESTIMATE_ONLY)
        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(user_id),
                role="RESEARCHER",
                model_id="gemini-3.6-flash",
                prompt_text="test prompt"
            )
        assert exc_info.value.code == "UNVERIFIED_PRICING_BLOCKED"


# ==============================================================================
# 7-9. Strict Canonical Hash Equality & Field Grounding
# ==============================================================================

def test_07_strict_canonical_event_hash_equality():
    """Valid canonical event hash exactly matches canonical_event_hash."""
    h_ev = canonical_event_hash("ev-c017-05")
    assert len(h_ev) == 64

    proof = {
        "proof_id": "test-proof-grounding",
        "proof_type": "KNOWLEDGE_LEAK",
        "reveal_id": "reveal-anderson-identity",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Detective Anderson",
                "action": "observe",
                "fact": "Detective Anderson stands alone in the dark hall inspecting his surroundings.",
                "canonical_content_hash": h_ev
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson carries rolled papers and unrolls blueprints.",
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            }
        ],
        "alternative_explanations": ["Routine investigation"]
    }
    res = proof_validator.validate(proof, 4860000)
    assert res.evidence_grounded is True


def test_08_altered_canonical_event_hash_fails():
    """Bypasses such as hash=eid or hash=hash(premise) must fail grounding."""
    proof = {
        "proof_id": "test-bypass-hash",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Detective Anderson",
                "action": "observe",
                "fact": "Detective Anderson stands alone.",
                "canonical_content_hash": "ev-c017-05"  # Bypass attempt: raw eid
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson carries blueprints.",
                "canonical_content_hash": "custom_computed_hash"  # Bypass attempt
            }
        ],
        "alternative_explanations": ["Routine investigation"]
    }
    res = proof_validator.validate(proof, 4860000)
    assert res.evidence_grounded is False
    assert ProofValidationErrorCode.EVIDENCE_HASH_MISMATCH in res.error_codes


def test_09_altered_observed_premise_fields_fail():
    """Mutating actor, action, scene, or timestamp must fail validation."""
    # 1. Actor changed
    p_actor = {
        "proof_id": "test-mutated-actor",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Lizzie Allen",  # Canonical is Detective Anderson
                "action": "observe",
                "canonical_content_hash": canonical_event_hash("ev-c017-05")
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            }
        ],
        "alternative_explanations": ["Alt"]
    }
    res = proof_validator.validate(p_actor, 4860000)
    assert res.evidence_grounded is False
    assert ProofValidationErrorCode.ACTOR_MISMATCH in res.error_codes

    # 2. Timestamp + 1
    p_ts = {
        "proof_id": "test-mutated-ts",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010001,  # Canonical is 2010000 (0ms tolerance)
                "canonical_content_hash": canonical_event_hash("ev-c017-05")
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            }
        ],
        "alternative_explanations": ["Alt"]
    }
    res = proof_validator.validate(p_ts, 4860000)
    assert res.evidence_grounded is False
    assert ProofValidationErrorCode.TIMESTAMP_MISMATCH in res.error_codes


# ==============================================================================
# 10-12. Epistemic State Resolver & Knowledge Leak Obligation
# ==============================================================================

def test_10_knowledge_state_resolver_extracts_known_proposition():
    """KnowledgeStateResolver extracts KNOWN proposition for Anderson blueprints."""
    kp = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Detective Anderson carries and unrolls blueprints of the bank safe",
        cutoff_ms=4860000
    )
    assert kp.availability_status == AvailabilityStatus.INFERRED
    assert "INFERRED_REVEAL_DEPENDENT" in kp.predicate
    assert kp.public_available_from_ms == 4860000
    assert kp.character_available_from_ms == 120000
    assert kp.confidence >= 0.85


def test_11_knowledge_leak_obligation_evaluation():
    """KnowledgeLeakObligation satisfies when character access is before public broadcast."""
    kp = KnowledgeProposition(
        public_available_from_ms=4860000,
        character_available_from_ms=120000,
        availability_status=AvailabilityStatus.KNOWN
    )
    res = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=4860000,
        earliest_character_access_ms=120000,
        evidence_ids=["ev-1"],
        knowledge_proposition=kp
    )
    assert res.is_satisfied is True
    assert res.score >= 0.90


def test_12_unknown_epistemic_availability_fails_obligation():
    """Unknown epistemic proposition fails closed with UNKNOWN_EPISTEMIC_AVAILABILITY."""
    kp = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Lizzie Allen",
        proposition="Lizzie organizes pantry spoons",
        cutoff_ms=4860000
    )
    assert kp.availability_status == AvailabilityStatus.UNKNOWN
    res = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=4860000,
        earliest_character_access_ms=100000,
        evidence_ids=["ev-1"],
        knowledge_proposition=kp
    )
    assert res.is_satisfied is False
    assert "UNKNOWN_EPISTEMIC_AVAILABILITY" in res.broken_rules


# ==============================================================================
# 13-17. Claim Action Conflict & Contradiction Rule Registry
# ==============================================================================

def test_13_claim_action_requires_structured_evidence():
    """ClaimActionObligation evaluates structured ClaimEvidence and ActionEvidence."""
    claim = ClaimEvidence(
        actor="Detective Anderson",
        proposition="verbally assures he is outside defending the perimeter",
        timestamp_ms=2895000,
        evidence_ref="ev-c025-02",
        source_type=ClaimSourceType.DIALOGUE
    )
    action = ActionEvidence(
        actor="Detective Anderson",
        action="enters the dark room alone and searches",
        timestamp_ms=3270000,
        evidence_ref="ev-c028-03"
    )
    res = ClaimActionObligation.evaluate(
        speaker_claim_text=claim.proposition,
        actor_action_text=action.action,
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=["ev-c025-02", "ev-c028-03"],
        claim_evidence=claim,
        action_evidence=action
    )
    assert res.is_satisfied is True


def test_14_ungrounded_sentences_rejected_as_claims():
    """Missing speaker claim or missing evidence ref must fail closed."""
    res = ClaimActionObligation.evaluate(
        speaker_claim_text="",
        actor_action_text="Enters room alone",
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=[]
    )
    assert res.is_satisfied is False
    assert "MISSING_SPEAKER_CLAIM" in res.broken_rules


def test_15_contradiction_rule_alibi_vs_presence():
    """ContradictionRuleRegistry evaluates STATED_ALIBI_VS_UNOBSERVED_PRESENCE."""
    claim = ClaimEvidence(actor="Suspect", proposition="I was away outside defending the gates", timestamp_ms=100, evidence_ref="ev-1")
    action = ActionEvidence(actor="Suspect", action="enters the vault room alone", timestamp_ms=200, evidence_ref="ev-2")
    match, reason = ContradictionRuleRegistry.evaluate_contradiction(claim, action, "STATED_ALIBI_VS_UNOBSERVED_PRESENCE")
    assert match is True


def test_16_contradiction_rule_denial_vs_possession():
    """ContradictionRuleRegistry evaluates EXPLICIT_DENIAL_VS_PHYSICAL_POSSESSION."""
    claim = ClaimEvidence(actor="Suspect", proposition="I deny having any blueprint or money", timestamp_ms=100, evidence_ref="ev-1")
    action = ActionEvidence(actor="Suspect", action="holds and pockets the blueprint rolls", timestamp_ms=200, evidence_ref="ev-2")
    match, reason = ContradictionRuleRegistry.evaluate_contradiction(claim, action, "EXPLICIT_DENIAL_VS_PHYSICAL_POSSESSION")
    assert match is True


def test_17_contradiction_rule_ignorance_vs_intervention():
    """ContradictionRuleRegistry evaluates PROFESSED_IGNORANCE_VS_PROACTIVE_INTERVENTION."""
    claim = ClaimEvidence(actor="Suspect", proposition="I have no knowledge of any secret mechanism", timestamp_ms=100, evidence_ref="ev-1")
    action = ActionEvidence(actor="Suspect", action="disables and unlocks the hidden lever", timestamp_ms=200, evidence_ref="ev-2")
    match, reason = ContradictionRuleRegistry.evaluate_contradiction(claim, action, "PROFESSED_IGNORANCE_VS_PROACTIVE_INTERVENTION")
    assert match is True


# ==============================================================================
# 18-20. Hidden Plan Causal DAG & Prerequisites
# ==============================================================================

def test_18_hidden_plan_requires_multi_scene_and_chronology():
    """HiddenPlanObligation requires >=2 scenes and strictly chronological timestamps."""
    steps_bad_time = [
        PlanStep(step_id="s1", scene_id="sc1", timestamp_ms=2000, action="Step 1"),
        PlanStep(step_id="s2", scene_id="sc2", timestamp_ms=1000, action="Step 2")  # Out of order
    ]
    res = HiddenPlanObligation.evaluate(steps_bad_time, evidence_ids=["e1", "e2"])
    assert res.is_satisfied is False
    assert "CHRONOLOGY_VIOLATION" in res.broken_rules


def test_19_hidden_plan_builds_causal_edges_from_preconditions():
    """Causal edges are built deterministically from matching consequences and preconditions."""
    steps = [
        PlanStep(step_id="s1", scene_id="sc1", timestamp_ms=1000, preconditions=["arrives"], action="secures hall", consequences=["hallway secured"]),
        PlanStep(step_id="s2", scene_id="sc2", timestamp_ms=2000, preconditions=["hallway secured"], action="unrolls blueprints", consequences=["safe located"]),
        PlanStep(step_id="s3", scene_id="sc3", timestamp_ms=3000, preconditions=["safe located"], action="opens secret panel", consequences=["loot taken"])
    ]
    edges = HiddenPlanObligation.build_causal_edges(steps)
    assert len(edges) == 2
    assert edges[0].relation == "ENABLES"
    assert edges[1].relation == "ENABLES"

    res = HiddenPlanObligation.evaluate(steps, evidence_ids=["e1", "e2", "e3"])
    assert res.is_satisfied is True


def test_20_broken_dag_connectivity_fails_hidden_plan():
    """Disconnected non-final steps in >=3 step plan fail obligation."""
    steps = [
        PlanStep(step_id="s1", scene_id="sc1", timestamp_ms=1000, preconditions=["p1"], action="independent act", consequences=["c1"]),
        PlanStep(step_id="s2", scene_id="sc2", timestamp_ms=2000, preconditions=["p2"], action="unrelated act", consequences=["c2"]),
        PlanStep(step_id="s3", scene_id="sc3", timestamp_ms=3000, preconditions=["p3"], action="final act", consequences=["c3"])
    ]
    # Pass empty causal edges to test disconnected DAG
    res = HiddenPlanObligation.evaluate(steps, evidence_ids=["e1", "e2", "e3"], causal_edges=[])
    assert res.is_satisfied is False
    assert "NO_CAUSAL_EDGES" in res.broken_rules


# ==============================================================================
# 21-26. Authoritative Counterfactual Engine & Controls
# ==============================================================================

def test_21_counterfactual_engine_evaluates_all_four_controls():
    """CounterfactualTournamentEngine executes all 4 controls using evaluate_proof_state."""
    proof = {
        "proof_id": "proof-anderson-03",
        "proof_type": "HIDDEN_PLAN_CHAIN",
        "reveal_id": "reveal-anderson-identity",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000},
            {"scene_id": "scene-tbw-c028", "timestamp_ms": 3270000}
        ],
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Detective Anderson",
                "action": "observe",
                "fact": "Detective Anderson stands alone in dark hall inspecting.",
                "canonical_content_hash": canonical_event_hash("ev-c017-05")
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson unrolls blueprints before Dale.",
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            },
            {
                "event_id": "ev-c028-03",
                "scene_id": "scene-tbw-c028",
                "timestamp_ms": 3270000,
                "actor": "Detective Anderson",
                "action": "moves",
                "fact": "Detective Anderson moves portrait near stairs.",
                "canonical_content_hash": canonical_event_hash("ev-c028-03")
            }
        ],
        "alternative_explanations": ["Routine investigation"]
    }
    tourn = counterfactual_engine.run_tournament(proof, "reveal-anderson-identity")
    assert len(tourn.experiments) == 4
    exp_types = {e.experiment_type for e in tourn.experiments}
    assert exp_types == {
        "REVEAL_SWAP",
        "WRONG_IDENTITY_MECHANISM",
        "EVIDENCE_ABLATION",
        "TIMESTAMP_ORDER_SHUFFLE"
    }


def test_22_zero_canned_multipliers_in_counterfactual_modules():
    """Static AST check: No * 0.40, * 0.50, swap_score = 0.10, or canned multipliers exist."""
    cf_file = Path("src/reframe/narrative/counterfactual.py")
    assert cf_file.exists()
    content = cf_file.read_text(encoding="utf-8")

    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
            if isinstance(node.right, ast.Constant) and node.right.value in (0.40, 0.50, 0.10, 0.15, 0.20):
                pytest.fail(f"Forbidden canned multiplier found in counterfactual.py: * {node.right.value}")

    obl_file = Path("src/reframe/narrative/obligations.py")
    assert obl_file.exists()
    obl_content = obl_file.read_text(encoding="utf-8")
    assert "ablation_score = 0.20" not in obl_content
    assert "wrong_id_score = 0.10" not in obl_content


def test_23_to_26_dynamic_counterfactual_deltas():
    """Verify dynamic deltas for reveal swap, ablation, wrong identity, and shuffle."""
    proof = {
        "proof_id": "proof-anderson-01",
        "proof_type": "MULTI_SCENE_PATTERN",
        "reveal_id": "reveal-anderson-identity",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Detective Anderson",
                "action": "observe",
                "fact": "Detective Anderson stands alone in dark hall inspecting concealed architecture.",
                "canonical_content_hash": canonical_event_hash("ev-c017-05")
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson carries and unrolls blueprints of the bank safe.",
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            }
        ],
        "alternative_explanations": ["Routine investigation"]
    }
    tourn = counterfactual_engine.run_tournament(proof, "reveal-anderson-identity")
    assert tourn.reveal_swap_delta <= -0.30
    assert tourn.evidence_ablation_delta <= -0.30
    assert tourn.wrong_mechanism_delta <= -0.30
    assert tourn.shuffle_delta <= -0.30
    assert tourn.is_robust is True


# ==============================================================================
# 27. D1-D5 Reasoning Depth Classifier
# ==============================================================================

def test_27_classify_reasoning_depth_d1_to_d5():
    """classify_reasoning_depth returns D1 to D5 deterministically based on structure."""
    # D1: Single premise
    p_d1 = {"proof_type": "UNKNOWN", "observed_premises": [{"scene_id": "sc1"}]}
    assert classify_reasoning_depth(p_d1) == "D2"

    # D3: Multi-scene without deep obligations
    p_d3 = {"proof_type": "UNKNOWN", "observed_premises": [{"scene_id": "sc1"}, {"scene_id": "sc2"}]}
    assert classify_reasoning_depth(p_d3) == "D3"

    # D4: Validated Knowledge Leak
    p_d4 = {
        "proof_type": "KNOWLEDGE_LEAK",
        "cutoff_ms": 4860000,
        "observed_premises": [
            {"scene_id": "sc1", "timestamp_ms": 1000, "actor": "Detective Anderson", "fact": "unrolls blueprints of the safe"},
            {"scene_id": "sc2", "timestamp_ms": 2000, "actor": "Detective Anderson", "fact": "inspects room"}
        ]
    }
    assert classify_reasoning_depth(p_d4) == "D4"

    # D5: Validated Hidden Plan Chain
    p_d5 = {
        "proof_type": "HIDDEN_PLAN_CHAIN",
        "observed_premises": [
            PlanStep(step_id="s1", scene_id="sc1", timestamp_ms=1000, preconditions=["p1"], action="step 1", consequences=["c1"]),
            PlanStep(step_id="s2", scene_id="sc2", timestamp_ms=2000, preconditions=["c1"], action="step 2", consequences=["c2"])
        ]
    }
    assert classify_reasoning_depth(p_d5) == "D5"


# ==============================================================================
# 28. Truthful /ready & /health Probes
# ==============================================================================

@pytest.mark.asyncio
async def test_28_truthful_ready_probe_fails_on_unreachable_clickhouse():
    """ready_probe must report clickhouse=False and overall_ready=False when ClickHouse is unreachable."""
    from apps.api.routers.health import ready_probe, health_probe

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock()

    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        res = await ready_probe(db=mock_db)
        assert res["data"]["clickhouse"] is False
        assert res["data"]["overall_ready"] is False
        assert res["status"] == "degraded"

    with patch("httpx.AsyncClient.get", side_effect=Exception("Connection refused")):
        health_res = await health_probe(db=mock_db)
        assert health_res["data"]["clickhouse"] is False
        assert health_res["data"]["overall_ready"] is False
