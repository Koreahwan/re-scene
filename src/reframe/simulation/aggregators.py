"""
Reframe V7 Online Metrics Aggregator
Resource-safe, streaming accumulation of simulation counts, durations, and cohorts.
Zero External Generative Model Calls.
Zero unseeded Python random usage.
Exact single-contribution session accounting.
"""
from __future__ import annotations
import hashlib
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict
from src.reframe.simulation.schemas import (
    GoldenPathState,
    DropoffReason,
    DerivedPersonaProfile,
    RepresentativeSessionTrace,
)

DOWNSTREAM_STATES: Set[str] = {
    "REWATCH", "THEORY_LAB", "THEORY_DRAFT", "THEORY_VALIDATION",
    "COMMUNITY_READ", "COMMUNITY_CREATE", "COMMENT", "COUNTERCLAIM", "MAGAZINE_READ"
}


class OnlineMetricsAggregator:
    def __init__(self, track_clusters: bool = True):
        self.track_clusters: bool = track_clusters
        self.total_sessions: int = 0
        self.state_entries: Dict[str, int] = defaultdict(int)
        self.dropoff_counts: Dict[str, int] = defaultdict(int)
        self.actions_count: Dict[str, int] = defaultdict(int)

        # Duration tracking (reservoir for percentiles)
        self.durations_reservoir: List[float] = []
        self.max_reservoir_size: int = 10000
        self.ttfv_sum: float = 0.0
        self.ttfv_count: int = 0

        # Cohort counters: slice -> key -> metric -> count / weight
        self.cohort_sessions: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.cohort_weighted_sessions: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.cohort_actions: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        self.cohort_weighted_actions: Dict[str, Dict[str, Dict[str, float]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))

        # Representative Traces Reservoir (Max 100)
        self.representative_traces: List[RepresentativeSessionTrace] = []
        self.max_traces: int = 100

        # Persona level cluster tracking for bootstrap
        self.persona_session_counts: Dict[str, int] = defaultdict(int)
        self.persona_golden_path_counts: Dict[str, int] = defaultdict(int)
        self.persona_deep_reframe_counts: Dict[str, int] = defaultdict(int)
        self.persona_cluster_successes: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.persona_cluster_denominators: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def record_session(
        self,
        trace: RepresentativeSessionTrace,
        profile: DerivedPersonaProfile,
        weight: float = 1.0,
    ) -> None:
        self.total_sessions += 1
        pid = profile.persona_id
        visited_set = set(trace.states_visited)

        # 1. State entries & Dropoff
        for s in trace.states_visited:
            self.state_entries[s] += 1

        if trace.dropoff_reason:
            self.dropoff_counts[trace.dropoff_reason] += 1

        # 2. Duration Reservoir (Recorded EXACTLY ONCE per session)
        if len(self.durations_reservoir) < self.max_reservoir_size:
            self.durations_reservoir.append(trace.total_duration_sec)
        else:
            idx = ((self.total_sessions * 2654435761) & 0xFFFFFFFF) % self.total_sessions
            if idx < self.max_reservoir_size:
                self.durations_reservoir[idx] = trace.total_duration_sec

        # 3. Time to First Value (Recorded EXACTLY ONCE per session that reaches REVEAL or DEEP_REFRAME)
        if "REVEAL" in visited_set or "DEEP_REFRAME" in visited_set:
            ttfv = (
                trace.transition_durations_sec.get("LANDING", 5.0) +
                trace.transition_durations_sec.get("FILM_HUB", 8.0) +
                trace.transition_durations_sec.get("SPOILER_GATE", 4.0) +
                trace.transition_durations_sec.get("REVEAL", 0.0)
            )
            self.ttfv_sum += ttfv
            self.ttfv_count += 1

        # 4. Representative Traces Reservoir (Recorded EXACTLY ONCE per session)
        if len(self.representative_traces) < self.max_traces:
            self.representative_traces.append(trace)
        else:
            idx = ((self.total_sessions * 2246822519) & 0xFFFFFFFF) % self.total_sessions
            if idx < self.max_traces:
                self.representative_traces[idx] = trace

        # 5. Actions Tracking
        if "DEEP_REFRAME" in visited_set:
            self.actions_count["deep_reframe_entered"] += 1
        if trace.deep_reframe_completed:
            self.actions_count["deep_reframe_completed"] += 1
        if trace.rewatch_started:
            self.actions_count["rewatch_started"] += 1
        if trace.rewatch_completed:
            self.actions_count["rewatch_completed"] += 1
        if trace.theory_started:
            self.actions_count["theory_started"] += 1
        if trace.theory_completed:
            self.actions_count["theory_completed"] += 1
        if trace.post_created:
            self.actions_count["post_created"] += 1
        if trace.comment_created:
            self.actions_count["comment_created"] += 1
        if trace.counterclaim_created:
            self.actions_count["counterclaim_created"] += 1
        if trace.magazine_article_read:
            self.actions_count["magazine_article_read"] += 1
        if trace.return_intent_score > 0.5:
            self.actions_count["high_return_intent"] += 1

        # Strict Outcome Definitions
        is_activated = "DEEP_REFRAME" in visited_set
        is_downstream = bool(visited_set & DOWNSTREAM_STATES)
        is_creator = bool(trace.post_created or trace.comment_created or trace.counterclaim_created)
        return_visit_after_downstream = bool(("RETURN_VISIT" in visited_set or trace.return_visit_reached) and is_downstream)

        has_terminal_action = bool(
            trace.rewatch_completed or
            trace.theory_completed or
            trace.post_created or
            trace.comment_created or
            trace.counterclaim_created or
            trace.magazine_article_read or
            return_visit_after_downstream
        )
        is_full_gp = bool(is_activated and is_downstream and has_terminal_action)

        if is_activated:
            self.actions_count["core_value_activated"] += 1
        if is_downstream:
            self.actions_count["downstream_engaged"] += 1
        if is_creator:
            self.actions_count["creator_converted"] += 1
        if is_full_gp:
            self.actions_count["golden_path_completed"] += 1

        # 6. Persona Cluster Tracking
        self.persona_session_counts[pid] += 1
        if is_full_gp:
            self.persona_golden_path_counts[pid] += 1
        if is_activated:
            self.persona_deep_reframe_counts[pid] += 1

        if self.track_clusters:
            succ = self.persona_cluster_successes[pid]
            denom = self.persona_cluster_denominators[pid]

            denom["landing_to_film_hub_rate"] += 1 if "LANDING" in visited_set else 0
            succ["landing_to_film_hub_rate"] += 1 if "FILM_HUB" in visited_set else 0

            denom["film_hub_to_reveal_rate"] += 1 if "FILM_HUB" in visited_set else 0
            succ["film_hub_to_reveal_rate"] += 1 if "REVEAL" in visited_set else 0

            denom["spoiler_gate_completion_rate"] += 1 if "SPOILER_GATE" in visited_set else 0
            succ["spoiler_gate_completion_rate"] += 1 if "REVEAL" in visited_set else 0

            denom["reveal_to_deep_reframe_rate"] += 1 if "REVEAL" in visited_set else 0
            succ["reveal_to_deep_reframe_rate"] += 1 if is_activated else 0

            denom["deep_reframe_entry_rate"] += 1 if "REVEAL" in visited_set else 0
            succ["deep_reframe_entry_rate"] += 1 if is_activated else 0

            denom["deep_reframe_completion_rate"] += 1 if is_activated else 0
            succ["deep_reframe_completion_rate"] += 1 if trace.deep_reframe_completed else 0

            denom["deep_reframe_read_rate"] += 1 if "REVEAL" in visited_set else 0
            succ["deep_reframe_read_rate"] += 1 if is_activated else 0

            denom["rewatch_start_rate"] += 1 if is_activated else 0
            succ["rewatch_start_rate"] += 1 if trace.rewatch_started else 0

            denom["rewatch_completion_rate"] += 1 if trace.rewatch_started else 0
            succ["rewatch_completion_rate"] += 1 if trace.rewatch_completed else 0

            denom["theory_start_rate"] += 1 if is_activated else 0
            succ["theory_start_rate"] += 1 if trace.theory_started else 0

            denom["theory_completion_rate"] += 1 if trace.theory_started else 0
            succ["theory_completion_rate"] += 1 if trace.theory_completed else 0

            denom["community_read_rate"] += 1 if is_activated else 0
            succ["community_read_rate"] += 1 if "COMMUNITY_READ" in visited_set else 0

            denom["community_contribution_rate"] += 1 if "COMMUNITY_READ" in visited_set else 0
            succ["community_contribution_rate"] += 1 if is_creator else 0

            denom["comment_rate"] += 1 if "COMMUNITY_READ" in visited_set else 0
            succ["comment_rate"] += 1 if trace.comment_created else 0

            denom["counterclaim_rate"] += 1 if "COMMUNITY_READ" in visited_set else 0
            succ["counterclaim_rate"] += 1 if trace.counterclaim_created else 0

            denom["magazine_read_rate"] += 1 if is_activated else 0
            succ["magazine_read_rate"] += 1 if trace.magazine_article_read else 0

            denom["golden_path_completion_rate"] += 1
            succ["golden_path_completion_rate"] += 1 if is_full_gp else 0

            denom["core_value_activation_rate"] += 1
            succ["core_value_activation_rate"] += 1 if is_activated else 0

            denom["downstream_engagement_rate"] += 1
            succ["downstream_engagement_rate"] += 1 if is_downstream else 0

            denom["creator_conversion_rate"] += 1
            succ["creator_conversion_rate"] += 1 if is_creator else 0

            denom["return_intent_proxy"] += 1
            succ["return_intent_proxy"] += 1 if trace.return_intent_score > 0.5 else 0

        # 7. Cohort Tracking (Recorded EXACTLY ONCE per session)
        cohort_slices = self._extract_cohort_slices(profile)
        for slice_dim, cohort_key in cohort_slices.items():
            self.cohort_sessions[slice_dim][cohort_key] += 1
            self.cohort_weighted_sessions[slice_dim][cohort_key] += weight

            if is_full_gp:
                self.cohort_actions[slice_dim][cohort_key]["golden_path_completed"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["golden_path_completed"] += weight
            if is_activated:
                self.cohort_actions[slice_dim][cohort_key]["deep_reframe_read"] += 1
                self.cohort_actions[slice_dim][cohort_key]["deep_reframe_entry"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["deep_reframe_read"] += weight
                self.cohort_weighted_actions[slice_dim][cohort_key]["deep_reframe_entry"] += weight
            if trace.deep_reframe_completed:
                self.cohort_actions[slice_dim][cohort_key]["deep_reframe_completion"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["deep_reframe_completion"] += weight
            if trace.rewatch_started:
                self.cohort_actions[slice_dim][cohort_key]["rewatch_started"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["rewatch_started"] += weight
            if trace.rewatch_completed:
                self.cohort_actions[slice_dim][cohort_key]["rewatch_completion"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["rewatch_completion"] += weight
            if trace.theory_completed:
                self.cohort_actions[slice_dim][cohort_key]["theory_completed"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["theory_completed"] += weight
            if is_creator:
                self.cohort_actions[slice_dim][cohort_key]["community_contribution"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["community_contribution"] += weight
            if trace.magazine_article_read:
                self.cohort_actions[slice_dim][cohort_key]["magazine_article_read"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["magazine_article_read"] += weight
            if trace.return_intent_score > 0.5:
                self.cohort_actions[slice_dim][cohort_key]["return_intent"] += 1
                self.cohort_weighted_actions[slice_dim][cohort_key]["return_intent"] += weight

    def _extract_cohort_slices(self, profile: DerivedPersonaProfile) -> Dict[str, str]:
        slices = {
            "age_band": profile.age_band,
            "census_region": profile.census_region,
            "location_context": profile.location_context,
            "education_group": profile.education_group,
            "occupation_group": profile.occupation_group,
            "state": profile.state,
        }
        if profile.traits:
            slices["fan_depth"] = profile.traits.fan_depth.value
            slices["reading_patience_band"] = "HIGH" if profile.traits.reading_patience > 0.66 else ("MED" if profile.traits.reading_patience > 0.33 else "LOW")
            slices["digital_comfort_band"] = "HIGH" if profile.traits.digital_comfort > 0.66 else ("MED" if profile.traits.digital_comfort > 0.33 else "LOW")
            slices["ai_trust_band"] = "HIGH" if profile.traits.trust_in_ai_analysis > 0.66 else ("MED" if profile.traits.trust_in_ai_analysis > 0.33 else "LOW")
            slices["rewatch_affinity_band"] = "HIGH" if profile.traits.rewatch_affinity > 0.66 else ("MED" if profile.traits.rewatch_affinity > 0.33 else "LOW")
        return slices
