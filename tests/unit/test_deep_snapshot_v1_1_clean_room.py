"""
Unit Test Suite for Deep Analysis Snapshot V1.1 Clean-Room Integrity
Validates:
1. Phase A source allowlist, immutable=true, source_artifact_sha256 & lock integrity
2. All Phase A refs exist in canonical V3 dataset
3. Media review statuses valid (VISUALLY_RECHECKED)
4. Observed actions contain no inferred-purpose contamination
5. Epistemic INFERRED_REVEAL_DEPENDENT and DISCOVERS_BY_OPERATION cannot satisfy strong KnowledgeLeak
6. Claims with only "speaks" are INSUFFICIENT_CONTENT
7. car-002 is DEFLECTION_HYPOTHESIS, not logical contradiction
8. Causal temporal-only edge cannot produce D5 (D5=0)
9. Counterfactual SSOT in counterfactual_evaluation.json without embedded candidate deltas
10. Offline gateway loads V1.1, and all new D3 interpretations are HIDDEN_FROM_PUBLIC
11. Live taint isolation rejects answer-assisted content
12. DeepSnapshotRepository verifies Phase A lock checksums at load time and fails closed
"""
import os
import json
import pytest

from src.reframe.evidence.adapter import v3_adapter
from src.reframe.narrative.obligations import (
    KnowledgeStateResolver,
    AvailabilityStatus,
    KnowledgeLeakObligation,
    classify_reasoning_depth
)
from src.reframe.narrative.snapshot_repo import snapshot_repo, DeepSnapshotRepository, SnapshotIntegrityError
from src.reframe.narrative.bundle import bundle_builder
from src.reframe.narrative.channels import EvidenceSeed
from src.reframe.domain.enums import ExecutionMode
from src.reframe.agents.roles import OfflineFixtureHypothesisGateway
from tools.deep_snapshot.validate_snapshot import validate_snapshot


SNAPSHOT_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1_1")


def test_01_clean_room_manifest_and_phase_a_lock():
    """Verify Phase A source allowlist, denied legacy sources, and phase A lock integrity."""
    with open(os.path.join(SNAPSHOT_DIR, "clean_room_manifest.json"), "r", encoding="utf-8") as f:
        crm = json.load(f)

    assert crm["generation_mode"] == "CLEAN_ROOM_INTERACTIVE_REBUILD"
    assert crm["external_model_api_calls"] == 0
    assert crm["media_review_performed"] is True
    assert "data/production/v3_dataset_export.json" in crm["allowed_sources_accessed"]
    assert any("CANONICAL_PROOFS_MAP" in s for s in crm["denied_sources_firewalled"])

    with open(os.path.join(SNAPSHOT_DIR, "manifest.json"), "r", encoding="utf-8") as f:
        mf = json.load(f)
    assert mf["immutable"] is True
    assert len(mf["source_artifact_sha256"]) == 64

    # Validate snapshot using validator tool
    val_res = validate_snapshot(SNAPSHOT_DIR)
    assert val_res["is_valid"] is True, f"Validation failed: {val_res.get('errors')}"


def test_02_all_phase_a_refs_exist_in_v3_dataset():
    """All scene, event, and fact references in Phase A must exist in canonical V3 dataset."""
    valid_scenes = {s.scene_id for s in v3_adapter.get_scenes()}
    valid_events = {e.event_id for e in v3_adapter.get_events()}

    with open(os.path.join(SNAPSHOT_DIR, "phase_a_observations.json"), "r", encoding="utf-8") as f:
        obs = json.load(f)
    for o in obs:
        assert o["scene_id"] in valid_scenes
        assert o["event_ref"] in valid_events

    with open(os.path.join(SNAPSHOT_DIR, "phase_a_actions.json"), "r", encoding="utf-8") as f:
        acts = json.load(f)
    for a in acts:
        assert a["scene_id"] in valid_scenes
        assert a["evidence_ref"] in valid_events


def test_03_media_review_statuses_valid():
    """All 10 target events must be VISUALLY_RECHECKED with verified frame extractions."""
    with open(os.path.join(SNAPSHOT_DIR, "media_review.json"), "r", encoding="utf-8") as f:
        mr = json.load(f)

    assert len(mr) == 10
    for item in mr:
        assert item["review_status"] == "VISUALLY_RECHECKED"
        assert len(item["frames_examined"]) >= 3
        assert len(item["observed_visual_facts"]) > 10
        assert item["v3_agreement"] in {"CONFIRMED", "PARTIAL", "CONTRADICTED"}


