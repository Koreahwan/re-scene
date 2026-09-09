"""
Unit Tests for Deep Analysis Snapshot V1, Epistemic Resolver & Live Isolation Boundary
Tests:
1. Snapshot file existence (all 20 files)
2. Snapshot schema and referential integrity against canonical V3 dataset
3. Timestamp range validity
4. KnowledgeStateResolver loading from snapshot without hardcoded branches
5. Live vs Offline isolation (DEVELOPMENT_ANSWER_ASSISTED vs LIVE_ANSWER_ASSISTED=False)
6. Proof candidate honest review status and presentation_status
"""
import os
import json
import pytest

from src.reframe.evidence.adapter import v3_adapter
from src.reframe.narrative.obligations import (
    KnowledgeStateResolver,
    AvailabilityStatus
)
from src.reframe.agents.adk_gateway import LIVE_ANSWER_ASSISTED
from src.reframe.narrative.bundle import bundle_builder
from src.reframe.domain.enums import ExecutionMode
from src.reframe.proof.store import CANONICAL_PROOFS_MAP, CANONICAL_PATTERNS_MAP


SNAPSHOT_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1")


def test_01_all_20_snapshot_files_exist():
    """All 20 snapshot files must exist and be non-empty."""
    expected_files = [
        "manifest.json",
        "evidence_index.json",
        "characters.json",
        "knowledge_propositions.json",
        "character_epistemic_states.json",
        "claims.json",
        "actions.json",
        "claim_action_relations.json",
        "access_opportunities.json",
        "goals.json",
        "plan_steps.json",
        "causal_edges.json",
        "motifs.json",
        "negative_evidence.json",
        "proof_candidates.json",
        "why_missed.json",
        "human_review_queue.json",
        "analysis_report.md",
        os.path.join("reveal_analysis", "reveal-anderson-identity.json"),
        os.path.join("reveal_analysis", "reveal-secret-room-location.json")
    ]
    for rel_path in expected_files:
        full_path = os.path.join(SNAPSHOT_DIR, rel_path)
        assert os.path.exists(full_path), f"Missing snapshot file: {rel_path}"
        assert os.path.getsize(full_path) > 0, f"Empty snapshot file: {rel_path}"


def test_02_snapshot_manifest_fields():
    """Manifest must declare proper metadata and zero external API calls."""
    with open(os.path.join(SNAPSHOT_DIR, "manifest.json"), "r", encoding="utf-8") as f:
        manifest = json.load(f)

    assert manifest["snapshot_id"] == "the_bat_whispers_deep_snapshot_v1"
    assert manifest["generation_mode"] == "GEMINI_INTERACTIVE_DEEP_SNAPSHOT"
    assert manifest["external_model_api_calls"] == 0
    assert manifest["answer_assisted_fixture"] is True
    assert manifest["trust_namespace"] == "ENGINE_INFERENCE"
    assert manifest["human_review_status"] == "NOT_REVIEWED"
    assert manifest["movie_id"] == "the-bat-whispers-1930"
    assert manifest["canonical_asset_sha256"] == "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"


def test_03_snapshot_referential_integrity():
    """All scene, event, and fact references in snapshot must exist in canonical V3 dataset."""
    valid_scenes = {s.scene_id for s in v3_adapter.get_scenes()}
    valid_events = {e.event_id for e in v3_adapter.get_events()}
    valid_facts = {f.fact_id for f in v3_adapter.get_facts()}

    with open(os.path.join(SNAPSHOT_DIR, "proof_candidates.json"), "r", encoding="utf-8") as f:
        candidates = json.load(f)

    for cand in candidates:
        for ec in cand.get("evidence_chain", []):
            sid = ec.get("scene_id")
            assert sid in valid_scenes, f"Invalid scene_id in evidence_chain: {sid}"
            assert ec.get("timestamp_ms", 0) >= 0

        for prem in cand.get("observed_premises", []):
            sid = prem.get("scene_id")
            eid = prem.get("event_id")
            fid = prem.get("fact_id")
            if sid:
                assert sid in valid_scenes, f"Invalid scene_id in premise: {sid}"
            if eid:
                assert eid in valid_events, f"Invalid event_id in premise: {eid}"
            if fid:
                assert fid in valid_facts, f"Invalid fact_id in premise: {fid}"


