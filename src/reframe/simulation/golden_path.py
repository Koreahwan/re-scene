"""
Reframe V7 Golden Path Scenario Matrix & State Machine Definitions
Grounded in current product truth and documented scenario matrix.
Zero External Generative Model Calls.
"""
from __future__ import annotations
from typing import Dict, List
from src.reframe.simulation.schemas import (
    ScenarioVariant,
    ScenarioConfig,
    GoldenPathState,
    DropoffReason,
)

# 5 Documented Scenario Matrix Variants (Section 24 & 25)
DEFAULT_SCENARIO_CONFIGS: Dict[ScenarioVariant, ScenarioConfig] = {
    ScenarioVariant.QUICK_VALUE: ScenarioConfig(
        variant=ScenarioVariant.QUICK_VALUE,
        auth_gate="JUST_IN_TIME",
        deep_reframe_depth="SHORT",
        trust_label_style="COMPACT",
        layout_style="EVIDENCE_FIRST",
        latency_level="LOW",
        media_latency_level="NORMAL",
        community_density="NORMAL",
        verified_proof_count=0,
        rewatch_pattern_public_count=0,
        deep_reframe_empty_state=True,
        hypothetical_product_config=False,
    ),
    ScenarioVariant.CURRENT_BASELINE: ScenarioConfig(
        variant=ScenarioVariant.CURRENT_BASELINE,
        auth_gate="THEORY_SAVE",
        deep_reframe_depth="STANDARD",
        trust_label_style="DETAILED",
        layout_style="STANDARD",
        latency_level="NORMAL",
        media_latency_level="NORMAL",
        community_density="NORMAL",
        verified_proof_count=0,
        rewatch_pattern_public_count=0,
        deep_reframe_empty_state=True,
        hypothetical_product_config=False,
    ),
    ScenarioVariant.EARLY_AUTH: ScenarioConfig(
        variant=ScenarioVariant.EARLY_AUTH,
        auth_gate="BEFORE_REVEAL",
        deep_reframe_depth="STANDARD",
        trust_label_style="DETAILED",
        layout_style="STANDARD",
        latency_level="NORMAL",
        media_latency_level="NORMAL",
        community_density="NORMAL",
        verified_proof_count=0,
        rewatch_pattern_public_count=0,
        deep_reframe_empty_state=True,
        hypothetical_product_config=False,
    ),
    ScenarioVariant.DEEP_ANALYSIS: ScenarioConfig(
        variant=ScenarioVariant.DEEP_ANALYSIS,
        auth_gate="THEORY_SAVE",
        deep_reframe_depth="DEEP_PROGRESSIVE_DISCLOSURE",
        trust_label_style="DETAILED",
        layout_style="ANALYSIS_FIRST",
        latency_level="NORMAL",
        media_latency_level="HIGH",
        community_density="NORMAL",
        verified_proof_count=0,
        rewatch_pattern_public_count=0,
        deep_reframe_empty_state=True,
        hypothetical_product_config=False,
    ),
    ScenarioVariant.COMMUNITY_FIRST: ScenarioConfig(
        variant=ScenarioVariant.COMMUNITY_FIRST,
        auth_gate="JUST_IN_TIME",
        deep_reframe_depth="STANDARD",
        trust_label_style="COMPACT",
        layout_style="COMMUNITY_AND_MAGAZINE_VISIBLE",
        latency_level="NORMAL",
        media_latency_level="NORMAL",
        community_density="HIGH",
        verified_proof_count=0,
        rewatch_pattern_public_count=0,
        deep_reframe_empty_state=True,
        hypothetical_product_config=False,
    ),
}


def get_scenario_config(variant: ScenarioVariant) -> ScenarioConfig:
    return DEFAULT_SCENARIO_CONFIGS.get(variant, DEFAULT_SCENARIO_CONFIGS[ScenarioVariant.CURRENT_BASELINE])


GOLDEN_PATH_PRIMARY_SEQUENCE = [
    GoldenPathState.LANDING,
    GoldenPathState.FILM_HUB,
    GoldenPathState.SPOILER_GATE,
    GoldenPathState.REVEAL,
    GoldenPathState.DEEP_REFRAME,
]
