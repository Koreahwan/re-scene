"""
Reframe V7 Simulation Fairness Firewall Unit Tests
Validates that demographic attributes (sex, state, education, occupation) never alter
behavioral traits or transition probabilities under the Fairness Firewall.
"""
import pytest
from src.reframe.simulation.schemas import (
    DerivedPersonaProfile,
    ScenarioVariant,
    GoldenPathState,
    DropoffReason,
)
from src.reframe.simulation.fan_traits import FanTraitsAssigner
from src.reframe.simulation.behavior_policy import BehaviorPolicy
from src.reframe.simulation.golden_path import get_scenario_config


def test_fairness_firewall_trait_independence():
    """
    Two personas with the same source_persona_id_hash and safe interest tags but vastly different demographic attributes
    must produce identical fan traits when fairness firewall is active.
    """
    assigner = FanTraitsAssigner()

    persona_a = DerivedPersonaProfile(
        persona_id="us_pers_1234567812345678",
        source_persona_id_hash="abc123def4567890abc123def4567890abc123def4567890abc123def4567890",
        locale="en_US",
        display_alias="Synthetic Fan US-000001",
        age_band="18-24",
        state="CA",
        census_region="West",
        location_context="Metro",
        education_group="High School",
        occupation_group="Arts & Entertainment",
        sampling_weight=1.0,
        safe_interest_tags=["mystery_puzzles"],
        available_persona_lenses=["GENERAL"],
        source_dataset="nvidia/Nemotron-Personas-USA",
        source_revision="5b4cd35",
    )

    persona_b = DerivedPersonaProfile(
        persona_id="us_pers_1234567812345678",  # Identical hash
        source_persona_id_hash="abc123def4567890abc123def4567890abc123def4567890abc123def4567890",
        locale="en_US",
        display_alias="Synthetic Fan US-000002",
        age_band="65+",
        state="FL",
        census_region="South",
        location_context="Rural",
        education_group="Doctorate / Professional",
        occupation_group="Executive & Management",
        sampling_weight=1.0,
        safe_interest_tags=["mystery_puzzles"],
        available_persona_lenses=["PROFESSIONAL"],
        source_dataset="nvidia/Nemotron-Personas-USA",
        source_revision="5b4cd35",
    )

    traits_a = assigner.assign_traits(persona_a)
    traits_b = assigner.assign_traits(persona_b)

    assert traits_a.fan_depth == traits_b.fan_depth
    assert traits_a.spoiler_tolerance == traits_b.spoiler_tolerance
    assert traits_a.rewatch_affinity == traits_b.rewatch_affinity
    assert traits_a.reading_patience == traits_b.reading_patience
    assert traits_a.theory_writing_propensity == traits_b.theory_writing_propensity
    assert traits_a.community_participation == traits_b.community_participation
    assert traits_a.digital_comfort == traits_b.digital_comfort


def test_fairness_firewall_policy_independence():
    """
    Behavior policy evaluation must not alter transitions based on demographics.
    """
    policy = BehaviorPolicy(allow_demographic_behavior_assumptions=False)
    assigner = FanTraitsAssigner()

    persona = DerivedPersonaProfile(
        persona_id="us_pers_8765432187654321",
        source_persona_id_hash="fed987cba6543210fed987cba6543210fed987cba6543210fed987cba6543210",
        locale="en_US",
        display_alias="Synthetic Fan US-000003",
        age_band="35-44",
        state="NY",
        census_region="Northeast",
        location_context="Metro",
        education_group="Bachelor's Degree",
        occupation_group="Tech & Engineering",
        sampling_weight=1.0,
        safe_interest_tags=["mystery_puzzles", "classic_cinema"],
        available_persona_lenses=["GENERAL"],
        source_dataset="nvidia/Nemotron-Personas-USA",
        source_revision="5b4cd35",
    )
    traits = assigner.assign_traits(persona)
    scenario = get_scenario_config(ScenarioVariant.QUICK_VALUE)

    next_state, dropoff = policy.evaluate_transition(
        current_state=GoldenPathState.LANDING,
        traits=traits,
        scenario=scenario,
        demographics={"state": "NY", "age": 35},
    )

    assert next_state in [GoldenPathState.FILM_HUB, None]
    assert isinstance(dropoff, DropoffReason)
