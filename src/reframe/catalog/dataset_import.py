import os
import re
import json
import hashlib
import tempfile
from copy import deepcopy
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Dict, Any, List, Literal, Optional, Tuple
import structlog
from pydantic import BaseModel, Field, field_validator

from src.reframe.catalog.service import catalog_service
from src.reframe.catalog.runtime_state import synchronized

ROOT = Path(__file__).resolve().parents[3]
logger = structlog.get_logger(__name__)


class MovieDatasetItem(BaseModel):
    movie_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    year: int = Field(ge=1880, le=2100)
    synopsis_safe: str = Field(min_length=1)
    runtime_ms: int = Field(gt=0)
    rights_status: Literal["UNCONFIRMED", "PUBLIC_DOMAIN", "APPROVED"] = "UNCONFIRMED"
    analysis_status: Literal["PREPARING", "READY"] = "PREPARING"
    poster_path: Optional[str] = None
    directors: List[str] = Field(default_factory=list)
    cast: List[str] = Field(default_factory=list)
    genres: List[str] = Field(default_factory=list)


class EditionDatasetItem(BaseModel):
    edition_id: str = Field(min_length=1, max_length=100)
    movie_id: str = Field(min_length=1, max_length=100)
    runtime_ms: int = Field(gt=0)
    dataset_version: str = Field(default="v1.0.0")
    source_url: Optional[str] = None
    asset_sha256: Optional[str] = None
    rights_review_status: str = Field(default="PENDING")


class SubtitleCueItem(BaseModel):
    cue_index: int = Field(ge=1)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str = Field(min_length=1)

    @field_validator("end_ms")
    @classmethod
    def check_monotonic(cls, v: int, info) -> int:
        start = info.data.get("start_ms", 0)
        if v <= start:
            raise ValueError(f"end_ms ({v}) must be greater than start_ms ({start})")
        return v


class RevealDatasetItem(BaseModel):
    reveal_id: str = Field(min_length=1, max_length=100)
    movie_id: str = Field(min_length=1, max_length=100)
    edition_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1)
    safe_title: str = Field(min_length=1)
    safe_preview: str = Field(min_length=1)
    timestamp_ms: int = Field(ge=0)
    spoiler_cutoff_ms: int = Field(ge=0)
    revealed_fact: Optional[str] = None
    severity: str = Field(default="MAJOR")


class ProofPremiseItem(BaseModel):
    event_id: str
    scene_id: str
    timestamp_ms: int = Field(ge=0)
    actor: str
    action: str
    fact: str
    frame_ids: List[str] = Field(default_factory=list)


class ProofDatasetItem(BaseModel):
    proof_id: str = Field(min_length=1, max_length=100)
    movie_id: str = Field(min_length=1, max_length=100)
    edition_id: str = Field(min_length=1, max_length=100)
    reveal_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    timestamp_ms: int = Field(ge=0)
    spoiler_cutoff_ms: int = Field(ge=0)
    observed_premises: List[ProofPremiseItem] = Field(default_factory=list)
    safe_preview_title: str = Field(default="Spoiler-protected content")
    safe_preview_summary: str = Field(default="Content hidden behind spoiler protection.")
    trust_namespace: str = Field(default="ENGINE_INFERENCE")
    verification_status: str = Field(default="UNVERIFIED")
    human_review_status: Literal["NOT_REVIEWED", "APPROVED"] = "NOT_REVIEWED"
    presentation_status: Literal["HIDDEN_FROM_PUBLIC", "PUBLIC"] = "HIDDEN_FROM_PUBLIC"
    proof_type: str = "MULTI_SCENE_PATTERN"
    blind_explanation: str = ""
    reveal_explanation: Optional[str] = None
    evidence_chain: List[Dict[str, Any]] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)


