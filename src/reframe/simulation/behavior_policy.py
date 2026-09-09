"""
Reframe V7 Behavior Policy
Calculates transition probabilities, stochastic completion probabilities,
and categorical branching distributions for US audience simulation.
Strict Fairness Firewall: Zero demographic behavioral assumptions.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import hashlib
from typing import Dict, Any, Optional, Tuple, List
from src.reframe.simulation.schemas import (
    SyntheticFanTraits,
    ScenarioConfig,
    GoldenPathState,
    DropoffReason,
    FanDepth,
)


def hash_to_uniform(
    persona_hash: str,
    scenario_id: str,
    replication_idx: int,
    step_name: str,
    global_seed: int,
) -> float:
    """
    Deterministic counter-based uniform pseudo-random number generator in [0.0, 1.0).
    Given the exact same tuple of inputs, returns the exact same float.
    Different replications or seeds yield statistically independent uniform values.
    """
    key = f"{persona_hash}:{scenario_id}:{replication_idx}:{step_name}:{global_seed}".encode("utf-8")
    digest = hashlib.sha256(key).digest()
    val = int.from_bytes(digest[:8], byteorder="big")
    return val / 18446744073709551616.0


class BehaviorPolicy:
    version: str = "reframe_us_audience_policy_v1"

    def __init__(self, allow_demographic_behavior_assumptions: bool = False):
        self.allow_demographic_behavior_assumptions = allow_demographic_behavior_assumptions

    def evaluate_transition(
        self,
        current_state: GoldenPathState,
        traits: SyntheticFanTraits,
        scenario: ScenarioConfig,
        demographics: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[GoldenPathState], Optional[DropoffReason]]:
        p, reason = self.get_transition_probability(current_state, traits, scenario)
        next_states = {
            GoldenPathState.LANDING: GoldenPathState.FILM_HUB,
            GoldenPathState.FILM_HUB: GoldenPathState.SPOILER_GATE,
            GoldenPathState.SPOILER_GATE: GoldenPathState.REVEAL,
            GoldenPathState.REVEAL: GoldenPathState.DEEP_REFRAME,
            GoldenPathState.DEEP_REFRAME: GoldenPathState.REWATCH,
            GoldenPathState.THEORY_LAB: GoldenPathState.THEORY_DRAFT,
            GoldenPathState.THEORY_DRAFT: GoldenPathState.THEORY_VALIDATION,
            GoldenPathState.COMMUNITY_READ: GoldenPathState.COMMUNITY_CREATE,
        }
        return next_states.get(current_state), reason

    def get_transition_probability(
        self,
        current_state: GoldenPathState,
        traits: SyntheticFanTraits,
        scenario: ScenarioConfig,
    ) -> Tuple[float, DropoffReason]:
        """
        Returns (success_probability, dropoff_reason_if_failed).
        """
        # 1. LANDING -> FILM_HUB
        if current_state == GoldenPathState.LANDING:
            latency_mult = 0.80 if scenario.latency_level == "HIGH" else (1.05 if scenario.latency_level == "LOW" else 1.0)
            layout_boost = 0.05 if scenario.layout_style in ["EVIDENCE_FIRST", "COMMUNITY_AND_MAGAZINE_VISIBLE"] else 0.0
            p = min(0.99, max(0.20, (0.75 + 0.15 * traits.digital_comfort + layout_boost) * latency_mult))
            reason = DropoffReason.API_LATENCY if scenario.latency_level == "HIGH" else DropoffReason.VALUE_NOT_CLEAR
            return p, reason

        # 2. FILM_HUB -> SPOILER_GATE
        elif current_state == GoldenPathState.FILM_HUB:
            auth_penalty = 0.25 if scenario.auth_gate == "BEFORE_REVEAL" and traits.digital_comfort < 0.6 else 0.0
            p = min(0.98, max(0.20, 0.78 + 0.15 * traits.reading_patience - auth_penalty))
            reason = DropoffReason.AUTH_FRICTION if auth_penalty > 0.1 else DropoffReason.NO_RELEVANT_FILM
            return p, reason

        # 3. SPOILER_GATE -> REVEAL
        elif current_state == GoldenPathState.SPOILER_GATE:
            p = min(0.98, max(0.15, 0.65 + 0.25 * traits.spoiler_tolerance + 0.08 * traits.evidence_preference))
            return p, DropoffReason.SPOILER_FRICTION

        # 4. REVEAL -> DEEP_REFRAME
        elif current_state == GoldenPathState.REVEAL:
            trust_mult = 1.05 if scenario.trust_label_style == "DETAILED" else 0.95
            proof_penalty = 0.10 if scenario.verified_proof_count == 0 and not scenario.hypothetical_product_config else 0.0
            p = min(0.98, max(0.15, (0.68 + 0.18 * traits.reading_patience + 0.12 * traits.trust_in_ai_analysis - proof_penalty) * trust_mult))
            if traits.trust_in_ai_analysis < 0.35:
                reason = DropoffReason.LOW_TRUST
            elif scenario.verified_proof_count == 0 and traits.evidence_preference > 0.7:
                reason = DropoffReason.NO_VERIFIED_PROOF
            else:
                reason = DropoffReason.CONTENT_TOO_DENSE
            return p, reason

        # 5. THEORY_LAB -> THEORY_DRAFT
        elif current_state == GoldenPathState.THEORY_LAB:
            auth_penalty = 0.20 if scenario.auth_gate == "THEORY_SAVE" and traits.digital_comfort < 0.5 else 0.0
            p = min(0.95, max(0.10, 0.60 + 0.35 * traits.theory_writing_propensity - auth_penalty))
            reason = DropoffReason.AUTH_FRICTION if auth_penalty > 0.1 else DropoffReason.THEORY_EFFORT
            return p, reason

        # 6. THEORY_DRAFT -> THEORY_VALIDATION
        elif current_state == GoldenPathState.THEORY_DRAFT:
            p = min(0.96, max(0.20, 0.55 + 0.30 * traits.evidence_preference + 0.12 * traits.reading_patience))
            return p, DropoffReason.THEORY_EFFORT

        # 7. COMMUNITY_READ -> COMMUNITY_CREATE
        elif current_state == GoldenPathState.COMMUNITY_READ:
            density_boost = 0.08 if scenario.community_density == "HIGH" else (-0.12 if scenario.community_density == "LOW" else 0.0)
            p = min(0.90, max(0.05, 0.35 + 0.45 * traits.community_participation + density_boost))
            reason = DropoffReason.COMMUNITY_COLD_START if scenario.community_density == "LOW" else DropoffReason.SESSION_COMPLETE
            return p, reason

        # 8. Return default fallback
        return 0.50, DropoffReason.SESSION_COMPLETE

    def get_deep_reframe_completion_probability(
        self,
        traits: SyntheticFanTraits,
        scenario: ScenarioConfig,
    ) -> float:
        """Stochastic completion probability for reading / engaging deeply with Deep Reframe cards."""
        trust_mult = 1.05 if scenario.trust_label_style == "DETAILED" else 0.95
        return min(0.96, max(0.15, (0.60 + 0.22 * traits.reading_patience + 0.14 * traits.trust_in_ai_analysis) * trust_mult))

    def get_rewatch_completion_probability(
        self,
        traits: SyntheticFanTraits,
        scenario: ScenarioConfig,
    ) -> float:
        """Stochastic completion probability for completing a rewatch sync loop."""
        latency_mult = 0.82 if scenario.media_latency_level == "HIGH" else 1.0
        return min(0.94, max(0.15, (0.58 + 0.36 * traits.rewatch_affinity) * latency_mult))

    def get_magazine_read_completion_probability(
        self,
        traits: SyntheticFanTraits,
        scenario: ScenarioConfig,
    ) -> float:
        """Stochastic completion probability for completing a full magazine article read."""
        return min(0.95, max(0.15, 0.55 + 0.28 * traits.magazine_reading_affinity + 0.14 * traits.reading_patience))

    def get_branch_distribution(
        self,
        current_state: GoldenPathState,
        traits: SyntheticFanTraits,
        scenario: ScenarioConfig,
    ) -> Dict[GoldenPathState, float]:
        """
        Returns normalized categorical probabilities over next states from branching points.
        """
        if current_state == GoldenPathState.DEEP_REFRAME:
            weights = {
                GoldenPathState.REWATCH: max(0.05, traits.rewatch_affinity * (0.80 if scenario.media_latency_level == "HIGH" else 1.10)),
                GoldenPathState.THEORY_LAB: max(0.05, traits.theory_writing_propensity * 1.05),
                GoldenPathState.COMMUNITY_READ: max(0.05, traits.community_participation * (1.20 if scenario.community_density == "HIGH" else 0.90)),
                GoldenPathState.MAGAZINE_READ: max(0.05, traits.magazine_reading_affinity * 1.10),
                GoldenPathState.RETURN_VISIT: max(0.05, traits.return_intent * 0.85),
            }
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()}

        elif current_state == GoldenPathState.REWATCH:
            weights = {
                GoldenPathState.THEORY_LAB: max(0.05, traits.theory_writing_propensity * 1.10),
                GoldenPathState.COMMUNITY_READ: max(0.05, traits.community_participation * 1.05),
                GoldenPathState.MAGAZINE_READ: max(0.05, traits.magazine_reading_affinity * 1.05),
                GoldenPathState.RETURN_VISIT: max(0.05, traits.return_intent * 0.90),
            }
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()}

        elif current_state == GoldenPathState.COMMUNITY_CREATE:
            weights = {
                GoldenPathState.COMMENT: max(0.10, traits.community_participation * 1.20),
                GoldenPathState.COUNTERCLAIM: max(0.05, traits.evidence_preference * 0.80 + traits.theory_writing_propensity * 0.40),
                GoldenPathState.RETURN_VISIT: max(0.05, traits.return_intent * 0.70),
            }
            total = sum(weights.values())
            return {k: v / total for k, v in weights.items()}

        return {GoldenPathState.RETURN_VISIT: 1.0}


behavior_policy = BehaviorPolicy()
