"""
Reframe V7 Simulation Metrics, Intervals & Bottlenecks Unit Tests
Validates funnel conversion metrics, Monte Carlo SIMULATION_INTERVAL labels, exact single-session accounting,
cohort metrics reconciliation, and composite friction scoring.
Zero External Generative Model Calls.
"""
import pytest
from src.reframe.simulation.aggregators import OnlineMetricsAggregator
from src.reframe.simulation.metrics import compute_funnel_metrics, compute_cohort_summaries
from src.reframe.simulation.intervals import calculate_simulation_intervals
from src.reframe.simulation.bottlenecks import rank_bottlenecks
from src.reframe.simulation.schemas import (
    ScenarioVariant,
    RepresentativeSessionTrace,
    DerivedPersonaProfile,
    GoldenPathState,
    DropoffReason,
)


@pytest.fixture
def mock_profile():
    return DerivedPersonaProfile(
        persona_id="us_pers_test0001",
        source_persona_id_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        locale="en_US",
        display_alias="Synthetic Fan US-000001",
        age_band="25-34",
        state="NY",
        census_region="Northeast",
        location_context="Metro",
        education_group="Bachelor's",
        occupation_group="Tech & Engineering",
        sampling_weight=1.0,
        safe_interest_tags=["mystery_puzzles"],
        available_persona_lenses=["GENERAL"],
        source_dataset="nvidia/Nemotron-Personas-USA",
        source_revision="5b4cd35",
    )


def test_online_metrics_aggregator_exact_three_sessions(mock_profile):
    """
    Verifies that 3 hand-built sessions with known durations and outcomes
    are recorded exactly once without duplicate addition to reservoirs or TTFV sums.
    """
    agg = OnlineMetricsAggregator(track_clusters=True)

    # Session 1: Reaches REVEAL -> DEEP_REFRAME -> completes DEEP_REFRAME -> REWATCH completed
    trace1 = RepresentativeSessionTrace(
        session_id="sess_1",
        persona_id="us_pers_test0001",
        scenario_id="CURRENT_BASELINE",
        replication_seed=42,
        states_visited=["LANDING", "FILM_HUB", "SPOILER_GATE", "REVEAL", "DEEP_REFRAME", "REWATCH"],
        transition_durations_sec={"LANDING": 5.0, "FILM_HUB": 10.0, "SPOILER_GATE": 5.0, "REVEAL": 10.0, "DEEP_REFRAME": 20.0, "REWATCH": 30.0},
        total_duration_sec=80.0,
        dropoff_step=None,
        dropoff_reason=DropoffReason.SESSION_COMPLETE.value,
        deep_reframe_completed=True,
        rewatch_started=True,
        rewatch_completed=True,
        theory_started=False,
        theory_completed=False,
        post_created=False,
        comment_created=False,
        counterclaim_created=False,
        magazine_article_read=False,
        return_visit_reached=False,
        return_intent_score=0.9,
    )

    # Session 2: Reaches SPOILER_GATE -> drops off
    trace2 = RepresentativeSessionTrace(
        session_id="sess_2",
        persona_id="us_pers_test0001",
        scenario_id="CURRENT_BASELINE",
        replication_seed=42,
        states_visited=["LANDING", "FILM_HUB", "SPOILER_GATE"],
        transition_durations_sec={"LANDING": 6.0, "FILM_HUB": 8.0, "SPOILER_GATE": 4.0},
        total_duration_sec=18.0,
        dropoff_step="SPOILER_GATE",
        dropoff_reason=DropoffReason.SPOILER_FRICTION.value,
        deep_reframe_completed=False,
        rewatch_started=False,
        rewatch_completed=False,
        theory_started=False,
        theory_completed=False,
        post_created=False,
        comment_created=False,
        counterclaim_created=False,
        magazine_article_read=False,
        return_visit_reached=False,
        return_intent_score=0.2,
    )

    # Session 3: Reaches DEEP_REFRAME -> does not complete -> drops off
    trace3 = RepresentativeSessionTrace(
        session_id="sess_3",
        persona_id="us_pers_test0001",
        scenario_id="CURRENT_BASELINE",
        replication_seed=42,
        states_visited=["LANDING", "FILM_HUB", "SPOILER_GATE", "REVEAL", "DEEP_REFRAME"],
        transition_durations_sec={"LANDING": 4.0, "FILM_HUB": 6.0, "SPOILER_GATE": 5.0, "REVEAL": 5.0, "DEEP_REFRAME": 10.0},
        total_duration_sec=30.0,
        dropoff_step="DEEP_REFRAME",
        dropoff_reason=DropoffReason.CONTENT_TOO_DENSE.value,
        deep_reframe_completed=False,
        rewatch_started=False,
        rewatch_completed=False,
        theory_started=False,
        theory_completed=False,
        post_created=False,
        comment_created=False,
        counterclaim_created=False,
        magazine_article_read=False,
        return_visit_reached=False,
        return_intent_score=0.4,
    )

    agg.record_session(trace1, mock_profile)
    agg.record_session(trace2, mock_profile)
    agg.record_session(trace3, mock_profile)

    assert agg.total_sessions == 3
    assert len(agg.durations_reservoir) == 3
    assert agg.durations_reservoir == [80.0, 18.0, 30.0]
    assert len(agg.representative_traces) == 3

    # TTFV: only session 1 and session 3 reached REVEAL / DEEP_REFRAME
    # session 1: 5 + 10 + 5 + 10 = 30.0
    # session 3: 4 + 6 + 5 + 5 = 20.0
    assert agg.ttfv_count == 2
    assert agg.ttfv_sum == 50.0

    metrics = compute_funnel_metrics(agg)
    assert metrics.time_to_first_value_sec == 25.0
    assert metrics.p50_session_duration_sec == 30.0

    # Actions count
    assert agg.actions_count["deep_reframe_entered"] == 2
    assert agg.actions_count["deep_reframe_completed"] == 1
    assert agg.actions_count["rewatch_started"] == 1
    assert agg.actions_count["rewatch_completed"] == 1