class FrameDatasetItem(BaseModel):
    frame_id: str = Field(min_length=1, max_length=100)
    movie_id: str = Field(min_length=1, max_length=100)
    edition_id: str = Field(min_length=1, max_length=100)
    absolute_timestamp_ms: int = Field(ge=0)
    filename: str = Field(min_length=1)


class SceneDatasetItem(BaseModel):
    scene_id: str = Field(min_length=1, max_length=100)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class MediaDatasetItem(BaseModel):
    filename: str = Field(min_length=1)
    asset_status: Literal["PENDING", "APPROVED"] = "PENDING"


class AIProofPublicationItem(BaseModel):
    """An operator-pinned semantic digest, not permission to claim human review."""
    proof_id: str = Field(min_length=1, max_length=100)
    record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FilmDatasetBundle(BaseModel):
    film: MovieDatasetItem
    edition: EditionDatasetItem
    subtitles: List[SubtitleCueItem] = Field(default_factory=list)
    reveals: List[RevealDatasetItem] = Field(default_factory=list)
    proofs: List[ProofDatasetItem] = Field(default_factory=list)
    frames: List[FrameDatasetItem] = Field(default_factory=list)
    scenes: List[SceneDatasetItem] = Field(default_factory=list)
    media: Optional[MediaDatasetItem] = None
    ai_publications: List[AIProofPublicationItem] = Field(default_factory=list)


