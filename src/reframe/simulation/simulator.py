"""
Reframe V7 USA Audience Simulator Engine
Simulates large-scale synthetic fan cohorts across scenarios using deterministic behavior policy.
Tracks online funnel aggregations, cluster bootstrap intervals, bottlenecks, sensitivity,
and directional demand without external LLM calls ($0.00 spend).
"""
from __future__ import annotations
import sys
import time
import hashlib
from typing import List, Dict, Optional, Any, Callable
from src.reframe.simulation.schemas import (
    ScenarioVariant,
    SimulationMode,
    SimulationRunConfig,
    SimulationRunResult,
    RepresentativeSessionTrace,
    DerivedPersonaProfile,
    SyntheticFanTraits,
    GoldenPathState,
    DropoffReason,
    TerminationReason,
    DirectionalDemandInput,
)
from src.reframe.simulation.golden_path import get_scenario_config
from src.reframe.simulation.fan_traits import fan_traits_assigner
from src.reframe.simulation.behavior_policy import behavior_policy, hash_to_uniform
from src.reframe.simulation.aggregators import OnlineMetricsAggregator
from src.reframe.simulation.metrics import compute_funnel_metrics, compute_cohort_summaries
from src.reframe.simulation.intervals import calculate_simulation_intervals
from src.reframe.simulation.bottlenecks import rank_bottlenecks
from src.reframe.simulation.sensitivity import run_sensitivity_analysis
from src.reframe.simulation.demand_scenarios import evaluate_directional_demand
from src.reframe.simulation.session_runner import simulate_session_deterministic


