"""
Reframe V7 Final Master Execution Verification Suite
Tests:
1. Guarded ADK Model Binding (reframe-live-guarded alias, BaseLlm registry)
2. LiveModelInvocationContext propagation via ContextVar and fail-closed behavior
3. Pre-call active BudgetReservation and AnalysisRun verification in database
4. Authoritative MCP ClickHouse payload in EvidenceBundle (no local v3 overwrite)
5. Zero Answer-Assisted Live Reasoning (LIVE_ANSWER_ASSISTED is False)
6. D4/D5 Deep Reasoning Objects & Dynamic Counterfactual Obligation Scoring
"""
import uuid
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from google.adk.models import LLMRegistry

from src.reframe.shared.config import settings
from src.reframe.domain.enums import ExecutionMode
from src.reframe.cost.guard import PaidCallGuardException
from src.reframe.cost.invoker import (
    GuardedGeminiInvoker,
    GuardedGeminiAdkLlm,
    LiveModelInvocationContext,
    live_invocation_ctx
)
from src.reframe.agents.root_agent import (
    create_reframe_root_agent,
    create_live_reframe_root_agent,
    reframe_root_agent,
    reframe_live_root_agent
)
from src.reframe.agents.adk_gateway import (
    LiveGoogleAdkExecutionGateway,
    LIVE_ANSWER_ASSISTED
)
from src.reframe.narrative.bundle import EvidenceBundleBuilder, EvidenceBundle
from src.reframe.narrative.channels import EvidenceSeed
from src.reframe.evidence.schemas import RevealDTO
from src.reframe.narrative.obligations import (
    ObservedEvidence,
    KnowledgeProposition,
    CharacterEpistemicState,
    ClaimEvidence,
    ActionEvidence,
    ContradictionRelation,
    AccessOpportunity,
    Goal,
    PlanStep,
    CausalEdge,
    WhyMissed,
    KnowledgeLeakObligation,
    ClaimActionObligation,
    HiddenPlanObligation,
    CounterfactualObligationScorer
)


# -------------------------------------------------------------
# 1. Guarded ADK Model Binding Tests
# -------------------------------------------------------------

def test_live_root_agent_model_binding():
    """Verify live root agent is created with model 'reframe-live-guarded' and tools."""
    live_agent = create_live_reframe_root_agent()
    assert live_agent.model == "reframe-live-guarded"
    assert len(live_agent.tools) == 3
    tool_names = [t.__name__ for t in live_agent.tools]
    assert "retrieve_narrative_evidence" in tool_names
    assert "retrieve_entity_evidence" in tool_names
    assert "retrieve_character_states" in tool_names


def test_llm_registry_has_guarded_gemini_adk_llm():
    """Verify LLMRegistry matches 'reframe-live-guarded' with GuardedGeminiAdkLlm."""
    supported = GuardedGeminiAdkLlm.supported_models()
    assert any("reframe-live-guarded" in p for p in supported)


# -------------------------------------------------------------
# 2. Async-Safe Invocation Context Tests
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_guarded_gemini_adk_llm_fails_closed_without_context():
    """GuardedGeminiAdkLlm must raise PaidCallGuardException if ContextVar is unset."""
    llm = GuardedGeminiAdkLlm()
    mock_request = MagicMock()
    mock_request.contents = []

    # Ensure context is unset
    token = live_invocation_ctx.set(None)
    try:
        with pytest.raises(PaidCallGuardException) as exc_info:
            async for _ in llm.generate_content_async(mock_request):
                pass
        assert "MISSING_INVOCATION_CONTEXT" in str(exc_info.value)
    finally:
        live_invocation_ctx.reset(token)


@pytest.mark.asyncio
async def test_invoker_fails_closed_on_invalid_uuid():
    """GuardedGeminiInvoker must reject non-UUID strings in live mode."""
    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"):

        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id="not-a-valid-uuid",
                principal_id="not-a-valid-uuid",
                role="REASONING",
                model_id="reframe-live-guarded",
                prompt_text="test prompt"
            )
        assert "INVALID_INVOCATION_CONTEXT" in str(exc_info.value)


# -------------------------------------------------------------
# 3. Pre-Call Budget Reservation Database Verification Tests
# -------------------------------------------------------------

@pytest.mark.asyncio
async def test_invoker_requires_existing_analysis_run_and_active_reservation():
    """GuardedGeminiInvoker must check for AnalysisRun and active BudgetReservation."""
    valid_run_id = str(uuid.uuid4())
    valid_user_id = str(uuid.uuid4())

    with patch.object(settings, "PAID_CALLS_ENABLED", True), \
         patch.object(settings, "SPEND_KILL_SWITCH_ACTIVE", False), \
         patch.object(settings, "LIVE_AGENT_ENABLED", True), \
         patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"):

        # In a fresh session without inserted run, it should fail with ANALYSIS_RUN_REQUIRED
        with pytest.raises(PaidCallGuardException) as exc_info:
            await GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=valid_run_id,
                principal_id=valid_user_id,
                role="REASONING",
                model_id="reframe-live-guarded",
                prompt_text="test prompt"
            )
        assert "ANALYSIS_RUN_REQUIRED" in str(exc_info.value)


