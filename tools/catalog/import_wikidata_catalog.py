"""
Reframe V7 Wikidata Catalog Importer
Idempotent batch importer of data/catalog/films_wikidata_v1.json into film_catalog table.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.reframe.catalog.repository import FilmCatalogRepository
from src.reframe.catalog.models import FilmCatalog


REQUIRED_COLUMNS = {
    "movie_id", "source_qid", "title_en", "title_ko", "year",
    "description_en", "description_ko", "runtime_minutes",
    "directors", "cast_members", "genres", "countries", "languages",
    "core_demo_supported", "poster_local_path", "poster_source_filename",
    "poster_sha256", "poster_license", "source_revision", "source_url",
    "fetched_at", "created_at", "updated_at",
}


def validate_catalog_payload(catalog_path: Path) -> list:
    """Validate harvested catalog payload structure, types, and ranges."""
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog file {catalog_path} does not exist")

    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    films = data.get("films", [])
    if len(films) != 20:
        raise ValueError(f"Expected exactly 20 films, found {len(films)}")

    seen_ids = set()
    seen_qids = set()
    for idx, f in enumerate(films):
        m_id = f.get("movie_id")
        qid = f.get("qid")
        t_en = f.get("title_en")
        year = f.get("year")
        rev = f.get("source_revision")
        s_url = f.get("source_url")
        f_utc = f.get("fetched_at_utc")

        if not m_id or not isinstance(m_id, str) or not m_id.strip():
            raise ValueError(f"Film #{idx}: missing or invalid movie_id")
        if not qid or not isinstance(qid, str) or not qid.strip():
            raise ValueError(f"Film #{idx}: missing or invalid qid")
        if not t_en or not isinstance(t_en, str) or not t_en.strip():
            raise ValueError(f"Film #{idx}: missing or invalid title_en")
        if year is None or not isinstance(year, int) or year < 1880 or year > 2100:
            raise ValueError(f"Film #{idx}: invalid release year {year}")
        if rev is None or not isinstance(rev, int) or rev <= 0:
            raise ValueError(f"Film #{idx}: invalid source_revision {rev}")
        if not s_url or not isinstance(s_url, str) or not s_url.startswith("http"):
            raise ValueError(f"Film #{idx}: invalid source_url {s_url}")
        if not f_utc or not isinstance(f_utc, str):
            raise ValueError(f"Film #{idx}: missing fetched_at_utc")

        # Range and type check on optional fields
        rt = f.get("runtime_minutes")
        if rt is not None and (not isinstance(rt, int) or rt < 0 or rt > 1000):
            raise ValueError(f"Film #{idx}: invalid runtime_minutes {rt}")

        for arr_field in ["directors", "cast", "genres", "countries", "languages"]:
            val = f.get(arr_field)
            if val is not None and not isinstance(val, list):
                raise ValueError(f"Film #{idx}: field '{arr_field}' must be a list")

        poster = f.get("poster")
        if poster is not None and not isinstance(poster, dict):
            raise ValueError(f"Film #{idx}: 'poster' must be a dictionary")

        if m_id in seen_ids:
            raise ValueError(f"Duplicate movie_id: {m_id}")
        if qid in seen_qids:
            raise ValueError(f"Duplicate qid: {qid}")
        seen_ids.add(m_id)
        seen_qids.add(qid)

    return films


from typing import Optional
from urllib.parse import urlsplit, urlunsplit


def mask_db_url(url: str) -> str:
    """Mask credentials in database connection URLs."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if parts.password:
            user = parts.username or ""
            host = parts.hostname or ""
            port = f":{parts.port}" if parts.port else ""
            netloc = f"{user}:***@{host}{port}"
            return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        pass
    return url


