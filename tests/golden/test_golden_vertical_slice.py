import json
from pathlib import Path
import pytest
from reframe.domain.models import Reveal
from reframe.domain.enums import RelationType, ReframeRunStatus, AbstainReason
from reframe.retrieval.guard import derive_spoiler_cutoff, validate_client_request_parameters
from reframe.mcp.gateway import MockNarrativeMemoryGateway
from reframe.verification.verifier import EvidenceVerifier


@pytest.fixture
def golden_fixture_data():
    fixture_path = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "the_bat_whispers_golden.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.asyncio
async def test_golden_vertical_slice_success(golden_fixture_data):
    """
    Validates Milestone 1 end-to-end vertical slice:
    1. Golden Reveal lookup & server cutoff calculation.
    2. Zero future scene leakage enforcement.
    3. Narrative memory candidate retrieval via Gateway.
    4. Evidence verification of candidates.
    5. Presentability filter (COINCIDENCE/IRRELEVANT pruned).
    6. Delivery of top evidence-backed reframed cards.
    """
    reveal_dict = golden_fixture_data["reveals"][0]
    reveal = Reveal(**reveal_dict)

    # 1. Server derives spoiler cutoff
    cutoff_ms = derive_spoiler_cutoff(reveal)
    assert cutoff_ms == 4860000

    # 2. Client parameters validation
    client_params = {"movie_id": reveal.movie_id, "reveal_id": reveal.reveal_id, "top_k": 5}
    validate_client_request_parameters(client_params)

    # 3. Setup Narrative Memory Gateway with fixture
    gateway = MockNarrativeMemoryGateway(
        scenes=golden_fixture_data["scenes"],
        events=golden_fixture_data["events"],
        facts=golden_fixture_data["facts"],
    )

    # 4. Search candidates
    candidates = await gateway.search_entity_candidates(
        movie_id=reveal.movie_id,
        reveal_id=reveal.reveal_id,
        cutoff_ms=cutoff_ms,
        entities=reveal.affected_entities,
        limit=20,
    )

    retrieved_scene_ids = [c.scene_id for c in candidates]

    # Invariant: Future scene (scene-tbw-010, 4,900,000 ms) MUST NOT be present
    assert "scene-tbw-010" not in retrieved_scene_ids
    assert all(c.start_ms < cutoff_ms for c in candidates)

    # 5. Fetch supporting facts and events
    events_map, facts_map = await gateway.get_supporting_evidence(
        movie_id=reveal.movie_id,
        cutoff_ms=cutoff_ms,
        scene_ids=retrieved_scene_ids,
    )

    # 6. Verification
    verifier = EvidenceVerifier()
    suite = golden_fixture_data.get("golden_eval_suite", {}).get("reveal-anderson-identity", {})
    expected_relations = suite.get("expected_relation_map", {})

    verified_pairs = []
    for cand in candidates:
        annotated_rel = RelationType(expected_relations.get(cand.scene_id, "REINTERPRETATION"))
        verified = verifier.verify_candidate_deterministic(
            reveal=reveal,
            candidate=cand,
            events=events_map.get(cand.scene_id, []),
            facts=facts_map.get(cand.scene_id, []),
            pre_annotated_relation=annotated_rel,
        )
        verified_pairs.append((cand, verified))

    # 7. Assemble final results
    result = verifier.assemble_results(
        run_id="run-test-001",
        reveal=reveal,
        spoiler_cutoff_ms=cutoff_ms,
        verified_items=verified_pairs,
        top_k=5,
    )

    # 8. Assertions
    assert result.status == ReframeRunStatus.COMPLETED
    assert len(result.cards) >= 3

    card_scene_ids = {c.scene_id for c in result.cards}
    assert {"scene-tbw-003", "scene-tbw-005", "scene-tbw-007"}.issubset(card_scene_ids)

    # Hard negatives (scene-tbw-002, scene-tbw-006) must be excluded
    assert "scene-tbw-002" not in card_scene_ids
    assert "scene-tbw-006" not in card_scene_ids

    # Each card must have concrete evidence citations
    for card in result.cards:
        assert card.evidence_facts or card.evidence_events
        assert card.relation_type.is_user_presentable


@pytest.mark.asyncio
async def test_golden_vertical_slice_abstain_on_zero_evidence(golden_fixture_data):
    """
    Validates that when candidate scenes have no evidence or are all unpresentable,
    the system safely abstains with EVIDENCE_INSUFFICIENT rather than hallucinating.
    """
    reveal = Reveal(**golden_fixture_data["reveals"][0])
    cutoff_ms = derive_spoiler_cutoff(reveal)

    verifier = EvidenceVerifier()

    # Pass empty or unsupported candidates
    result = verifier.assemble_results(
        run_id="run-test-abstain",
        reveal=reveal,
        spoiler_cutoff_ms=cutoff_ms,
        verified_items=[],
        top_k=5,
    )

    assert result.status == ReframeRunStatus.ABSTAINED
    assert result.abstain_reason == AbstainReason.EVIDENCE_INSUFFICIENT
    assert len(result.cards) == 0
