"""
Unit Tests for V6 Multi-Channel Retrieval Engine & Evidence Bundles
Zero Paid Model Calls.
"""
import pytest
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.narrative.channels import (
    EntityRetrievalChannel,
    KnowledgeConflictChannel,
    ClaimActionChannel,
    AccessOpportunityChannel,
    PlanCausalChannel,
    multi_channel_engine
)
from src.reframe.narrative.bundle import bundle_builder


def test_entity_retrieval_channel():
    """Entity channel must return pre-cutoff scenes containing Detective Anderson / The Bat."""
    candidates = EntityRetrievalChannel.retrieve(
        target_entities=["Detective Anderson", "The Bat"],
        cutoff_ms=4860000
    )
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.channel_name == "ENTITY"
        assert cand.salience_score > 0.0
        for sid in cand.scene_ids:
            scene = v3_adapter.get_scene(sid)
            assert scene.start_ms < 4860000


def test_knowledge_conflict_channel():
    """Knowledge Conflict channel must identify unbriefed searches or fireplace inspections."""
    candidates = KnowledgeConflictChannel.retrieve(
        target_entities=["Detective Anderson"],
        cutoff_ms=4860000
    )
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.channel_name == "KNOWLEDGE_CONFLICT"
        assert len(cand.event_ids) > 0


def test_claim_action_channel():
    """Claim-Action channel must identify statement/action pairs across distinct scenes."""
    candidates = ClaimActionChannel.retrieve(
        target_entities=["Detective Anderson"],
        cutoff_ms=4860000
    )
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.channel_name == "CLAIM_ACTION"
        assert len(cand.scene_ids) >= 1


def test_access_opportunity_channel():
    """Access/Opportunity channel must identify spatial mechanism alignments."""
    candidates = AccessOpportunityChannel.retrieve(
        target_locations=["Fireplace", "Manor", "Study"],
        cutoff_ms=3660000
    )
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.channel_name == "ACCESS_OPPORTUNITY"


def test_plan_causal_channel():
    """Plan/Causal channel must identify multi-scene preparation paths."""
    candidates = PlanCausalChannel.retrieve(
        target_entities=["Detective Anderson"],
        cutoff_ms=4860000
    )
    assert len(candidates) > 0
    for cand in candidates:
        assert cand.channel_name == "PLAN_CAUSAL"


def test_evidence_bundle_builder_no_future_leakage():
    """EvidenceBundleBuilder must assemble bundle with zero future scene leakage."""
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    assert reveal is not None

    bundle = bundle_builder.build_bundle(reveal=reveal)
    assert bundle.bundle_id.startswith("bundle-reveal-anderson-identity")
    assert len(bundle.related_scenes) >= 2

    for s in bundle.related_scenes:
        assert s.start_ms < reveal.timestamp_ms

    for ev in bundle.observed_events:
        assert ev.timestamp_ms < reveal.timestamp_ms

    assert len(bundle.alternative_explanations) >= 2
    assert len(bundle.counterfactual_controls) >= 2