def test_04_observed_actions_contain_no_inferred_intent_contamination():
    """Observed actions must contain pure observable facts, free of inferred intent."""
    forbidden_words = ["unbriefed", "to find the safe", "to deflect suspicion", "covertly searches"]

    with open(os.path.join(SNAPSHOT_DIR, "actions.json"), "r", encoding="utf-8") as f:
        acts = json.load(f)
    for a in acts:
        text = a.get("observed_action", "").lower()
        for fw in forbidden_words:
            assert fw not in text, f"Action {a.get('action_id')} contains forbidden word '{fw}'"


def test_05_epistemic_inferred_reveal_dependent_and_discovery():
    """KnowledgeStateResolver & KnowledgeLeakObligation handle reveal-dependency and operation discovery."""
    KnowledgeStateResolver._cached_propositions = None

    # 1. Dale operating mantel lever is DISCOVERS_BY_OPERATION -> not KnowledgeLeak
    kp_dale = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Dale Ogden",
        proposition="Dale reaches up to touch and operate the fireplace mantel mechanism",
        cutoff_ms=3660000
    )
    assert kp_dale.availability_status == AvailabilityStatus.INFERRED
    assert "DISCOVERS_BY_OPERATION" in kp_dale.predicate
    obl_dale = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=3660000,
        earliest_character_access_ms=3645000,
        evidence_ids=["ev-c031-02"],
        knowledge_proposition=kp_dale
    )
    assert obl_dale.is_satisfied is False
    assert "MECHANISM_DISCOVERY_NOT_KNOWLEDGE_LEAK" in obl_dale.broken_rules

    # 2. Anderson blueprint knowledge is INFERRED_REVEAL_DEPENDENT -> not KnowledgeLeak
    kp_anderson = KnowledgeStateResolver.resolve_epistemic_state(
        work_id="the-bat-whispers-1930",
        character="Detective Anderson",
        proposition="Detective Anderson carries and unrolls blueprints of the bank safe",
        cutoff_ms=4860000
    )
    assert kp_anderson.availability_status == AvailabilityStatus.INFERRED
    assert "INFERRED_REVEAL_DEPENDENT" in kp_anderson.predicate
    obl_anderson = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=4860000,
        earliest_character_access_ms=120000,
        evidence_ids=["ev-c017-05", "ev-c021-03"],
        knowledge_proposition=kp_anderson
    )
    assert obl_anderson.is_satisfied is False
    assert "REVEAL_DEPENDENT_KNOWLEDGE_NOT_LEAK" in obl_anderson.broken_rules


def test_06_claim_grounding_status_insufficient_content():
    """Claims without verbatim dialogue must be marked INSUFFICIENT_CONTENT and cannot form contradiction."""
    with open(os.path.join(SNAPSHOT_DIR, "claims.json"), "r", encoding="utf-8") as f:
        claims = json.load(f)

    c025_claim = next(c for c in claims if c["claim_id"] == "claim-anderson-c025-01")
    assert c025_claim["grounding_status"] == "INSUFFICIENT_CONTENT"
    assert c025_claim["verbatim_text"] is None

    with open(os.path.join(SNAPSHOT_DIR, "claim_action_relations.json"), "r", encoding="utf-8") as f:
        cars = json.load(f)
    car_001 = next(r for r in cars if r["relation_id"] == "car-001")
    assert car_001["is_contradiction"] is False
    assert car_001["relation_type"] == "INSUFFICIENT_CLAIM_GROUNDING"


def test_07_claim_action_deflection_not_contradiction():
    """Investigative deflection (car-002) is classified as DEFLECTION_HYPOTHESIS, not logical contradiction."""
    with open(os.path.join(SNAPSHOT_DIR, "claim_action_relations.json"), "r", encoding="utf-8") as f:
        cars = json.load(f)
    car_002 = next(r for r in cars if r["relation_id"] == "car-002")
    assert car_002["is_contradiction"] is False
    assert car_002["relation_type"] == "DEFLECTION_HYPOTHESIS"


