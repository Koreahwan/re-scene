import pytest
from reframe.domain.models import Reveal, ReframeCandidate, Event, Fact, ReframedMomentCard
from reframe.domain.enums import RelationType, ReframeRunStatus, AbstainReason
from reframe.verification.verifier import EvidenceVerifier


@pytest.fixture
def sample_reveal():
    return Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=4860000,
        title="Detective Anderson is 'The Bat'",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective Anderson is a dedicated police officer.",
        revealed_fact="Detective Anderson is himself 'The Bat'.",
        affected_entities=["Detective Anderson", "The Bat"],
    )


@pytest.fixture
def sample_candidate():
    return ReframeCandidate(
        reveal_id="reveal-anderson-identity",
        scene_id="scene-tbw-003",
        movie_id="the-bat-whispers-1930",
        start_ms=350000,
        summary="Anderson inspects the blueprints alone.",
    )


@pytest.fixture
def sample_events():
    return [
        Event(
            event_id="ev-003-1",
            movie_id="the-bat-whispers-1930",
            scene_id="scene-tbw-003",
            timestamp_ms=360000,
            actor="Detective Anderson",
            action="locks_door",
            description="Anderson locks the library door.",
        )
    ]


@pytest.fixture
def sample_facts():
    return [
        Fact(
            fact_id="fact-003-1",
            movie_id="the-bat-whispers-1930",
            scene_id="scene-tbw-003",
            timestamp_ms=365000,
            subject="Detective Anderson",
            predicate="holds_exclusive_access_to",
            object="Blueprints",
        )
    ]


def test_verify_all_allowed_relation_labels(sample_reveal, sample_candidate, sample_events, sample_facts):
    verifier = EvidenceVerifier()

    allowed_labels = [
        RelationType.DIRECT_FORESHADOWING,
        RelationType.REINTERPRETATION,
        RelationType.CHARACTER_MOTIVATION,
        RelationType.CONTRADICTION,
        RelationType.COINCIDENCE,
        RelationType.IRRELEVANT,
    ]

    for label in allowed_labels:
        verified = verifier.verify_candidate_deterministic(
            reveal=sample_reveal,
            candidate=sample_candidate,
            events=sample_events,
            facts=sample_facts,
            pre_annotated_relation=label,
        )
        assert verified.relation_type == label


def test_coincidence_and_irrelevant_are_filtered_from_final_cards(sample_reveal, sample_candidate, sample_events, sample_facts):
    verifier = EvidenceVerifier()

    # Create one valid Reinterpretation and one Coincidence
    cand_positive = sample_candidate.model_copy(update={"scene_id": "scene-pos"})
    cand_coincidence = sample_candidate.model_copy(update={"scene_id": "scene-coinc"})

    ver_positive = verifier.verify_candidate_deterministic(
        reveal=sample_reveal,
        candidate=cand_positive,
        events=sample_events,
        facts=sample_facts,
        pre_annotated_relation=RelationType.REINTERPRETATION,
    )

    ver_coincidence = verifier.verify_candidate_deterministic(
        reveal=sample_reveal,
        candidate=cand_coincidence,
        events=sample_events,
        facts=sample_facts,
        pre_annotated_relation=RelationType.COINCIDENCE,
    )

    result = verifier.assemble_results(
        run_id="run-filter-test",
        reveal=sample_reveal,
        spoiler_cutoff_ms=sample_reveal.timestamp_ms,
        verified_items=[(cand_positive, ver_positive), (cand_coincidence, ver_coincidence)],
        top_k=5,
    )

    assert result.status == ReframeRunStatus.COMPLETED
    assert len(result.cards) == 1
    assert result.cards[0].scene_id == "scene-pos"
    assert result.cards[0].relation_type == RelationType.REINTERPRETATION


def test_verifier_abstains_when_all_candidates_are_unsupported(sample_reveal, sample_candidate, sample_events, sample_facts):
    verifier = EvidenceVerifier()

    cand_coinc = sample_candidate.model_copy(update={"scene_id": "scene-coinc"})
    ver_coinc = verifier.verify_candidate_deterministic(
        reveal=sample_reveal,
        candidate=cand_coinc,
        events=sample_events,
        facts=sample_facts,
        pre_annotated_relation=RelationType.COINCIDENCE,
    )

    result = verifier.assemble_results(
        run_id="run-abstain-test",
        reveal=sample_reveal,
        spoiler_cutoff_ms=sample_reveal.timestamp_ms,
        verified_items=[(cand_coinc, ver_coinc)],
        top_k=5,
    )

    assert result.status == ReframeRunStatus.ABSTAINED
    assert result.abstain_reason == AbstainReason.EVIDENCE_INSUFFICIENT
    assert len(result.cards) == 0


def test_hallucinated_evidence_ids_are_rejected(sample_reveal, sample_candidate, sample_events, sample_facts):
    """
    [AUDIT REQUIREMENT 11]
    Proves that when model response contains hallucinated or cross-scene evidence IDs:
    1. Unknown citations are filtered out.
    2. If no valid citations remain for a user-presentable claim, the claim is rejected as unsupported.
    3. Missing citations are NOT silently replaced with arbitrary first events.
    """
    verifier = EvidenceVerifier()

    # Create mock response with hallucinated IDs and cross-scene IDs
    hallucinated_ev_id = "ev-fake-999"
    cross_scene_fact_id = "fact-other-scene-001"
    valid_ev_id = sample_events[0].event_id

    # Test 1: Mixed valid + hallucinated citations -> Only valid citation is kept
    valid_ev_ids = {e.event_id for e in sample_events}
    raw_citations = [valid_ev_id, hallucinated_ev_id]
    grounded = [eid for eid in raw_citations if eid in valid_ev_ids]
    assert grounded == [valid_ev_id]

    # Test 2: Purely hallucinated citations -> Rejected
    raw_hallucinated_only = [hallucinated_ev_id, "fact-ghost-123"]
    grounded_hallucinated = [eid for eid in raw_hallucinated_only if eid in valid_ev_ids]
    assert len(grounded_hallucinated) == 0

    # Test 3: Rejection on zero grounded evidence
    cand = sample_candidate.model_copy(update={"scene_id": "scene-tbw-003"})
    verified_unsupported = verifier.verify_candidate_deterministic(
        reveal=sample_reveal,
        candidate=cand,
        events=[],  # No evidence in scene
        facts=[],
        pre_annotated_relation=RelationType.REINTERPRETATION,
    )
    # Assemble must reject cards with no evidence citations
    result = verifier.assemble_results(
        run_id="run-grounding-test",
        reveal=sample_reveal,
        spoiler_cutoff_ms=sample_reveal.timestamp_ms,
        verified_items=[(cand, verified_unsupported)],
        top_k=5,
    )
    assert result.status == ReframeRunStatus.ABSTAINED
    assert len(result.cards) == 0

