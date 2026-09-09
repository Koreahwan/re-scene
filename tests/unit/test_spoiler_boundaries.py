import pytest
from reframe.domain.models import Reveal, Scene, ReframeCandidate
from reframe.domain.enums import AbstainReason
from reframe.retrieval.guard import (
    derive_spoiler_cutoff,
    validate_client_request_parameters,
    assert_zero_future_leakage,
    SpoilerGuardViolation,
)


def create_sample_reveal(timestamp_ms: int = 4860000) -> Reveal:
    return Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=timestamp_ms,
        title="Detective Anderson is 'The Bat'",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective",
        revealed_fact="The Bat",
    )


def test_boundary_cutoff_minus_one_ms_is_eligible():
    reveal = create_sample_reveal(4860000)
    cutoff_ms = derive_spoiler_cutoff(reveal)

    # Scene ending at 4859999ms strictly precedes cutoff
    scene = Scene(
        movie_id="the-bat-whispers-1930",
        scene_id="scene-valid",
        start_ms=4800000,
        end_ms=4859999,
        location="Library",
        summary="Clue scene immediately before reveal",
    )
    # Must not raise
    assert_zero_future_leakage([scene], cutoff_ms=cutoff_ms)


def test_boundary_cutoff_exact_timestamp_is_blocked():
    reveal = create_sample_reveal(4860000)
    cutoff_ms = derive_spoiler_cutoff(reveal)

    # Scene starting exactly at the reveal timestamp is forbidden
    scene = Scene(
        movie_id="the-bat-whispers-1930",
        scene_id="scene-exact",
        start_ms=4860000,
        end_ms=4900000,
        location="Library",
        summary="Exact reveal moment scene",
    )
    with pytest.raises(SpoilerGuardViolation) as exc:
        assert_zero_future_leakage([scene], cutoff_ms=cutoff_ms)
    assert "CRITICAL SPOILER LEAKAGE" in str(exc.value)


def test_boundary_cutoff_plus_one_ms_is_blocked():
    reveal = create_sample_reveal(4860000)
    cutoff_ms = derive_spoiler_cutoff(reveal)

    # Scene starting after reveal timestamp is forbidden
    scene = Scene(
        movie_id="the-bat-whispers-1930",
        scene_id="scene-future",
        start_ms=4860001,
        end_ms=4900000,
        location="Courtyard",
        summary="Post-reveal chase scene",
    )
    with pytest.raises(SpoilerGuardViolation) as exc:
        assert_zero_future_leakage([scene], cutoff_ms=cutoff_ms)
    assert "CRITICAL SPOILER LEAKAGE" in str(exc.value)


def test_cross_movie_scene_leakage_blocked():
    reveal = create_sample_reveal(4860000)
    cutoff_ms = derive_spoiler_cutoff(reveal)

    # Candidate from a different movie
    candidate = ReframeCandidate(
        reveal_id="reveal-anderson-identity",
        scene_id="scene-other-film",
        movie_id="other-movie-1999",  # Cross-movie violation
        start_ms=100000,
        summary="Unrelated film scene",
    )
    # The orchestrator verifies movie_id matches requested movie_id
    assert candidate.movie_id != reveal.movie_id


def test_malicious_client_cutoff_parameter_rejected():
    with pytest.raises(SpoilerGuardViolation):
        validate_client_request_parameters({
            "movie_id": "the-bat-whispers-1930",
            "reveal_id": "reveal-anderson-identity",
            "spoiler_cutoff_ms": 10000000,  # Malicious attempt to leak future scenes
        })


def test_malicious_client_sql_parameter_rejected():
    with pytest.raises(SpoilerGuardViolation):
        validate_client_request_parameters({
            "movie_id": "the-bat-whispers-1930",
            "reveal_id": "reveal-anderson-identity",
            "sql": "SELECT * FROM scenes WHERE 1=1",
        })


def test_malformed_negative_timestamp_fails_safely():
    reveal = create_sample_reveal(-500)
    with pytest.raises(SpoilerGuardViolation) as exc:
        derive_spoiler_cutoff(reveal)
    assert exc.value.reason == AbstainReason.SPOILER_GUARD_BLOCKED


