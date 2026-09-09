"""
Reframe V7 Metrics Computation
Calculates exact funnel conversions, conditional denominators, cohort slices, and duration percentiles.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import numpy as np
from typing import Dict, List, Tuple
from src.reframe.simulation.schemas import (
    FunnelMetrics,
    CohortSummary,
    MetricDetail,
)
from src.reframe.simulation.aggregators import OnlineMetricsAggregator


def compute_funnel_metrics(agg: OnlineMetricsAggregator) -> FunnelMetrics:
    total = max(1, agg.total_sessions)
    n_landing = agg.state_entries.get("LANDING", total)
    n_film_hub = agg.state_entries.get("FILM_HUB", 0)
    n_spoiler_gate = agg.state_entries.get("SPOILER_GATE", 0)
    n_reveal = agg.state_entries.get("REVEAL", 0)
    n_deep_reframe = agg.state_entries.get("DEEP_REFRAME", 0)
    n_deep_reframe_comp = agg.actions_count.get("deep_reframe_completed", n_deep_reframe)
    n_rewatch = agg.actions_count.get("rewatch_started", 0)
    n_rewatch_comp = agg.actions_count.get("rewatch_completed", 0)
    n_theory_start = agg.actions_count.get("theory_started", 0)
    n_theory_comp = agg.actions_count.get("theory_completed", 0)
    n_comm_read = agg.state_entries.get("COMMUNITY_READ", 0)
    n_post = agg.actions_count.get("post_created", 0)
    n_comment = agg.actions_count.get("comment_created", 0)
    n_counterclaim = agg.actions_count.get("counterclaim_created", 0)
    n_comm_contrib = agg.actions_count.get("creator_converted", n_post + n_comment + n_counterclaim)
    n_mag_read = agg.actions_count.get("magazine_article_read", 0)
    n_return = agg.actions_count.get("high_return_intent", 0)
    n_core_val = agg.actions_count.get("core_value_activated", 0)
    n_downstream = agg.actions_count.get("downstream_engaged", 0)
    n_creator = agg.actions_count.get("creator_converted", 0)
    n_gp_comp = agg.actions_count.get("golden_path_completed", 0)
    n_error = agg.dropoff_counts.get("ERROR", 0)

    # Durations p50 / p95
    if agg.durations_reservoir:
        arr = np.array(agg.durations_reservoir)
        p50_duration = float(np.percentile(arr, 50))
        p95_duration = float(np.percentile(arr, 95))
    else:
        p50_duration = 45.0
        p95_duration = 180.0

    ttfv = (agg.ttfv_sum / agg.ttfv_count) if agg.ttfv_count > 0 else 18.0

    # Rate calculations helper
    def safe_rate(num: int, den: int) -> float:
        if den <= 0:
            return 0.0
        return round(min(1.0, max(0.0, num / den)), 4)

    landing_to_film_hub_rate = safe_rate(n_film_hub, n_landing)
    film_hub_to_reveal_rate = safe_rate(n_reveal, n_film_hub)
    film_hub_to_spoiler_gate_rate = safe_rate(n_spoiler_gate, n_film_hub)
    spoiler_gate_to_reveal_rate = safe_rate(n_reveal, n_spoiler_gate)
    spoiler_gate_completion_rate = safe_rate(n_reveal, n_spoiler_gate)
    reveal_to_deep_reframe_rate = safe_rate(n_deep_reframe, n_reveal)
    deep_reframe_entry_rate = safe_rate(n_deep_reframe, n_reveal)
    deep_reframe_completion_rate = safe_rate(n_deep_reframe_comp, n_deep_reframe)
    rewatch_start_rate = safe_rate(n_rewatch, n_deep_reframe)
    rewatch_completion_rate = safe_rate(n_rewatch_comp, n_rewatch)
    theory_start_rate = safe_rate(n_theory_start, n_deep_reframe)
    theory_completion_rate = safe_rate(n_theory_comp, n_theory_start)
    community_read_rate = safe_rate(n_comm_read, n_deep_reframe)
    community_contribution_rate = safe_rate(n_comm_contrib, n_comm_read)
    comment_rate = safe_rate(n_comment, n_comm_read)
    counterclaim_rate = safe_rate(n_counterclaim, n_comm_read)
    magazine_read_rate = safe_rate(n_mag_read, n_deep_reframe)
    return_intent_proxy = safe_rate(n_return, total)
    core_value_activation_rate = safe_rate(n_core_val, total)
    downstream_engagement_rate = safe_rate(n_downstream, total)
    creator_conversion_rate = safe_rate(n_creator, total)
    golden_path_completion_rate = safe_rate(n_gp_comp, total)
    moderation_candidate_rate = round(max(0.001, min(1.0, (n_comment * 0.02 + n_counterclaim * 0.03) / total)), 4)
    error_abandonment_rate = safe_rate(n_error, total)

    metric_details = {
        "landing_to_film_hub": MetricDetail(metric_name="landing_to_film_hub", numerator=n_film_hub, denominator=n_landing, rate=landing_to_film_hub_rate),
        "film_hub_to_spoiler_gate": MetricDetail(metric_name="film_hub_to_spoiler_gate", numerator=n_spoiler_gate, denominator=n_film_hub, rate=film_hub_to_spoiler_gate_rate),
        "spoiler_gate_to_reveal": MetricDetail(metric_name="spoiler_gate_to_reveal", numerator=n_reveal, denominator=n_spoiler_gate, rate=spoiler_gate_to_reveal_rate),
        "reveal_to_deep_reframe": MetricDetail(metric_name="reveal_to_deep_reframe", numerator=n_deep_reframe, denominator=n_reveal, rate=reveal_to_deep_reframe_rate),
        "deep_reframe_entry": MetricDetail(metric_name="deep_reframe_entry", numerator=n_deep_reframe, denominator=n_reveal, rate=deep_reframe_entry_rate),
        "deep_reframe_completion": MetricDetail(metric_name="deep_reframe_completion", numerator=n_deep_reframe_comp, denominator=n_deep_reframe, rate=deep_reframe_completion_rate),
        "rewatch_start": MetricDetail(metric_name="rewatch_start", numerator=n_rewatch, denominator=n_deep_reframe, rate=rewatch_start_rate),
        "rewatch_completion": MetricDetail(metric_name="rewatch_completion", numerator=n_rewatch_comp, denominator=n_rewatch, rate=rewatch_completion_rate),
        "theory_start": MetricDetail(metric_name="theory_start", numerator=n_theory_start, denominator=n_deep_reframe, rate=theory_start_rate),
        "theory_completion": MetricDetail(metric_name="theory_completion", numerator=n_theory_comp, denominator=n_theory_start, rate=theory_completion_rate),
        "community_read": MetricDetail(metric_name="community_read", numerator=n_comm_read, denominator=n_deep_reframe, rate=community_read_rate),
        "community_contribution": MetricDetail(metric_name="community_contribution", numerator=n_comm_contrib, denominator=n_comm_read, rate=community_contribution_rate),
        "magazine_read": MetricDetail(metric_name="magazine_read", numerator=n_mag_read, denominator=n_deep_reframe, rate=magazine_read_rate),
        "full_golden_path": MetricDetail(metric_name="full_golden_path", numerator=n_gp_comp, denominator=total, rate=golden_path_completion_rate),
    }

    denominators = {
        "total_sessions": total,
        "landing_sessions": n_landing,
        "film_hub_sessions": n_film_hub,
        "spoiler_gate_sessions": n_spoiler_gate,
        "reveal_sessions": n_reveal,
        "deep_reframe_sessions": n_deep_reframe,
        "rewatch_started_sessions": n_rewatch,
        "theory_started_sessions": n_theory_start,
        "community_read_sessions": n_comm_read,
    }

    return FunnelMetrics(
        landing_to_film_hub_rate=landing_to_film_hub_rate,
        film_hub_to_reveal_rate=film_hub_to_reveal_rate,
        film_hub_to_spoiler_gate_rate=film_hub_to_spoiler_gate_rate,
        spoiler_gate_to_reveal_rate=spoiler_gate_to_reveal_rate,
        spoiler_gate_completion_rate=spoiler_gate_completion_rate,
        reveal_to_deep_reframe_rate=reveal_to_deep_reframe_rate,
        deep_reframe_entry_rate=deep_reframe_entry_rate,
        deep_reframe_completion_rate=deep_reframe_completion_rate,
        deep_reframe_read_rate=deep_reframe_entry_rate,  # Maintained as entry rate alias
        rewatch_start_rate=rewatch_start_rate,
        rewatch_completion_rate=rewatch_completion_rate,
        theory_start_rate=theory_start_rate,
        theory_completion_rate=theory_completion_rate,
        community_read_rate=community_read_rate,
        community_contribution_rate=community_contribution_rate,
        comment_rate=comment_rate,
        counterclaim_rate=counterclaim_rate,
        magazine_read_rate=magazine_read_rate,
        return_intent_proxy=return_intent_proxy,
        core_value_activation_rate=core_value_activation_rate,
        downstream_engagement_rate=downstream_engagement_rate,
        creator_conversion_rate=creator_conversion_rate,
        full_golden_path_rate=golden_path_completion_rate,
        golden_path_completion_rate=golden_path_completion_rate,
        time_to_first_value_sec=round(ttfv, 2),
        p50_session_duration_sec=round(p50_duration, 2),
        p95_session_duration_sec=round(p95_duration, 2),
        moderation_candidate_rate=moderation_candidate_rate,
        error_abandonment_rate=error_abandonment_rate,
        metric_details=metric_details,
        denominators=denominators,
        dropoff_counts_by_reason=dict(agg.dropoff_counts),
        state_entry_counts=dict(agg.state_entries),
    )


def compute_cohort_summaries(
    agg: OnlineMetricsAggregator
) -> Tuple[List[CohortSummary], List[CohortSummary]]:
    """
    Returns (balanced_eval_cohorts, source_weighted_cohorts).
    """
    balanced_list: List[CohortSummary] = []
    weighted_list: List[CohortSummary] = []
    total_unweighted = max(1, agg.total_sessions)
    total_weighted = max(0.001, sum(sum(v.values()) for v in agg.cohort_weighted_sessions.values()) / max(1, len(agg.cohort_weighted_sessions)))

    for slice_dim, cohorts in agg.cohort_sessions.items():
        for cohort_key, count in sorted(cohorts.items()):
            actions = agg.cohort_actions[slice_dim][cohort_key]
            unweighted_share = count / total_unweighted

            n_dr_entry = actions.get("deep_reframe_entry", 0)
            n_dr_comp = actions.get("deep_reframe_completion", 0)
            n_rew_start = actions.get("rewatch_started", 0)
            n_rew_comp = actions.get("rewatch_completion", 0)

            dr_entry_rate = round(n_dr_entry / max(1, count), 4)
            dr_comp_rate = round(n_dr_comp / max(1, n_dr_entry), 4) if n_dr_entry > 0 else 0.0
            rew_comp_rate = round(n_rew_comp / max(1, n_rew_start), 4) if n_rew_start > 0 else 0.0

            balanced_list.append(CohortSummary(
                slice_dimension=slice_dim,
                cohort_key=cohort_key,
                session_count=count,
                unweighted_share=round(unweighted_share, 4),
                weighted_share=round(unweighted_share, 4),
                golden_path_completion_rate=round(actions.get("golden_path_completed", 0) / max(1, count), 4),
                deep_reframe_read_rate=dr_entry_rate,
                deep_reframe_entry_rate=dr_entry_rate,
                deep_reframe_completion_rate=dr_comp_rate,
                rewatch_start_rate=round(n_rew_start / max(1, count), 4),
                rewatch_completion_rate=rew_comp_rate,
                theory_completion_rate=round(actions.get("theory_completed", 0) / max(1, count), 4),
                community_contribution_rate=round(actions.get("community_contribution", 0) / max(1, count), 4),
                magazine_read_rate=round(actions.get("magazine_article_read", 0) / max(1, count), 4),
                return_intent_proxy=round(actions.get("return_intent", 0) / max(1, count), 4),
            ))

            w_count = agg.cohort_weighted_sessions[slice_dim][cohort_key]
            w_actions = agg.cohort_weighted_actions[slice_dim][cohort_key]
            w_share = w_count / max(0.001, total_weighted)

            w_dr_entry = w_actions.get("deep_reframe_entry", 0.0)
            w_dr_comp = w_actions.get("deep_reframe_completion", 0.0)
            w_rew_start = w_actions.get("rewatch_started", 0.0)
            w_rew_comp = w_actions.get("rewatch_completion", 0.0)

            w_dr_entry_rate = round(w_dr_entry / max(0.001, w_count), 4)
            w_dr_comp_rate = round(w_dr_comp / max(0.001, w_dr_entry), 4) if w_dr_entry > 0 else 0.0
            w_rew_comp_rate = round(w_rew_comp / max(0.001, w_rew_start), 4) if w_rew_start > 0 else 0.0

            weighted_list.append(CohortSummary(
                slice_dimension=slice_dim,
                cohort_key=cohort_key,
                session_count=count,
                unweighted_share=round(unweighted_share, 4),
                weighted_share=round(w_share, 4),
                golden_path_completion_rate=round(w_actions.get("golden_path_completed", 0.0) / max(0.001, w_count), 4),
                deep_reframe_read_rate=w_dr_entry_rate,
                deep_reframe_entry_rate=w_dr_entry_rate,
                deep_reframe_completion_rate=w_dr_comp_rate,
                rewatch_start_rate=round(w_rew_start / max(0.001, w_count), 4),
                rewatch_completion_rate=w_rew_comp_rate,
                theory_completion_rate=round(w_actions.get("theory_completed", 0.0) / max(0.001, w_count), 4),
                community_contribution_rate=round(w_actions.get("community_contribution", 0.0) / max(0.001, w_count), 4),
                magazine_read_rate=round(w_actions.get("magazine_article_read", 0.0) / max(0.001, w_count), 4),
                return_intent_proxy=round(w_actions.get("return_intent", 0.0) / max(0.001, w_count), 4),
            ))

    return balanced_list, weighted_list
