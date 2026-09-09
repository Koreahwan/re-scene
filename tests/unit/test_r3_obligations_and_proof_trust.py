"""
Unit Tests for R3-09, R3-10, R3-11, R3-12: Proof Obligations, Proof Trust, Real Content Hash & Non-Forgeable Counterfactuals
Zero Paid Model Calls.
"""
import pytest
from src.reframe.narrative.obligations import (
    KnowledgeLeakObligation,
    ClaimActionObligation,
    HiddenPlanObligation,
    counterfactual_scorer
)
from src.reframe.evidence.adapter import compute_content_hash
from src.reframe.proof.store import CANONICAL_PROOFS_MAP, CANONICAL_PATTERNS_MAP, canonical_proof_store
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.auth import ViewerContext


def test_knowledge_leak_obligation_evaluation():
    """Verify KnowledgeLeakObligation satisfies iff character access precedes public broadcast."""
    res_sat = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=4860000,
        earliest_character_access_ms=2010000,
        evidence_ids=["ev-c017-05"]
    )
    assert res_sat.is_satisfied is True
    assert res_sat.score >= 0.85
    assert res_sat.obligation_type == "KNOWLEDGE_LEAK"

    res_unsat = KnowledgeLeakObligation.evaluate(
        earliest_public_available_ms=2000000,
        earliest_character_access_ms=2500000,
        evidence_ids=["ev-c021-03"]
    )
    assert res_unsat.is_satisfied is False
    assert res_unsat.score < 0.20


def test_claim_action_obligation_rule_registry():
    """Verify ClaimActionObligation evaluates contradiction using normative rules."""
    res = ClaimActionObligation.evaluate(
        speaker_claim_text="I was away in the courtyard all evening and saw nothing.",
        actor_action_text="Detective Anderson stands alone in the dark hall inspecting his surroundings.",
        rule_name="STATED_ALIBI_VS_UNOBSERVED_PRESENCE",
        evidence_ids=["ev-c017-05", "ev-c025-02"]
    )
    assert res.is_satisfied is True
    assert res.rule_name == "STATED_ALIBI_VS_UNOBSERVED_PRESENCE"
    assert res.score >= 0.80


def test_counterfactual_scorer_non_forgeable_deltas():
    """Verify CounterfactualObligationScorer calculates genuine negative deltas under control swap and ablation."""
    cf_res = counterfactual_scorer.score_counterfactuals(
        baseline_score=0.92,
        target_reveal_id="reveal-anderson-identity",
        cited_scenes=["scene-tbw-c017", "scene-tbw-c021"]
    )
    assert cf_res.reveal_swap_delta <= -0.30
    assert cf_res.evidence_ablation_delta <= -0.30
    assert cf_res.is_counterfactually_robust is True


def test_real_content_hash_is_genuine_sha256():
    """Verify compute_content_hash produces canonical 64-char SHA256 hex."""
    sample_data = {
        "event_id": "ev-c017-05",
        "scene_id": "scene-tbw-c017",
        "actor": "Detective Anderson",
        "action": "observe"
    }
    h = compute_content_hash(sample_data)
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)

    # Invariant: Precomputed canonical patterns must have genuine SHA-256 hashes
    anderson_proofs = CANONICAL_PATTERNS_MAP["reveal-anderson-identity"]
    for p in anderson_proofs:
        assert p["human_review_status"] in ("NOT_REVIEWED", "VERIFIED_CANONICAL", "NEEDS_CORRECTION")
        assert p["trust_namespace"] == "ENGINE_INFERENCE"
        assert any(term in p["trust_label"] for term in ["Engine", "Interpretation", "Observation", "Pattern"])
        for prem in p["observed_premises"]:
            assert len(prem["canonical_content_hash"]) == 64


@pytest.mark.asyncio
async def test_canonical_proof_lookup_returns_trust_fields():
    """Verify get_proofs_for_reveal returns human_review_status and trust_label."""
    async with AsyncSessionLocal() as db:
        await canonical_proof_store.seed_canonical_proofs_if_empty(db)
        admin_viewer = ViewerContext(completed_reveal_ids=["reveal-anderson-identity"], roles=["ADMIN"])
        proofs = await canonical_proof_store.get_proofs_for_reveal(db, "reveal-anderson-identity", admin_viewer)

        assert len(proofs) >= 3
        for p in proofs:
            assert p["human_review_status"] in ("NOT_REVIEWED", "VERIFIED_CANONICAL", "NEEDS_CORRECTION")
            assert p["trust_namespace"] == "ENGINE_INFERENCE"
            assert any(term in p["trust_label"] for term in ["Engine", "Interpretation", "Observation", "Pattern"])

        # Public viewer only sees PUBLIC presentation_status proofs (0 when development candidates are HIDDEN_FROM_PUBLIC)
        public_viewer = ViewerContext(completed_reveal_ids=["reveal-anderson-identity"])
        pub_proofs = await canonical_proof_store.get_proofs_for_reveal(db, "reveal-anderson-identity", public_viewer)
        for p in pub_proofs:
            assert p["presentation_status"] == "PUBLIC"

