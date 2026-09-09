"""
Reframe V7 Purge Synthetic Demo Content CLI Tool
Safely purges only synthetic records tracked via SyntheticContentProvenance.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import argparse
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.simulation.service import audience_lab_service


def parse_args():
    parser = argparse.ArgumentParser(description="Purge synthetic demo content.")
    parser.add_argument(
        "--confirm-delete-synthetic-only",
        action="store_true",
        default=False,
        help="Mandatory safety confirmation to delete synthetic demo content.",
    )
    return parser.parse_args()


async def main_async():
    args = parse_args()
    if not args.confirm_delete_synthetic_only:
        print("Error: Safety violation. You MUST provide --confirm-delete-synthetic-only to execute purge.")
        sys.exit(1)

    print("Purging synthetic demo content...")
    async with AsyncSessionLocal() as db:
        res = await audience_lab_service.purge_synthetic_demo_content(
            db=db,
            confirm_delete_synthetic_only=True,
        )
    print("Purge results:", res)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
