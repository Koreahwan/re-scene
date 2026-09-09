"""
Unit Tests for R2-03, R2-04, R2-05, R2-06, R2-07 Gateways, Channels, and Counterfactuals
Zero Paid Model Calls.
"""
import pytest
from src.reframe.agents.roles import (
    get_hypothesis_gateway,
    get_critic_gateway,
    get_judge_gateway,
    OfflineFixtureHypothesisGateway,
    OfflineFixtureCriticGateway,
    OfflineFixtureJudgeGateway,
    ExecutionMode
)
from src.reframe.narrative.channels import (
    multi_channel_engine,
    EntityRetrievalChannel,
    KnowledgeConflictChannel,
    ClaimActionChannel,
    AccessOpportunityChannel,
    PlanCausalChannel,
    EvidenceSeed
)
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.narrative.bundle import bundle_builder
from src.reframe.narrative.counterfactual import counterfactual_engine
from src.reframe.agents.runtime import agent_runtime


def test_offline_gateways_selected_by_default():
    """Verify that offline fixture gateways are selected in default config with 0 paid calls."""
    hyp_gw = get_hypothesis_gateway()
    crit_gw = get_critic_gateway()
    judge_gw = get_judge_gateway()

    assert isinstance(hyp_gw, OfflineFixtureHypothesisGateway)
    assert isinstance(crit_gw, OfflineFixtureCriticGateway)
    assert isinstance(judge_gw, OfflineFixtureJudgeGateway)


def test_offline_gateway_telemetry_reports_zero_paid_calls():
    """Verify that offline gateways emit telemetry with paid_model_calls=0 and OFFLINE_FIXTURE mode."""
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    bundle = bundle_builder.build_bundle(reveal=reveal, cutoff_ms=4860000)

    hyp_gw = get_hypothesis_gateway()
    hypotheses, telem = hyp_gw.generate_hypotheses(bundle=bundle, analysis_run_id="test-run-01")

    assert telem.paid_model_calls == 0
    assert telem.input_tokens == 0
    assert telem.output_tokens == 0
    assert telem.execution_mode == ExecutionMode.OFFLINE_FIXTURE
    assert telem.status == "SKIPPED_OFFLINE"
    assert len(hypotheses) >= 1


def test_multi_channel_retrieval_produces_typed_evidence_seeds():
    """Verify that all 5 channels produce EvidenceSeed instances with structured payloads."""
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    seeds = multi_channel_engine.retrieve_candidates(reveal=reveal, cutoff_ms=4860000)

    assert len(seeds) > 0
    channel_names = set(s.channel_name for s in seeds)
    assert "ENTITY" in channel_names
    assert "KNOWLEDGE_CONFLICT" in channel_names
    assert "CLAIM_ACTION" in channel_names

    for s in seeds:
        assert isinstance(s, EvidenceSeed)
        assert s.cutoff_ms == 4860000
        assert len(s.scene_ids) > 0
        assert s.salience_score > 0.0


def test_counterfactual_tournament_evaluates_four_experiments():
    """Verify that counterfactual tournament runs all 4 controls and produces signed deltas."""
    proof_candidate = {
        "proof_id": "test-cf-proof-01",
        "reveal_id": "reveal-anderson-identity",
        "observed_premises": [
            {"event_id": "ev-c017-05", "scene_id": "scene-tbw-c017", "timestamp_ms": 2010000, "fact": "Detective Anderson stands alone in the dark hall inspecting his surroundings."},
            {"event_id": "ev-c021-03", "scene_id": "scene-tbw-c021", "timestamp_ms": 2490000, "fact": "Detective Anderson carries rolled papers across the room and unrolls blueprints before Dale and the group."}
        ]
    }
    result = counterfactual_engine.run_tournament(proof_candidate, target_reveal_id="reveal-anderson-identity")

    assert result.is_robust is True
    assert len(result.experiments) == 4
    exp_types = [e.experiment_type for e in result.experiments]
    assert "REVEAL_SWAP" in exp_types
    assert "WRONG_IDENTITY_MECHANISM" in exp_types
    assert "EVIDENCE_ABLATION" in exp_types
    assert "TIMESTAMP_ORDER_SHUFFLE" in exp_types
    assert result.reveal_swap_delta <= -0.40
    assert result.evidence_ablation_delta <= -0.40


@pytest.mark.asyncio
async def test_agent_runtime_offline_execution_end_to_end():
    """Verify that AgentRuntime executes end-to-end in offline mode with 0 cost."""
    result = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="test-offline-adk-01"
    )
    assert result["status"] in ("COMPLETED", "ABSTAINED")
    assert len(result["hypotheses"]) >= 1
    # Check that telemetries show 0 paid calls
    telemetries = result["telemetries"]
    assert len(telemetries) >= 3
    for t in telemetries:
        assert t["paid_model_calls"] == 0
        assert t["execution_mode"] == "OFFLINE_FIXTURE"
