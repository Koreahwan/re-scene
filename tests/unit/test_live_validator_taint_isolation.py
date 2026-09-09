"""
Unit Test Suite for Live Validator Taint Isolation and Epistemic Semantics (Requirement 12 / Patch)
Proves that in LIVE_GOOGLE mode:
1. Generic scene/event/action rows DO NOT infer knowledge (fails closed with UNKNOWN / INVALID).
2. Typed proposition-specific MCP knowledge rows allow pure live epistemic evaluation.
3. ProofValidator and CounterfactualEngine never access offline development snapshot files.
4. DeepSnapshotRepository._load_json call count in LIVE_GOOGLE is strictly 0.
Zero Paid Model Calls ($0.00).
"""
import pytest
from unittest.mock import patch, MagicMock

from src.reframe.domain.enums import ExecutionMode
from src.reframe.narrative.obligations import (
    ProofValidationContext,
    KnowledgeSourceType,
    KnowledgeStateResolver,
    AvailabilityStatus,
    LiveKnowledgeEvidence
)
from src.reframe.narrative.snapshot_repo import DeepSnapshotRepository
from src.reframe.proof.validator import proof_validator, ProofValidationVerdict
from src.reframe.proof.hasher import canonical_event_hash
from src.reframe.narrative.counterfactual import counterfactual_engine


@pytest.fixture
def synthetic_live_candidate():
    return {
        "proof_id": "proof-live-test-01",
        "proof_type": "KNOWLEDGE_LEAK",
        "title": "Detective Anderson Performs Unbriefed Search Operations",
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
                "canonical_content_hash": canonical_event_hash("ev-c017-05")
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson carries rolled papers across the room and unrolls blueprints before Dale and the group.",
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            }
        ],
        "alternative_explanations": ["Standard police sweep", "Routine plan review"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }


def test_live_google_validator_case_a_generic_events_fail_closed(synthetic_live_candidate):
    """
    Case A: Generic Anderson event rows only.
    - Snapshot access = 0
    - Knowledge state UNKNOWN
    - KNOWLEDGE_LEAK INVALID
    """
    generic_event_rows = [
        {
            "actor": "Detective Anderson",
            "action": "observe",
            "timestamp_ms": 2010000,
            "event_id": "ev-c017-05",
            "scene_id": "scene-tbw-c017",
            "source_table": "events"
        },
        {
            "actor": "Detective Anderson",
            "action": "displays",
            "timestamp_ms": 2490000,
            "event_id": "ev-c021-03",
            "scene_id": "scene-tbw-c021",
            "source_table": "events"
        }
    ]

    context_generic = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=generic_event_rows
    )

    load_json_spy = MagicMock(side_effect=DeepSnapshotRepository._load_json)

    with patch.object(DeepSnapshotRepository, "_load_json", load_json_spy):
        # 1. Epistemic state resolution must fail closed with UNKNOWN
        kp = KnowledgeStateResolver.resolve_epistemic_state(
            work_id="the-bat-whispers-1930",
            character="Detective Anderson",
            proposition="Detective Anderson carries blueprints",
            cutoff_ms=4860000,
            context=context_generic
        )
        assert kp.availability_status == AvailabilityStatus.UNKNOWN
        assert kp.confidence == 0.0

        # 2. Validator must reject ungrounded knowledge leak
        val_res = proof_validator.validate(
            synthetic_live_candidate,
            spoiler_cutoff_ms=4860000,
            context=context_generic
        )
        assert val_res.is_valid is False
        assert val_res.verdict == ProofValidationVerdict.INVALID

        # 3. Snapshot repository must NOT have been opened
        assert load_json_spy.call_count == 0


def test_live_google_validator_case_b_typed_epistemic_evidence_succeeds(synthetic_live_candidate):
    """
    Case B: Typed proposition-specific MCP knowledge row.
    - Snapshot access = 0
    - Knowledge state KNOWN
    - Obligation evaluation proceeds live
    """
    typed_epistemic_rows = [
        LiveKnowledgeEvidence(
            character="Detective Anderson",
            proposition_id="prop-live-01",
            normalized_proposition="Detective Anderson carries and unrolls blueprints",
            availability_ms=2010000,
            public_available_from_ms=4860000,
            access_type="OBSERVED",
            evidence_refs=["ev-c017-05", "ev-c021-03"],
            source_table="epistemic_evidence",
            confidence=0.95
        ).model_dump()
    ]

    context_typed = ProofValidationContext(
        execution_mode=ExecutionMode.LIVE_GOOGLE,
        evidence_source="LIVE_MCP",
        knowledge_source=KnowledgeSourceType.LIVE_MCP_EVIDENCE_ONLY,
        answer_assisted=False,
        mcp_evidence=typed_epistemic_rows
    )

    load_json_spy = MagicMock(side_effect=DeepSnapshotRepository._load_json)

    with patch.object(DeepSnapshotRepository, "_load_json", load_json_spy):
        # 1. Epistemic state resolution succeeds from live epistemic evidence
        kp = KnowledgeStateResolver.resolve_epistemic_state(
            work_id="the-bat-whispers-1930",
            character="Detective Anderson",
            proposition="Detective Anderson carries and unrolls blueprints",
            cutoff_ms=4860000,
            context=context_typed
        )
        assert kp.availability_status == AvailabilityStatus.KNOWN
        assert kp.predicate == "OBSERVED_OPERATIONAL_KNOWLEDGE"
        assert kp.character_available_from_ms == 2010000

        # 2. Counterfactual tournament evaluates live without snapshot access
        cf_res = counterfactual_engine.run_tournament(
            synthetic_live_candidate,
            target_reveal_id="reveal-anderson-identity",
            context=context_typed
        )
        assert cf_res is not None

        # 3. Snapshot repository was NEVER opened
        assert load_json_spy.call_count == 0