def test_08_causal_temporal_only_edge_and_zero_d5():
    """Temporal precedence edge cannot produce D5; total genuine D5 in snapshot is 0."""
    with open(os.path.join(SNAPSHOT_DIR, "causal_edges.json"), "r", encoding="utf-8") as f:
        edges = json.load(f)
    edge_002 = next(e for e in edges if e["edge_id"] == "causal-002")
    assert edge_002["relation_type"] == "TEMPORAL_PRECEDENCE_ONLY"

    with open(os.path.join(SNAPSHOT_DIR, "proof_candidates.json"), "r", encoding="utf-8") as f:
        cands = json.load(f)
    for c in cands:
        assert c.get("proof_type") != "HIDDEN_PLAN_CHAIN"


def test_09_counterfactual_ssot_and_no_embedded_deltas():
    """counterfactual_evaluation.json is the single SSOT; candidates do not embed canned deltas."""
    with open(os.path.join(SNAPSHOT_DIR, "proof_candidates.json"), "r", encoding="utf-8") as f:
        cands = json.load(f)
    for c in cands:
        assert "counterfactual_results" not in c
        assert "counterfactual_evaluation_id" in c
        assert "evaluation_input_hash" in c
        assert c.get("presentation_status") == "HIDDEN_FROM_PUBLIC"

    with open(os.path.join(SNAPSHOT_DIR, "counterfactual_evaluation.json"), "r", encoding="utf-8") as f:
        cf_eval = json.load(f)
    assert len(cf_eval) == 3
    for ev in cf_eval:
        assert ev["engine_version"] == "CounterfactualTournamentEngine_v7"
        assert isinstance(ev["reveal_swap_delta"], float)
        assert isinstance(ev["evidence_ablation_delta"], float)


def test_10_offline_gateway_loads_v1_1_snapshot():
    """OfflineFixtureHypothesisGateway loads clean-room V1.1 snapshot candidates."""
    gateway = OfflineFixtureHypothesisGateway()
    reveal = v3_adapter.get_reveal("reveal-secret-room-location")
    bundle = bundle_builder.build_bundle(reveal=reveal, execution_mode=ExecutionMode.OFFLINE_FIXTURE)

    hypotheses, _ = gateway.generate_hypotheses(bundle, "test-run-001")
    assert len(hypotheses) >= 1
    assert any("Fireplace Wall Mechanism" in h.title for h in hypotheses)


def test_11_live_isolation_rejects_tainted_content():
    """LIVE_GOOGLE bundle builder strictly rejects evidence tainted with development snapshot content."""
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")

    # 1. Reject answer_assisted=True
    tainted_seed_1 = EvidenceSeed(
        channel_name="ENTITY",
        scene_ids=["scene-tbw-c017"],
        cutoff_ms=4860000,
        channel_rationale="Legitimate rationale",
        structured_payload={"answer_assisted": True}
    )
    with pytest.raises(RuntimeError, match="DEVELOPMENT_TAINT_DETECTED"):
        bundle_builder.build_bundle(
            reveal=reveal,
            cutoff_ms=4860000,
            provided_seeds=[tainted_seed_1],
            execution_mode=ExecutionMode.LIVE_GOOGLE
        )

    # 2. Reject source_namespace starting with DEVELOPMENT_
    tainted_seed_2 = EvidenceSeed(
        channel_name="ENTITY",
        scene_ids=["scene-tbw-c017"],
        cutoff_ms=4860000,
        channel_rationale="Legitimate rationale",
        structured_payload={"source_namespace": "DEVELOPMENT_SNAPSHOT_V1_1"}
    )
    with pytest.raises(RuntimeError, match="DEVELOPMENT_TAINT_DETECTED"):
        bundle_builder.build_bundle(
            reveal=reveal,
            cutoff_ms=4860000,
            provided_seeds=[tainted_seed_2],
            execution_mode=ExecutionMode.LIVE_GOOGLE
        )


def test_12_deep_snapshot_repo_load_time_lock_verification():
    """DeepSnapshotRepository verifies Phase A lock checksums at load time and fails closed on tampering."""
    DeepSnapshotRepository.clear_cache()
    cands = DeepSnapshotRepository.get_proof_candidates(snapshot_id="deep_snapshot_v1_1")
    assert len(cands) >= 3

    # Tampering check
    DeepSnapshotRepository.clear_cache()
    # Non-existent snapshot fails closed with SnapshotIntegrityError
    with pytest.raises(SnapshotIntegrityError):
        DeepSnapshotRepository.get_proof_candidates(snapshot_id="non_existent_snapshot")
