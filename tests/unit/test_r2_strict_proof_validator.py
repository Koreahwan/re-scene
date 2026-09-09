"""
Unit Tests for R2-01 & R2-02 Strict Proof Validation and Mutation Tests
Zero Paid Model Calls.
"""
import pytest
from src.reframe.proof.validator import (
    DeterministicProofValidator,
    ProofValidationVerdict,
    ProofValidationErrorCode,
    proof_validator
)
from src.reframe.evidence.adapter import v3_adapter


from src.reframe.proof.hasher import canonical_event_hash


def test_canonical_seeded_proofs_validate_successfully():
    """Verify that legitimate grounded proofs pass deterministic validation and non-normative types fail."""
    p1 = {
        "proof_id": "test-valid-anderson-01",
        "proof_type": "CLAIM_ACTION_CONFLICT",
        "title": "Detective Anderson Stated Alibi Contradicts Manor Presence",
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
                "fact": "Detective Anderson claimed he was away outside and not in the manor.",
                "canonical_content_hash": canonical_event_hash("ev-c017-05")
            },
            {
                "event_id": "ev-c021-03",
                "scene_id": "scene-tbw-c021",
                "timestamp_ms": 2490000,
                "actor": "Detective Anderson",
                "action": "displays",
                "fact": "Detective Anderson enters inside the safe room and searches the blueprints.",
                "canonical_content_hash": canonical_event_hash("ev-c021-03")
            }
        ],
        "alternative_explanations": ["Standard police investigation sweep", "Routine examination of architectural plans"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }
    result = proof_validator.validate(p1, spoiler_cutoff_ms=4860000)
    assert result.is_valid is True
    assert result.verdict == ProofValidationVerdict.VALID
    assert result.temporal_valid is True
    assert result.evidence_grounded is True
    assert len(result.error_codes) == 0

    # Non-normative proof types (e.g. MULTI_SCENE_PATTERN) must be rejected
    p_pattern = dict(p1, proof_type="MULTI_SCENE_PATTERN")
    res_pattern = proof_validator.validate(p_pattern, spoiler_cutoff_ms=4860000)
    assert res_pattern.is_valid is False
    assert ProofValidationErrorCode.PROOF_OBLIGATION_FAILED in res_pattern.error_codes


def test_mutation_rejects_unknown_event_id():
    """R2-02: Validator must reject unknown event ID without prefix exception."""
    mutated = {
        "proof_id": "test-mut-unknown-event",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {"event_id": "ev-fabricated-999", "scene_id": "scene-tbw-c017", "timestamp_ms": 2010000, "fact": "Fabricated event statement"},
            {"event_id": "ev-c021-03", "scene_id": "scene-tbw-c021", "timestamp_ms": 2490000, "fact": "Detective Anderson carries rolled papers across the room."}
        ],
        "alternative_explanations": ["Routine sweep"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }
    result = proof_validator.validate(mutated, spoiler_cutoff_ms=4860000)
    assert result.is_valid is False
    assert result.verdict == ProofValidationVerdict.INVALID
    assert ProofValidationErrorCode.UNKNOWN_EVENT in result.error_codes


def test_mutation_rejects_event_scene_mismatch():
    """R2-02: Validator must reject premise where event's canonical scene does not match cited scene."""
    mutated = {
        "proof_id": "test-mut-scene-mismatch",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c011", "timestamp_ms": 1320000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {"event_id": "ev-c017-05", "scene_id": "scene-tbw-c011", "timestamp_ms": 2010000, "fact": "Detective Anderson stands alone in the dark hall."},
            {"event_id": "ev-c021-03", "scene_id": "scene-tbw-c021", "timestamp_ms": 2490000, "fact": "Detective Anderson carries rolled papers."}
        ],
        "alternative_explanations": ["Routine sweep"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }
    result = proof_validator.validate(mutated, spoiler_cutoff_ms=4860000)
    assert result.is_valid is False
    assert ProofValidationErrorCode.EVENT_SCENE_MISMATCH in result.error_codes


def test_mutation_rejects_timestamp_divergence():
    """R2-02: Validator must reject premise where cited timestamp diverges from canonical event timestamp."""
    mutated = {
        "proof_id": "test-mut-timestamp-divergence",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
        ],
        "observed_premises": [
            {"event_id": "ev-c017-05", "scene_id": "scene-tbw-c017", "timestamp_ms": 500000, "fact": "Detective Anderson stands alone."},
            {"event_id": "ev-c021-03", "scene_id": "scene-tbw-c021", "timestamp_ms": 2490000, "fact": "Detective Anderson carries rolled papers."}
        ],
        "alternative_explanations": ["Routine sweep"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }
    result = proof_validator.validate(mutated, spoiler_cutoff_ms=4860000)
    assert result.is_valid is False
    assert ProofValidationErrorCode.TIMESTAMP_MISMATCH in result.error_codes


def test_mutation_rejects_future_scene_leakage():
    """R2-02: Validator must reject any evidence occurring after spoiler cutoff."""
    mutated = {
        "proof_id": "test-mut-future-leak",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
            {"scene_id": "scene-tbw-c041", "timestamp_ms": 4830000}
        ],
        "observed_premises": [
            {"event_id": "ev-c017-05", "scene_id": "scene-tbw-c017", "timestamp_ms": 2010000, "fact": "Detective Anderson stands alone."},
            {"event_id": "ev-c041-02", "scene_id": "scene-tbw-c041", "timestamp_ms": 4830000, "fact": "Police tackle cloaked Bat."}
        ],
        "alternative_explanations": ["Routine sweep"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }
    # Against secret room cutoff (3660000 ms)
    result = proof_validator.validate(mutated, spoiler_cutoff_ms=3660000)
    assert result.is_valid is False
    assert ProofValidationErrorCode.FUTURE_SCENE in result.error_codes


def test_mutation_rejects_single_scene_proof():
    """R2-02: Validator must reject single-scene proof."""
    mutated = {
        "proof_id": "test-mut-single-scene",
        "proof_type": "KNOWLEDGE_LEAK",
        "evidence_chain": [
            {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}
        ],
        "observed_premises": [
            {"event_id": "ev-c017-05", "scene_id": "scene-tbw-c017", "timestamp_ms": 2010000, "fact": "Detective Anderson stands alone."}
        ],
        "alternative_explanations": ["Routine sweep"],
        "counterfactual_results": {"wrong_reveal_delta": -0.85, "ablation_delta": -0.65}
    }
    result = proof_validator.validate(mutated, spoiler_cutoff_ms=4860000)
    assert result.is_valid is False
    assert ProofValidationErrorCode.PROOF_OBLIGATION_FAILED in result.error_codes
