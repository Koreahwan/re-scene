import pytest
from reframe.domain.models import Reveal, ReframeCandidate, Event, Fact
from reframe.domain.enums import RelationType
from reframe.verification.verifier import EvidenceVerifier


@pytest.mark.asyncio
async def test_verifier_changes_verdict_when_evidence_changes():
    """
    Proves that the Verifier is semantically grounded and sensitive to actual evidence content:
    - Suspicious deception actions -> REINTERPRETATION or DIRECT_FORESHADOWING
    - Neutral/unrelated actions -> COINCIDENCE or IRRELEVANT (filtered out)
    """
    verifier = EvidenceVerifier()

    reveal = Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=4860000,
        title="Detective Anderson is Unmasked as 'The Bat'",
        reveal_type="IDENTITY",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective Anderson is a dedicated police officer.",
        revealed_fact="Detective Anderson is himself 'The Bat'.",
        affected_entities=["Detective Anderson", "The Bat", "Secret Safe Room"],
    )

    # 1. Candidate with incriminating action evidence (locking door, stealing blueprint key)
    cand_incriminating = ReframeCandidate(
        reveal_id=reveal.reveal_id,
        scene_id="scene-test-incriminating",
        movie_id=reveal.movie_id,
        start_ms=1200000,
        summary="Anderson locks the door and pockets the brass key.",
        characters=["Detective Anderson"],
        objects=["Iron Key"],
    )
    incriminating_events = [
        Event(
            event_id="ev-inc-1",
            movie_id=reveal.movie_id,
            scene_id="scene-test-incriminating",
            timestamp_ms=1210000,
            actor="Detective Anderson",
            action="pockets_secret_key",
            description="Anderson stealthily steals the key to the secret room.",
            entities=["Detective Anderson", "The Bat", "Iron Key"],
        )
    ]
    incriminating_facts = [
        Fact(
            fact_id="fact-inc-1",
            movie_id=reveal.movie_id,
            scene_id="scene-test-incriminating",
            timestamp_ms=1220000,
            subject="Detective Anderson",
            predicate="possesses",
            object="Secret Room Key",
            fact_type="OBSERVATION",
        )
    ]

    verdict_inc = await verifier.verify_candidate(
        reveal=reveal,
        candidate=cand_incriminating,
        events=incriminating_events,
        facts=incriminating_facts,
    )
    assert verdict_inc.relation_type in [
        RelationType.REINTERPRETATION,
        RelationType.DIRECT_FORESHADOWING,
        RelationType.CHARACTER_MOTIVATION,
    ]
    assert verdict_inc.relation_type.is_user_presentable is True
    assert verdict_inc.is_supported is True

    # 2. Candidate with neutral action (drinking coffee)
    cand_neutral = ReframeCandidate(
        reveal_id=reveal.reveal_id,
        scene_id="scene-test-neutral",
        movie_id=reveal.movie_id,
        start_ms=950000,
        summary="Anderson asks butler for black coffee.",
        characters=["Detective Anderson", "Billy the Butler"],
        objects=["Coffee Pot"],
    )
    neutral_events = [
        Event(
            event_id="ev-neu-1",
            movie_id=reveal.movie_id,
            scene_id="scene-test-neutral",
            timestamp_ms=960000,
            actor="Detective Anderson",
            action="drinks_coffee",
            description="Anderson drinks coffee in the kitchen.",
            entities=["Detective Anderson"],
        )
    ]

    verdict_neu = await verifier.verify_candidate(
        reveal=reveal,
        candidate=cand_neutral,
        events=neutral_events,
        facts=[],
    )
    assert verdict_neu.relation_type in [RelationType.COINCIDENCE, RelationType.IRRELEVANT]
    assert verdict_neu.relation_type.is_user_presentable is False
