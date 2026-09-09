"""
Reframe V7 Simulation Engine Unit Tests
Validates state transitions, golden path metrics, scenario variants, and deterministic reproducibility (seed 42).
"""
import pytest
from src.reframe.simulation.schemas import (
    SimulationMode,
    ScenarioVariant,
    SimulationRunConfig,
    DerivedPersonaProfile,
)
from src.reframe.simulation.simulator import AudienceSimulator


@pytest.fixture
def sample_personas():
    return [
        DerivedPersonaProfile(
            persona_id=f"us_pers_{i:016x}",
            source_persona_id_hash=f"{i:064x}",
            locale="en_US",
            display_alias=f"Synthetic Fan US-{i:06d}",
            age_band="25-34",
            state="NY" if i % 4 == 0 else "CA",
            census_region="Northeast" if i % 4 == 0 else "West",
            location_context="Metro",
            education_group="Bachelor's",
            occupation_group="Tech & Engineering",
            sampling_weight=1.0,
            safe_interest_tags=["mystery_puzzles"],
            available_persona_lenses=["GENERAL"],
            source_dataset="nvidia/Nemotron-Personas-USA",
            source_revision="5b4cd35",
        )
        for i in range(100)
    ]


def test_simulation_engine_deterministic_reproducibility(sample_personas):
    """
    Running two simulations with the same seed and personas must produce identical metric counts.
    """
    config = SimulationRunConfig(
        mode=SimulationMode.CI,
        unique_source_personas=100,
        variants=[ScenarioVariant.QUICK_VALUE, ScenarioVariant.CURRENT_BASELINE],
        replications=1,
        seed=42,
    )

    sim_a = AudienceSimulator(config)
    res_a = sim_a.run_simulation(sample_personas)

    sim_b = AudienceSimulator(config)
    res_b = sim_b.run_simulation(sample_personas)

    assert res_a.synthetic_sessions == res_b.synthetic_sessions
    assert res_a.paid_model_calls == 0
    assert res_b.paid_model_calls == 0
    assert res_a.aggregate_funnel.golden_path_completion_rate == res_b.aggregate_funnel.golden_path_completion_rate
    assert res_a.aggregate_funnel.deep_reframe_read_rate == res_b.aggregate_funnel.deep_reframe_read_rate


def test_simulation_engine_scenario_variants(sample_personas):
    """
    Verifies that all 5 scenario variants execute and produce valid metrics.
    """
    config = SimulationRunConfig(
        mode=SimulationMode.CI,
        unique_source_personas=50,
        variants=[
            ScenarioVariant.QUICK_VALUE,
            ScenarioVariant.CURRENT_BASELINE,
            ScenarioVariant.EARLY_AUTH,
            ScenarioVariant.DEEP_ANALYSIS,
            ScenarioVariant.COMMUNITY_FIRST,
        ],
        replications=1,
        seed=100,
    )

    sim = AudienceSimulator(config)
    res = sim.run_simulation(sample_personas[:50])

    assert res.synthetic_sessions == 50 * 5 * 1  # 250 sessions
    assert len(res.scenario_metrics) == 5
    for var in [
        ScenarioVariant.QUICK_VALUE,
        ScenarioVariant.CURRENT_BASELINE,
        ScenarioVariant.EARLY_AUTH,
        ScenarioVariant.DEEP_ANALYSIS,
        ScenarioVariant.COMMUNITY_FIRST,
    ]:
        assert var.value in res.scenario_metrics
        assert res.scenario_metrics[var.value].state_entry_counts["LANDING"] == 50
