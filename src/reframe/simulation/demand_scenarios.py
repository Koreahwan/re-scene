"""
Reframe V7 Directional Demand Scenarios
Assumption-based directional modeling combining external visitor assumptions with simulated conversion rates.
Zero External Generative Model Calls.
"""
from __future__ import annotations
from typing import Dict, Any
from src.reframe.simulation.schemas import (
    DirectionalDemandInput,
    DirectionalDemandResult,
    FunnelMetrics,
)


def evaluate_directional_demand(
    demand_input: DirectionalDemandInput,
    metrics: FunnelMetrics,
    source_run_id: Optional[str] = None,
    source_policy_version: str = "reframe_us_audience_policy_v1",
    source_scenario: str = "CURRENT_BASELINE",
) -> DirectionalDemandResult:
    """
    Evaluates monthly feature volumes and server workload based on explicit external traffic assumptions.
    Strict Invariant: real_user_forecast is False.
    """
    v = demand_input.monthly_visitors
    gp_rate = metrics.golden_path_completion_rate
    rewatch_rate = metrics.rewatch_start_rate
    theory_rate = metrics.theory_completion_rate * metrics.theory_start_rate
    comm_rate = metrics.community_contribution_rate
    mag_rate = metrics.magazine_read_rate

    # Min / Expected / Max ranges (±20% variance)
    gp_exp = int(v * gp_rate)
    rewatch_exp = int(v * rewatch_rate)
    theory_exp = int(v * theory_rate)
    comm_exp = int(v * comm_rate)
    mag_exp = int(v * mag_rate)

    # Workload items
    mod_items = int(comm_exp * metrics.moderation_candidate_rate * 1.5)

    # API Request Volume estimated
    req_exp = int(v * 16.5)

    return DirectionalDemandResult(
        forecast_class="ASSUMPTION_BASED_DIRECTIONAL",
        real_user_forecast=False,
        source_run_id=source_run_id or (str(demand_input.simulation_run_id) if demand_input.simulation_run_id else None),
        source_policy_version=source_policy_version,
        source_scenario=source_scenario,
        disclaimer=(
            "This directional demand scenario is strictly assumption-based and derived from external visitor assumptions "
            "combined with synthetic behavior conversion rates. It is not an empirical real-user forecast or market validation."
        ),
        monthly_visitors=v,
        monthly_golden_path_completions={
            "min": int(gp_exp * 0.8),
            "expected": gp_exp,
            "max": int(gp_exp * 1.2),
        },
        monthly_rewatch_sessions={
            "min": int(rewatch_exp * 0.75),
            "expected": rewatch_exp,
            "max": int(rewatch_exp * 1.25),
        },
        monthly_theories_created={
            "min": int(theory_exp * 0.7),
            "expected": theory_exp,
            "max": int(theory_exp * 1.3),
        },
        monthly_community_contributions={
            "min": int(comm_exp * 0.7),
            "expected": comm_exp,
            "max": int(comm_exp * 1.3),
        },
        monthly_magazine_reads={
            "min": int(mag_exp * 0.8),
            "expected": mag_exp,
            "max": int(mag_exp * 1.2),
        },
        expected_synthetic_moderation_workload_items={
            "min": max(1, int(mod_items * 0.6)),
            "expected": max(1, mod_items),
            "max": max(2, int(mod_items * 1.5)),
        },
        request_volume_monthly={
            "min": int(req_exp * 0.8),
            "expected": req_exp,
            "max": int(req_exp * 1.2),
        },
    )

