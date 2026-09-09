"""
Unit Tests for Real Google ADK Hypothesis, Critic, and Judge Workflow
Zero Paid Model Calls.
"""
import pytest
from src.reframe.agents.runtime import agent_runtime
from src.reframe.agents.roles import (
    HypothesisRoleExecutor,
    CriticRoleExecutor,
    JudgeRoleExecutor,
    HypothesisRoleOutput
)
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.narrative.bundle import bundle_builder


@pytest.mark.asyncio
async def test_execute_adk_analysis_produces_real_validated_proofs():
    """Agent runtime must execute the 3-role pipeline and return structured result with distinct telemetries."""
    result = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="test-adk-run-001"
    )

    assert result["status"] in ("COMPLETED", "ABSTAINED")
    assert len(result["hypotheses"]) >= 1
    assert len(result["critiques"]) >= 1
    assert len(result["judgments"]) >= 1
    assert len(result["telemetries"]) >= 3  # Hypothesis, Critic, Judge
    for telem in result["telemetries"]:
        assert telem["paid_model_calls"] == 0


def test_critic_rejects_future_contaminated_premise():
    """Critic must detect and reject hypotheses with premises starting at or after the spoiler cutoff."""
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    bundle = bundle_builder.build_bundle(reveal=reveal)

    # Construct tainted hypothesis with timestamp >= cutoff (4860000ms)
    tainted_hyp = HypothesisRoleOutput(
        title="Tainted Clue",
        proof_type="KNOWLEDGE_LEAK",
        h0_blind_explanation="Blind test",
        hr_reveal_explanation="Reveal explanation",
        ha_alternatives=["Alternative 1", "Alternative 2"],
        observed_premises=[
            {"event_id": "ev-tainted", "scene_id": "scene-tbw-c042", "timestamp_ms": 4900000, "fact": "Future event"}
        ]
    )

    critic_res, _ = CriticRoleExecutor.critique(
        hypothesis=tainted_hyp,
        bundle=bundle,
        cutoff_ms=4860000
    )

    assert critic_res.future_contamination_detected is True
    assert critic_res.critic_verdict == "REJECT"

    # Judge must also reject
    judge_res, _ = JudgeRoleExecutor.judge(
        hypothesis=tainted_hyp,
        critic_result=critic_res,
        cf_delta=-0.85,
        validation_valid=False
    )
    assert judge_res.verdict == "REJECTED"
    assert judge_res.proof_strength < 0.30