def validate_film_dataset(bundle_dict: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates a complete film dataset bundle against Reframe architecture invariants:
    - Zero future scene leakage (proof premise <= cutoff <= runtime)
    - Runtime bounds consistency
    - Foreign-key consistency between movie, edition, reveal, and proof items
    - Non-empty, non-whitespace ID verification
    - Uniqueness of reveal_id, proof_id, frame_id, and subtitle cue_index
    - Strict frame filename path traversal & absolute path prohibition
    - Chronological ordering of subtitle cues
    - Real SHA-256 formatting check; prohibition of placeholder/pending strings
    - Status-specific requirements (PUBLIC_DOMAIN / READY require certified hashes and source_url)
    - Exact runtime reconciliation between film and edition
    Returns (is_valid, list_of_error_messages).
    """
    errors: List[str] = []

    try:
        bundle = FilmDatasetBundle(**bundle_dict)
    except Exception as exc:
        return False, [f"Schema validation error: {str(exc)}"]

    movie_id = bundle.film.movie_id.strip()
    edition_id = bundle.edition.edition_id.strip()
    runtime_ms = bundle.edition.runtime_ms
    for label, value in (("movie_id", bundle.film.movie_id), ("edition_id", bundle.edition.edition_id)):
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", value):
            errors.append(f"Invalid {label}: use lowercase letters, digits, hyphens and underscores only.")

    if not movie_id:
        errors.append("Film movie_id cannot be whitespace-only.")
    if not edition_id:
        errors.append("Edition edition_id cannot be whitespace-only.")

    if bundle.edition.movie_id != movie_id:
        errors.append(
            f"Edition movie_id mismatch: edition specifies '{bundle.edition.movie_id}' but film is '{movie_id}'"
        )

    # Runtime consistency check
    if bundle.film.runtime_ms != runtime_ms:
        errors.append(
            f"Film runtime_ms ({bundle.film.runtime_ms}) does not match edition runtime_ms ({runtime_ms})."
        )

    # SHA-256 format and placeholder validation
    sha = bundle.edition.asset_sha256
    if sha is not None:
        if not isinstance(sha, str) or not re.match(r"^[a-fA-F0-9]{64}$", sha):
            errors.append(
                f"Invalid asset_sha256 format '{sha}'. Must be a 64-character lowercase hex hash; placeholder/pending strings are rejected."
            )

    # Rights & Analysis Status requirements
    if bundle.film.rights_status in ("PUBLIC_DOMAIN", "APPROVED"):
        if not sha or not re.match(r"^[a-fA-F0-9]{64}$", sha):
            errors.append(f"Rights status '{bundle.film.rights_status}' requires a certified 64-character hex asset_sha256.")
        if not bundle.edition.source_url:
            errors.append(f"Rights status '{bundle.film.rights_status}' requires an authenticated source_url.")

    if bundle.film.analysis_status == "READY":
        if not sha or not bundle.edition.source_url:
            errors.append("Analysis status 'READY' requires asset_sha256 and source_url.")
        if not bundle.reveals:
            errors.append("Analysis status 'READY' requires at least one ingested reveal.")
        if not bundle.proofs:
            errors.append("Analysis status 'READY' requires at least one forensic proof.")

    scene_ids = set()
    for scene in bundle.scenes:
        if not scene.scene_id.strip() or scene.scene_id in scene_ids:
            errors.append(f"Invalid or duplicate scene_id '{scene.scene_id}'.")
        scene_ids.add(scene.scene_id)
        if not scene.start_ms < scene.end_ms <= runtime_ms:
            errors.append(f"Scene '{scene.scene_id}' is outside edition runtime bounds.")
    for proof in bundle.proofs:
        for premise in proof.observed_premises:
            scene = next((s for s in bundle.scenes if s.scene_id == premise.scene_id), None)
            if not scene or not scene.start_ms <= premise.timestamp_ms < scene.end_ms:
                errors.append(f"Premise '{premise.event_id}' must reference its actual containing scene.")
    if bundle.media:
        filename = bundle.media.filename.replace("\\", "/")
        if (Path(filename).is_absolute() or ":" in filename or ".." in filename.split("/")
                or filename.startswith("/")):
            errors.append("Media filename must stay within the local raw media directory.")
        if bundle.media.asset_status == "APPROVED" and (
                bundle.film.rights_status not in ("APPROVED", "PUBLIC_DOMAIN")
                or bundle.edition.rights_review_status != "APPROVED" or not sha or not bundle.edition.source_url):
            errors.append("Approved media requires reviewed rights, source_url and asset_sha256.")

    # Validate reveals uniqueness and runtime bounds
    valid_reveal_ids = set()
    for idx, rev in enumerate(bundle.reveals):
        rev_id = rev.reveal_id.strip()
        if not rev_id:
            errors.append(f"Reveal #{idx} reveal_id cannot be whitespace-only.")
        if rev_id in valid_reveal_ids:
            errors.append(f"Duplicate reveal_id '{rev_id}' found in bundle.")
        valid_reveal_ids.add(rev_id)

        if rev.movie_id != movie_id:
            errors.append(f"Reveal #{idx} ({rev.reveal_id}) movie_id '{rev.movie_id}' != '{movie_id}'")
        if rev.edition_id != edition_id:
            errors.append(f"Reveal #{idx} ({rev.reveal_id}) edition_id '{rev.edition_id}' != '{edition_id}'")
        if rev.timestamp_ms > runtime_ms:
            errors.append(
                f"Reveal #{idx} ({rev.reveal_id}) timestamp {rev.timestamp_ms}ms exceeds edition runtime {runtime_ms}ms"
            )
        if rev.spoiler_cutoff_ms > runtime_ms:
            errors.append(
                f"Reveal #{idx} ({rev.reveal_id}) cutoff {rev.spoiler_cutoff_ms}ms exceeds edition runtime {runtime_ms}ms"
            )
        if rev.timestamp_ms > rev.spoiler_cutoff_ms:
            errors.append(
                f"Reveal #{idx} ({rev.reveal_id}) timestamp {rev.timestamp_ms}ms occurs after spoiler cutoff {rev.spoiler_cutoff_ms}ms"
            )

    # Validate frames: uniqueness, security, path traversal, runtime bounds
    valid_frame_ids = set()
    for idx, frm in enumerate(bundle.frames):
        f_id = frm.frame_id.strip()
        if not f_id:
            errors.append(f"Frame #{idx} frame_id cannot be whitespace-only.")
        if f_id in valid_frame_ids:
            errors.append(f"Duplicate frame_id '{f_id}' found in bundle.")
        valid_frame_ids.add(f_id)

        if frm.movie_id != movie_id or frm.edition_id != edition_id:
            errors.append(f"Frame ({frm.frame_id}) belongs to different movie/edition")
        if frm.absolute_timestamp_ms > runtime_ms:
            errors.append(f"Frame ({frm.frame_id}) timestamp {frm.absolute_timestamp_ms}ms exceeds runtime {runtime_ms}ms")

        # Filename traversal & absolute path rejection
        fn = frm.filename
        if os.path.isabs(fn) or fn.startswith("/") or fn.startswith("\\") or (len(fn) > 1 and fn[1] == ":"):
            errors.append(f"Frame ({frm.frame_id}) filename '{fn}' must be a relative path; absolute paths are forbidden.")
        if ".." in Path(fn).parts or fn.startswith("..") or "/../" in fn or "\\..\\" in fn or "../" in fn or "..\\" in fn:
            errors.append(f"Frame ({frm.frame_id}) filename '{fn}' contains path traversal ('..') which is forbidden.")

    # Validate proofs: uniqueness, cutoff bounds, premise bounds, zero future scene leakage
    seen_proof_ids = set()
    for idx, prf in enumerate(bundle.proofs):
        p_id = prf.proof_id.strip()
        if not p_id:
            errors.append(f"Proof #{idx} proof_id cannot be whitespace-only.")
        if p_id in seen_proof_ids:
            errors.append(f"Duplicate proof_id '{p_id}' found in bundle.")
        seen_proof_ids.add(p_id)

        if prf.movie_id != movie_id:
            errors.append(f"Proof #{idx} ({prf.proof_id}) movie_id '{prf.movie_id}' != '{movie_id}'")
        if prf.edition_id != edition_id:
            errors.append(f"Proof #{idx} ({prf.proof_id}) edition_id '{prf.edition_id}' != '{edition_id}'")
        if prf.reveal_id not in valid_reveal_ids:
            errors.append(
                f"Proof #{idx} ({prf.proof_id}) references unlisted reveal_id '{prf.reveal_id}'"
            )
        if prf.timestamp_ms > runtime_ms:
            errors.append(
                f"Proof #{idx} ({prf.proof_id}) timestamp {prf.timestamp_ms}ms exceeds runtime {runtime_ms}ms"
            )
        if prf.spoiler_cutoff_ms > runtime_ms:
            errors.append(
                f"Proof #{idx} ({prf.proof_id}) spoiler_cutoff_ms {prf.spoiler_cutoff_ms}ms exceeds runtime {runtime_ms}ms"
            )
        if prf.timestamp_ms > prf.spoiler_cutoff_ms:
            errors.append(
                f"Proof #{idx} ({prf.proof_id}) timestamp {prf.timestamp_ms}ms occurs after spoiler cutoff {prf.spoiler_cutoff_ms}ms"
            )

        for prem_idx, premise in enumerate(prf.observed_premises):
            if premise.timestamp_ms > runtime_ms:
                errors.append(
                    f"Proof #{idx} ({prf.proof_id}) premise #{prem_idx} timestamp {premise.timestamp_ms}ms exceeds runtime {runtime_ms}ms"
                )
            if premise.timestamp_ms > prf.spoiler_cutoff_ms:
                errors.append(
                    f"Proof #{idx} ({prf.proof_id}) premise #{prem_idx} timestamp {premise.timestamp_ms}ms exceeds proof cutoff {prf.spoiler_cutoff_ms}ms (future scene leakage)"
                )
            for f_id_ref in premise.frame_ids:
                if f_id_ref not in valid_frame_ids:
                    errors.append(
                        f"Proof #{idx} ({prf.proof_id}) premise references missing frame_id '{f_id_ref}'"
                    )

    publication_ids = set()
    for publication in bundle.ai_publications:
        if publication.proof_id not in seen_proof_ids or publication.proof_id in publication_ids:
            errors.append("AI publication must reference a unique proof in this edition bundle.")
        publication_ids.add(publication.proof_id)
        proof = next((p for p in bundle.proofs if p.proof_id == publication.proof_id), None)
        if proof and (proof.human_review_status != "NOT_REVIEWED"
                      or proof.presentation_status != "HIDDEN_FROM_PUBLIC"):
            errors.append("AI publication must preserve the unreviewed, hidden fallback; public output requires a bound DB record.")

    # Validate subtitle cues: index uniqueness, runtime bounds, and non-decreasing chronological order
    seen_cue_indices = set()
    for cue in bundle.subtitles:
        if cue.cue_index in seen_cue_indices:
            errors.append(f"Duplicate subtitle cue_index '{cue.cue_index}' found in bundle.")
        seen_cue_indices.add(cue.cue_index)

        if cue.end_ms > runtime_ms:
            errors.append(f"Subtitle cue #{cue.cue_index} end_ms ({cue.end_ms}) exceeds runtime ({runtime_ms}ms)")

    # Subtitle cues sequence order
    for i in range(len(bundle.subtitles) - 1):
        c1 = bundle.subtitles[i]
        c2 = bundle.subtitles[i + 1]
        if c1.start_ms > c2.start_ms:
            errors.append(
                f"Subtitle cues out of chronological order: cue #{c1.cue_index} (start {c1.start_ms}ms) > cue #{c2.cue_index} (start {c2.start_ms}ms)"
            )

    return len(errors) == 0, errors


def preflight_check_frame_files(bundle_dict: Dict[str, Any], base_dir: Path) -> List[str]:
    """
    Preflight verification tool checking physical presence of frame files under base_dir.
    Rejects directory traversal or missing frame files on disk.
    """
    missing = []
    base_resolved = base_dir.resolve()
    for frm in bundle_dict.get("frames", []):
        fn = frm.get("filename")
        if fn:
            target = (base_resolved / fn).resolve()
            if not target.is_relative_to(base_resolved):
                missing.append(f"Frame '{frm.get('frame_id')}' path '{fn}' attempts directory traversal.")
            elif not target.is_file():
                missing.append(f"Frame '{frm.get('frame_id')}' file '{fn}' not found under {base_dir}.")
    return missing


def convert_bundle_to_catalog_entry(bundle_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adapter converting validated dataset bundle to runtime CatalogService film entry.
    Reconciles field name differences such as asset_sha256 -> canonical_asset_sha256.
    """
    film = bundle_dict["film"]
    edition = bundle_dict["edition"]
    reveals = bundle_dict.get("reveals", [])
    scenes = bundle_dict.get("scenes", [])

    sha = edition.get("asset_sha256")
    clean_sha = sha if (sha and not "pending" in str(sha).lower()) else None

    return {
        "movie_id": film["movie_id"],
        "edition_id": edition["edition_id"],
        "title": film["title"],
        "year": film["year"],
        "synopsis_safe": film["synopsis_safe"],
        "runtime_ms": edition["runtime_ms"],
        "rights_status": film.get("rights_status", "UNCONFIRMED"),
        "analysis_status": film.get("analysis_status", "PREPARING"),
        "canonical_asset_sha256": clean_sha,
        "dataset_version": edition.get("dataset_version", "v1.0.0"),
        "reveals_count": len(reveals),
        "scenes_count": len(scenes),
        "scenes": deepcopy(scenes),
        "media": deepcopy(bundle_dict.get("media")),
        "rights_review_status": edition.get("rights_review_status", "PENDING"),
        "available_modes": film.get("available_modes", ["STRICT_CANON"]),
        "poster_path": film.get("poster_path"),
        "directors": film.get("directors", []),
        "cast": film.get("cast", []),
        "genres": film.get("genres", [])
    }


_APPLIED_BUNDLE_HASHES: Dict[Tuple[str, str], str] = {}


@contextmanager
def _storage_lock(storage_dir: Path):
    """OS-owned lock: released on process exit, including an interrupted import."""
    with (storage_dir / ".import.lock").open("a+b") as lock_file:
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def _persist_bundle(target: Path, content: str) -> None:
    descriptor, name = tempfile.mkstemp(prefix=".dataset-", suffix=".tmp", dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def _preflight_assets(bundle: Dict[str, Any], asset_root: Path) -> List[str]:
    errors = preflight_check_frame_files(bundle, asset_root / "data/production/evidence_frames")
    media = bundle.get("media")
    if media and media["asset_status"] == "APPROVED":
        base = (asset_root / "data/external/raw").resolve()
        path = (base / media["filename"]).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            errors.append("Approved media asset is missing or outside the raw media directory.")
        else:
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != bundle["edition"]["asset_sha256"].lower():
                errors.append("Approved media asset does not match the edition asset_sha256.")
    return errors


def _register_bundle(bundle: Dict[str, Any], asset_root: Path) -> None:
    from apps.api.routers.media import register_evidence_frame
    from src.reframe.proof.store import register_dynamic_proof

    movie_id, edition_id = bundle["film"]["movie_id"], bundle["edition"]["edition_id"]
    entry = convert_bundle_to_catalog_entry(bundle)
    entry["_asset_root"] = str(asset_root)
    entry["_ai_publications"] = {p["proof_id"]: p["record_sha256"] for p in bundle.get("ai_publications", [])}
    reveals = deepcopy(bundle["reveals"])
    for reveal in reveals:
        related = [p for p in bundle["proofs"] if p["reveal_id"] == reveal["reveal_id"]]
        reveal["proof_count"] = len(related)
        reveal["proof_types"] = sorted({p["proof_type"] for p in related})
    catalog_service.register_film_dataset(movie_id, entry, reveals, {
        r["reveal_id"]: {"safe_title": r["safe_title"], "safe_preview": r["safe_preview"]}
        for r in reveals
    })
    for frame in bundle["frames"]:
        register_evidence_frame(movie_id, edition_id, frame["frame_id"],
            frame["absolute_timestamp_ms"], frame["filename"])
    for proof in bundle["proofs"]:
        register_dynamic_proof(dict(proof, work_id=movie_id))


@synchronized
def apply_film_dataset(
    bundle_dict: Dict[str, Any],
    dry_run: bool = True,
    storage_dir: Optional[Path] = None,
    *,
    asset_root: Optional[Path] = None,
    persist: bool = True,
) -> Dict[str, Any]:
    """
    Validates and optionally applies a film dataset bundle into the runtime catalog and media layers.
    - If dry_run=True (default): validates and returns preview verdict without modifying state.
    - If dry_run=False: applies atomically, guarantees idempotency on re-application of same bundle,
      persists to disk to survive service restart, and preserves existing state on failure.
    """
    is_valid, errors = validate_film_dataset(bundle_dict)
    if not is_valid:
        return {
            "success": False,
            "verdict": "VALIDATION_FAILED",
            "errors": errors,
            "counts": {}
        }

    film = bundle_dict.get("film", {})
    edition = bundle_dict.get("edition", {})
    movie_id = film.get("movie_id")
    edition_id = edition.get("edition_id")
    composite_key = (movie_id, edition_id)

    if dry_run:
        return {
            "success": True,
            "verdict": "READY_FOR_IMPORT",
            "movie_id": movie_id,
            "edition_id": edition_id,
            "counts": {
                "reveals": len(bundle_dict.get("reveals", [])),
                "proofs": len(bundle_dict.get("proofs", [])),
                "subtitles": len(bundle_dict.get("subtitles", [])),
                "frames": len(bundle_dict.get("frames", []))
            },
            "errors": []
        }

    bundle = FilmDatasetBundle(**bundle_dict).model_dump()
    bundle_json = json.dumps(bundle, sort_keys=True)
    bundle_hash = hashlib.sha256(bundle_json.encode("utf-8")).hexdigest()
    storage_dir = Path(storage_dir or ROOT / "data/production/imported_datasets").resolve()
    asset_root = Path(asset_root or ROOT).resolve()
    from apps.api.routers import media as media_router
    from src.reframe.proof import store as proof_store

    registries = [catalog_service.__dict__, media_router._DYNAMIC_FRAME_REGISTRY,
        proof_store._DYNAMIC_PROOFS_BY_ID, proof_store._DYNAMIC_PROOFS_BY_REVEAL,
        _APPLIED_BUNDLE_HASHES]
    snapshots = [deepcopy(state) for state in registries]
    try:
        errors = _preflight_assets(bundle, asset_root)
        if errors:
            return {"success": False, "verdict": "ASSET_PREFLIGHT_FAILED", "errors": errors}
        if persist:
            storage_dir.mkdir(parents=True, exist_ok=True)
        dataset_file = storage_dir / f"{movie_id}_{edition_id}.json"
        # Restoring an immutable release reads only; production's root filesystem
        # is read-only. Writers still take both the process and filesystem locks.
        with _storage_lock(storage_dir) if persist else nullcontext():
            current_hash = _APPLIED_BUNDLE_HASHES.get(composite_key)
            if ((current_hash is not None and current_hash != bundle_hash)
                    or (dataset_file.exists() and
                        FilmDatasetBundle(**json.loads(dataset_file.read_text(encoding="utf-8"))).model_dump() != bundle)):
                return {"success": False, "verdict": "CONFLICT_DETECTED",
                    "errors": [f"Conflict with existing version for {composite_key}"]}
            if current_hash == bundle_hash and (dataset_file.exists() or not persist):
                return {"success": True, "verdict": "ALREADY_APPLIED", "idempotent": True, "errors": []}

            # Readers hold the same process lock. Failed registration or persistence is rolled back.
            _register_bundle(bundle, asset_root)
            if persist and not dataset_file.exists():
                _persist_bundle(dataset_file, bundle_json)
            _APPLIED_BUNDLE_HASHES[composite_key] = bundle_hash

        return {
            "success": True,
            "verdict": "APPLIED",
            "movie_id": movie_id,
            "edition_id": edition_id,
            "counts": {
                "reveals": len(bundle_dict.get("reveals", [])),
                "proofs": len(bundle_dict.get("proofs", [])),
                "subtitles": len(bundle_dict.get("subtitles", [])),
                "frames": len(bundle_dict.get("frames", []))
            },
            "errors": []
        }
    except Exception as exc:
        for state, snapshot in zip(registries, snapshots):
            state.clear()
            state.update(snapshot)
        return {
            "success": False,
            "verdict": "APPLICATION_FAILED",
            "errors": [f"Application failed: {str(exc)}"]
        }


def load_imported_datasets_from_disk(storage_dir: Optional[Path] = None, *, asset_root: Optional[Path] = None) -> int:
    """Restores persisted dataset bundles on service startup."""
    if storage_dir is None:
        root = Path(__file__).resolve().parents[3]
        storage_dir = root / "data/production/imported_datasets"
    if not storage_dir.is_dir():
        return 0

    count = 0
    for f in sorted(storage_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            res = apply_film_dataset(data, dry_run=False, storage_dir=storage_dir, asset_root=asset_root, persist=False)
            if res.get("success"):
                count += 1
            else:
                raise ValueError("; ".join(res.get("errors", [res.get("verdict", "Import failed")])) )
        except Exception as exc:
            logger.error("dataset_restore_failed", file=f.name, error=str(exc))
            raise RuntimeError(f"Dataset restore failed for {f.name}") from exc
    return count


def dry_run_import(bundle_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility alias for apply_film_dataset with dry_run=True."""
    return apply_film_dataset(bundle_dict, dry_run=True)
