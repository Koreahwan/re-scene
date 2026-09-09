"""
Unit Tests for Google ADK Agent Shell, Official MCP Telemetry, and Proof Validator
"""
import pytest
from src.reframe.agents.root_agent import reframe_root_agent
from src.reframe.agents.telemetry import telemetry_ledger
from src.reframe.agents.tools.mcp_tools import execute_mcp_query, retrieve_entity_evidence
from src.reframe.agents.runtime import agent_runtime
from src.reframe.proof.validator import proof_validator, ProofValidationVerdict


def test_adk_root_agent_structure():
    assert reframe_root_agent.name == "reframe_root_agent"
    assert len(reframe_root_agent.tools) >= 2


@pytest.mark.asyncio
async def test_official_mcp_tool_execution_and_telemetry():
    telemetry_ledger.clear()
    query = "SELECT scene_id, start_ms, end_ms, summary FROM reframe.scenes WHERE start_ms < 4860000"
    rows = await execute_mcp_query(
        query=query,
        phase="candidate_retrieval",
        analysis_run_id="test-run-mcp-01"
    )
    assert len(rows) > 0

    invocations = telemetry_ledger.get_run_invocations("test-run-mcp-01")
    assert len(invocations) == 1
    inv = invocations[0]
    assert inv.phase == "candidate_retrieval"
    assert inv.tool_name == "run_query"
    assert inv.transport in ("official-mcp-fastmcp", "test-adapter-mock")
    assert inv.latency_ms >= 0
    assert inv.returned_rows == len(rows)


@pytest.mark.asyncio
async def test_agent_runtime_p0_reveals_execution():
    # 1. Anderson identity reveal
    anderson_res = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="test-run-anderson-01"
    )
    assert anderson_res["status"] in ("COMPLETED", "ABSTAINED")
    assert len(anderson_res["hypotheses"]) >= 1
    assert len(anderson_res["telemetries"]) >= 3

    # 2. Secret room location reveal
    secret_res = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-secret-room-location",
        cutoff_ms=3660000,
        analysis_run_id="test-run-secret-01"
    )
    assert secret_res["status"] in ("COMPLETED", "ABSTAINED")
    assert len(secret_res["hypotheses"]) >= 1



def test_proof_validator_rejects_future_scene_leakage():
    # Attempting to validate a proof citing a future scene (e.g. c041 at 4800000ms against cutoff 3660000ms)
    invalid_candidate = {
        "proof_id": "invalid-future-proof",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c011", "timestamp_ms": 1320000},
            {"scene_id": "scene-tbw-c041", "timestamp_ms": 4800000}
        ],
        "observed_premises": [
            {"event_id": "ev-c011-01", "scene_id": "scene-tbw-c011", "timestamp_ms": 1320000}
        ],
        "alternative_explanations": ["Alternative explanation"],
        "counterfactual_results": {"wrong_reveal_delta": -0.8}
    }

    result = proof_validator.validate(invalid_candidate, spoiler_cutoff_ms=3660000)
    assert result.is_valid is False
    assert result.temporal_valid is False
    assert result.verdict == ProofValidationVerdict.INVALID


def test_proof_validator_rejects_single_scene_proof():
    # Proof with only 1 scene
    single_scene_candidate = {
        "proof_id": "invalid-single-scene",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c011", "timestamp_ms": 1320000}
        ],
        "observed_premises": [
            {"event_id": "ev-c011-01", "scene_id": "scene-tbw-c011", "timestamp_ms": 1320000}
        ],
        "alternative_explanations": ["Alternative"],
        "counterfactual_results": {"wrong_reveal_delta": -0.8}
    }

    result = proof_validator.validate(single_scene_candidate, spoiler_cutoff_ms=4860000)
    assert result.is_valid is False
    assert result.evidence_grounded is False