def test_cohort_summaries_reconciliation(mock_profile):
    """
    Verifies that CohortSummary completion rates are populated and numerators
    reconcile with aggregate counts.
    """
    agg = OnlineMetricsAggregator(track_clusters=True)
    trace = RepresentativeSessionTrace(
        session_id="sess_c1",
        persona_id="us_pers_test0001",
        scenario_id="CURRENT_BASELINE",
        replication_seed=42,
        states_visited=["LANDING", "FILM_HUB", "SPOILER_GATE", "REVEAL", "DEEP_REFRAME", "REWATCH"],
        transition_durations_sec={"LANDING": 5.0, "FILM_HUB": 5.0, "SPOILER_GATE": 5.0, "REVEAL": 5.0, "DEEP_REFRAME": 10.0, "REWATCH": 15.0},
        total_duration_sec=45.0,
        dropoff_step=None,
        dropoff_reason=DropoffReason.SESSION_COMPLETE.value,
        deep_reframe_completed=True,
        rewatch_started=True,
        rewatch_completed=True,
        theory_started=False,
        theory_completed=False,
        post_created=False,
        comment_created=False,
        counterclaim_created=False,
        magazine_article_read=False,
        return_visit_reached=False,
        return_intent_score=0.8,
    )
    agg.record_session(trace, mock_profile)

    balanced, weighted = compute_cohort_summaries(agg)
    assert len(balanced) > 0
    c0 = balanced[0]
    assert c0.deep_reframe_entry_rate == 1.0
    assert c0.deep_reframe_completion_rate == 1.0
    assert c0.rewatch_start_rate == 1.0
    assert c0.rewatch_completion_rate == 1.0


def test_online_metrics_aggregator_and_intervals(mock_profile):
    aggregator = OnlineMetricsAggregator(track_clusters=True)

    # Feed 100 simulated sessions
    for i in range(100):
        trace = RepresentativeSessionTrace(
            session_id=f"sess_{i}",
            persona_id=f"us_pers_test_{i % 10}",
            scenario_id="CURRENT_BASELINE",
            replication_seed=42,
            states_visited=[
                GoldenPathState.LANDING.value,
                GoldenPathState.FILM_HUB.value,
                GoldenPathState.SPOILER_GATE.value,
                GoldenPathState.REVEAL.value,
                GoldenPathState.DEEP_REFRAME.value,
            ],
            transition_durations_sec={"LANDING": 5.0, "FILM_HUB": 10.0, "SPOILER_GATE": 5.0, "REVEAL": 5.0, "DEEP_REFRAME": 25.0},
            total_duration_sec=50.0,
            dropoff_step=GoldenPathState.DEEP_REFRAME.value if i >= 50 else None,
            dropoff_reason=DropoffReason.NO_VERIFIED_PROOF.value if i >= 50 else DropoffReason.SESSION_COMPLETE.value,
            deep_reframe_completed=(i < 60),
            rewatch_started=(i < 40),
            rewatch_completed=(i < 30),
            theory_started=(i < 30),
            theory_completed=(i < 20),
            magazine_article_read=(i < 60),
            return_intent_score=0.8,
        )
        aggregator.record_session(trace, mock_profile)

    metrics = compute_funnel_metrics(aggregator)
    assert aggregator.total_sessions == 100
    assert metrics.state_entry_counts["LANDING"] == 100
    assert metrics.landing_to_film_hub_rate == 1.0

    intervals = calculate_simulation_intervals(metrics, total_sessions=100, agg=aggregator)
    assert "golden_path_completion_rate" in intervals
    gp_interval = intervals["golden_path_completion_rate"]
    assert gp_interval.label == "SIMULATION_INTERVAL"
    assert 0.0 <= gp_interval.lower_bound <= gp_interval.point_estimate <= gp_interval.upper_bound <= 1.0


def test_rank_ux_bottlenecks_formula(mock_profile):
    aggregator = OnlineMetricsAggregator()

    # Record 70 dropoffs at SPOILER_GATE and 30 at DEEP_REFRAME
    for i in range(100):
        trace = RepresentativeSessionTrace(
            session_id=f"sess_{i}",
            persona_id="us_pers_test0001",
            scenario_id="CURRENT_BASELINE",
            replication_seed=42,
            states_visited=[
                GoldenPathState.LANDING.value,
                GoldenPathState.FILM_HUB.value,
                GoldenPathState.SPOILER_GATE.value,
            ],
            transition_durations_sec={"LANDING": 5.0, "FILM_HUB": 10.0, "SPOILER_GATE": 15.0},
            total_duration_sec=30.0,
            dropoff_step=GoldenPathState.SPOILER_GATE.value if i < 70 else GoldenPathState.DEEP_REFRAME.value,
            dropoff_reason=DropoffReason.SPOILER_FRICTION.value if i < 70 else DropoffReason.NO_VERIFIED_PROOF.value,
            rewatch_started=False,
            theory_completed=False,
            magazine_article_read=False,
            return_intent_score=0.4,
        )
        aggregator.record_session(trace, mock_profile)

    report = rank_bottlenecks(aggregator)
    assert report.bottlenecks is not None
    assert len(report.bottlenecks) >= 1
    # SPOILER_GATE should be rank #1
    top = report.bottlenecks[0]
    assert top.rank == 1
    assert top.state == "SPOILER_GATE"
    assert top.affected_sessions == 70
    assert top.sensitivity_score >= 0.0