# -------------------------------------------------------------
# 4. Authoritative Live Evidence Bundle Payload (Adversarial Test)
# -------------------------------------------------------------

def test_live_google_mode_preserves_authoritative_mcp_payload():
    """
    Adversarial test:
    When execution_mode == LIVE_GOOGLE, synthetic MCP event description 'SYNTHETIC_MCP_ACTION'
    must NOT be overwritten by local V3 adapter data.
    """
    from src.reframe.evidence.adapter import v3_adapter
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    assert reveal is not None

    synthetic_seed = EvidenceSeed(
        source_call_id="mcp-test-call-001",
        phase="CANDIDATE_RETRIEVAL",
        dataset_version="v3",
        channel_name="MCP_CLICKHOUSE_RETRIEVAL",
        scene_ids=["scene-01"],
        event_ids=["event-01-01"],
        cutoff_ms=4860000,
        salience_score=0.95,
        channel_rationale="Synthetic MCP retrieval test seed",
        structured_payload={
            "query_hash": "hash-abc",
            "transport": "OFFICIAL_MCP_CLICKHOUSE_STDIO",
            "row_count": 2,
            "raw_rows": [
                {
                    "scene_id": "scene-01",
                    "movie_id": "the-bat-whispers-1930",
                    "start_ms": 120000,
                    "end_ms": 180000,
                    "location": "Oakdale Bank Vault",
                    "summary": "SYNTHETIC_MCP_SCENE_SUMMARY",
                    "characters": ["Detective Anderson"],
                    "objects": ["Blueprint"]
                },
                {
                    "event_id": "event-01-01",
                    "movie_id": "the-bat-whispers-1930",
                    "scene_id": "scene-01",
                    "timestamp_ms": 130000,
                    "actor": "Detective Anderson",
                    "action": "EXAMINES_SAFE",
                    "description": "SYNTHETIC_MCP_AUTHORITATIVE_PAYLOAD",
                    "confidence": 1.0
                }
            ]
        }
    )

    # Build bundle under LIVE_GOOGLE
    bundle = EvidenceBundleBuilder.build_bundle(
        reveal=reveal,
        provided_seeds=[synthetic_seed],
        execution_mode=ExecutionMode.LIVE_GOOGLE
    )

    # Verify that the bundle contains the exact MCP description
    assert len(bundle.observed_events) > 0
    assert bundle.observed_events[0].description == "SYNTHETIC_MCP_AUTHORITATIVE_PAYLOAD"
    assert bundle.related_scenes[0].summary == "SYNTHETIC_MCP_SCENE_SUMMARY"


# -------------------------------------------------------------
# 5. Answer-Assisted Live Reasoning Elimination Test
# -------------------------------------------------------------

def test_live_answer_assisted_is_false():
    """Verify that LIVE_ANSWER_ASSISTED constant is strictly False."""
    assert LIVE_ANSWER_ASSISTED is False


# -------------------------------------------------------------
# 6. D4/D5 Deep Reasoning Objects & Obligations Tests
# -------------------------------------------------------------

def test_d4_d5_structured_domain_models():
    """Verify instantiation of all required D4/D5 domain models."""
    obs = ObservedEvidence(
        evidence_id="ev-01",
        scene_id="scene-01",
        timestamp_ms=100000,
        actor="Detective Anderson",
        action="Disables alarm",
        fact="Alarm circuit severed"
    )
    assert obs.evidence_id == "ev-01"

    kp = KnowledgeProposition(
        text="The vault combination was changed at noon",
        subject="Detective Anderson",
        predicate="KNOWS_SECRET",
        object="Vault combination",
        public_available_from_ms=4860000,
        character_available_from_ms=150000
    )
    assert kp.public_available_from_ms > kp.character_available_from_ms

    epistemic = CharacterEpistemicState(
        character="Detective Anderson",
        timestamp_ms=150000,
        known_propositions=[kp.proposition_id],
        access_type="OBSERVED"
    )
    assert epistemic.character == "Detective Anderson"

    claim = ClaimEvidence(
        actor="Detective Anderson",
        proposition="I was stationed at headquarters all morning",
        timestamp_ms=200000,
        evidence_ref="ev-02"
    )
    act = ActionEvidence(
        actor="Detective Anderson",
        action="Enters room alone and examines safe",
        timestamp_ms=180000,
        evidence_ref="ev-03"
    )
    contra = ContradictionRelation(
        claim=claim,
        action=act,
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE"
    )
    assert contra.severity == "HIGH"

    goal = Goal(
        actor="Detective Anderson",
        target_outcome="Steal securities without detection"
    )
    step1 = PlanStep(
        goal_id=goal.goal_id,
        scene_id="scene-01",
        timestamp_ms=100000,
        action="Cut main power line",
        consequences=["Alarms disabled"]
    )
    step2 = PlanStep(
        goal_id=goal.goal_id,
        scene_id="scene-02",
        timestamp_ms=200000,
        action="Extract bank notes",
        consequences=["Vault emptied"]
    )
    edge = CausalEdge(
        from_step=step1.step_id,
        to_step=step2.step_id,
        relation="ENABLES"
    )
    assert edge.relation == "ENABLES"

    missed = WhyMissed(
        dominant_surface_interpretation="Police officer inspecting crime scene",
        attention_misdirection="Focus placed on screaming witness",
        role_expectation="Investigator presumed loyal to law enforcement"
    )
    assert missed.dominant_surface_interpretation != ""