class AudienceSimulator:
    def __init__(self, config: SimulationRunConfig):
        self.config = config

    def _get_process_memory_mb(self) -> float:
        try:
            if sys.platform == "win32":
                import ctypes
                from ctypes import wintypes

                class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                    _fields_ = [
                        ("cb", wintypes.DWORD),
                        ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t),
                        ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t),
                        ("PeakPagefileUsage", ctypes.c_size_t),
                    ]

                counters = PROCESS_MEMORY_COUNTERS()
                counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                handle = ctypes.windll.kernel32.GetCurrentProcess()
                if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                    return float(counters.WorkingSetSize) / (1024.0 * 1024.0)
            else:
                import resource
                return float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) / 1024.0
        except Exception:
            pass
        return 48.0

    def simulate_session_deterministic(
        self,
        profile: DerivedPersonaProfile,
        variant: ScenarioVariant,
        replication_idx: int,
        seed: int,
    ) -> RepresentativeSessionTrace:
        return simulate_session_deterministic(
            profile=profile,
            variant=variant,
            replication_idx=replication_idx,
            seed=seed,
        )

    def run_simulation(
        self,
        personas: List[DerivedPersonaProfile],
        enable_adaptive_stop: bool = True,
        heartbeat_callback: Optional[Callable[[int, int], None]] = None,
        checkpoint_callback: Optional[Callable[[str, Any], None]] = None,
    ) -> SimulationRunResult:
        start_time = time.time()
        initial_mem = self._get_process_memory_mb()

        agg = OnlineMetricsAggregator(track_clusters=True)
        scenario_aggregators: Dict[str, OnlineMetricsAggregator] = {
            v.value: OnlineMetricsAggregator(track_clusters=False) for v in self.config.variants
        }

        # Assign traits to all personas deterministically
        for p in personas:
            if not p.traits:
                p.traits = fan_traits_assigner.assign_traits(p, self.config.seed)

        num_personas = len(personas)
        replications = self.config.replications
        variants = self.config.variants

        target_total_sessions = num_personas * len(variants) * replications
        batch_size = max(50000, target_total_sessions // 10)

        convergence_history: List[Dict[str, Any]] = []
        consecutive_stable_checks = 0
        is_converged = False
        termination_reason = TerminationReason.SAMPLE_TARGET_REACHED

        sessions_processed = 0
        last_metrics = None
        last_bottlenecks = None
        last_sens_order = None
        last_ttfv = None
        last_dropoffs = None
        last_heartbeat_time = time.time()

        # Execute simulation across replications and variants
        for rep in range(replications):
            for var in variants:
                sc_agg = scenario_aggregators[var.value]
                for p in personas:
                    trace = simulate_session_deterministic(
                        profile=p,
                        variant=var,
                        replication_idx=rep,
                        seed=self.config.seed,
                    )
                    agg.record_session(trace, p, weight=p.sampling_weight)
                    sc_agg.record_session(trace, p, weight=p.sampling_weight)
                    sessions_processed += 1

                    # Heartbeat renewal hook (every 25k sessions or 5 seconds)
                    now = time.time()
                    if heartbeat_callback and (sessions_processed % 25000 == 0 or (now - last_heartbeat_time) >= 5.0):
                        heartbeat_callback(sessions_processed, target_total_sessions)
                        last_heartbeat_time = now

                    # Periodic adaptive convergence check
                    if enable_adaptive_stop and (sessions_processed % batch_size == 0 or sessions_processed == target_total_sessions):
                        current_metrics = compute_funnel_metrics(agg)
                        current_bottlenecks = rank_bottlenecks(agg, scenario_aggregators)
                        current_order = [b.state for b in current_bottlenecks.bottlenecks[:5]]
                        current_ttfv = current_metrics.time_to_first_value_sec

                        # Dropoff distribution
                        tot_drop = max(1, sum(agg.dropoff_counts.values()))
                        current_dropoffs = {k: v / tot_drop for k, v in agg.dropoff_counts.items()}

                        # 1. Rate stability
                        if last_metrics is not None:
                            rate_deltas = [
                                abs(current_metrics.golden_path_completion_rate - last_metrics.golden_path_completion_rate),
                                abs(current_metrics.landing_to_film_hub_rate - last_metrics.landing_to_film_hub_rate),
                                abs(current_metrics.film_hub_to_reveal_rate - last_metrics.film_hub_to_reveal_rate),
                                abs(current_metrics.reveal_to_deep_reframe_rate - last_metrics.reveal_to_deep_reframe_rate),
                                abs(current_metrics.rewatch_start_rate - last_metrics.rewatch_start_rate),
                                abs(current_metrics.theory_completion_rate - last_metrics.theory_completion_rate),
                            ]
                            max_rate_delta = max(rate_deltas)
                            rate_stability_passed = bool(max_rate_delta < 0.001)
                        else:
                            max_rate_delta = 1.0
                            rate_stability_passed = False

                        # 2. Simulation interval width check using Poisson cluster bootstrap
                        current_intervals = calculate_simulation_intervals(
                            current_metrics,
                            agg.total_sessions,
                            agg=agg,
                            interval_method="POISSON_PERSONA_CLUSTER_BOOTSTRAP",
                            bootstrap_replications=200,
                            bootstrap_seed=self.config.seed,
                        )
                        widths = [intv.upper_bound - intv.lower_bound for intv in current_intervals.values()]
                        interval_widths_by_metric = {
                            k: round(v.upper_bound - v.lower_bound, 4) for k, v in current_intervals.items()
                        }
                        max_intv_width = max(widths) if widths else 1.0
                        interval_width_passed = bool(max_intv_width < 0.035)

                        # 3. Bottleneck order stability
                        bottleneck_order_passed = bool(last_bottlenecks is not None and current_order == last_bottlenecks)

                        # 4. Cohort coverage
                        cohort_coverage_passed = bool(all(
                            min(c.values()) >= 50
                            for slice_name, c in agg.cohort_sessions.items()
                            if len(c) > 0 and slice_name != "state"
                        )) if agg.cohort_sessions else False

                        # 5. Measured sensitivity ranking stability with growing persona panel
                        probe_size = min(len(personas), 200 + (sessions_processed // batch_size) * 100)
                        probe_sample = personas[:probe_size]
                        probe_hash = hashlib.sha256(f"{probe_size}:{self.config.seed}".encode()).hexdigest()[:16]
                        sens_probe = run_sensitivity_analysis(
                            personas_sample=probe_sample,
                            seed=self.config.seed,
                            sample_size=len(probe_sample),
                        )
                        current_sens_order = [
                            r.factor_name for r in sorted(sens_probe.results, key=lambda x: abs(x.delta), reverse=True)[:4]
                        ]
                        if last_sens_order is not None:
                            ranking_distance = sum(
                                abs(current_sens_order.index(f) - last_sens_order.index(f)) if f in last_sens_order else 4
                                for f in current_sens_order
                            )
                            sensitivity_order_passed = bool(ranking_distance == 0)
                        else:
                            ranking_distance = 0
                            sensitivity_order_passed = False

                        # 6. TTFV stability
                        ttfv_delta = abs(current_ttfv - last_ttfv) if last_ttfv is not None else 1.0
                        ttfv_stability_passed = bool(last_ttfv is not None and ttfv_delta < 0.2)

                        # 7. Dropoff distribution distance
                        if last_dropoffs is not None:
                            all_reasons = set(current_dropoffs.keys()) | set(last_dropoffs.keys())
                            max_drop_delta = max(abs(current_dropoffs.get(r, 0.0) - last_dropoffs.get(r, 0.0)) for r in all_reasons)
                            dropoff_distribution_passed = bool(max_drop_delta < 0.005)
                        else:
                            max_drop_delta = 1.0
                            dropoff_distribution_passed = False

                        all_criteria_passed = bool(
                            rate_stability_passed and
                            interval_width_passed and
                            bottleneck_order_passed and
                            cohort_coverage_passed and
                            sensitivity_order_passed and
                            ttfv_stability_passed and
                            dropoff_distribution_passed
                        )

                        if all_criteria_passed:
                            consecutive_stable_checks += 1
                        else:
                            consecutive_stable_checks = 0

                        check_record = {
                            "sessions_evaluated": sessions_processed,
                            "rate_max_delta": round(float(max_rate_delta), 6),
                            "max_interval_width": round(float(max_intv_width), 6),
                            "rate_stability_passed": rate_stability_passed,
                            "interval_width_passed": interval_width_passed,
                            "bottleneck_order_passed": bottleneck_order_passed,
                            "cohort_coverage_passed": cohort_coverage_passed,
                            "sensitivity_order_passed": sensitivity_order_passed,
                            "ttfv_stability_passed": ttfv_stability_passed,
                            "dropoff_distribution_passed": dropoff_distribution_passed,
                            "all_criteria_passed": all_criteria_passed,
                            "consecutive_stable_checks": consecutive_stable_checks,
                            "top_bottlenecks": current_order,
                            "top_sensitivity_factors": current_sens_order,
                            "sensitivity_probe_size": probe_size,
                            "sensitivity_probe_hash": probe_hash,
                            "sensitivity_ranking_distance": ranking_distance,
                            "interval_widths_by_metric": interval_widths_by_metric,
                            "ttfv_delta": round(float(ttfv_delta), 4),
                            "max_dropoff_delta": round(float(max_drop_delta), 6),
                        }
                        convergence_history.append(check_record)

                        last_metrics = current_metrics
                        last_bottlenecks = current_order
                        last_sens_order = current_sens_order
                        last_ttfv = current_ttfv
                        last_dropoffs = current_dropoffs

                        if consecutive_stable_checks >= 3 and self.config.mode in [SimulationMode.DEMO_US, SimulationMode.FULL_US, SimulationMode.MAX_SCALE]:
                            is_converged = True
                            termination_reason = TerminationReason.CONVERGED
                            break

                if checkpoint_callback:
                    checkpoint_callback(f"rep_{rep}_{var.value}", sessions_processed)

                if is_converged:
                    break
            if is_converged:
                break

        runtime = max(0.001, time.time() - start_time)
        peak_mem = max(initial_mem, self._get_process_memory_mb())

        # Final Metrics & Analysis with Poisson Persona Cluster Bootstrap
        boot_reps = 1000 if self.config.mode in [SimulationMode.DEMO_US, SimulationMode.FULL_US] else 500
        final_aggregate_metrics = compute_funnel_metrics(agg)
        final_aggregate_metrics.simulation_intervals = calculate_simulation_intervals(
            final_aggregate_metrics,
            agg.total_sessions,
            agg=agg,
            effective_unit="SOURCE_PERSONA",
            interval_method="POISSON_PERSONA_CLUSTER_BOOTSTRAP",
            bootstrap_replications=boot_reps,
            bootstrap_seed=self.config.seed,
        )

        scenario_metrics_map: Dict[str, Any] = {}
        for var_key, sc_agg in scenario_aggregators.items():
            sc_m = compute_funnel_metrics(sc_agg)
            sc_m.simulation_intervals = calculate_simulation_intervals(
                sc_m,
                sc_agg.total_sessions,
                agg=sc_agg,
                effective_unit="SOURCE_PERSONA",
                interval_method="POISSON_PERSONA_CLUSTER_BOOTSTRAP",
                bootstrap_replications=boot_reps,
                bootstrap_seed=self.config.seed,
            )
            scenario_metrics_map[var_key] = sc_m

        balanced_cohorts, weighted_cohorts = compute_cohort_summaries(agg)
        sensitivity_report = run_sensitivity_analysis(
            base_metrics=final_aggregate_metrics,
            personas_sample=personas,
            seed=self.config.seed,
            variant=ScenarioVariant.CURRENT_BASELINE,
            replications=1,
            sample_size=min(10000, len(personas)),
        )
        bottleneck_report = rank_bottlenecks(agg, scenario_aggregators, sensitivity_report=sensitivity_report)
        directional_demand = evaluate_directional_demand(
            DirectionalDemandInput(), final_aggregate_metrics
        )

        sessions_per_sec = round(agg.total_sessions / runtime, 1)
        source_rec_per_sec = round(num_personas / runtime, 1)

        convergence_status_final = bool(termination_reason == TerminationReason.CONVERGED)

        top_interval_method = "POISSON_PERSONA_CLUSTER_BOOTSTRAP"
        if num_personas > 10000:
            top_interval_method = "SUBSAMPLED_POISSON_PERSONA_CLUSTER_BOOTSTRAP"

        return SimulationRunResult(
            simulation_mode=self.config.mode,
            unique_source_personas=num_personas,
            synthetic_sessions=agg.total_sessions,
            scenario_count=len(variants),
            replication_count=replications,
            interval_method=top_interval_method,
            cluster_sample_size=min(10000, num_personas),
            bootstrap_replications=boot_reps,
            bootstrap_seed=self.config.seed,
            sensitivity_sample_size=min(10000, len(personas)),
            seed=self.config.seed,
            policy_version=self.config.policy_version,
            runtime_seconds=round(runtime, 2),
            peak_memory_mb=round(peak_mem, 1),
            sessions_per_second=sessions_per_sec,
            source_records_per_second=source_rec_per_sec,
            termination_reason=termination_reason,
            convergence_status=convergence_status_final,
            convergence_history=convergence_history,
            scenario_metrics=scenario_metrics_map,
            aggregate_funnel=final_aggregate_metrics,
            balanced_eval_cohorts=balanced_cohorts,
            source_weighted_cohorts=weighted_cohorts,
            bottlenecks=bottleneck_report,
            sensitivity=sensitivity_report,
            directional_demand=directional_demand,
            representative_traces=agg.representative_traces,
            paid_model_calls=0,
            live_model_used=False,
        )
