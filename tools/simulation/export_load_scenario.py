"""
Reframe V7 Export Load Scenario Tool
Exports weighted Locust load testing profiles and request mix definitions.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.reframe.simulation.load_export import generate_load_profile
from src.reframe.simulation.schemas import SimulationRunConfig, SimulationMode
from src.reframe.simulation.service import audience_lab_service


def parse_args():
    parser = argparse.ArgumentParser(description="Export simulation-derived Locust load profiles.")
    parser.add_argument("--output-dir", default="data/simulation/load", help="Output directory for load assets")
    parser.add_argument("--target-host", default="http://localhost:8000", help="Target API host (default localhost)")
    parser.add_argument("--users", type=int, default=250, help="Default virtual users (max 1000 without override)")
    parser.add_argument("--duration", type=int, default=10, help="Duration in minutes")
    return parser.parse_args()


def main():
    args = parse_args()
    out_dir = Path(args.output_dir)
    
    import asyncio
    personas = audience_lab_service.load_reproducibility_personas(count=1000)
    sim_res = asyncio.run(audience_lab_service.execute_simulation_run(
        SimulationRunConfig(mode=SimulationMode.CI, unique_source_personas=1000, replications=1),
        personas=personas,
    ))

    manifest = generate_load_profile(
        metrics=sim_res.aggregate_funnel,
        output_dir=out_dir,
        target_host=args.target_host,
        default_users=min(1000, args.users),
        duration_min=args.duration,
    )
    print(f"Successfully generated load scenario in {out_dir}")
    print(f"Manifest: {out_dir / 'load_manifest.json'}")



if __name__ == "__main__":
    main()