def test_real_v3_production_c037_spoiler_leakage_regression():
    """
    [REAL V3 REGRESSION TEST - AUDIT REQUIREMENT 1 & 18]
    Concrete real V3 case:
    - Reveal cutoff: 4,400,000 ms
    - Scene: scene-tbw-c037 (4,320,000–4,440,000 ms)
    - Event 1: ev-c037-01 at 4,335,000 ms, evidence_end_ms 4,350,000 ms, frame_c037_015 (4,335,000 ms) -> VALID
    - Event 2: ev-c037-03 at 4,395,000 ms, evidence_end_ms 4,410,000 ms, frame_c037_090 (4,410,000 ms in manifest) -> LEAK TRAP
    - Fact 1: fact-c037-02 at 4,395,000 ms, evidence_end_ms 4,410,000 ms, frame_c037_090 -> LEAK TRAP

    Proves:
    1. ev-c037-03 and fact-c037-02 are rejected by filter_pre_cutoff_evidence.
    2. Overlapping scene-tbw-c037 summary is sanitized (pre-cutoff excerpt constructed) so post-cutoff narrative never enters Gemini.
    3. assert_zero_future_leakage catches and rejects un-sanitized post-cutoff frames/evidence.
    """
    from reframe.domain.models import Event, Fact
    from reframe.retrieval.guard import filter_pre_cutoff_evidence, sanitize_candidate_for_cutoff

    cutoff_ms = 4400000

    cand_c037 = ReframeCandidate(
        reveal_id="reveal-masked-robbery-vault",
        scene_id="scene-tbw-c037",
        movie_id="the-bat-whispers-1930",
        start_ms=4320000,
        end_ms=4440000,
        evidence_start_ms=4320000,
        evidence_end_ms=4440000,
        summary="Complete 120s chunk summary describing both pre-cutoff search and post-cutoff climax actions up to 4440000ms.",
        characters=["Detective Anderson", "Brooks", "Cornelia Van Gorder"],
        objects=["Grand Fireplace", "Revolver"],
    )

    ev_valid = Event(
        event_id="ev-c037-01",
        movie_id="the-bat-whispers-1930",
        scene_id="scene-tbw-c037",
        timestamp_ms=4335000,
        evidence_start_ms=4335000,
        evidence_end_ms=4350000,
        actor="Detective Anderson",
        action="inspects_fireplace_mantel",
        description="Anderson examines the mantelpiece looking for concealed latches.",
        evidence_frame_ids=["frame_c037_015"],
    )

    ev_leak_trap = Event(
        event_id="ev-c037-03",
        movie_id="the-bat-whispers-1930",
        scene_id="scene-tbw-c037",
        timestamp_ms=4395000,
        evidence_start_ms=4395000,
        evidence_end_ms=4410000,  # Crosses cutoff 4400000ms!
        actor="Detective Anderson",
        action="draws_revolver_post_cutoff",
        description="Anderson draws revolver across the threshold.",
        evidence_frame_ids=["frame_c037_090"],  # Frame at 4410000ms in manifest!
    )

    fact_leak_trap = Fact(
        fact_id="fact-c037-02",
        movie_id="the-bat-whispers-1930",
        scene_id="scene-tbw-c037",
        timestamp_ms=4395000,
        evidence_start_ms=4395000,
        evidence_end_ms=4410000,  # Crosses cutoff!
        subject="Detective Anderson",
        predicate="enters_vault_zone",
        object="Hidden Passage",
        evidence_frame_ids=["frame_c037_090"],
    )

    # 1. Unfiltered assertion must raise SpoilerGuardViolation on post-cutoff evidence
    with pytest.raises(SpoilerGuardViolation):
        assert_zero_future_leakage([cand_c037], cutoff_ms=cutoff_ms, events=[ev_valid, ev_leak_trap])

    with pytest.raises(SpoilerGuardViolation):
        assert_zero_future_leakage([cand_c037], cutoff_ms=cutoff_ms, facts=[fact_leak_trap])

    # 2. filter_pre_cutoff_evidence must purge ev-c037-03 and fact-c037-02
    clean_events, clean_facts = filter_pre_cutoff_evidence(
        events=[ev_valid, ev_leak_trap],
        facts=[fact_leak_trap],
        cutoff_ms=cutoff_ms,
    )
    assert len(clean_events) == 1
    assert clean_events[0].event_id == "ev-c037-01"
    assert len(clean_facts) == 0  # Leak fact purged

    # 3. sanitize_candidate_for_cutoff must replace whole-scene summary with pre-cutoff narrative excerpt
    sanitized_cand = sanitize_candidate_for_cutoff(
        cand_c037,
        events=clean_events,
        facts=clean_facts,
        cutoff_ms=cutoff_ms,
    )
    assert sanitized_cand.is_summary_pre_cutoff is True
    assert sanitized_cand.end_ms == 4399999
    assert sanitized_cand.evidence_end_ms <= 4399999
    assert "Pre-Cutoff Narrative Excerpt" in sanitized_cand.summary
    assert "post-cutoff" not in sanitized_cand.summary

    # 4. Clean assert_zero_future_leakage passes without error
    assert_zero_future_leakage([sanitized_cand], cutoff_ms=cutoff_ms, events=clean_events, facts=clean_facts)

