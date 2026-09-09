"""
Reframe V7 Catalog Service — Multi-Film Analysis & Capability Layer
Supports The Bat Whispers (1930) and candidate demonstration films
(Detour, D.O.A., The Stranger) with strict catalog isolation and zero future scene leakage.
"""
import os
import json
from typing import List, Optional, Dict, Any
import structlog

from src.reframe.shared.config import settings
from src.reframe.catalog.schemas import FilmSummaryDTO, FilmDetailDTO, RevealSummaryDTO, RevealDetailDTO
from src.reframe.identity.auth import ViewerContext
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility

logger = structlog.get_logger(__name__)

# Canonical Film Catalog Entry for The Bat Whispers
THE_BAT_WHISPERS_FILM: Dict[str, Any] = {
    "movie_id": "the-bat-whispers-1930",
    "edition_id": "tbw-fullscreen-archive",
    "title": "The Bat Whispers",
    "year": 1930,
    "synopsis_safe": "A mysterious cloaked criminal known as 'The Bat' terrorizes a country estate while searching for stolen bank loot.",
    "runtime_ms": 5119080,  # Canonical asset manifest: 85m 19.08s
    "rights_status": "PUBLIC_DOMAIN",
    "analysis_status": "READY",
    "canonical_asset_sha256": settings.CANONICAL_ASSET_SHA256,
    "dataset_version": settings.DEFAULT_DATASET_VERSION,
    "reveals_count": 4,
    "scenes_count": 43,
    "available_modes": ["STRICT_CANON", "DEEP_READING", "THEORY_LAB"]
}

# Registered candidate demo films (P1 multi-film pipeline)
# Rights status and canonical hashes require independent verification.
CANDIDATE_DEMO_FILMS: Dict[str, Dict[str, Any]] = {
    "detour-1945": {
        "movie_id": "detour-1945",
        "edition_id": "detour-ia-Detour-mp4",
        "title": "Detour",
        "year": 1945,
        "synopsis_safe": "A hitchhiker heading to Hollywood takes over a dead driver's identity and becomes trapped in blackmail.",
        "runtime_ms": 4058320,  # 01:07:38.320 unconfirmed metadata duration
        "rights_status": "UNCONFIRMED",
        "analysis_status": "PREPARING",
        "canonical_asset_sha256": None,
        "dataset_version": "v1.0.0",
        "reveals_count": 0,
        "scenes_count": 0,
        "available_modes": ["STRICT_CANON"]
    },
    "doa-1950": {
        "movie_id": "doa-1950",
        "edition_id": "doa-ia-quality-upgrade",
        "title": "D.O.A.",
        "year": 1950,
        "synopsis_safe": "A small-town accountant arrives at a police station to report his own murder after being fatally poisoned.",
        "runtime_ms": 5018280,  # 01:23:38.280 unconfirmed metadata duration
        "rights_status": "UNCONFIRMED",
        "analysis_status": "PREPARING",
        "canonical_asset_sha256": None,
        "dataset_version": "v1.0.0",
        "reveals_count": 0,
        "scenes_count": 0,
        "available_modes": ["STRICT_CANON"]
    },
    "the-stranger-1946": {
        "movie_id": "the-stranger-1946",
        "edition_id": "the-stranger-ia-TheStranger_0",
        "title": "The Stranger",
        "year": 1946,
        "synopsis_safe": "A war crimes investigator arrives in Connecticut seeking an escaped architect of the atrocities hiding under an alias.",
        "runtime_ms": 5472940,  # 01:31:12.940 unconfirmed metadata duration (edition length varies)
        "rights_status": "UNCONFIRMED",
        "analysis_status": "PREPARING",
        "canonical_asset_sha256": None,
        "dataset_version": "v1.0.0",
        "reveals_count": 0,
        "scenes_count": 0,
        "available_modes": ["STRICT_CANON"]
    }
}

