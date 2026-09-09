import pytest
from reframe.domain.models import Reveal, Scene, ReframeCandidate
from reframe.domain.enums import AbstainReason
from reframe.retrieval.guard import (
    derive_spoiler_cutoff,
    validate_client_request_parameters,
    assert_zero_future_leakage,
    SpoilerGuardViolation,
)


def test_derive_spoiler_cutoff_success():
    reveal = Reveal(
        reveal_id="rev-01",
        movie_id="tbw-1930",
        timestamp_ms=4860000,
        title="Identity Reveal",
        subject="Anderson",
        predicate="is",
        previous_belief="Detective",
        revealed_fact="The Bat",
    )
    cutoff = derive_spoiler_cutoff(reveal)
    assert cutoff == 4860000


def test_derive_spoiler_cutoff_invalid_timestamp():
    reveal = Reveal(
        reveal_id="rev-01",
        movie_id="tbw-1930",
        timestamp_ms=0,
        title="Identity Reveal",
        subject="Anderson",
        predicate="is",
        previous_belief="Detective",
        revealed_fact="The Bat",
    )
    with pytest.raises(SpoilerGuardViolation) as exc:
        derive_spoiler_cutoff(reveal)
    assert exc.value.reason == AbstainReason.SPOILER_GUARD_BLOCKED


def test_validate_client_request_parameters_rejects_client_cutoff():
    with pytest.raises(SpoilerGuardViolation):
        validate_client_request_parameters({"movie_id": "tbw-1930", "spoiler_cutoff_ms": 1000})

    with pytest.raises(SpoilerGuardViolation):
        validate_client_request_parameters({"movie_id": "tbw-1930", "sql": "SELECT * FROM scenes"})


def test_validate_client_request_parameters_accepts_clean_request():
    # Should not raise
    validate_client_request_parameters({"movie_id": "tbw-1930", "reveal_id": "rev-01", "top_k": 5})


def test_assert_zero_future_leakage_passes_valid_prior_scenes():
    scenes = [
        Scene(
            movie_id="tbw-1930",
            scene_id="s1",
            start_ms=100000,
            end_ms=150000,
            location="Room",
            summary="Scene 1",
        ),
        Scene(
            movie_id="tbw-1930",
            scene_id="s2",
            start_ms=4859999,
            end_ms=4860000,
            location="Room",
            summary="Scene 2",
        ),
    ]
    # Cutoff is 4860000: start_ms strictly < cutoff passes
    assert_zero_future_leakage(scenes, cutoff_ms=4860000)


def test_assert_zero_future_leakage_blocks_future_scenes():
    future_scenes = [
        Scene(
            movie_id="tbw-1930",
            scene_id="s_past",
            start_ms=100000,
            end_ms=150000,
            location="Room",
            summary="Past Scene",
        ),
        Scene(
            movie_id="tbw-1930",
            scene_id="s_future",
            start_ms=4860000,  # Exact cutoff is forbidden
            end_ms=4900000,
            location="Room",
            summary="Climax Scene",
        ),
    ]
    with pytest.raises(SpoilerGuardViolation) as exc:
        assert_zero_future_leakage(future_scenes, cutoff_ms=4860000)
    assert "CRITICAL SPOILER LEAKAGE" in str(exc.value)
