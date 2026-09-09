"""
Reframe V7 Film Catalog Repository
Database access layer for public film metadata catalog.
"""
from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import func, or_, select, cast, String, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.reframe.catalog.models import FilmCatalog

BAT_ALIASES = {"the-bat-whispers", "the-bat-whispers-1930", "wd-q3985804"}


class FilmCatalogRepository:
    """Async repository for film catalog persistence."""

    @staticmethod
    async def list_films(
        session: AsyncSession,
        q: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        exclude_movie_ids: Optional[List[str]] = None,
    ) -> Tuple[List[FilmCatalog], int]:
        """List and search films with pagination and total count."""
        stmt = select(FilmCatalog)
        count_stmt = select(func.count()).select_from(FilmCatalog)
        if exclude_movie_ids:
            stmt = stmt.where(FilmCatalog.movie_id.not_in(exclude_movie_ids))
            count_stmt = count_stmt.where(FilmCatalog.movie_id.not_in(exclude_movie_ids))

        if q:
            clean_q = q.strip().lower()
            if clean_q:
                # Escape LIKE special characters %, _, \
                escaped_q = clean_q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                q_like = f"%{escaped_q}%"

                # Check if clean_q is a pure QID (e.g. Q3985804 or q3985804)
                is_qid = bool(re.match(r"^q\d+$", clean_q))

                conditions = [
                    func.lower(FilmCatalog.title_en).like(q_like, escape="\\"),
                    func.lower(FilmCatalog.title_ko).like(q_like, escape="\\"),
                    func.lower(FilmCatalog.source_qid) == clean_q,
                ]

                # If not a QID, also search director names (name_en and name_ko)
                # while strictly avoiding false matches against QIDs.
                if not is_qid:
                    bind = session.get_bind() if hasattr(session, "get_bind") else getattr(session, "bind", None)
                    dialect_name = getattr(bind, "dialect", None).name if bind and hasattr(bind, "dialect") else "sqlite"

                    if dialect_name == "postgresql":
                        director_cond = text(
                            "EXISTS (SELECT 1 FROM json_array_elements(film_catalog.directors) d "
                            "WHERE (lower(coalesce(d->>'name_en', '')) LIKE :q_like ESCAPE '\\') "
                            "OR (lower(coalesce(d->>'name_ko', '')) LIKE :q_like ESCAPE '\\'))"
                        ).bindparams(q_like=q_like)
                    else:
                        director_cond = text(
                            "EXISTS (SELECT 1 FROM json_each(film_catalog.directors) "
                            "WHERE (lower(coalesce(json_extract(value, '$.name_en'), '')) LIKE :q_like ESCAPE '\\') "
                            "OR (lower(coalesce(json_extract(value, '$.name_ko'), '')) LIKE :q_like ESCAPE '\\'))"
                        ).bindparams(q_like=q_like)
                    conditions.append(director_cond)

                filter_cond = or_(*conditions)
                stmt = stmt.where(filter_cond)
                count_stmt = count_stmt.where(filter_cond)

        # Deterministic sort: The Bat Whispers first, then chronological by year, then movie_id
        stmt = stmt.order_by(
            FilmCatalog.core_demo_supported.desc(),
            FilmCatalog.year.asc(),
            FilmCatalog.movie_id.asc(),
        )

        total = await session.scalar(count_stmt) or 0

        # Safe pagination
        safe_offset = max(0, offset)
        safe_limit = min(max(1, limit), 50)
        stmt = stmt.offset(safe_offset).limit(safe_limit)

        result = await session.scalars(stmt)
        return list(result.all()), total

    @staticmethod
    async def get_film_by_id(
        session: AsyncSession,
        movie_id: str,
    ) -> Optional[FilmCatalog]:
        """Lookup a film by movie_id, supporting legacy Bat Whispers aliases."""
        target_id = movie_id
        if movie_id.lower() in BAT_ALIASES:
            target_id = "the-bat-whispers-1930"

        stmt = select(FilmCatalog).where(
            or_(
                FilmCatalog.movie_id == target_id,
                FilmCatalog.source_qid == target_id.upper(),
            )
        )
        return await session.scalar(stmt)

    @staticmethod
    def sync_import_films(
        session: Session,
        films_data: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """
        Synchronous batch import of harvested film catalog records.
        Executed in a single transaction.
        Invariants:
        - Same ID/QID/revision/content: no-op (skipped).
        - ID/QID conflict: explicitly rejected.
        - Same revision with mutated content: explicitly rejected.
        - Different revision overwrite of existing row: explicitly rejected.
        """
        # 1. Pre-validate all inputs before database operations
        seen_ids = set()
        seen_qids = set()
        for idx, f in enumerate(films_data):
            m_id = f.get("movie_id")
            qid = f.get("qid")
            t_en = f.get("title_en")
            s_rev = f.get("source_revision")
            f_utc = f.get("fetched_at_utc")

            if not m_id or not isinstance(m_id, str) or not m_id.strip():
                raise ValueError(f"Invalid catalog record at index {idx}: missing movie_id")
            if not qid or not isinstance(qid, str) or not qid.strip():
                raise ValueError(f"Invalid catalog record at index {idx}: missing qid")
            if not t_en or not isinstance(t_en, str) or not t_en.strip():
                raise ValueError(f"Invalid catalog record at index {idx}: missing title_en")
            if s_rev is None:
                raise ValueError(f"Invalid catalog record at index {idx}: missing source_revision")
            if not f_utc:
                raise ValueError(f"Invalid catalog record at index {idx}: missing fetched_at_utc")

            if m_id in seen_ids:
                raise ValueError(f"Duplicate movie_id '{m_id}' in import payload")
            if qid in seen_qids:
                raise ValueError(f"Duplicate source_qid '{qid}' in import payload")
            seen_ids.add(m_id)
            seen_qids.add(qid)

        inserted = 0
        skipped = 0

        # 2. Process all records atomically
        for f in films_data:
            movie_id = f["movie_id"].strip()
            qid = f["qid"].strip()
            poster = f.get("poster") or {}

            existing_by_id = session.query(FilmCatalog).filter(FilmCatalog.movie_id == movie_id).first()
            existing_by_qid = session.query(FilmCatalog).filter(FilmCatalog.source_qid == qid).first()

            # ID / QID conflict checks
            if existing_by_id and existing_by_id.source_qid != qid:
                raise ValueError(
                    f"ID/QID conflict: movie_id '{movie_id}' is already registered with QID '{existing_by_id.source_qid}', cannot associate with '{qid}'"
                )
            if existing_by_qid and existing_by_qid.movie_id != movie_id:
                raise ValueError(
                    f"ID/QID conflict: source_qid '{qid}' is already registered with movie_id '{existing_by_qid.movie_id}', cannot associate with '{movie_id}'"
                )

            if existing_by_id:
                # Revision check
                if existing_by_id.source_revision != f["source_revision"]:
                    raise ValueError(
                        f"Revision overwrite rejected: movie_id '{movie_id}' has existing revision '{existing_by_id.source_revision}', overwriting with different revision '{f['source_revision']}' is prohibited"
                    )

                # Comprehensive canonical content mutation check under identical revision
                diffs = []
                if existing_by_id.title_en != f.get("title_en"):
                    diffs.append("title_en")
                if existing_by_id.title_ko != f.get("title_ko"):
                    diffs.append("title_ko")
                if existing_by_id.year != f.get("year"):
                    diffs.append("year")
                if existing_by_id.description_en != f.get("description_en"):
                    diffs.append("description_en")
                if existing_by_id.description_ko != f.get("description_ko"):
                    diffs.append("description_ko")
                if existing_by_id.runtime_minutes != f.get("runtime_minutes"):
                    diffs.append("runtime_minutes")
                if existing_by_id.directors != f.get("directors", []):
                    diffs.append("directors")
                if existing_by_id.cast_members != f.get("cast", []):
                    diffs.append("cast")
                if existing_by_id.genres != f.get("genres", []):
                    diffs.append("genres")
                if existing_by_id.countries != f.get("countries", []):
                    diffs.append("countries")
                if existing_by_id.languages != f.get("languages", []):
                    diffs.append("languages")
                if existing_by_id.core_demo_supported != bool(f.get("core_demo_supported", False)):
                    diffs.append("core_demo_supported")
                if existing_by_id.poster_local_path != poster.get("local_path"):
                    diffs.append("poster_local_path")
                if existing_by_id.poster_source_filename != poster.get("source_filename"):
                    diffs.append("poster_source_filename")
                if existing_by_id.poster_sha256 != poster.get("sha256"):
                    diffs.append("poster_sha256")
                if existing_by_id.poster_license != poster.get("license"):
                    diffs.append("poster_license")
                if existing_by_id.source_url != f.get("source_url"):
                    diffs.append("source_url")

                if diffs:
                    raise ValueError(
                        f"Content mutation rejected: movie_id '{movie_id}' has modified fields ({', '.join(diffs)}) under unchanged revision '{existing_by_id.source_revision}'"
                    )

                # Exactly identical: idempotent no-op (preserve existing row and timestamps)
                skipped += 1
                continue

            # New entry creation
            fetched_at_dt = datetime.datetime.fromisoformat(f["fetched_at_utc"])
            entry = FilmCatalog(
                movie_id=movie_id,
                source_qid=qid,
                title_en=f["title_en"],
                title_ko=f.get("title_ko"),
                year=f.get("year"),
                description_en=f.get("description_en"),
                description_ko=f.get("description_ko"),
                runtime_minutes=f.get("runtime_minutes"),
                directors=f.get("directors", []),
                cast_members=f.get("cast", []),
                genres=f.get("genres", []),
                countries=f.get("countries", []),
                languages=f.get("languages", []),
                core_demo_supported=f.get("core_demo_supported", False),
                poster_local_path=poster.get("local_path"),
                poster_source_filename=poster.get("source_filename"),
                poster_sha256=poster.get("sha256"),
                poster_license=poster.get("license"),
                source_revision=f["source_revision"],
                source_url=f["source_url"],
                fetched_at=fetched_at_dt,
            )
            session.add(entry)
            inserted += 1

        session.flush()
        return {"inserted": inserted, "updated": 0, "skipped": skipped, "total": len(films_data)}
