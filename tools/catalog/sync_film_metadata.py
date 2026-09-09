"""
Reframe V7 Film Metadata and Poster Sync Utility
Synchronizes data/catalog/films_wikidata_v1.json safely into the film_catalog table.
Enforces URL credential masking, target identity verification, schema/revision validation,
content immutability checks, atomic transactions, and explicit opt-in confirmation.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, select, text, inspect
from sqlalchemy.orm import Session
from src.reframe.catalog.models import FilmCatalog
from tools.catalog.target_safety import (
    mask_db_url,
    match_structured_target,
    verify_db_target_and_schema,
    compute_canonical_film_diff,
    validate_catalog_payload,
    REQUIRED_COLUMNS,
)


def compute_film_diff(row: FilmCatalog, film: dict) -> Dict[str, Dict[str, Any]]:
    """Compute field-level changes across ALL canonical fields between database row and incoming payload."""
    return compute_canonical_film_diff(row, film)


def sync_catalog(
    db_url: str,
    catalog_path: Path,
    expected_target: Optional[str] = None,
    confirm_sync: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Safely synchronize catalog metadata.
    Enforces atomic transaction, revision matching, and credential protection.
    """
    if not db_url or not db_url.strip():
        raise ValueError("Explicit db_url is required (no silent env fallback).")

    if confirm_sync and not dry_run and (not expected_target or not expected_target.strip()):
        raise ValueError("Target database identity required: expected_target must be explicitly provided for writes.")

    if expected_target and not match_structured_target(db_url, expected_target):
        masked = mask_db_url(db_url)
        masked_exp = mask_db_url(expected_target)
        raise ValueError(
            f"Target database identity mismatch: expected structured target '{masked_exp}' does not match '{masked}'"
        )

    films = validate_catalog_payload(catalog_path)
    masked_url = mask_db_url(db_url)
    print(f"Connecting to verified database target: {masked_url}")

    engine = create_engine(db_url, echo=False)
    try:
        verify_db_target_and_schema(engine, "0013_v7_film_catalog_metadata")

        report = {
            "target": masked_url,
            "dry_run": dry_run or not confirm_sync,
            "created": [],
            "updated": [],
            "no_op": [],
            "conflicts": [],
        }

        with Session(engine) as session:
            try:
                for film in films:
                    movie_id = film["movie_id"]
                    incoming_rev = film.get("source_revision", 0)
                    poster = film.get("poster") or {}
                    poster_path = film.get("poster_local_path") or poster.get("local_path")

                    stmt = select(FilmCatalog).where(FilmCatalog.movie_id == movie_id)
                    row = session.scalar(stmt)

                    if not row:
                        report["created"].append({
                            "movie_id": movie_id,
                            "title_en": film["title_en"],
                            "revision": incoming_rev,
                        })
                        if confirm_sync and not dry_run:
                            new_row = FilmCatalog(
                                movie_id=movie_id,
                                source_qid=film["qid"],
                                title_en=film["title_en"],
                                title_ko=film.get("title_ko"),
                                year=film.get("year"),
                                description_en=film.get("description_en"),
                                description_ko=film.get("description_ko"),
                                runtime_minutes=film.get("runtime_minutes"),
                                directors=film.get("directors", []),
                                cast_members=film.get("cast", []),
                                genres=film.get("genres", []),
                                countries=film.get("countries", []),
                                languages=film.get("languages", []),
                                core_demo_supported=film.get("core_demo_supported", False),
                                poster_local_path=poster_path,
                                poster_source_filename=poster.get("source_filename"),
                                poster_sha256=poster.get("sha256"),
                                poster_license=poster.get("license"),
                                source_revision=incoming_rev,
                                source_url=film.get("source_url", ""),
                                fetched_at=datetime.now(timezone.utc),
                            )
                            session.add(new_row)
                    else:
                        diffs = compute_film_diff(row, film)
                        if not diffs:
                            report["no_op"].append({
                                "movie_id": movie_id,
                                "revision": row.source_revision,
                            })
                        elif row.source_revision == incoming_rev:
                            conflict_info = {
                                "movie_id": movie_id,
                                "revision": row.source_revision,
                                "reason": "Content mutation under identical revision (immutable payload violation)",
                                "diffs": diffs,
                            }
                            report["conflicts"].append(conflict_info)
                            raise ValueError(
                                f"Revision conflict for movie '{movie_id}': cannot modify content without bumping source_revision. Diff: {diffs}"
                            )
                        elif incoming_rev > row.source_revision:
                            report["updated"].append({
                                "movie_id": movie_id,
                                "old_revision": row.source_revision,
                                "new_revision": incoming_rev,
                                "diffs": diffs,
                            })
                            if confirm_sync and not dry_run:
                                if film.get("qid") and film.get("qid") != row.source_qid:
                                    raise ValueError(
                                        f"Cannot mutate immutable identity 'source_qid' for movie '{movie_id}': "
                                        f"existing '{row.source_qid}' vs incoming '{film.get('qid')}'"
                                    )
                                row.title_en = film["title_en"]
                                row.title_ko = film.get("title_ko")
                                row.year = film.get("year")
                                row.description_ko = film.get("description_ko")
                                row.description_en = film.get("description_en")
                                row.runtime_minutes = film.get("runtime_minutes")
                                row.directors = film.get("directors", [])
                                row.genres = film.get("genres", [])
                                row.cast_members = film.get("cast", [])
                                row.countries = film.get("countries", [])
                                row.languages = film.get("languages", [])
                                row.core_demo_supported = film.get("core_demo_supported", row.core_demo_supported)
                                row.source_url = film.get("source_url", row.source_url)
                                row.poster_local_path = poster_path
                                row.poster_source_filename = poster.get("source_filename")
                                row.poster_sha256 = poster.get("sha256")
                                row.poster_license = poster.get("license")
                                row.source_revision = incoming_rev
                                row.updated_at = datetime.now(timezone.utc)
                        else:
                            raise ValueError(
                                f"Stale revision for movie '{movie_id}': incoming revision {incoming_rev} is older than DB revision {row.source_revision}"
                            )

                if confirm_sync and not dry_run:
                    session.commit()
                    print(
                        f"Sync committed: {len(report['created'])} created, "
                        f"{len(report['updated'])} updated, {len(report['no_op'])} unchanged."
                    )
                else:
                    session.rollback()
                    print(
                        f"[DRY-RUN / INSPECT] No DB changes committed. "
                        f"Proposed: {len(report['created'])} created, "
                        f"{len(report['updated'])} updated, {len(report['no_op'])} unchanged."
                    )
                return report
            except Exception as e:
                session.rollback()
                print(f"Sync failed and rolled back: {type(e).__name__} - {e}")
                raise
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Safely sync film metadata and posters to DB.")
    parser.add_argument(
        "--db-url",
        type=str,
        required=True,
        help="Explicit database URL. Required (no silent env fallback).",
    )
    parser.add_argument(
        "--expected-target",
        type=str,
        default=None,
        help="Expected database identity substring/path to prevent accidental writes.",
    )
    parser.add_argument(
        "--catalog-path",
        type=Path,
        default=REPO_ROOT / "data" / "catalog" / "films_wikidata_v1.json",
        help="Path to films_wikidata_v1.json",
    )
    parser.add_argument(
        "--confirm-sync",
        action="store_true",
        default=False,
        help="Explicit confirmation to write changes to target database (default: False / inspect mode).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Dry-run / inspect only.",
    )
    args = parser.parse_args()

    sync_catalog(
        db_url=args.db_url,
        catalog_path=args.catalog_path,
        expected_target=args.expected_target,
        confirm_sync=args.confirm_sync,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
