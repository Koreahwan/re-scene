"""
Reframe V7 Generate Simulation Run Artifacts
Executes CI (30k sessions), SMOKE (100k sessions), DEMO_US Adaptive, and DEMO_US Exact 5M
routed strictly through AudienceLabService.execute_certified_simulation.
Writes full evaluation artifact JSON and gzip files to data/simulation/runs/.
Programmatically asserts full lineage, single completion lifecycle, and interval validity.
Zero External Generative Model Calls ($0.00).
"""
import sys
import json
import gzip
import asyncio
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.reframe.simulation.schemas import (
    SimulationMode,
    ScenarioVariant,
    SimulationRunConfig,
    SimulationRunResult,
)
from src.reframe.simulation.service import audience_lab_service
from src.reframe.simulation.load_export import generate_load_profile


def assert_artifact_lineage_and_validity(res: SimulationRunResult, expected_source_mode: str, manifest_path: Path, source_path: Path):
    with open(manifest_path, "r", encoding="utf-8") as f:
        mf = json.load(f)

    assert res.source_mode == expected_source_mode, f"source_mode mismatch: {res.source_mode} != {expected_source_mode}"
    assert res.source_cache_sha256 == mf["sample_sha256"], "source_cache_sha256 does not match manifest"
    assert len(res.source_cache_manifest_sha256) == 64, "Missing manifest SHA-256"
    assert res.sample_method == mf.get("sample_method")
    assert res.source_rows_seen == mf.get("source_rows_seen")
    assert res.eligible_adult_rows == mf.get("eligible_adult_rows")
    assert res.full_stream_completed is True, "full_stream_completed must be True"
    assert len(res.policy_hash) == 64, "Missing valid policy_hash"
    assert len(res.scenario_hash) == 64, "Missing valid scenario_hash"
    assert res.paid_model_calls == 0, "Zero external model calls invariant violated"
    assert res.live_model_used is False, "Zero model invariant violated"

    # Funnel Metric Invariants
    fn = res.aggregate_funnel
    assert 0.0 <= fn.golden_path_completion_rate <= 1.0
    assert 0.0 <= fn.landing_to_film_hub_rate <= 1.0
    assert 0.0 <= fn.film_hub_to_reveal_rate <= 1.0
    assert 0.0 <= fn.spoiler_gate_completion_rate <= 1.0
    assert 0.0 <= fn.deep_reframe_entry_rate <= 1.0
    assert 0.0 <= fn.deep_reframe_completion_rate <= 1.0
    assert 0.0 <= fn.rewatch_start_rate <= 1.0
    assert 0.0 <= fn.rewatch_completion_rate <= 1.0
    assert 0.0 <= fn.theory_start_rate <= 1.0
    assert 0.0 <= fn.theory_completion_rate <= 1.0

    for name, intv in fn.simulation_intervals.items():
        assert 0.0 <= intv.lower_bound <= 1.0, f"{name} lower_bound out of [0, 1]"
        assert 0.0 <= intv.upper_bound <= 1.0, f"{name} upper_bound out of [0, 1]"
        assert intv.lower_bound <= intv.upper_bound, f"{name} lower_bound > upper_bound"


