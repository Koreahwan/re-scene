"""
Reframe V7 Deterministic Session Runner
Executes individual persona session traces through the golden path state machine.
Enforces single-draw completion sampling lifecycle across all features.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import hashlib
from typing import Optional
from src.reframe.simulation.schemas import (
    ScenarioVariant,
    RepresentativeSessionTrace,
    DerivedPersonaProfile,
    SyntheticFanTraits,
    GoldenPathState,
    DropoffReason,
    ScenarioConfig,
)
from src.reframe.simulation.golden_path import get_scenario_config
from src.reframe.simulation.fan_traits import fan_traits_assigner
from src.reframe.simulation.behavior_policy import behavior_policy, hash_to_uniform


def simulate_session_deterministic(
    profile: DerivedPersonaProfile,
    variant: ScenarioVariant,
    replication_idx: int,
    seed: int,
    scenario_override: Optional[ScenarioConfig] = None,
    traits_override: Optional[SyntheticFanTraits] = None,
    session_id_prefix: str = "sim_sess_",
) -> RepresentativeSessionTrace:
    """
    Unified, deterministic session simulation engine.
    Used by both main simulation and paired sensitivity reruns.
    Zero generative model calls.
    Single-draw feature completion sampling.
    """
    scenario = scenario_override or get_scenario_config(variant)
    traits = traits_override or profile.traits or fan_traits_assigner.assign_traits(profile, seed)

    # Deterministic Session ID
    sess_hash = hashlib.sha256(
        f"{profile.source_persona_id_hash}:{variant.value}:{replication_idx}:{seed}".encode("utf-8")
    ).hexdigest()[:16]
    session_id = f"{session_id_prefix}{sess_hash}"

    states_visited = [GoldenPathState.LANDING.value]
    u_dur_landing = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, "DUR_LANDING", seed)
    durations = {"LANDING": round(4.0 + u_dur_landing * 6.0, 1)}
    current_state = GoldenPathState.LANDING
    final_dropoff_reason = DropoffReason.SESSION_COMPLETE.value

    deep_reframe_completed = False
    rewatch_started = False
    rewatch_completed = False
    theory_started = False
    theory_completed = False
    post_created = False
    comment_created = False
    counterclaim_created = False
    magazine_article_read = False
    return_visit_reached = False

    for step in range(14):
        # Multi-branch decision points
        if current_state in (GoldenPathState.DEEP_REFRAME, GoldenPathState.REWATCH, GoldenPathState.COMMUNITY_CREATE):
            dist = behavior_policy.get_branch_distribution(current_state, traits, scenario)
            u_branch = hash_to_uniform(
                profile.source_persona_id_hash,
                variant.value,
                replication_idx,
                f"BRANCH_{current_state.value}_{step}",
                seed,
            )
            cum = 0.0
            next_st = list(dist.keys())[-1]
            for st_candidate, prob in dist.items():
                cum += prob
                if u_branch <= cum:
                    next_st = st_candidate
                    break

            current_state = next_st
            states_visited.append(current_state.value)
            u_dur = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, f"DUR_{current_state.value}_{step}", seed)
            durations[current_state.value] = round(6.0 + u_dur * 20.0, 1)

            # Feature entry single-draw lifecycle
            if current_state == GoldenPathState.DEEP_REFRAME:
                if not deep_reframe_completed:
                    u_dr = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, "COMP_DEEP_REFRAME_ONCE", seed)
                    p_dr = behavior_policy.get_deep_reframe_completion_probability(traits, scenario)
                    if u_dr < p_dr:
                        deep_reframe_completed = True
            elif current_state == GoldenPathState.REWATCH:
                rewatch_started = True
                if not rewatch_completed:
                    u_rw = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, "COMP_REWATCH_ONCE", seed)
                    p_rw = behavior_policy.get_rewatch_completion_probability(traits, scenario)
                    if u_rw < p_rw:
                        rewatch_completed = True
            elif current_state in (GoldenPathState.THEORY_LAB, GoldenPathState.THEORY_DRAFT):
                theory_started = True
            elif current_state == GoldenPathState.THEORY_VALIDATION:
                theory_started = True
                theory_completed = True
            elif current_state == GoldenPathState.COMMUNITY_CREATE:
                post_created = True
            elif current_state == GoldenPathState.COMMENT:
                comment_created = True
            elif current_state == GoldenPathState.COUNTERCLAIM:
                counterclaim_created = True
            elif current_state == GoldenPathState.MAGAZINE_READ:
                if not magazine_article_read:
                    u_mag = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, "COMP_MAGAZINE_ONCE", seed)
                    p_mag = behavior_policy.get_magazine_read_completion_probability(traits, scenario)
                    if u_mag < p_mag:
                        magazine_article_read = True
            elif current_state == GoldenPathState.RETURN_VISIT:
                return_visit_reached = True
                final_dropoff_reason = DropoffReason.SESSION_COMPLETE.value
                break
        else:
            # Linear transitions
            prob, r_fail = behavior_policy.get_transition_probability(current_state, traits, scenario)
            u_trans = hash_to_uniform(
                profile.source_persona_id_hash,
                variant.value,
                replication_idx,
                f"TRANS_{current_state.value}_{step}",
                seed,
            )

            if u_trans < prob:
                next_map = {
                    GoldenPathState.LANDING: GoldenPathState.FILM_HUB,
                    GoldenPathState.FILM_HUB: GoldenPathState.SPOILER_GATE,
                    GoldenPathState.SPOILER_GATE: GoldenPathState.REVEAL,
                    GoldenPathState.REVEAL: GoldenPathState.DEEP_REFRAME,
                    GoldenPathState.THEORY_LAB: GoldenPathState.THEORY_DRAFT,
                    GoldenPathState.THEORY_DRAFT: GoldenPathState.THEORY_VALIDATION,
                    GoldenPathState.COMMUNITY_READ: GoldenPathState.COMMUNITY_CREATE,
                }
                next_st = next_map.get(current_state, GoldenPathState.RETURN_VISIT)
                current_state = next_st
                states_visited.append(current_state.value)
                u_dur = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, f"DUR_{current_state.value}_{step}", seed)
                durations[current_state.value] = round(6.0 + u_dur * 20.0, 1)

                # Feature entry single-draw lifecycle
                if current_state == GoldenPathState.DEEP_REFRAME:
                    if not deep_reframe_completed:
                        u_dr = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, "COMP_DEEP_REFRAME_ONCE", seed)
                        p_dr = behavior_policy.get_deep_reframe_completion_probability(traits, scenario)
                        if u_dr < p_dr:
                            deep_reframe_completed = True
                elif current_state == GoldenPathState.REWATCH:
                    rewatch_started = True
                    if not rewatch_completed:
                        u_rw = hash_to_uniform(profile.source_persona_id_hash, variant.value, replication_idx, "COMP_REWATCH_ONCE", seed)
                        p_rw = behavior_policy.get_rewatch_completion_probability(traits, scenario)
                        if u_rw < p_rw:
                            rewatch_completed = True
                elif current_state in (GoldenPathState.THEORY_LAB, GoldenPathState.THEORY_DRAFT):
                    theory_started = True
                elif current_state == GoldenPathState.THEORY_VALIDATION:
                    theory_started = True
                    theory_completed = True
                elif current_state == GoldenPathState.COMMUNITY_CREATE:
                    post_created = True
                elif current_state == GoldenPathState.RETURN_VISIT:
                    return_visit_reached = True
            else:
                final_dropoff_reason = r_fail.value
                break

    if theory_completed:
        theory_started = True

    total_duration = sum(durations.values())

    return RepresentativeSessionTrace(
        session_id=session_id,
        persona_id=profile.persona_id,
        scenario_id=variant.value,
        replication_seed=seed + replication_idx,
        states_visited=states_visited,
        transition_durations_sec=durations,
        total_duration_sec=round(total_duration, 1),
        dropoff_step=states_visited[-1] if final_dropoff_reason != DropoffReason.SESSION_COMPLETE.value else None,
        dropoff_reason=final_dropoff_reason,
        deep_reframe_completed=deep_reframe_completed,
        rewatch_started=rewatch_started,
        rewatch_completed=rewatch_completed,
        theory_started=theory_started,
        theory_completed=theory_completed,
        post_created=post_created,
        comment_created=comment_created,
        counterclaim_created=counterclaim_created,
        magazine_article_read=magazine_article_read,
        return_visit_reached=return_visit_reached,
        return_intent_score=round(float(traits.return_intent), 4),
    )
