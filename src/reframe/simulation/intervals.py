"""
Reframe V7 Simulation Interval Estimator
Calculates cluster-aware Monte Carlo simulation intervals using real Poisson persona-cluster bootstrap
or explicit design effect approximation in bounded memory batches.
Strict Invariant: No artificial post-hoc clamping.
Strict Disclosure: Labeled SIMULATION_INTERVAL only.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import math
import numpy as np
from typing import Dict, Optional, Tuple, List, Any
from src.reframe.simulation.schemas import SimulationInterval, FunnelMetrics
from src.reframe.simulation.aggregators import OnlineMetricsAggregator


def compute_persona_cluster_bootstrap(
    agg: OnlineMetricsAggregator,
    bootstrap_replications: int = 500,
    bootstrap_seed: int = 42,
    confidence_level: float = 0.95,
    max_subsample_clusters: int = 10000,
    batch_size: int = 100,
) -> Tuple[Dict[str, Tuple[float, float, float]], str, int, str]:
    """
    Deterministic Poisson persona-cluster bootstrap executed in bounded memory batches:
    1. Extract success/denominator counts by source persona cluster.
    2. Resample clusters using Poisson(1.0) cluster weights in batches of batch_size.
    3. Aggregate replicate numerator and denominator sums across clusters.
    4. Compute replicate rates and extract empirical quantiles without post-hoc clamping.
    5. Returns (results_dict, interval_method, cluster_sample_size, bootstrap_scheme).
    """
    persona_ids = list(agg.persona_cluster_successes.keys())
    n_personas = len(persona_ids)
    if n_personas == 0 or not agg.persona_cluster_successes:
        return {}, "DESIGN_EFFECT_APPROXIMATION", 0, "DESIGN_EFFECT"

    alpha = 1.0 - confidence_level
    lower_pct = (alpha / 2.0) * 100.0
    upper_pct = (1.0 - alpha / 2.0) * 100.0

    first_pid = persona_ids[0]
    metric_names = list(agg.persona_cluster_successes[first_pid].keys())
    n_metrics = len(metric_names)

    # Pre-extract integer arrays for vectorized cluster resampling
    succ_matrix = np.zeros((n_personas, n_metrics), dtype=np.float32)
    denom_matrix = np.zeros((n_personas, n_metrics), dtype=np.float32)

    for p_idx, pid in enumerate(persona_ids):
        for m_idx, m_name in enumerate(metric_names):
            succ_matrix[p_idx, m_idx] = agg.persona_cluster_successes[pid].get(m_name, 0)
            denom_matrix[p_idx, m_idx] = agg.persona_cluster_denominators[pid].get(m_name, 0)

    # Deterministic RNG
    rng = np.random.RandomState(bootstrap_seed)

    # Subsampling selection if persona universe is very large
    if n_personas > max_subsample_clusters:
        sub_indices = rng.choice(n_personas, size=max_subsample_clusters, replace=False)
        sub_succ = succ_matrix[sub_indices]
        sub_denom = denom_matrix[sub_indices]
        n_clusters = max_subsample_clusters
        interval_method = "SUBSAMPLED_POISSON_PERSONA_CLUSTER_BOOTSTRAP"
        cluster_sample_size = max_subsample_clusters
    else:
        sub_succ = succ_matrix
        sub_denom = denom_matrix
        n_clusters = n_personas
        interval_method = "POISSON_PERSONA_CLUSTER_BOOTSTRAP"
        cluster_sample_size = n_personas

    bootstrap_scheme = "POISSON_CLUSTER_RESAMPLING"

    # Compute population point estimates from the cluster sample
    total_sample_succ = np.sum(sub_succ, axis=0)
    total_sample_denom = np.sum(sub_denom, axis=0)
    sample_pt_estimates = np.where(total_sample_denom > 0, total_sample_succ / np.maximum(1.0, total_sample_denom), 0.0)

    # Execute Poisson cluster resampling in bounded batches to avoid large array allocations
    all_replicate_rates: List[np.ndarray] = []
    reps_remaining = bootstrap_replications

    while reps_remaining > 0:
        current_batch = min(batch_size, reps_remaining)
        # Bounded weight allocation: current_batch x n_clusters
        weights = rng.poisson(lam=1.0, size=(current_batch, n_clusters)).astype(np.float32)
        batch_succ = weights @ sub_succ
        batch_denom = weights @ sub_denom
        batch_rates = np.where(batch_denom > 0, batch_succ / np.maximum(1.0, batch_denom), sample_pt_estimates)
        all_replicate_rates.append(batch_rates)
        reps_remaining -= current_batch

    replicate_rates = np.vstack(all_replicate_rates)

    results: Dict[str, Tuple[float, float, float]] = {}
    for m_idx, m_name in enumerate(metric_names):
        rates = replicate_rates[:, m_idx]
        pt = float(sample_pt_estimates[m_idx])
        low = float(np.percentile(rates, lower_pct))
        high = float(np.percentile(rates, upper_pct))
        # Valid natural bounds within [0, 1] without artificial clamping against point estimate
        natural_low = round(max(0.0, min(1.0, low)), 4)
        natural_high = round(max(0.0, min(1.0, high)), 4)
        results[m_name] = (round(pt, 4), natural_low, natural_high)

    return results, interval_method, cluster_sample_size, bootstrap_scheme


def calculate_simulation_intervals(
    metrics: FunnelMetrics,
    total_sessions: int,
    agg: Optional[OnlineMetricsAggregator] = None,
    effective_unit: str = "SOURCE_PERSONA",
    confidence_level: float = 0.95,
    interval_method: str = "POISSON_PERSONA_CLUSTER_BOOTSTRAP",
    bootstrap_replications: int = 500,
    bootstrap_seed: int = 42,
) -> Dict[str, SimulationInterval]:
    """
    Computes cluster-aware simulation intervals for primary conversion rates.
    Uses Poisson persona-cluster bootstrap or documented design effect approximation.
    Explicitly labeled SIMULATION_INTERVAL with mandatory synthetic disclaimer.
    """
    intervals: Dict[str, SimulationInterval] = {}
    disclaimer = (
        "The interval describes variability under the configured synthetic behavior model "
        "and does not estimate sampling uncertainty among actual Reframe users."
    )

    if interval_method in ("POISSON_PERSONA_CLUSTER_BOOTSTRAP", "SUBSAMPLED_POISSON_PERSONA_CLUSTER_BOOTSTRAP", "PERSONA_CLUSTER_BOOTSTRAP", "SUBSAMPLED_PERSONA_CLUSTER_BOOTSTRAP") and agg and agg.persona_cluster_successes:
        boot_res, resolved_method, cluster_size, scheme = compute_persona_cluster_bootstrap(
            agg=agg,
            bootstrap_replications=bootstrap_replications,
            bootstrap_seed=bootstrap_seed,
            confidence_level=confidence_level,
        )
        if boot_res:
            for name, (boot_pt, low, high) in boot_res.items():
                orig_rate = getattr(metrics, name, boot_pt)
                pt = round(float(orig_rate), 4)

                intervals[name] = SimulationInterval(
                    metric_name=name,
                    point_estimate=pt,
                    lower_bound=low,
                    upper_bound=high,
                    confidence_level=confidence_level,
                    effective_unit=effective_unit,
                    interval_method=resolved_method,
                    cluster_sample_size=cluster_size,
                    bootstrap_scheme=scheme,
                    bootstrap_replications=bootstrap_replications,
                    bootstrap_seed=bootstrap_seed,
                    label="SIMULATION_INTERVAL",
                    disclaimer=disclaimer,
                )
            return intervals

    # Fallback to explicit DESIGN_EFFECT_APPROXIMATION
    z = 1.96 if confidence_level >= 0.95 else 1.645
    if agg and agg.persona_session_counts:
        n_clusters = max(1, len(agg.persona_session_counts))
        avg_cluster_size = total_sessions / n_clusters
        icc = 0.08
        deff = max(1.0, 1.0 + (avg_cluster_size - 1.0) * icc)
    else:
        deff = 1.0

    rate_names = [
        ("landing_to_film_hub_rate", metrics.landing_to_film_hub_rate, metrics.denominators.get("landing_sessions", total_sessions)),
        ("film_hub_to_reveal_rate", metrics.film_hub_to_reveal_rate, metrics.denominators.get("film_hub_sessions", total_sessions)),
        ("spoiler_gate_completion_rate", metrics.spoiler_gate_completion_rate, metrics.denominators.get("spoiler_gate_sessions", total_sessions)),
        ("reveal_to_deep_reframe_rate", metrics.reveal_to_deep_reframe_rate, metrics.denominators.get("reveal_sessions", total_sessions)),
        ("deep_reframe_entry_rate", metrics.deep_reframe_entry_rate, metrics.denominators.get("reveal_sessions", total_sessions)),
        ("deep_reframe_completion_rate", metrics.deep_reframe_completion_rate, metrics.denominators.get("deep_reframe_sessions", total_sessions)),
        ("deep_reframe_read_rate", metrics.deep_reframe_read_rate, metrics.denominators.get("reveal_sessions", total_sessions)),
        ("rewatch_start_rate", metrics.rewatch_start_rate, metrics.denominators.get("deep_reframe_sessions", total_sessions)),
        ("rewatch_completion_rate", metrics.rewatch_completion_rate, metrics.denominators.get("rewatch_started_sessions", total_sessions)),
        ("theory_start_rate", metrics.theory_start_rate, metrics.denominators.get("deep_reframe_sessions", total_sessions)),
        ("theory_completion_rate", metrics.theory_completion_rate, metrics.denominators.get("theory_started_sessions", total_sessions)),
        ("community_read_rate", metrics.community_read_rate, metrics.denominators.get("deep_reframe_sessions", total_sessions)),
        ("community_contribution_rate", metrics.community_contribution_rate, metrics.denominators.get("community_read_sessions", total_sessions)),
        ("magazine_read_rate", metrics.magazine_read_rate, metrics.denominators.get("deep_reframe_sessions", total_sessions)),
        ("golden_path_completion_rate", metrics.golden_path_completion_rate, total_sessions),
        ("core_value_activation_rate", metrics.core_value_activation_rate, total_sessions),
        ("downstream_engagement_rate", metrics.downstream_engagement_rate, total_sessions),
        ("creator_conversion_rate", metrics.creator_conversion_rate, total_sessions),
        ("return_intent_proxy", metrics.return_intent_proxy, total_sessions),
    ]

    for name, p, denom in rate_names:
        n_effective = max(1, denom / deff)
        se = math.sqrt(max(0.0, (p * (1.0 - p)) / n_effective))
        margin = z * se
        low = round(max(0.0, p - margin), 4)
        high = round(min(1.0, p + margin), 4)

        intervals[name] = SimulationInterval(
            metric_name=name,
            point_estimate=round(p, 4),
            lower_bound=low,
            upper_bound=high,
            confidence_level=confidence_level,
            effective_unit=effective_unit,
            interval_method="DESIGN_EFFECT_APPROXIMATION",
            cluster_sample_size=len(agg.persona_session_counts) if agg else 0,
            bootstrap_scheme="DESIGN_EFFECT",
            bootstrap_replications=0,
            bootstrap_seed=bootstrap_seed,
            label="SIMULATION_INTERVAL",
            disclaimer=disclaimer,
        )

    return intervals