async def main():
    runs_dir = PROJECT_ROOT / "data" / "simulation" / "runs"
    load_dir = PROJECT_ROOT / "data" / "simulation" / "load"
    personas_dir = PROJECT_ROOT / "data" / "simulation" / "personas"
    runs_dir.mkdir(parents=True, exist_ok=True)
    load_dir.mkdir(parents=True, exist_ok=True)

    cache_100k_path = personas_dir / "nemotron_usa_100k_cache.jsonl.gz"
    cache_100k_manifest = personas_dir / "nemotron_usa_100k_cache_manifest.json"
    sample_10k_path = personas_dir / "nemotron_usa_repro_sample_v1.jsonl.gz"
    sample_10k_manifest = personas_dir / "nemotron_usa_repro_sample_v1_manifest.json"

    # 1. CI Run (10,000 personas * 3 variants * 1 rep = 30,000 sessions)
    print("\n--- Executing CI Simulation (30,000 sessions) ---")
    ci_config = SimulationRunConfig(
        mode=SimulationMode.CI,
        unique_source_personas=10000,
        variants=[
            ScenarioVariant.QUICK_VALUE,
            ScenarioVariant.CURRENT_BASELINE,
            ScenarioVariant.COMMUNITY_FIRST,
        ],
        replications=1,
        seed=42,
    )
    ci_res = await audience_lab_service.execute_certified_simulation(
        config=ci_config,
        source_mode="REPRO_SAMPLE",
        source_path=sample_10k_path,
        manifest_path=sample_10k_manifest,
        enable_adaptive_stop=False,
    )
    assert_artifact_lineage_and_validity(ci_res, "REPRO_SAMPLE", sample_10k_manifest, sample_10k_path)

    with open(runs_dir / "usa_audience_ci_v1_summary.json", "w", encoding="utf-8") as f:
        json.dump(ci_res.model_dump(), f, indent=2)
    print(f"CI run completed: {ci_res.synthetic_sessions:,} sessions in {ci_res.runtime_seconds}s ({ci_res.sessions_per_second:.0f} sess/sec).")

    # 2. SMOKE Run (10,000 personas * 5 variants * 2 reps = 100,000 sessions)
    print("\n--- Executing SMOKE Simulation (100,000 sessions) ---")
    smoke_config = SimulationRunConfig(
        mode=SimulationMode.SMOKE,
        unique_source_personas=10000,
        variants=[
            ScenarioVariant.QUICK_VALUE,
            ScenarioVariant.CURRENT_BASELINE,
            ScenarioVariant.EARLY_AUTH,
            ScenarioVariant.DEEP_ANALYSIS,
            ScenarioVariant.COMMUNITY_FIRST,
        ],
        replications=2,
        seed=42,
    )
    smoke_res = await audience_lab_service.execute_certified_simulation(
        config=smoke_config,
        source_mode="REPRO_SAMPLE",
        source_path=sample_10k_path,
        manifest_path=sample_10k_manifest,
        enable_adaptive_stop=False,
    )
    assert_artifact_lineage_and_validity(smoke_res, "REPRO_SAMPLE", sample_10k_manifest, sample_10k_path)

    with open(runs_dir / "usa_audience_smoke_v1_summary.json", "w", encoding="utf-8") as f:
        json.dump(smoke_res.model_dump(), f, indent=2)
    print(f"SMOKE run completed: {smoke_res.synthetic_sessions:,} sessions in {smoke_res.runtime_seconds}s ({smoke_res.sessions_per_second:.0f} sess/sec).")

    # 3. DEMO_US ADAPTIVE Run (100,000 distinct real personas * 5 variants * 10 reps with Adaptive Stop)
    print("\n--- Executing DEMO_US Adaptive Simulation ---")
    demo_config = SimulationRunConfig(
        mode=SimulationMode.DEMO_US,
        unique_source_personas=100000,
        variants=[
            ScenarioVariant.QUICK_VALUE,
            ScenarioVariant.CURRENT_BASELINE,
            ScenarioVariant.EARLY_AUTH,
            ScenarioVariant.DEEP_ANALYSIS,
            ScenarioVariant.COMMUNITY_FIRST,
        ],
        replications=10,
        seed=42,
    )
    demo_res = await audience_lab_service.execute_certified_simulation(
        config=demo_config,
        source_mode="LOCAL_DERIVED_CACHE",
        source_path=cache_100k_path,
        manifest_path=cache_100k_manifest,
        enable_adaptive_stop=True,
    )
    assert_artifact_lineage_and_validity(demo_res, "LOCAL_DERIVED_CACHE", cache_100k_manifest, cache_100k_path)

    with open(runs_dir / "usa_audience_demo_v1_summary.json", "w", encoding="utf-8") as f:
        json.dump(demo_res.model_dump(), f, indent=2)

    with gzip.open(runs_dir / "usa_audience_demo_v1_full.json.gz", "wt", encoding="utf-8") as gz:
        json.dump(demo_res.model_dump(), gz)

    with open(runs_dir / "usa_audience_demo_v1_bottlenecks.json", "w", encoding="utf-8") as f:
        json.dump(demo_res.bottlenecks.model_dump() if demo_res.bottlenecks else {}, f, indent=2)

    with open(runs_dir / "usa_audience_demo_v1_cohorts.json", "w", encoding="utf-8") as f:
        json.dump({
            "balanced_eval_cohorts": [c.model_dump() for c in demo_res.balanced_eval_cohorts],
            "source_weighted_cohorts": [c.model_dump() for c in demo_res.source_weighted_cohorts],
        }, f, indent=2)

    with open(runs_dir / "usa_audience_demo_v1_sensitivity.json", "w", encoding="utf-8") as f:
        json.dump(demo_res.sensitivity.model_dump() if demo_res.sensitivity else {}, f, indent=2)

    with open(runs_dir / "usa_audience_demo_v1_sample_traces.json", "w", encoding="utf-8") as f:
        json.dump({
            "sample_count": len(demo_res.representative_traces),
            "traces": [t.model_dump() for t in demo_res.representative_traces[:50]],
        }, f, indent=2)

    print(f"DEMO_US Adaptive run completed: {demo_res.synthetic_sessions:,} sessions in {demo_res.runtime_seconds}s (converged: {demo_res.convergence_status}, termination: {demo_res.termination_reason.value}).")

    # Export load profile
    generate_load_profile(demo_res.aggregate_funnel, output_dir=load_dir)
    print(f"Exported load profile to {load_dir}")

    # 4. DEMO_US EXACT 5M Run (100,000 personas * 5 variants * 10 reps = exactly 5,000,000 sessions)
    print("\n--- Executing DEMO_US EXACT 5,000,000 Session Run ---")
    exact_5m_config = SimulationRunConfig(
        mode=SimulationMode.DEMO_US,
        unique_source_personas=100000,
        variants=[
            ScenarioVariant.QUICK_VALUE,
            ScenarioVariant.CURRENT_BASELINE,
            ScenarioVariant.EARLY_AUTH,
            ScenarioVariant.DEEP_ANALYSIS,
            ScenarioVariant.COMMUNITY_FIRST,
        ],
        replications=10,
        seed=42,
    )
    exact_res = await audience_lab_service.execute_certified_simulation(
        config=exact_5m_config,
        source_mode="LOCAL_DERIVED_CACHE",
        source_path=cache_100k_path,
        manifest_path=cache_100k_manifest,
        enable_adaptive_stop=False,
    )
    assert_artifact_lineage_and_validity(exact_res, "LOCAL_DERIVED_CACHE", cache_100k_manifest, cache_100k_path)

    with open(runs_dir / "usa_audience_exact_5m_summary.json", "w", encoding="utf-8") as f:
        json.dump(exact_res.model_dump(), f, indent=2)

    with gzip.open(runs_dir / "usa_audience_exact_5m_full.json.gz", "wt", encoding="utf-8") as gz:
        json.dump(exact_res.model_dump(), gz)

    print(f"\nDEMO_US Exact 5M run completed successfully:")
    print(f"- Unique Personas: {exact_res.unique_source_personas:,}")
    print(f"- Total Sessions: {exact_res.synthetic_sessions:,}")
    print(f"- Runtime: {exact_res.runtime_seconds}s ({exact_res.sessions_per_second:,.0f} sess/sec)")
    print(f"- Peak Memory: {exact_res.peak_memory_mb:.1f} MB")
    print(f"- Termination: {exact_res.termination_reason.value} (converged: {exact_res.convergence_status})")
    print(f"- Interval Method: {exact_res.interval_method} (reps: {exact_res.bootstrap_replications})")
    print(f"- Golden Path Completion Rate: {exact_res.aggregate_funnel.golden_path_completion_rate:.4f}")
    print(f"- Output Artifacts written to {runs_dir}")


if __name__ == "__main__":
    asyncio.run(main())