def match_structured_target(db_url: str, expected_target: str) -> bool:
    """Perform structured target identity check without credential exposure."""
    if not expected_target:
        return True
    try:
        parts = urlsplit(db_url)
        if parts.scheme.startswith("sqlite"):
            p_str = parts.path
            if p_str.startswith("///"):
                p_str = p_str[3:]
            elif p_str.startswith("/"):
                p_str = p_str[1:]
            norm_db = Path(p_str).resolve().as_posix()
            norm_exp = Path(expected_target).resolve().as_posix() if ("/" in expected_target or "\\" in expected_target) else expected_target
            return norm_exp == norm_db or norm_exp in norm_db
        else:
            db_name = parts.path.lstrip("/")
            return expected_target in (parts.netloc, parts.hostname, db_name, f"{parts.hostname}/{db_name}")
    except Exception:
        return expected_target in db_url


from tools.catalog.target_safety import (
    mask_db_url,
    match_structured_target,
    verify_db_target_and_schema,
    validate_catalog_payload,
    REQUIRED_COLUMNS,
)


def run_importer(
    db_url: str,
    catalog_path: Path,
    dry_run: bool = False,
    expected_target: Optional[str] = None
) -> dict:
    """
    Execute import in a single transaction.
    Schema creation via metadata.create_all() is strictly prohibited;
    schema must be created via reviewed migrations.
    """
    films = validate_catalog_payload(catalog_path)

    if dry_run:
        print(f"[DRY RUN] Pure validator passed for {len(films)} films in {catalog_path.name}.")
        print("[DRY RUN] Target database write skipped.")
        return {"dry_run": True, "count": len(films), "status": "VALIDATED"}

    if not db_url or not db_url.strip():
        raise ValueError("Explicit db_url is required for catalog import.")

    if not dry_run and (not expected_target or not expected_target.strip()):
        raise ValueError("Target database identity required: expected_target must be explicitly provided for writes.")

    if expected_target and expected_target.strip():
        if not match_structured_target(db_url, expected_target):
            masked = mask_db_url(db_url)
            masked_exp = mask_db_url(expected_target)
            raise ValueError(
                f"Target database identity mismatch: expected structured target '{masked_exp}' does not match '{masked}'"
            )

    masked_url = mask_db_url(db_url)
    print(f"Connecting to verified target database: {masked_url}")
    engine = create_engine(db_url, echo=False)
    try:
        verify_db_target_and_schema(engine, "0013_v7_film_catalog_metadata")

        with Session(engine) as session:
            try:
                stats = FilmCatalogRepository.sync_import_films(session, films)
                session.commit()
                print(f"Catalog import successful: {stats}")
                return stats
            except Exception as e:
                session.rollback()
                print(f"Catalog import failed, transaction rolled back: {type(e).__name__}")
                raise
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Import Wikidata film catalog into database.")
    parser.add_argument(
        "--db-url",
        type=str,
        default=None,
        help="Explicit database connection URL (sync). Required when writing.",
    )
    parser.add_argument(
        "--expected-target",
        type=str,
        default=None,
        help="Expected database identity substring to prevent accidental writes",
    )
    parser.add_argument(
        "--catalog-path",
        type=str,
        default=str(REPO_ROOT / "data" / "catalog" / "films_wikidata_v1.json"),
        help="Path to films_wikidata_v1.json",
    )
    parser.add_argument(
        "--confirm-write",
        action="store_true",
        help="Explicitly confirm intent to write to target database",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate catalog without writing to database",
    )
    args = parser.parse_args()

    if not args.dry_run:
        if not args.db_url:
            print("Error: Explicit --db-url is required when writing to database (no silent env fallback).", file=sys.stderr)
            sys.exit(1)
        if not args.confirm_write:
            print("Error: Target database write requires explicit --confirm-write flag.", file=sys.stderr)
            sys.exit(1)

    catalog_path = Path(args.catalog_path)
    res = run_importer(
        args.db_url,
        catalog_path,
        dry_run=args.dry_run,
        expected_target=args.expected_target
    )
    print(f"Result: {res}")


if __name__ == "__main__":
    main()
