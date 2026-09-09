"""
Reframe V7 Database Target Safety & Metadata Contract Verification
Common validation module for importer, metadata sync, and simulation seeding tools.
Enforces:
- Strict URL credential masking (passwords and query parameters)
- Whole-identity structured target verification (rejects substring, basename, partial matches)
- Strict Alembic migration revision verification (fails if alembic_version table is absent)
- Column completeness, types, nullability, PK, and single-column UNIQUE verification
- Complete canonical content diffing (directors, cast, countries, languages, QID, source URL)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

REQUIRED_COLUMNS = {
    "movie_id", "source_qid", "title_en", "title_ko", "year",
    "description_en", "description_ko", "runtime_minutes",
    "directors", "cast_members", "genres", "countries", "languages",
    "core_demo_supported", "poster_local_path", "poster_source_filename",
    "poster_sha256", "poster_license", "source_revision", "source_url",
    "fetched_at", "created_at", "updated_at",
}

SENSITIVE_PARAM_KEYS = {
    "password", "token", "secret", "api_key", "apikey", "key", "auth", "access_token"
}


def mask_db_url(url: str) -> str:
    """
    Safely mask credentials in database URLs.
    Masks user password in netloc and sensitive query string parameters.
    Fail-closed: if parsing or reconstruction fails, returns a safe redacted string.
    """
    if not url or not isinstance(url, str):
        return ""
    try:
        parts = urlsplit(url)
        # 1. Mask netloc password
        netloc = parts.netloc
        if parts.password:
            user = parts.username or ""
            host = parts.hostname or ""
            port = f":{parts.port}" if parts.port else ""
            netloc = f"{user}:***@{host}{port}"

        # 2. Mask query parameters
        query = parts.query
        if query:
            q_pairs = parse_qsl(query, keep_blank_values=True)
            masked_pairs = []
            for k, v in q_pairs:
                if k.lower() in SENSITIVE_PARAM_KEYS or "pass" in k.lower() or "secret" in k.lower() or "token" in k.lower():
                    masked_pairs.append((k, "***"))
                else:
                    masked_pairs.append((k, v))
            query = urlencode(masked_pairs, safe="*")

        return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
    except Exception:
        return "<invalid_url_credentials_redacted>"


def match_structured_target(db_url: str, expected_target: Optional[str]) -> bool:
    """
    Perform structured target identity check without credential exposure.
    Fails closed on missing or partial targets.
    - SQLite: Must match the exact normalized absolute file path (no basename-only, no substring).
    - Network DBs (Postgres, etc.): Must match host, port, and database name as a complete unit.
      Reject if only host or only database name is provided.
    """
    if not expected_target or not isinstance(expected_target, str) or not expected_target.strip():
        return False
    if not db_url or not isinstance(db_url, str) or not db_url.strip():
        return False

    try:
        parts = urlsplit(db_url)
        scheme = parts.scheme.lower()

        if scheme.startswith("sqlite"):
            p_str = parts.path
            # Normalize SQLite path formats
            if p_str.startswith("///"):
                p_str = p_str[3:]
            elif p_str.startswith("/"):
                # On Windows, path may be /C:/...
                if len(p_str) > 2 and p_str[2] == ":":
                    p_str = p_str[1:]

            exp_str = expected_target.strip()
            if exp_str.lower().startswith("sqlite"):
                exp_parts = urlsplit(exp_str)
                exp_str = exp_parts.path
                if exp_str.startswith("///"):
                    exp_str = exp_str[3:]
                elif exp_str.startswith("/"):
                    if len(exp_str) > 2 and exp_str[2] == ":":
                        exp_str = exp_str[1:]

            db_path = Path(p_str).resolve()
            exp_path = Path(exp_str).resolve()
            # Exact resolved path equality (case-insensitive for Windows compatibility)
            return str(db_path).lower() == str(exp_path).lower()

        else:
            # Network DB: postgresql, mysql, etc.
            host = (parts.hostname or "").lower()
            port = parts.port or 5432
            database = parts.path.lstrip("/").lower()

            if not host or not database:
                return False

            # expected_target must be structured as host:port/database or host/database
            exp = expected_target.strip()
            if "://" in exp:
                exp_parts = urlsplit(exp)
                exp_host = (exp_parts.hostname or "").lower()
                exp_port = exp_parts.port or 5432
                exp_db = exp_parts.path.lstrip("/").lower()
                return exp_host == host and exp_port == port and exp_db == database

            if "/" not in exp:
                # Disallow partial identity (host only or db only)
                return False

            exp_host_part, exp_db = exp.split("/", 1)
            exp_db = exp_db.lower()

            if ":" in exp_host_part:
                exp_host, exp_port_str = exp_host_part.split(":", 1)
                try:
                    exp_port = int(exp_port_str)
                except ValueError:
                    return False
            else:
                exp_host = exp_host_part
                exp_port = 5432

            exp_host = exp_host.lower()
            return exp_host == host and exp_port == port and exp_db == database

    except Exception:
        return False


def verify_db_target_and_schema(
    engine: Engine,
    expected_revision: str = "0013_v7_film_catalog_metadata"
) -> None:
    """
    Verifies that the target database schema was prepared via official Alembic migration.
    Rejects:
    - Missing alembic_version table
    - Stale or incorrect Alembic revision
    - Missing film_catalog table
    - Missing required columns
    - Primary key mismatch (must be exactly ['movie_id'])
    - Missing single-column UNIQUE constraint on source_qid (composite-only unique is rejected)
    - Column nullability violations on non-nullable fields
    """
    insp = inspect(engine)

    # 1. Table existence check
    if not insp.has_table("film_catalog"):
        raise RuntimeError("Target table 'film_catalog' does not exist.")

    # 2. Alembic version table check
    if not insp.has_table("alembic_version"):
        raise RuntimeError(
            "Target database is missing 'alembic_version' table. "
            "Direct metadata.create_all() is strictly prohibited; "
            "all schemas must be provisioned via official Alembic migrations."
        )

    with engine.connect() as conn:
        rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if rev != expected_revision:
            raise RuntimeError(
                f"Alembic migration revision mismatch: expected '{expected_revision}', got '{rev}'"
            )

    # 3. Column presence and nullability check
    columns = insp.get_columns("film_catalog")
    col_map = {c["name"]: c for c in columns}
    missing_cols = REQUIRED_COLUMNS - set(col_map.keys())
    if missing_cols:
        raise RuntimeError(f"Target table 'film_catalog' missing required columns: {missing_cols}")

    non_nullable_fields = ["movie_id", "source_qid", "title_en", "year", "source_revision", "source_url", "fetched_at"]
    for field in non_nullable_fields:
        c_info = col_map.get(field)
        if c_info and c_info.get("nullable", True) is not False:
            raise RuntimeError(f"Column 'film_catalog.{field}' must be NON-NULLABLE, but nullable=True detected.")

    # 4. Primary Key constraint
    pk_info = insp.get_pk_constraint("film_catalog")
    if not pk_info or pk_info.get("constrained_columns") != ["movie_id"]:
        raise RuntimeError(
            f"Primary key mismatch on 'film_catalog': expected ['movie_id'], got {pk_info.get('constrained_columns') if pk_info else None}"
        )

    # 5. Single-column UNIQUE constraint or unique index on source_qid
    unique_constraints = insp.get_unique_constraints("film_catalog")
    has_single_col_unique = any(
        uc.get("column_names") == ["source_qid"] for uc in unique_constraints
    )

    if not has_single_col_unique:
        indexes = insp.get_indexes("film_catalog")
        has_single_col_unique = any(
            idx.get("unique", False) and idx.get("column_names") == ["source_qid"]
            for idx in indexes
        )

    if not has_single_col_unique:
        raise RuntimeError(
            "Unique constraint violation: 'film_catalog.source_qid' must have a dedicated single-column UNIQUE constraint or unique index. "
            "Composite unique constraints are strictly rejected."
        )


def compute_canonical_film_diff(row: Any, film: dict) -> Dict[str, Dict[str, Any]]:
    """
    Compare ALL canonical fields between database record and incoming film payload.
    Covers:
    - title_en, title_ko, year, description_en, description_ko, runtime_minutes
    - directors, cast_members, genres, countries, languages
    - source_qid, source_url, core_demo_supported
    - poster_local_path, poster_source_filename, poster_sha256, poster_license
    """
    diffs = {}
    poster = film.get("poster") or {}
    poster_path = film.get("poster_local_path") or poster.get("local_path")
    poster_fn = poster.get("source_filename")
    poster_sha = poster.get("sha256")
    poster_lic = poster.get("license")

    def _norm_list(val):
        if not val:
            return []
        if isinstance(val, (list, set, tuple)):
            try:
                return sorted(list(val), key=lambda x: json.dumps(x, sort_keys=True) if isinstance(x, dict) else str(x))
            except Exception:
                return list(val)
        return [val]

    fields_to_check = [
        ("title_en", row.title_en, film.get("title_en")),
        ("title_ko", row.title_ko, film.get("title_ko")),
        ("year", row.year, film.get("year")),
        ("description_en", row.description_en, film.get("description_en")),
        ("description_ko", row.description_ko, film.get("description_ko")),
        ("runtime_minutes", row.runtime_minutes, film.get("runtime_minutes")),
        ("source_qid", row.source_qid, film.get("qid")),
        ("source_url", row.source_url, film.get("source_url")),
        ("core_demo_supported", bool(row.core_demo_supported), bool(film.get("core_demo_supported", False))),
        ("poster_local_path", row.poster_local_path, poster_path),
        ("poster_source_filename", row.poster_source_filename, poster_fn),
        ("poster_sha256", row.poster_sha256, poster_sha),
        ("poster_license", row.poster_license, poster_lic),
    ]

    for field, old_val, new_val in fields_to_check:
        if old_val != new_val:
            diffs[field] = {"old": old_val, "new": new_val}

    list_fields = [
        ("directors", row.directors, film.get("directors")),
        ("cast_members", row.cast_members, film.get("cast")),
        ("genres", row.genres, film.get("genres")),
        ("countries", row.countries, film.get("countries")),
        ("languages", row.languages, film.get("languages")),
    ]

    for field, old_val, new_val in list_fields:
        norm_old = _norm_list(old_val)
        norm_new = _norm_list(new_val)
        if norm_old != norm_new:
            diffs[field] = {"old": old_val, "new": new_val}

    return diffs


def validate_catalog_payload(catalog_path: Path) -> List[dict]:
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
