"""
Reframe V7 Seed Synthetic Demo Content CLI Tool
Seeds idempotent synthetic community posts, comments, counterclaims, and/or magazine articles.
Strictly requires explicit opt-in flags, default False confirmation, and explicit scope definition.
Zero External Generative Model Calls.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Ensure all domain models are registered in Base.metadata
import src.reframe.jobs.models
import src.reframe.identity.models
import src.reframe.community.models
import src.reframe.spoiler.models
import src.reframe.simulation.models
import src.reframe.evidence.models
import src.reframe.cost.models
import src.reframe.audit.models
import src.reframe.moderation.models
import src.reframe.proof.models
import src.reframe.catalog.models

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.simulation.service import audience_lab_service
from tools.catalog.target_safety import mask_db_url, match_structured_target


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Seed idempotent synthetic demo content into database."
    )
    # Confirmation is strictly default=False
    parser.add_argument(
        "--confirm-seed",
        action="store_true",
        default=False,
        help="Explicit confirmation required to write synthetic records to DB.",
    )
    parser.add_argument(
        "--expected-target",
        type=str,
        default=None,
        help="Expected database identity (exact normalized path for SQLite, host:port/db for network DBs).",
    )
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Explicit database URL. If omitted, uses active settings with identity verification.",
    )
    # Differentiate scopes: separate magazine and community seeding
    parser.add_argument(
        "--seed-magazine",
        action="store_true",
        default=False,
        help="Seed curated synthetic magazine articles only.",
    )
    parser.add_argument(
        "--seed-community",
        action="store_true",
        default=False,
        help="Seed synthetic community audience posts, comments, and reactions.",
    )
    # Granular community counts (defaults only apply when --seed-community is active)
    parser.add_argument(
        "--posts",
        type=int,
        default=150,
        help="Target synthetic posts (1..150, default: 150 when community seeding)",
    )
    parser.add_argument(
        "--comments",
        type=int,
        default=800,
        help="Target comments (1..800, default: 800 when community seeding)",
    )
    parser.add_argument(
        "--counterclaims",
        type=int,
        default=150,
        help="Target counterclaims (1..150, default: 150 when community seeding)",
    )
    parser.add_argument(
        "--reactions",
        type=int,
        default=2000,
        help="Target reactions (1..2000, default: 2000 when community seeding)",
    )
    return parser.parse_args(argv)


async def run_seeder(args) -> dict:
    # 1. Require explicit confirmation
    if not args.confirm_seed:
        raise ValueError("Confirmation required: --confirm-seed must be explicitly passed.")

    # 2. Require at least one explicit scope
    if not args.seed_magazine and not args.seed_community:
        raise ValueError(
            "Scope required: at least one of --seed-magazine or --seed-community must be specified."
        )

    # 3. Guard against accidental writes to non-target databases (require expected_target)
    if not args.expected_target or not args.expected_target.strip():
        raise ValueError("Target database identity required: --expected-target must be explicitly provided.")

    target_db_url = args.db_url or getattr(settings, "DATABASE_URL", "") or ""
    if not match_structured_target(target_db_url, args.expected_target):
        masked_url = mask_db_url(target_db_url)
        raise ValueError(
            f"Target database identity mismatch: expected '{args.expected_target}', active is '{masked_url}'"
        )

    # 4. Validate counts if community seeding
    post_count = 0
    comment_count = 0
    counterclaim_count = 0
    reaction_count = 0

    if args.seed_community:
        if args.posts < 0 or args.posts > 150:
            raise ValueError(f"Invalid post count {args.posts}: must be between 0 and 150")
        if args.comments < 0 or args.comments > 800:
            raise ValueError(f"Invalid comment count {args.comments}: must be between 0 and 800")
        if args.counterclaims < 0 or args.counterclaims > 150:
            raise ValueError(f"Invalid counterclaim count {args.counterclaims}: must be between 0 and 150")
        if args.reactions < 0 or args.reactions > 2000:
            raise ValueError(f"Invalid reaction count {args.reactions}: must be between 0 and 2000")
        post_count = args.posts
        comment_count = args.comments
        counterclaim_count = args.counterclaims
        reaction_count = args.reactions

    print(
        f"Seeding synthetic demo content (magazine={args.seed_magazine}, "
        f"community={args.seed_community}, posts={post_count})..."
    )

    custom_engine = None
    if args.db_url:
        async_url = args.db_url
        if async_url.startswith("sqlite:///") and not async_url.startswith("sqlite+aiosqlite:///"):
            async_url = async_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
        custom_engine = create_async_engine(async_url, echo=False)
        session_factory = async_sessionmaker(custom_engine, expire_on_commit=False)
    else:
        session_factory = AsyncSessionLocal

    try:
        async with session_factory() as db:
            res = await audience_lab_service.seed_synthetic_demo_content(
                db=db,
                enable_magazine=args.seed_magazine,
                enable_community=args.seed_community,
                post_target_count=post_count,
                comment_target_count=comment_count,
                counterclaim_target_count=counterclaim_count,
                reaction_target_count=reaction_count,
            )

        # Enforce magazine-only scope invariant
        if not args.seed_community:
            if res.get("created_posts") or res.get("created_comments") or res.get("created_counterclaims"):
                raise RuntimeError("Scope violation: community content was created during a magazine-only seed operation.")

        print("Seed results:", res)
        return res
    finally:
        if custom_engine:
            await custom_engine.dispose()


def main():
    args = parse_args()
    try:
        asyncio.run(run_seeder(args))
    except Exception as e:
        print(f"Error seeding synthetic content: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
