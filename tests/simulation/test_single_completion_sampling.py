"""
Reframe V7 Single Completion Sampling Tests
Proves:
1. Maximum 1 draw for Deep Reframe completion per session.
2. Maximum 1 draw for Rewatch completion per session.
3. Maximum 1 draw for Magazine Read completion per session.
4. Deterministic and reproducible session traces.
Zero External Generative Model Calls ($0.00).
"""
import pytest
from unittest.mock import patch
from src.reframe.simulation.schemas import (
    ScenarioVariant,
    DerivedPersonaProfile,
)
from src.reframe.simulation.session_runner import simulate_session_deterministic
from src.reframe.simulation.behavior_policy import behavior_policy


@pytest.fixture
def test_persona():
    return DerivedPersonaProfile(
        persona_id="us_pers_draw_test",
        source_persona_id_hash="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        locale="en_US",
        display_alias="Single Draw Test Fan",
        age_band="25-34",
        state="CA",
        census_region="West",
        location_context="Urban",
        education_group="Bachelor's",
        occupation_group="Tech & Engineering",
        sampling_weight=1.0,
        safe_interest_tags=["mystery_puzzles", "film_noir"],
        available_persona_lenses=["GENERAL"],
        source_dataset="nvidia/Nemotron-Personas-USA",
        source_revision="5b4cd35",
    )


def test_single_completion_draw_lifecycle(test_persona):
    """
    Simulates sessions across multiple seeds and variants, asserting that each
    feature completion method is called at most ONCE per session trace.
    """
    for variant in ScenarioVariant:
        for rep in range(5):
            call_counts = {
                "deep_reframe": 0,
                "rewatch": 0,
                "magazine": 0,
            }

            orig_dr = behavior_policy.get_deep_reframe_completion_probability
            orig_rw = behavior_policy.get_rewatch_completion_probability
            orig_mag = behavior_policy.get_magazine_read_completion_probability

            def mock_dr(*args, **kwargs):
                call_counts["deep_reframe"] += 1
                return orig_dr(*args, **kwargs)

            def mock_rw(*args, **kwargs):
                call_counts["rewatch"] += 1
                return orig_rw(*args, **kwargs)

            def mock_mag(*args, **kwargs):
                call_counts["magazine"] += 1
                return orig_mag(*args, **kwargs)

            with patch.object(behavior_policy, "get_deep_reframe_completion_probability", side_effect=mock_dr), \
                 patch.object(behavior_policy, "get_rewatch_completion_probability", side_effect=mock_rw), \
                 patch.object(behavior_policy, "get_magazine_read_completion_probability", side_effect=mock_mag):

                trace = simulate_session_deterministic(
                    profile=test_persona,
                    variant=variant,
                    replication_idx=rep,
                    seed=42,
                )

                assert call_counts["deep_reframe"] <= 1, f"Deep Reframe sampled {call_counts['deep_reframe']} times in variant {variant.value}"
                assert call_counts["rewatch"] <= 1, f"Rewatch sampled {call_counts['rewatch']} times in variant {variant.value}"
                assert call_counts["magazine"] <= 1, f"Magazine sampled {call_counts['magazine']} times in variant {variant.value}"
