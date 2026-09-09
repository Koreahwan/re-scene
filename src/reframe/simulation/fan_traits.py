"""
Reframe V7 Synthetic Fan Traits Assignment
Assigns seeded, stratified, reproducible synthetic Reframe fan traits.
Zero Demographic Behavioral Assumptions.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import hashlib
import struct
from typing import Optional, List
from src.reframe.simulation.schemas import (
    SyntheticFanTraits,
    FanDepth,
    DerivedPersonaProfile,
)


def _hash_to_uniform_floats(seed_key: str, count: int) -> List[float]:
    """Generates `count` pseudo-random floats in [0.0, 1.0) deterministically from seed_key."""
    results = []
    hasher = hashlib.sha256(seed_key.encode("utf-8"))
    digest = hasher.digest()
    for i in range(count):
        # Derive integer from chunks of digest
        offset = (i * 4) % (len(digest) - 4)
        val = struct.unpack(">I", digest[offset:offset + 4])[0]
        results.append((val % 1000000) / 1000000.0)
        # Re-hash if needed for more floats
        if (i + 1) * 4 >= len(digest):
            hasher.update(b"extra")
            digest = hasher.digest()
    return results


class FanTraitsAssigner:
    def __init__(self, policy_version: str = "reframe_us_fan_traits_v1"):
        self.policy_version = policy_version

    def assign_traits(
        self,
        profile: DerivedPersonaProfile,
        assignment_seed: int = 42,
        seed: Optional[int] = None,
    ) -> SyntheticFanTraits:
        """
        Assigns synthetic fan traits deterministically.
        Strict Fairness Firewall: DOES NOT read sex, state, region, education, occupation, marital status.
        Age band does NOT reduce digital comfort.
        """
        effective_seed = seed if seed is not None else assignment_seed
        seed_key = f"{profile.source_persona_id_hash}:{effective_seed}:{self.policy_version}"
        rnd = _hash_to_uniform_floats(seed_key, 16)

        # 1. Fan Depth Stratification
        # CASUAL: 35%, REGULAR: 35%, DEEP_ANALYST: 12%, FILM_FORM_FAN: 10%, THEORY_EXPLORER: 8%
        fd_rand = rnd[0]
        if fd_rand < 0.35:
            fan_depth = FanDepth.CASUAL
        elif fd_rand < 0.70:
            fan_depth = FanDepth.REGULAR
        elif fd_rand < 0.82:
            fan_depth = FanDepth.DEEP_ANALYST
        elif fd_rand < 0.92:
            fan_depth = FanDepth.FILM_FORM_FAN
        else:
            fan_depth = FanDepth.THEORY_EXPLORER

        # Base traits centered around realistic distributions
        # Adjust slightly based on fan depth archetypes
        spoiler_tolerance = rnd[1]
        rewatch_affinity = rnd[2]
        reading_patience = rnd[3]
        theory_writing = rnd[4]
        community_part = rnd[5]
        evidence_pref = rnd[6]
        digital_comfort = rnd[7]  # Uniformly distributed independent of age/demographics
        trust_in_ai = rnd[8]
        moderation_sens = rnd[9]
        return_intent = rnd[10]
        magazine_affinity = rnd[11]

        # Archetype adjustments (behavioral definition of fan depth)
        if fan_depth == FanDepth.CASUAL:
            reading_patience = reading_patience * 0.7
            theory_writing = theory_writing * 0.4
            community_part = community_part * 0.5
            magazine_affinity = magazine_affinity * 0.6
        elif fan_depth == FanDepth.DEEP_ANALYST:
            reading_patience = min(1.0, reading_patience * 1.2 + 0.2)
            evidence_pref = min(1.0, evidence_pref * 1.2 + 0.3)
            theory_writing = min(1.0, theory_writing * 1.2 + 0.2)
            magazine_affinity = min(1.0, magazine_affinity * 1.1 + 0.2)
        elif fan_depth == FanDepth.FILM_FORM_FAN:
            rewatch_affinity = min(1.0, rewatch_affinity * 1.2 + 0.25)
            magazine_affinity = min(1.0, magazine_affinity * 1.3 + 0.2)
            reading_patience = min(1.0, reading_patience * 1.1 + 0.1)
        elif fan_depth == FanDepth.THEORY_EXPLORER:
            theory_writing = min(1.0, theory_writing * 1.4 + 0.3)
            community_part = min(1.0, community_part * 1.3 + 0.2)
            evidence_pref = min(1.0, evidence_pref * 1.1 + 0.1)

        # Safe Interest Tags Weak Adjustment (deterministic, max ±0.10)
        tags = set(profile.safe_interest_tags)
        if "classic_cinema" in tags or "film_noir_classic" in tags:
            rewatch_affinity = min(1.0, rewatch_affinity + 0.08)
            magazine_affinity = min(1.0, magazine_affinity + 0.08)
        if "mystery_puzzles" in tags or "crime_investigation" in tags:
            theory_writing = min(1.0, theory_writing + 0.08)
            evidence_pref = min(1.0, evidence_pref + 0.08)
        if "creative_writing" in tags:
            theory_writing = min(1.0, theory_writing + 0.06)

        return SyntheticFanTraits(
            fan_depth=fan_depth,
            spoiler_tolerance=round(max(0.0, min(1.0, spoiler_tolerance)), 4),
            rewatch_affinity=round(max(0.0, min(1.0, rewatch_affinity)), 4),
            reading_patience=round(max(0.0, min(1.0, reading_patience)), 4),
            theory_writing_propensity=round(max(0.0, min(1.0, theory_writing)), 4),
            community_participation=round(max(0.0, min(1.0, community_part)), 4),
            evidence_preference=round(max(0.0, min(1.0, evidence_pref)), 4),
            digital_comfort=round(max(0.0, min(1.0, digital_comfort)), 4),
            trust_in_ai_analysis=round(max(0.0, min(1.0, trust_in_ai)), 4),
            moderation_sensitivity=round(max(0.0, min(1.0, moderation_sens)), 4),
            return_intent=round(max(0.0, min(1.0, return_intent)), 4),
            magazine_reading_affinity=round(max(0.0, min(1.0, magazine_affinity)), 4),
            behavioral_ground_truth=False,
            demographic_behavior_inference=False,
            trait_assignment_seed=assignment_seed,
            trait_policy_version=self.policy_version,
        )


fan_traits_assigner = FanTraitsAssigner()
