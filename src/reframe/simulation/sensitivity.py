"""
Reframe V7 Empirical Sensitivity Analysis
Measures actual metric responses to individual factor perturbations (±20%) by running paired simulations.
Strict Pairwise Invariant: Baseline and Perturbation use identical personas, scenario, seed, replications, and metric definitions.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import copy
import hashlib
from typing import List, Dict, Any, Tuple, Optional
from src.reframe.simulation.schemas import (
    SensitivityReport,
    SensitivityFactorResult,
    FunnelMetrics,
    DerivedPersonaProfile,
    ScenarioVariant,
    ScenarioConfig,
    GoldenPathState,
    DropoffReason,
    RepresentativeSessionTrace,
)
from src.reframe.simulation.golden_path import get_scenario_config
from src.reframe.simulation.aggregators import OnlineMetricsAggregator
from src.reframe.simulation.metrics import compute_funnel_metrics
from src.reframe.simulation.session_runner import simulate_session_deterministic

FACTORS = [
    "auth_friction",
    "content_density",
    "ai_trust",
    "api_latency",
    "media_latency",
    "community_density",
    "magazine_density",
    "rewatch_friction",
    "theory_effort",
    "evidence_clarity",
]


def _simulate_sample(
    personas: List[DerivedPersonaProfile],
    variant: ScenarioVariant,
    seed: int,
    replications: int = 1,
    factor_name: Optional[str] = None,
    direction: float = 0.0,
) -> Tuple[FunnelMetrics, OnlineMetricsAggregator]:
    """
    Executes a deterministic paired simulation run on a sample of personas
    using the shared unified session simulation engine.
    """
    scenario = copy.deepcopy(get_scenario_config(variant))
    agg = OnlineMetricsAggregator(track_clusters=False)

    # 1. Apply factor perturbation to scenario configuration if applicable
    if factor_name == "api_latency":
        if direction > 0:
            scenario.latency_level = "HIGH"
        else:
            scenario.latency_level = "LOW"
    elif factor_name == "media_latency":
        if direction > 0:
            scenario.media_latency_level = "HIGH"
        else:
            scenario.media_latency_level = "NORMAL"
    elif factor_name == "community_density":
        if direction > 0:
            scenario.community_density = "HIGH"
        else:
            scenario.community_density = "LOW"

    for rep in range(replications):
        for p in personas:
            traits = copy.deepcopy(p.traits) if p.traits else None
            if not traits:
                continue

            # 2. Apply ±20% numeric perturbation to fan traits
            if factor_name == "auth_friction":
                traits.digital_comfort = min(1.0, max(0.0, traits.digital_comfort * (1.0 - direction)))
            elif factor_name == "content_density":
                traits.reading_patience = min(1.0, max(0.0, traits.reading_patience * (1.0 - direction)))
            elif factor_name == "ai_trust":
                traits.trust_in_ai_analysis = min(1.0, max(0.0, traits.trust_in_ai_analysis * (1.0 + direction)))
            elif factor_name == "magazine_density":
                traits.magazine_reading_affinity = min(1.0, max(0.0, traits.magazine_reading_affinity * (1.0 + direction)))
            elif factor_name == "rewatch_friction":
                traits.rewatch_affinity = min(1.0, max(0.0, traits.rewatch_affinity * (1.0 - direction)))
            elif factor_name == "theory_effort":
                traits.theory_writing_propensity = min(1.0, max(0.0, traits.theory_writing_propensity * (1.0 - direction)))
            elif factor_name == "evidence_clarity":
                traits.evidence_preference = min(1.0, max(0.0, traits.evidence_preference * (1.0 + direction)))

            # 3. Simulate session using shared unified engine
            trace = simulate_session_deterministic(
                profile=p,
                variant=variant,
                replication_idx=rep,
                seed=seed,
                scenario_override=scenario,
                traits_override=traits,
                session_id_prefix="sens_sess_",
            )
            agg.record_session(trace, p, weight=p.sampling_weight)

    return compute_funnel_metrics(agg), agg


def run_sensitivity_analysis(
    base_metrics: Optional[FunnelMetrics] = None,
    personas_sample: Optional[List[DerivedPersonaProfile]] = None,
    seed: int = 42,
    variant: ScenarioVariant = ScenarioVariant.CURRENT_BASELINE,
    replications: int = 1,
    sample_size: int = 10000,
) -> SensitivityReport:
    """
    Computes empirical sensitivity responses by rerunning paired simulations with ±20% factor perturbations.
    Strictly uses identical sample, seed, scenario, and definitions.
    Dynamically derives dominant assumptions from measured absolute metric deltas.
    """
    if not personas_sample or len(personas_sample) == 0:
        return SensitivityReport(
            factors_tested=FACTORS,
            perturbation_percentage=20.0,
            sample_size=0,
            paired_scenario=variant.value,
            results=[],
            dominant_assumptions=["NOT_COMPUTED: No persona sample available for paired sensitivity reruns."],
        )

    sample = personas_sample[:min(sample_size, len(personas_sample))]
    actual_sample_size = len(sample)

    # 1. Run unperturbed paired baseline on the EXACT same sample
    base_funnel, base_agg = _simulate_sample(
        personas=sample,
        variant=variant,
        seed=seed,
        replications=replications,
        factor_name=None,
        direction=0.0,
    )
    base_gp_rate = base_funnel.golden_path_completion_rate
    scenario_hash = hashlib.sha256(f"{variant.value}:{seed}:{replications}".encode()).hexdigest()[:12]

    results: List[SensitivityFactorResult] = []
    factor_impact_map: Dict[str, float] = {}

    # 2. Run paired perturbed simulations for every factor and direction
    for factor in FACTORS:
        factor_deltas: List[float] = []
        for perturbation, direction in [("+20%", 0.20), ("-20%", -0.20)]:
            pert_funnel, pert_agg = _simulate_sample(
                personas=sample,
                variant=variant,
                seed=seed,
                replications=replications,
                factor_name=factor,
                direction=direction,
            )

            pert_gp_rate = pert_funnel.golden_path_completion_rate
            delta_gp = round(float(pert_gp_rate - base_gp_rate), 4)

            # Mathematically guaranteed bound in [-1.0, 1.0]
            delta_gp = max(-1.0, min(1.0, delta_gp))
            factor_deltas.append(abs(delta_gp))

            delta_rewatch = round(float(pert_funnel.rewatch_start_rate - base_funnel.rewatch_start_rate), 4)
            delta_theory = round(float(pert_funnel.theory_completion_rate - base_funnel.theory_completion_rate), 4)
            delta_comm = round(float(pert_funnel.community_contribution_rate - base_funnel.community_contribution_rate), 4)
            delta_mag = round(float(pert_funnel.magazine_read_rate - base_funnel.magazine_read_rate), 4)
            delta_ret = round(float(pert_funnel.return_intent_proxy - base_funnel.return_intent_proxy), 4)

            pert_config_hash = hashlib.sha256(f"{factor}:{direction}:{seed}".encode()).hexdigest()[:12]

            results.append(SensitivityFactorResult(
                factor_name=factor,
                perturbation=perturbation,
                baseline_rate=round(float(base_gp_rate), 4),
                perturbed_rate=round(float(pert_gp_rate), 4),
                delta=delta_gp,
                numerator=pert_agg.actions_count.get("golden_path_completed", 0),
                denominator=pert_agg.total_sessions,
                paired_seed=seed,
                scenario_hash=scenario_hash,
                perturbed_config_hash=pert_config_hash,
                golden_path_delta=delta_gp,
                rewatch_delta=max(-1.0, min(1.0, delta_rewatch)),
                theory_delta=max(-1.0, min(1.0, delta_theory)),
                community_delta=max(-1.0, min(1.0, delta_comm)),
                magazine_delta=max(-1.0, min(1.0, delta_mag)),
                return_intent_delta=max(-1.0, min(1.0, delta_ret)),
            ))
        factor_impact_map[factor] = max(factor_deltas) if factor_deltas else 0.0

    # 3. Dynamically derive dominant assumptions from measured absolute deltas
    ranked_factors = sorted(factor_impact_map.items(), key=lambda x: x[1], reverse=True)
    dominant_assumptions = []
    for f_name, max_d in ranked_factors[:4]:
        dominant_assumptions.append(
            f"Measured factor '{f_name}' exhibits maximum absolute Golden Path response of {max_d:.4f} under ±20% perturbation."
        )

    return SensitivityReport(
        factors_tested=FACTORS,
        perturbation_percentage=20.0,
        sample_size=actual_sample_size,
        paired_scenario=variant.value,
        results=results,
        dominant_assumptions=dominant_assumptions,
    )