def test_04_snapshot_timestamps_within_valid_runtime():
    """All timestamps across snapshot actions and claims must be within movie runtime (5119080ms)."""
    max_runtime_ms = 5119080

    with open(os.path.join(SNAPSHOT_DIR, "actions.json"), "r", encoding="utf-8") as f:
        actions = json.load(f)
    for act in actions:
        ts = act.get("timestamp_ms", 0)
        assert 0 <= ts <= max_runtime_ms, f"Action timestamp {ts} out of bounds"

    with open(os.path.join(SNAPSHOT_DIR, "claims.json"), "r", encoding="utf-8") as f:
        claims = json.load(f)
    for clm in claims:
        ts = clm.get("timestamp_ms", 0)
        assert 0 <= ts <= max_runtime_ms, f"Claim timestamp {ts} out of bounds"


def test_05_knowledge_state_resolver_loads_from_snapshot():
    """KnowledgeStateResolver must load propositions from deep snapshot v1."""
    # Reset cache to test loading
    KnowledgeStateResolver._cached_propositions = None

    kp_anderson = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Detective Anderson carries blueprints across the room",
        cutoff_ms=4860000
    )
    assert kp_anderson.availability_status == AvailabilityStatus.INFERRED
    assert kp_anderson.subject == "Detective Anderson"
    assert kp_anderson.public_available_from_ms == 4860000
    assert kp_anderson.character_available_from_ms == 120000

    kp_secret_room = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Dale Ogden",
        proposition="Dale operates the fireplace mantel mechanism",
        cutoff_ms=3660000
    )
    assert kp_secret_room.availability_status == AvailabilityStatus.INFERRED
    assert kp_secret_room.public_available_from_ms == 3660000
    assert kp_secret_room.character_available_from_ms == 3645000

    # Unknown character / proposition fails closed
    kp_unknown = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Random Extra",
        proposition="Random unrelated proposition",
        cutoff_ms=3660000
    )
    assert kp_unknown.availability_status == AvailabilityStatus.UNKNOWN
    assert kp_unknown.public_available_from_ms == 0


def test_06_live_isolation_boundary_enforced():
    """Live execution mode must strictly isolate snapshot fixtures and golden answers."""
    assert LIVE_ANSWER_ASSISTED is False

    from src.reframe.narrative.channels import EvidenceSeed
    seeds = [
        EvidenceSeed(
            channel_name="ENTITY",
            scene_ids=["scene-tbw-c017"],
            event_ids=["ev-c017-05"],
            cutoff_ms=4860000,
            channel_rationale="Anderson stands alone in the dark hall",
            evidence_hashes=["hash-01"]
        )
    ]
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    bundle = bundle_builder.build_bundle(
        reveal=reveal,
        cutoff_ms=4860000,
        provided_seeds=seeds,
        execution_mode=ExecutionMode.LIVE_GOOGLE
    )

    bundle_json = bundle.model_dump_json()
    assert "deep_snapshot_v1" not in bundle_json
    assert "CANONICAL_PROOFS_MAP" not in bundle_json
    assert "the_bat_whispers_deep_snapshot_v1" not in bundle_json


def test_07_canonical_proofs_presentation_statuses():
    """All unverified / development candidates must be HIDDEN_FROM_PUBLIC, and all candidates must be NOT_REVIEWED or NEEDS_CORRECTION."""
    for rev_id, proofs in CANONICAL_PATTERNS_MAP.items():
        for p in proofs:
            assert p.get("human_review_status") in {"NOT_REVIEWED", "NEEDS_CORRECTION"}
            assert p.get("presentation_status") == "HIDDEN_FROM_PUBLIC", (
                f"Candidate {p.get('proof_id')} must be HIDDEN_FROM_PUBLIC until independently proven"
            )
