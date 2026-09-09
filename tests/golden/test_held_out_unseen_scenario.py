import pytest
from reframe.domain.models import Reveal, Scene, Event, Fact
from reframe.domain.enums import RelationType, ReframeRunStatus, AbstainReason
from reframe.application.orchestrator import ReframeOrchestrator
from reframe.mcp.gateway import MockNarrativeMemoryGateway
from reframe.verification.verifier import EvidenceVerifier
from reframe.evals.evaluator import GoldenDatasetEvaluator


@pytest.mark.asyncio
async def test_synthetic_held_out_generalization_scenario():
    """
    [SYNTHETIC GENERALIZATION UNIT TEST]
    Tests an entirely novel, synthetic movie scenario created outside the production dataset
    to prove that the orchestrator and verifier do NOT rely on hardcoded IDs, answer keys,
    or pre-baked prompts.
    """
    # 1. Novel Film Entities
    novel_movie_id = "phantom-shadow-1935"
    novel_reveal = Reveal(
        reveal_id="reveal-phantom-identity",
        movie_id=novel_movie_id,
        timestamp_ms=4500000,
        title="The Phantom is Butler James",
        reveal_type="IDENTITY",
        subject="Butler James",
        predicate="is_identity_of",
        previous_belief="Butler James was a loyal family servant.",
        revealed_fact="Butler James was the Phantom orchestrating the thefts.",
        affected_entities=["Butler James", "The Phantom", "Cellar Key"],
    )

    # 2. Candidate Scenes (Before Cutoff) and Leakage Traps (After Cutoff)
    scenes = [
        {
            "movie_id": novel_movie_id,
            "scene_id": "scene-held-001",
            "start_ms": 300000,
            "summary": "Butler James serves tea to guests.",
            "characters": ["Butler James", "Lady Eleanor"],
            "objects": ["Tea Cup"],
        },
        {
            "movie_id": novel_movie_id,
            "scene_id": "scene-held-002",
            "start_ms": 1200000,
            "summary": "Butler James secretly unlocks the cellar door while everyone is dining.",
            "characters": ["Butler James"],
            "objects": ["Cellar Key"],
        },
        {
            "movie_id": novel_movie_id,
            "scene_id": "scene-held-003-trap",
            "start_ms": 4600000,  # Future trap (> cutoff 4500000)
            "summary": "Butler James is arrested at the train station.",
            "characters": ["Butler James"],
            "objects": ["Handcuffs"],
        }
    ]

    events = [
        {
            "event_id": "ev-held-002",
            "movie_id": novel_movie_id,
            "scene_id": "scene-held-002",
            "timestamp_ms": 1210000,
            "actor": "Butler James",
            "action": "unlocks_cellar_door",
            "description": "James turns the brass key in the cellar door.",
            "entities": ["Butler James", "Cellar Key"]
        }
    ]

    facts = [
        {
            "fact_id": "fact-held-002",
            "movie_id": novel_movie_id,
            "scene_id": "scene-held-002",
            "timestamp_ms": 1215000,
            "subject": "Butler James",
            "predicate": "has_access_to",
            "object": "Cellar Key",
            "fact_type": "OBSERVATION",
        }
    ]

    gateway = MockNarrativeMemoryGateway(scenes=scenes, events=events, facts=facts)
    verifier = EvidenceVerifier()
    orchestrator = ReframeOrchestrator(
        gateway=gateway,
        verifier=verifier,
        reveals_registry={novel_reveal.reveal_id: novel_reveal},
    )

    # 3. Execute Analysis (No answer key provided!)
    result, _ = await orchestrator.execute_reframe_analysis(
        movie_id=novel_movie_id,
        reveal_id=novel_reveal.reveal_id,
        top_k=5,
    )

    # 4. Invariant & Grounding Assertions
    assert result.status == ReframeRunStatus.COMPLETED
    assert result.spoiler_cutoff_ms == 4500000

    # Ensure future trap scene was blocked
    scene_ids_returned = [c.scene_id for c in result.cards]
    assert "scene-held-003-trap" not in scene_ids_returned
    assert "scene-held-002" in scene_ids_returned

    card = next(c for c in result.cards if c.scene_id == "scene-held-002")
    assert card.start_ms < 4500000
    assert card.relation_type in [RelationType.REINTERPRETATION, RelationType.CHARACTER_MOTIVATION, RelationType.DIRECT_FORESHADOWING]
    assert "James" in card.after_meaning or "Phantom" in card.after_meaning or "butler" in card.after_meaning.lower()

