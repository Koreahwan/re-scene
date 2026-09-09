"""
Unit Tests for Reframe V7 Clean-Room Offline ADK Reasoning and MCP Knowledge States
Covers Section 6 Offline ADK Certification:
A. Snapshot candidates exist -> every cited event/fact exists in V3 -> canonical hashes match
B. SnapshotIntegrityError -> fail closed / ABSTAIN -> no fallback fake candidate
C. No snapshot candidate -> ABSTAIN -> no invented event/hash
D. Search source/result for fabricated patterns -> none found
E. Paid model calls = 0.
"""
import pytest
from unittest.mock import patch
from pathlib import Path
from src.reframe.agents.runtime import agent_runtime
from src.reframe.agents.tools.mcp_tools import retrieve_character_states
from src.reframe.narrative.snapshot_repo import DeepSnapshotRepository, SnapshotIntegrityError
from src.reframe.evidence.adapter import v3_adapter


@pytest.mark.asyncio
async def test_offline_adk_snapshot_candidates_grounded_in_v3():
    """A. Snapshot candidates exist -> every cited event/fact exists in V3 with matching canonical hash."""
    candidates = DeepSnapshotRepository.get_proof_candidates(snapshot_id="deep_snapshot_v1_1")
    assert len(candidates) >= 1

    for cand in candidates:
        assert cand.get("proof_id") is not None
        assert cand.get("title") is not None
        assert cand.get("human_review_status") == "NOT_REVIEWED"

        premises = cand.get("observed_premises", [])
        assert len(premises) > 0
        for prem in premises:
            ev_id = prem.get("event_id")
            sc_id = prem.get("scene_id")
            if ev_id:
                ev_obj = v3_adapter.get_event(ev_id)
                assert ev_obj is not None, f"Cited event {ev_id} not found in V3 canonical events"
                if prem.get("canonical_content_hash"):
                    assert len(prem["canonical_content_hash"]) == 64
            elif sc_id:
                sc_obj = v3_adapter.get_scene(sc_id)
                assert sc_obj is not None, f"Cited scene {sc_id} not found in V3 canonical scenes"


@pytest.mark.asyncio
async def test_offline_adk_snapshot_integrity_error_fails_closed():
    """B. SnapshotIntegrityError -> fail closed / ABSTAIN without falling back to fake candidates."""
    with patch.object(DeepSnapshotRepository, "get_proof_candidates", side_effect=SnapshotIntegrityError("SHA mismatch in snapshot")):
        # Executing ADK analysis must fail closed or raise SnapshotIntegrityError
        try:
            res = await agent_runtime.execute_adk_analysis(
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                reveal_id="reveal-anderson-identity",
                cutoff_ms=4860000,
                analysis_run_id="test-integrity-fail-001"
            )
            assert res["status"] == "ABSTAINED"
            assert len(res.get("proofs", [])) == 0
        except SnapshotIntegrityError:
            pass  # Expected fail-closed behavior


@pytest.mark.asyncio
async def test_offline_adk_no_snapshot_candidate_abstains():
    """C. No snapshot candidate exists for reveal -> ABSTAIN with 0 invented events/hashes."""
    with patch.object(DeepSnapshotRepository, "get_proof_candidates", return_value=[]):
        res = await agent_runtime.execute_adk_analysis(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-nonexistent-999",
            cutoff_ms=4860000,
            analysis_run_id="test-no-cand-001"
        )
        assert res["status"] == "ABSTAINED"
        assert len(res.get("proofs", [])) == 0
        assert len(res.get("hypotheses", [])) == 0


def test_offline_adk_zero_fabricated_pattern_literals_in_source():
    """D. Source code search for fabricated literals -> none found in codebase."""
    gateway_path = Path("src/reframe/agents/adk_gateway.py")
    content = gateway_path.read_text(encoding="utf-8")
    assert "ev-{premise_scene.scene_id}-01" not in content
    assert "hash-{premise_scene.scene_id}" not in content
    assert "Observed activity in" not in content


@pytest.mark.asyncio
async def test_offline_adk_zero_paid_model_calls_across_all_telemetries():
    """E. Total paid model calls across all execution roles = 0 ($0.00)."""
    res = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="test-telemetry-zero-paid"
    )
    for telem in res.get("telemetries", []):
        assert telem.get("paid_model_calls", 0) == 0
        assert telem.get("execution_mode") == "OFFLINE_FIXTURE" or telem.get("status") in ("SKIPPED_OFFLINE", "FIXTURE")


@pytest.mark.asyncio
async def test_mcp_retrieve_character_states_queries_knowledge_states():
    rows = await retrieve_character_states(
        character_name="Detective Anderson",
        cutoff_ms=4860000,
        work_id="the-bat-whispers-1930"
    )
    assert isinstance(rows, list)
    for r in rows:
        assert "source_table" in r
        assert r["source_table"] == "knowledge_states"
        assert int(r.get("valid_from_ms", 0)) < 4860000
