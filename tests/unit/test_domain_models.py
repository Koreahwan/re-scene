import pytest
from reframe.domain.models import Scene, ReframedMomentCard
from reframe.domain.enums import RelationType


def test_scene_timestamp_validation():
    # start_ms must be non-negative
    with pytest.raises(ValueError):
        Scene(
            movie_id="tbw-1930",
            scene_id="s1",
            start_ms=-1,
            end_ms=1000,
            location="Room",
            summary="Invalid start",
        )

    # end_ms must be greater than start_ms
    with pytest.raises(ValueError):
        Scene(
            movie_id="tbw-1930",
            scene_id="s2",
            start_ms=1000,
            end_ms=1000,
            location="Room",
            summary="Equal timestamps",
        )


def test_reframed_moment_card_forbids_coincidence_and_irrelevant():
    # Permitted relation
    card = ReframedMomentCard(
        scene_id="s1",
        start_ms=100,
        end_ms=200,
        location="Room",
        scene_summary="Valid",
        relation_type=RelationType.REINTERPRETATION,
        before_meaning="Before",
        after_meaning="After",
    )
    assert card.relation_type == RelationType.REINTERPRETATION

    # Forbidden on final user card
    with pytest.raises(ValueError):
        ReframedMomentCard(
            scene_id="s2",
            start_ms=100,
            end_ms=200,
            location="Room",
            scene_summary="Invalid",
            relation_type=RelationType.COINCIDENCE,
            before_meaning="Before",
            after_meaning="After",
        )

    with pytest.raises(ValueError):
        ReframedMomentCard(
            scene_id="s3",
            start_ms=100,
            end_ms=200,
            location="Room",
            scene_summary="Invalid",
            relation_type=RelationType.IRRELEVANT,
            before_meaning="Before",
            after_meaning="After",
        )
