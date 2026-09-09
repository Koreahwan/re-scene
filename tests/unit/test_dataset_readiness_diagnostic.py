"""
Unit tests for DatasetReadinessDiagnostic (G1-C).
Verifies baseline integrity, entity counts, referential integrity, and proof type prerequisites.
Ensures injected faults trigger explicit FAIL status with concrete error reporting.
Zero Paid Model Calls.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import patch

from src.reframe.evidence.readiness import DatasetReadinessDiagnostic, readiness_diagnostic


def test_audit_file_integrity():
    """All 6 V3 canonical data and preflight audit files exist with valid SHA-256."""
    res = readiness_diagnostic.audit_file_integrity()
    assert res["status"] == "PASS"
    files = res["files"]
    assert "v3_dataset_export" in files
    assert "reveals_registry" in files
    assert "canonical_corrections_v3" in files
    assert "preprocessing_checkpoint_v3_gemini36" in files
    assert "v3_frame_manifest" in files
    assert "v7_p2_gate4_preflight" in files

    for f_info in files.values():
        assert f_info["exists"] is True
        assert f_info["size_bytes"] > 0
        assert len(f_info["sha256"]) == 64


def test_audit_entity_counts_and_baselines():
    """Exact baseline validation: 43 scenes, 187 events, 94 facts, 385 frames, 4 reveals."""
    res = readiness_diagnostic.audit_entity_counts_and_baselines()
    assert res["status"] == "PASS"
    counts = res["counts"]
    assert counts["scenes"] == 43
    assert counts["events"] == 187
    assert counts["facts"] == 94
    assert counts["frames"] == 385
    assert counts["registry_reveals"] == 4
    assert counts["checkpoint_chunks"] == 43
    assert all(res["checks"].values())


def test_audit_referential_integrity():
    """Referential integrity across scenes, events, facts, frames, corrections, and reveals."""
    res = readiness_diagnostic.audit_referential_integrity()
    assert res["status"] == "PASS"
    assert res["unresolved_count"] == 0
    assert len(res["errors"]) == 0


def test_audit_proof_type_prerequisites():
    """Evaluates readiness for KNOWLEDGE_LEAK, CLAIM_ACTION_CONFLICT, HIDDEN_PLAN_CHAIN."""
    res = readiness_diagnostic.audit_proof_type_prerequisites()
    assert res["status"] == "FAIL"  # Truthfully reflects that prerequisites are PARTIAL_INCOMPLETE or MISSING
    evals = res["evaluations"]

    # Target Reveal 1: Anderson Identity
    assert "reveal-anderson-identity" in evals
    anderson_eval = evals["reveal-anderson-identity"]
    anderson_pts = anderson_eval["proof_types"]
    assert "KNOWLEDGE_LEAK" in anderson_pts
    assert "CLAIM_ACTION_CONFLICT" in anderson_pts
    assert "HIDDEN_PLAN_CHAIN" in anderson_pts

    # Anderson Knowledge states have predicate=None in current export
    assert anderson_pts["KNOWLEDGE_LEAK"]["status"] == "PARTIAL_INCOMPLETE"
    assert anderson_pts["HIDDEN_PLAN_CHAIN"]["status"] == "READY"

    # Target Reveal 2: Secret Room Location
    assert "reveal-secret-room-location" in evals
    secret_room_eval = evals["reveal-secret-room-location"]
    secret_room_pts = secret_room_eval["proof_types"]
    assert "KNOWLEDGE_LEAK" in secret_room_pts
    assert "CLAIM_ACTION_CONFLICT" in secret_room_pts
    assert "HIDDEN_PLAN_CHAIN" in secret_room_pts


def test_injected_fault_triggers_diagnostic_failure(tmp_path):
    """Fault injection: Missing file or corrupted ID triggers explicit FAIL."""
    diag = DatasetReadinessDiagnostic(data_root=str(tmp_path))
    # Empty directory -> file integrity must fail
    res = diag.audit_file_integrity()
    assert res["status"] == "FAIL"
    assert res["files"]["v3_dataset_export"]["exists"] is False