SAFE_REVEAL_PREVIEWS: Dict[str, Dict[str, str]] = {
    "reveal-anderson-identity": {
        "safe_title": "Key Climax Revelation (01:21:00)",
        "safe_preview": "The master criminal's identity revelation at the climax of the investigation."
    },
    "reveal-secret-room-location": {
        "safe_title": "Hidden Room Revelation (00:46:15)",
        "safe_preview": "The architectural layout and secret compartments within the Fleming manor."
    },
    "reveal-brooks-innocence": {
        "safe_title": "Gardener Allegiance Revelation (01:02:40)",
        "safe_preview": "The motives and true background of the gardener in the household."
    },
    "reveal-masked-robbery-vault": {
        "safe_title": "Oakdale Bank Vault Revelation (00:15:20)",
        "safe_preview": "The sequence and circumstances surrounding the Oakdale bank robbery."
    }
}


def load_reveals_from_disk() -> List[dict]:
    registry_path = os.path.join(os.path.dirname(__file__), "../../../data/production/reveals_registry.json")
    if os.path.exists(registry_path):
        with open(registry_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


from src.reframe.catalog.runtime_state import synchronized


class CatalogService:
    def __init__(self):
        # In-memory registry keyed by composite (movie_id, edition_id)
        self._dynamic_films: Dict[tuple, Dict[str, Any]] = {}
        self._film_editions: Dict[str, List[str]] = {}
        self._primary_editions: Dict[str, str] = {}
        self._dynamic_reveals: Dict[tuple, List[dict]] = {}
        self._reveal_to_movie_edition: Dict[str, tuple] = {}
        self._dynamic_previews: Dict[str, Dict[str, str]] = {}

    def normalize_movie_id(self, movie_id: str) -> str:
        """
        Normalizes known alias identifiers for The Bat Whispers to its canonical ID.
        Strictly preserves all other movie IDs (never converts unknown IDs to Bat Whispers).
        """
        clean = (movie_id or "").strip().lower()
        if clean in ("the-bat-whispers", "the-bat-whispers-1930", "wd-q3985804"):
            return "the-bat-whispers-1930"
        return clean

    @synchronized
    def register_film_dataset(
        self,
        movie_id: str,
        film_entry: Dict[str, Any],
        reveals: Optional[List[dict]] = None,
        safe_previews: Optional[Dict[str, Dict[str, str]]] = None
    ) -> None:
        """
        Allows programmatic registration of analysis datasets with strict validation.
        Enforces composite (movie_id, edition_id) keying, valid positive runtime,
        reveals ownership matching, and duplicate/conflict rejection.
        """
        norm_id = self.normalize_movie_id(movie_id)
        if not norm_id:
            raise ValueError("movie_id cannot be empty or whitespace-only.")

        edition_id = str(film_entry.get("edition_id") or "").strip()
        if not edition_id:
            raise ValueError("edition_id cannot be empty or whitespace-only in film_entry.")

        entry_movie = str(film_entry.get("movie_id") or "").strip()
        if entry_movie and self.normalize_movie_id(entry_movie) != norm_id:
            raise ValueError(f"film_entry movie_id '{entry_movie}' does not match registered movie_id '{norm_id}'.")

        runtime_ms = film_entry.get("runtime_ms")
        if runtime_ms is None or not isinstance(runtime_ms, int) or runtime_ms <= 0:
            raise ValueError(f"runtime_ms must be a positive integer, got '{runtime_ms}'.")

        composite_key = (norm_id, edition_id)
        if composite_key == (THE_BAT_WHISPERS_FILM["movie_id"], THE_BAT_WHISPERS_FILM["edition_id"]):
            raise ValueError("The built-in edition cannot be replaced by a dataset import.")

        # Validate reveals
        validated_reveals: List[dict] = []
        if reveals is not None:
            seen_rev_ids = set()
            for idx, r in enumerate(reveals):
                rev_id = str(r.get("reveal_id") or "").strip()
                if not rev_id:
                    raise ValueError(f"Reveal #{idx} has empty or whitespace-only reveal_id.")
                if rev_id in seen_rev_ids:
                    raise ValueError(f"Duplicate reveal_id '{rev_id}' within registration.")
                seen_rev_ids.add(rev_id)
                if rev_id in SAFE_REVEAL_PREVIEWS:
                    raise ValueError(f"Reserved reveal ID '{rev_id}'.")

                # Check conflict with previously registered reveals from other film/editions
                if rev_id in self._reveal_to_movie_edition:
                    prev_owner = self._reveal_to_movie_edition[rev_id]
                    if prev_owner != composite_key:
                        raise ValueError(
                            f"Reveal ID '{rev_id}' conflicts with existing registration for movie/edition {prev_owner}."
                        )

                # Validate movie_id and edition_id on the reveal record
                r_movie = r.get("movie_id")
                if r_movie and self.normalize_movie_id(r_movie) != norm_id:
                    raise ValueError(
                        f"Reveal '{rev_id}' movie_id '{r_movie}' does not match target movie '{norm_id}'."
                    )

                r_edition = r.get("edition_id")
                if r_edition and r_edition != edition_id:
                    raise ValueError(
                        f"Reveal '{rev_id}' edition_id '{r_edition}' does not match target edition '{edition_id}'."
                    )

                r_ts = r.get("timestamp_ms", 0)
                r_cutoff = r.get("spoiler_cutoff_ms", r_ts)
                if r_ts > runtime_ms:
                    raise ValueError(
                        f"Reveal '{rev_id}' timestamp {r_ts}ms exceeds edition runtime {runtime_ms}ms."
                    )
                if r_cutoff > runtime_ms:
                    raise ValueError(
                        f"Reveal '{rev_id}' cutoff {r_cutoff}ms exceeds edition runtime {runtime_ms}ms."
                    )

                clean_rev = dict(r)
                clean_rev["reveal_id"] = rev_id
                clean_rev["movie_id"] = norm_id
                clean_rev["edition_id"] = edition_id
                validated_reveals.append(clean_rev)

        # Validate safe previews
        if safe_previews:
            for rev_id, meta in safe_previews.items():
                if rev_id in self._reveal_to_movie_edition:
                    prev_owner = self._reveal_to_movie_edition[rev_id]
                    if prev_owner != composite_key:
                        raise ValueError(
                            f"safe_preview for '{rev_id}' conflicts with reveal registered for {prev_owner}."
                        )

        # Store entry
        stored_entry = dict(film_entry)
        stored_entry["movie_id"] = norm_id
        stored_entry["edition_id"] = edition_id
        existing = self._dynamic_films.get(composite_key)
        if existing is not None and (existing != stored_entry
                or self._dynamic_reveals.get(composite_key, []) != validated_reveals):
            raise ValueError(f"Conflicting edition registration: {composite_key}")
        self._dynamic_films[composite_key] = stored_entry

        if norm_id not in self._film_editions:
            self._film_editions[norm_id] = []
        if edition_id not in self._film_editions[norm_id]:
            self._film_editions[norm_id].append(edition_id)

        if norm_id not in self._primary_editions:
            self._primary_editions[norm_id] = edition_id

        if reveals is not None:
            self._dynamic_reveals[composite_key] = validated_reveals
            for r in validated_reveals:
                self._reveal_to_movie_edition[r["reveal_id"]] = composite_key

        if safe_previews:
            self._dynamic_previews.update(safe_previews)

    @synchronized
    def get_film_entry(self, norm_id: str, edition_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Resolves film entry strictly respecting edition_id if provided, or registered primary."""
        if norm_id == THE_BAT_WHISPERS_FILM["movie_id"]:
            if edition_id is None or edition_id == THE_BAT_WHISPERS_FILM["edition_id"]:
                return THE_BAT_WHISPERS_FILM
            if (norm_id, edition_id) in self._dynamic_films:
                return self._dynamic_films[(norm_id, edition_id)]
            return None

        if edition_id is not None:
            if (norm_id, edition_id) in self._dynamic_films:
                return self._dynamic_films[(norm_id, edition_id)]
            if norm_id in CANDIDATE_DEMO_FILMS and CANDIDATE_DEMO_FILMS[norm_id]["edition_id"] == edition_id:
                return CANDIDATE_DEMO_FILMS[norm_id]
            return None

        # When edition_id is None, return primary registered edition
        if norm_id in self._primary_editions:
            primary_ed = self._primary_editions[norm_id]
            return self._dynamic_films.get((norm_id, primary_ed))
        if norm_id in CANDIDATE_DEMO_FILMS:
            return CANDIDATE_DEMO_FILMS[norm_id]
        return None

    def is_film_registered(self, movie_id: str, edition_id: Optional[str] = None) -> bool:
        norm_id = self.normalize_movie_id(movie_id)
        return self.get_film_entry(norm_id, edition_id) is not None

    @synchronized
    def get_imported_entries(self) -> List[Dict[str, Any]]:
        from copy import deepcopy
        return [deepcopy(self._dynamic_films[(movie, edition)])
                for movie, edition in sorted(self._primary_editions.items())]

    def get_film_summary(self, movie_id: str = "the-bat-whispers-1930", edition_id: Optional[str] = None) -> Optional[FilmSummaryDTO]:
        norm_id = self.normalize_movie_id(movie_id)
        film_data = self.get_film_entry(norm_id, edition_id)
        if film_data:
            return FilmSummaryDTO(**film_data)
        return None

    def get_film_detail(self, movie_id: str, viewer: ViewerContext, edition_id: Optional[str] = None) -> Optional[FilmDetailDTO]:
        norm_id = self.normalize_movie_id(movie_id)
        film_data = self.get_film_entry(norm_id, edition_id)
        if not film_data:
            return None

        actual_edition = film_data.get("edition_id")
        progress_key = f"{norm_id}:{actual_edition}"
        progress_ms = viewer.work_progress_by_edition.get(progress_key, 0)
        state = "WATCHING" if progress_ms > 0 else "NOT_STARTED"
        runtime_ms = film_data.get("runtime_ms", 0)
        if runtime_ms > 0 and progress_ms >= runtime_ms:
            state = "COMPLETED"

        data = dict(film_data)
        data["viewer_progress_ms"] = progress_ms
        data["viewer_state"] = state
        return FilmDetailDTO(**data)

    @synchronized
    def get_reveals(self, movie_id: str, viewer: ViewerContext, edition_id: Optional[str] = None) -> List[RevealSummaryDTO]:
        """
        Retrieves reveals strictly for the requested movie_id and edition_id.
        Does NOT leak Bat Whispers reveals or other editions.
        """
        norm_id = self.normalize_movie_id(movie_id)
        target_edition = edition_id

        if target_edition is None:
            film_entry = self.get_film_entry(norm_id, None)
            if not film_entry:
                return []
            target_edition = film_entry.get("edition_id")

        raw_reveals: List[dict] = []
        if norm_id == THE_BAT_WHISPERS_FILM["movie_id"] and target_edition == THE_BAT_WHISPERS_FILM["edition_id"]:
            raw_reveals = load_reveals_from_disk()
        elif (norm_id, target_edition) in self._dynamic_reveals:
            raw_reveals = self._dynamic_reveals[(norm_id, target_edition)]
        else:
            return []

        result = []
        for r in raw_reveals:
            # Enforce movie_id and edition_id match
            rec_movie = r.get("movie_id")
            if rec_movie and self.normalize_movie_id(rec_movie) != norm_id:
                continue
            rec_edition = r.get("edition_id")
            if rec_edition and rec_edition != target_edition:
                continue

            rev_id = r["reveal_id"]
            ts = r["timestamp_ms"]
            cutoff_ms = r.get("spoiler_cutoff_ms", ts)
            ed_id = rec_edition or target_edition
            from src.reframe.spoiler.analysis_boundary import retrospective_cutoff, analysis_visibility, SEPARATED_ANALYSIS_EDITIONS
            entry = self.get_film_entry(norm_id, ed_id) or {}
            cutoff_ms = retrospective_cutoff(norm_id, ed_id, cutoff_ms, entry.get('runtime_ms'))

            safe_meta = self._dynamic_previews.get(rev_id) or SAFE_REVEAL_PREVIEWS.get(rev_id, {
                "safe_title": r.get("safe_title", "Key narrative twist"),
                "safe_preview": r.get("safe_preview", "A pivotal story revelation.")
            })

            if (norm_id, ed_id) in SEPARATED_ANALYSIS_EDITIONS:
                safe_meta = {'safe_title':'Post-reveal reinterpretation',
                             'safe_preview':'Full-film context stays hidden until this edition has been watched.'}
            scope = SpoilerScope(
                work_id=norm_id,
                edition_id=ed_id,
                minimum_progress_ms=cutoff_ms,
                required_reveal_ids=[rev_id],
                severity=r.get("severity", "MAJOR"),
                safe_title=safe_meta["safe_title"],
                safe_preview=safe_meta["safe_preview"]
            )

            visibility = analysis_visibility(scope, viewer)
            is_locked = (visibility != SpoilerVisibility.VISIBLE)
            item = {
                "reveal_id": rev_id,
                "work_id": norm_id,
                "edition_id": ed_id,
                "title": r["title"] if not is_locked else safe_meta["safe_title"],
                "timestamp_ms": ts,
                "spoiler_cutoff_ms": cutoff_ms,
                "severity": r.get("severity", "MAJOR"),
                "safe_title": safe_meta["safe_title"],
                "visibility": visibility,
                "is_locked": is_locked,
                "safe_preview": {
                    "title": safe_meta["safe_title"],
                    "summary": safe_meta["safe_preview"] if is_locked else None
                }
            }
            result.append(RevealSummaryDTO(**item))

        return result

    @synchronized
    def get_reveal_by_id(
        self,
        reveal_id: str,
        viewer: ViewerContext,
        movie_id: Optional[str] = None,
        edition_id: Optional[str] = None
    ) -> Optional[RevealDetailDTO]:
        norm_id = self.normalize_movie_id(movie_id) if movie_id else None

        all_reveals = []
        if not norm_id or (norm_id == THE_BAT_WHISPERS_FILM["movie_id"] and (not edition_id or edition_id == THE_BAT_WHISPERS_FILM["edition_id"])):
            all_reveals.extend(load_reveals_from_disk())

        if norm_id and edition_id:
            if (norm_id, edition_id) in self._dynamic_reveals:
                all_reveals.extend(self._dynamic_reveals[(norm_id, edition_id)])
        elif norm_id:
            for (m_id, ed_id), rev_list in self._dynamic_reveals.items():
                if m_id == norm_id:
                    all_reveals.extend(rev_list)
        else:
            for rev_list in self._dynamic_reveals.values():
                all_reveals.extend(rev_list)

        match = next((r for r in all_reveals if r["reveal_id"] == reveal_id), None)
        if not match:
            return None

        match_movie = self.normalize_movie_id(match.get("movie_id", THE_BAT_WHISPERS_FILM["movie_id"]))
        if norm_id and match_movie != norm_id:
            return None

        match_edition = match.get("edition_id", THE_BAT_WHISPERS_FILM["edition_id"])
        if edition_id and match_edition != edition_id:
            return None

        safe_meta = self._dynamic_previews.get(reveal_id) or SAFE_REVEAL_PREVIEWS.get(reveal_id, {
            "safe_title": match.get("safe_title", "Key narrative twist"),
            "safe_preview": match.get("safe_preview", "A pivotal story revelation.")
        })

        ts = match["timestamp_ms"]
        cutoff_ms = match.get("spoiler_cutoff_ms", ts)
        from src.reframe.spoiler.analysis_boundary import retrospective_cutoff, analysis_visibility, SEPARATED_ANALYSIS_EDITIONS
        entry = self.get_film_entry(match_movie, match_edition) or {}
        cutoff_ms = retrospective_cutoff(match_movie, match_edition, cutoff_ms, entry.get('runtime_ms'))
        if (match_movie, match_edition) in SEPARATED_ANALYSIS_EDITIONS:
            safe_meta = {'safe_title':'Post-reveal reinterpretation',
                         'safe_preview':'Full-film context stays hidden until this edition has been watched.'}

        scope = SpoilerScope(
            work_id=match_movie,
            edition_id=match_edition,
            minimum_progress_ms=cutoff_ms,
            required_reveal_ids=[reveal_id],
            severity=match.get("severity", "MAJOR"),
            safe_title=safe_meta["safe_title"],
            safe_preview=safe_meta["safe_preview"]
        )

        visibility = analysis_visibility(scope, viewer)
        is_locked = (visibility != SpoilerVisibility.VISIBLE)

        item = {
            "reveal_id": reveal_id,
            "work_id": match_movie,
            "edition_id": match_edition,
            "title": match["title"] if not is_locked else safe_meta["safe_title"],
            "timestamp_ms": ts,
            "spoiler_cutoff_ms": cutoff_ms,
            "severity": match.get("severity", "MAJOR"),
            "safe_title": safe_meta["safe_title"],
            "visibility": visibility,
            "is_locked": is_locked,
            "description": match.get("revealed_fact") if not is_locked else None,
            "proof_types": match.get("proof_types", ["KNOWLEDGE_LEAK", "CLAIM_ACTION_CONFLICT"]),
            "proof_count": match.get("proof_count", 0),
            "safe_preview": {
                "title": safe_meta["safe_title"],
                "summary": safe_meta["safe_preview"] if is_locked else None
            }
        }
        return RevealDetailDTO(**item)

    @synchronized
    def validate_watch_progress(
        self,
        work_id: str,
        edition_id: str,
        progress_ms: int,
        completed_reveal_ids: List[str]
    ) -> None:
        """
        Validates watch progress inputs strictly against (work_id, edition_id).
        Rejects unverified editions, runtime <= 0, out-of-bounds progress, or foreign reveal IDs.
        """
        norm_id = self.normalize_movie_id(work_id)
        clean_edition = (edition_id or "").strip()
        if not clean_edition:
            raise ValueError(f"Missing or invalid edition_id for work '{work_id}'.")

        film_data = self.get_film_entry(norm_id, clean_edition)
        if not film_data:
            raise ValueError(
                f"Edition '{clean_edition}' is not registered for work '{norm_id}'. Cannot record watch progress."
            )

        runtime_ms = film_data.get("runtime_ms")
        if runtime_ms is None or not isinstance(runtime_ms, int) or runtime_ms <= 0:
            raise ValueError(
                f"Invalid runtime ({runtime_ms}) for work '{norm_id}', edition '{clean_edition}'. Cannot save watch progress."
            )

        if progress_ms < 0 or progress_ms > runtime_ms:
            raise ValueError(f"Progress ms {progress_ms} out of valid bounds (0 to {runtime_ms}).")

        # Determine valid reveals strictly for (norm_id, clean_edition)
        valid_reveal_ids = set()
        if norm_id == THE_BAT_WHISPERS_FILM["movie_id"] and clean_edition == THE_BAT_WHISPERS_FILM["edition_id"]:
            valid_reveal_ids = set(SAFE_REVEAL_PREVIEWS.keys())
        elif (norm_id, clean_edition) in self._dynamic_reveals:
            valid_reveal_ids = {r["reveal_id"] for r in self._dynamic_reveals[(norm_id, clean_edition)]}

        for rev_id in completed_reveal_ids:
            if rev_id not in valid_reveal_ids:
                raise ValueError(
                    f"Invalid completed reveal ID '{rev_id}' for work '{norm_id}', edition '{clean_edition}'."
                )


catalog_service = CatalogService()
