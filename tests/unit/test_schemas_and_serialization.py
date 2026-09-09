import json
import pytest
from reframe.domain.models import (
    Film,
    Scene,
    Event,
    Fact,
    KnowledgeState,
    Reveal,
    ReframeCandidate,
    VerifiedReframe,
    ReframedMomentCard,
    ReframeResult,
)
from reframe.domain.enums import (
    RelationType,
    FactType,
    KnowledgeStatus,
    ReframeRunStatus,
    AbstainReason,
)


def test_film_serialization_roundtrip():
    film = Film(
        movie_id="the-bat-whispers-1930",
        title="The Bat Whispers",
        year=1930,
        runtime_ms=5040000,
        language="en",
        rights_status="APPROVED",
        dataset_version="tbw-0001",
    )
    json_data = film.model_dump_json()
    loaded = Film.model_validate_json(json_data)
    assert loaded == film


def test_scene_serialization_roundtrip():
    scene = Scene(
        movie_id="the-bat-whispers-1930",
        scene_id="scene-001",
        start_ms=10000,
        end_ms=60000,
        location="Parlor",
        characters=["Detective Anderson"],
        objects=["Blueprints"],
        summary="Anderson inspects the room.",
        dataset_version="tbw-0001",
    )
    json_data = scene.model_dump_json()
    loaded = Scene.model_validate_json(json_data)
    assert loaded == scene


def test_event_and_fact_serialization_roundtrip():
    event = Event(
        event_id="ev-01",
        movie_id="the-bat-whispers-1930",
        scene_id="scene-001",
        timestamp_ms=15000,
        actor="Anderson",
        action="unlocks_door",
        description="Anderson turns the key.",
    )
    fact = Fact(
        fact_id="fact-01",
        movie_id="the-bat-whispers-1930",
        scene_id="scene-001",
        timestamp_ms=15000,
        subject="Anderson",
        predicate="holds_key_to",
        object="Secret Room",
        fact_type=FactType.EXPLICIT,
    )
    assert Event.model_validate_json(event.model_dump_json()) == event
    assert Fact.model_validate_json(fact.model_dump_json()) == fact


def test_reframe_result_serialization_roundtrip():
    card = ReframedMomentCard(
        scene_id="scene-001",
        start_ms=10000,
        end_ms=60000,
        location="Library",
        scene_summary="Anderson alone in library",
        relation_type=RelationType.REINTERPRETATION,
        before_meaning="Investigating clues",
        after_meaning="Stealing blueprints",
        evidence_facts=["fact-01"],
        evidence_events=["ev-01"],
    )
    result = ReframeResult(
        run_id="run_12345",
        movie_id="the-bat-whispers-1930",
        reveal_id="reveal-01",
        spoiler_cutoff_ms=4860000,
        status=ReframeRunStatus.COMPLETED,
        cards=[card],
    )
    json_data = result.model_dump_json()
    loaded = ReframeResult.model_validate_json(json_data)
    assert loaded == result
    assert len(loaded.cards) == 1
    assert loaded.cards[0].relation_type == RelationType.REINTERPRETATION