def test_d4_epistemic_knowledge_leak_obligation():
    """Verify KnowledgeLeakObligation evaluates character access vs public broadcast."""
    # Case 1: Early access -> satisfied
    res_sat = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=4860000,
        earliest_character_access_ms=150000,
        evidence_ids=["ev-01"]
    )
    assert res_sat.is_satisfied is True
    assert res_sat.score > 0.80

    # Case 2: Post-public access -> unsatisfied
    res_unsat = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=100000,
        earliest_character_access_ms=200000,
        evidence_ids=["ev-01"]
    )
    assert res_unsat.is_satisfied is False
    assert "POST_PUBLIC_ACTION" in res_unsat.broken_rules


def test_d4_claim_action_conflict_obligation():
    """Verify ClaimActionObligation evaluates speech vs physical action contradiction."""
    res_alibi = ClaimActionObligation.evaluate(
        speaker_claim_text="I was away from the room defending the entrance",
        actor_action_text="Enters room alone and searches desk",
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=["ev-01", "ev-02"]
    )
    assert res_alibi.is_satisfied is True
    assert res_alibi.score > 0.80

    # Missing speech claim -> fails closed
    res_missing_claim = ClaimActionObligation.evaluate(
        speaker_claim_text="",
        actor_action_text="Enters room alone",
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=["ev-01"]
    )
    assert res_missing_claim.is_satisfied is False
    assert "MISSING_SPEAKER_CLAIM" in res_missing_claim.broken_rules


def test_d5_hidden_plan_chain_obligation():
    """Verify HiddenPlanObligation requires multi-step, multi-scene chronological order."""
    valid_steps = [
        {"scene_id": "scene-01", "timestamp_ms": 100000, "action": "Cut wire"},
        {"scene_id": "scene-02", "timestamp_ms": 200000, "action": "Take loot"}
    ]
    res_valid = HiddenPlanObligation.evaluate(
        plan_steps=valid_steps,
        evidence_ids=["ev-01", "ev-02"]
    )
    assert res_valid.is_satisfied is True

    # Single scene -> unsatisfied
    single_scene_steps = [
        {"scene_id": "scene-01", "timestamp_ms": 100000, "action": "Cut wire"},
        {"scene_id": "scene-01", "timestamp_ms": 120000, "action": "Take loot"}
    ]
    res_single = HiddenPlanObligation.evaluate(
        plan_steps=single_scene_steps,
        evidence_ids=["ev-01", "ev-02"]
    )
    assert res_single.is_satisfied is False
    assert "SINGLE_SCENE_PLAN" in res_single.broken_rules


def test_counterfactual_obligation_scorer_dynamic_deltas():
    """Verify CounterfactualObligationScorer computes genuine deltas across controls."""
    proof_dict = {
        "proof_type": "MULTI_SCENE_PATTERN",
        "observed_premises": [
            {
                "event_id": "ev-c017-05",
                "scene_id": "scene-tbw-c017",
                "timestamp_ms": 2010000,
                "actor": "Detective Anderson",
                "action": "observe",
                "fact": "Detective Anderson stands alone in dark hall inspecting concealed architecture."
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson carries and unrolls blueprints of the bank safe."
            }
        ],
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ]
    }

    cf_res = CounterfactualObligationScorer.score_counterfactuals(
        proof_candidate=proof_dict,
        target_reveal_id="reveal-anderson-identity"
    )

    assert cf_res.is_counterfactually_robust is True
    assert cf_res.reveal_swap_delta <= -0.30
    assert cf_res.evidence_ablation_delta <= -0.30
    assert cf_res.wrong_identity_delta <= -0.30
    assert cf_res.shuffle_delta <= -0.30
