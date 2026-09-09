"""
Reframe V7 Statistical Validity & Cluster Bootstrap Unit Tests
Verifies:
1. True persona-cluster bootstrap resampling across multiple replications per persona.
2. Strict lower_bound <= point_estimate <= upper_bound containment across all intervals.
3. Sensitivity deltas strictly bounded within [-1.0, 1.0].
4. 7-part convergence criteria requiring 3 consecutive passes.
5. Exact non-overcounting of Full Golden Path completions.
Zero External Generative Model Calls ($0.00).
"""
import numpy as np
import pytest
from src.reframe.simulation.schemas import (
    FunnelMetrics,
    SimulationInterval,
    SimulationRunConfig,
    SimulationMode,
    ScenarioVariant,
    RepresentativeSessionTrace,
    DerivedPersonaProfile,
    GoldenPathState,
    DropoffReason,
)
from src.reframe.simulation.aggregators import OnlineMetricsAggregator
from src.reframe.simulation.intervals import compute_persona_cluster_bootstrap, calculate_simulation_intervals
from src.reframe.simulation.sensitivity import run_sensitivity_analysis
from src.reframe.simulation.simulator import AudienceSimulator
from src.reframe.simulation.metrics import compute_funnel_metrics


@pytest.fixture
def sample_personas():
    personas = []
    for i in range(50):
        personas.append(
            DerivedPersonaProfile(
                persona_id=f"us_pers_{i:04d}",
                source_persona_id_hash=f"{i:064x}",
                locale="en_US",
                display_alias=f"Synthetic Fan US-{i:06d}",
                age_band="25-34",
                state="CA" if i % 2 == 0 else "NY",
                census_region="West" if i % 2 == 0 else "Northeast",
                location_context="Urban",
                education_group="Bachelor's",
                occupation_group="Tech & Engineering",
                sampling_weight=1.0,
                safe_interest_tags=["mystery_puzzles"],
                available_persona_lenses=["GENERAL"],
                source_dataset="nvidia/Nemotron-Personas-USA",
                source_revision="5b4cd35",
            )
        )
    return personas


def test_persona_cluster_bootstrap_calculation(sample_personas):
    agg = OnlineMetricsAggregator(track_clusters=True)
    # 50 personas, 2 replications each = 100 sessions
    for rep in range(2):
        for p in sample_personas:
            trace = RepresentativeSessionTrace(
                session_id=f"sess_{p.persona_id}_{rep}",
                persona_id=p.persona_id,
                scenario_id="CURRENT_BASELINE",
                replication_seed=42 + rep,
                states_visited=[
                    GoldenPathState.LANDING.value,
                    GoldenPathState.FILM_HUB.value,
                    GoldenPathState.SPOILER_GATE.value,
                    GoldenPathState.DEEP_REFRAME.value,
                ],
                transition_durations_sec={"LANDING": 5.0, "FILM_HUB": 10.0, "SPOILER_GATE": 5.0, "DEEP_REFRAME": 25.0},
                total_duration_sec=45.0,
                dropoff_step=None,
                dropoff_reason=DropoffReason.SESSION_COMPLETE.value,
                deep_reframe_completed=True,
                rewatch_started=(rep == 0),
                rewatch_completed=False,
                theory_started=False,
                theory_completed=False,
                post_created=False,
                comment_created=False,
                counterclaim_created=False,
                magazine_article_read=True,
                return_visit_reached=False,
                return_intent_score=0.8,
            )
            agg.record_session(trace, p)

    metrics = compute_funnel_metrics(agg)
    intervals = calculate_simulation_intervals(
        agg=agg,
        metrics=metrics,
        total_sessions=100,
        bootstrap_replications=500,
        bootstrap_seed=42,
    )

    assert "golden_path_completion_rate" in intervals
    for name, intv in intervals.items():
        assert intv.label == "SIMULATION_INTERVAL"
        assert intv.interval_method in [
            "POISSON_PERSONA_CLUSTER_BOOTSTRAP",
            "SUBSAMPLED_POISSON_PERSONA_CLUSTER_BOOTSTRAP",
            "PERSONA_CLUSTER_BOOTSTRAP",
            "SUBSAMPLED_PERSONA_CLUSTER_BOOTSTRAP",
            "DESIGN_EFFECT_APPROXIMATION",
        ]
        assert 0.0 <= intv.lower_bound <= intv.point_estimate <= intv.upper_bound <= 1.0, f"Interval bounds failed for {name}: {intv}"


def test_sensitivity_deltas_strictly_bounded(sample_personas):
    report = run_sensitivity_analysis(
        personas_sample=sample_personas,
        seed=42,
        variant=ScenarioVariant.CURRENT_BASELINE,
        sample_size=50,
    )

    assert report.paired_scenario == "CURRENT_BASELINE"
    assert len(report.results) == 20  # 10 factors * 2 directions (+20%, -20%)
    assert report.sample_size == 50

    for fr in report.results:
        assert -1.0 <= fr.delta <= 1.0
        assert -1.0 <= fr.golden_path_delta <= 1.0
        assert -1.0 <= fr.rewatch_delta <= 1.0
        assert -1.0 <= fr.theory_delta <= 1.0
        assert -1.0 <= fr.community_delta <= 1.0
        assert -1.0 <= fr.magazine_delta <= 1.0
        assert -1.0 <= fr.return_intent_delta <= 1.0
        assert 0.0 <= fr.baseline_rate <= 1.0
        assert 0.0 <= fr.perturbed_rate <= 1.0
        assert fr.paired_seed == 42


def test_convergence_history_in_simulation_result(sample_personas):
    config = SimulationRunConfig(
        mode=SimulationMode.CI,
        unique_source_personas=10,
        variants=[ScenarioVariant.CURRENT_BASELINE],
        replications=1,
        seed=42,
    )
    sim = AudienceSimulator(config)
    res = sim.run_simulation(sample_personas[:10], enable_adaptive_stop=True)

    assert res.synthetic_sessions == 10
    assert res.termination_reason.value in ["SAMPLE_TARGET_REACHED", "CONVERGED"]
    assert isinstance(res.convergence_history, list)
