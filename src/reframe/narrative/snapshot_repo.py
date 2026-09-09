"""
Reframe V7 Deep Snapshot Repository
Authoritative loader and query interface for clean-room Deep Snapshot artifacts (V1.1).
Serves as the Single Source of Truth (SSOT) for offline development reasoning.
Verifies Phase A lock checksums, corpus corrections, and normalized files at load time.
Fails closed with SnapshotIntegrityError on invalid, missing, or corrupted snapshots.
Zero Paid Model Calls.
"""
import os
import json
import hashlib
from typing import Dict, Any, List, Optional
import structlog

logger = structlog.get_logger(__name__)

DEVELOPMENT_ANSWER_ASSISTED: bool = True
DEFAULT_SNAPSHOT_ID: str = "deep_snapshot_v1_1"
EXPECTED_DEEP_SNAPSHOT_V1_1_CORPUS_CORRECTIONS_SHA256: str = "6ffa08484bbda4af542911f4987b786fde5057ede950ca563683634fa7cf0b90"


class SnapshotIntegrityError(Exception):
    """Raised when deep snapshot artifacts fail directory, lock, manifest, or checksum verification."""
    pass


class DeepSnapshotRepository:
    """
    In-memory cached repository for Deep Snapshot artifacts.
    Loads and provides structured proof candidates, epistemic propositions, claims, actions, and causal DAGs.
    Fails closed with SnapshotIntegrityError if snapshot is missing, corrupted, or fails lock hash verification.
    """
    _cache: Dict[str, Any] = {}
    _lock_verified: Dict[str, bool] = {}

    @classmethod
    def _get_base_dir(cls, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> str:
        # Strict SSOT path — zero fallback to superseded deep_snapshot_v1
        base_dir = os.path.join("data", "analysis", "the_bat_whispers", snapshot_id)
        if not os.path.exists(base_dir):
            raise SnapshotIntegrityError(f"Snapshot directory not found: {base_dir}")
        return base_dir

    @classmethod
    def _verify_phase_a_lock(cls, base_dir: str, snapshot_id: str) -> bool:
        """Verifies actual SHA256 checksums of all Phase A locked files, corpus corrections, and normalized artifacts at load time."""
        if cls._lock_verified.get(snapshot_id) is True:
            return True

        lock_path = os.path.join(base_dir, "phase_a_lock.json")
        if not os.path.exists(lock_path):
            logger.error("phase_a_lock_missing", snapshot_id=snapshot_id, path=lock_path)
            raise SnapshotIntegrityError(f"Phase A lock file missing: {lock_path}")

        try:
            with open(lock_path, "r", encoding="utf-8") as f:
                lock_data = json.load(f)

            for locked_file, meta in lock_data.get("files_locked", {}).items():
                target_path = os.path.join(base_dir, locked_file)
                if not os.path.exists(target_path):
                    logger.error("phase_a_locked_file_missing", file=locked_file)
                    raise SnapshotIntegrityError(f"Phase A locked file missing: {locked_file}")

                with open(target_path, "rb") as f:
                    actual_sha = hashlib.sha256(f.read()).hexdigest()

                expected_sha = meta.get("sha256")
                if actual_sha != expected_sha:
                    logger.error("phase_a_lock_hash_mismatch", file=locked_file, expected=expected_sha, actual=actual_sha)
                    raise SnapshotIntegrityError(
                        f"Phase A lock hash mismatch on '{locked_file}': expected {expected_sha}, got {actual_sha}"
                    )

            # Check manifest.json
            manifest_path = os.path.join(base_dir, "manifest.json")
            if not os.path.exists(manifest_path):
                raise SnapshotIntegrityError(f"Snapshot manifest missing: {manifest_path}")

            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)

            if manifest_data.get("snapshot_id") != "the_bat_whispers_deep_snapshot_v1_1":
                raise SnapshotIntegrityError("Manifest snapshot_id mismatch")
            if manifest_data.get("dataset_version") != "v1.1_clean_room":
                raise SnapshotIntegrityError("Manifest dataset_version mismatch")

            exp_corr_sha = manifest_data.get("corpus_corrections_sha256")
            if not exp_corr_sha:
                raise SnapshotIntegrityError("Manifest missing corpus_corrections_sha256 anchor")

            # Check corpus_corrections.json
            corrections_path = os.path.join(base_dir, "corpus_corrections.json")
            if not os.path.exists(corrections_path):
                raise SnapshotIntegrityError(f"Corpus corrections file missing: {corrections_path}")

            with open(corrections_path, "rb") as f:
                actual_corr_bytes = f.read()
                actual_corr_sha = hashlib.sha256(actual_corr_bytes).hexdigest()

            if actual_corr_sha != exp_corr_sha or actual_corr_sha != EXPECTED_DEEP_SNAPSHOT_V1_1_CORPUS_CORRECTIONS_SHA256:
                raise SnapshotIntegrityError(
                    f"Corpus corrections hash mismatch against manifest anchor: expected {EXPECTED_DEEP_SNAPSHOT_V1_1_CORPUS_CORRECTIONS_SHA256}, got {actual_corr_sha}"
                )

            corr_data = json.loads(actual_corr_bytes.decode("utf-8"))
            if corr_data.get("original_phase_a_base_sha") != "059cc9f320e3c85cb9b4e4bf9578ea9f4c498f62":
                raise SnapshotIntegrityError("Corpus corrections base SHA mismatch")

            # Verify files in phase_a_original/
            orig_dir = os.path.join(base_dir, "phase_a_original")
            if not os.path.exists(orig_dir):
                raise SnapshotIntegrityError(f"phase_a_original directory missing: {orig_dir}")

            for orig_file, exp_sha in corr_data.get("original_phase_a_file_hashes", {}).items():
                orig_file_path = os.path.join(orig_dir, orig_file)
                if not os.path.exists(orig_file_path):
                    raise SnapshotIntegrityError(f"Original Phase A file missing: {orig_file_path}")
                with open(orig_file_path, "rb") as f:
                    act_sha = hashlib.sha256(f.read()).hexdigest()
                if act_sha != exp_sha:
                    raise SnapshotIntegrityError(
                        f"Original Phase A file hash mismatch on '{orig_file}': expected {exp_sha}, got {act_sha}"
                    )

            # Verify normalized output files
            for norm_file, exp_sha in corr_data.get("normalized_output_hashes", {}).items():
                norm_file_path = os.path.join(base_dir, norm_file)
                if not os.path.exists(norm_file_path):
                    raise SnapshotIntegrityError(f"Normalized output file missing: {norm_file_path}")
                with open(norm_file_path, "rb") as f:
                    act_sha = hashlib.sha256(f.read()).hexdigest()
                if act_sha != exp_sha:
                    raise SnapshotIntegrityError(
                        f"Normalized output file hash mismatch on '{norm_file}': expected {exp_sha}, got {act_sha}"
                    )

            expected_overlay_hash = corr_data.get("correction_overlay_hash")
            if expected_overlay_hash:
                corr_bytes = json.dumps(corr_data.get("corrections", []), sort_keys=True).encode("utf-8")
                actual_overlay_hash = hashlib.sha256(corr_bytes).hexdigest()
                if actual_overlay_hash != expected_overlay_hash:
                    raise SnapshotIntegrityError(
                        f"Corpus corrections overlay hash mismatch: expected {expected_overlay_hash}, got {actual_overlay_hash}"
                    )

            cls._lock_verified[snapshot_id] = True
            return True
        except SnapshotIntegrityError:
            raise
        except Exception as e:
            logger.error("phase_a_lock_verification_failed", error=str(e))
            raise SnapshotIntegrityError(f"Phase A lock verification failed: {e}") from e

    @classmethod
    def _load_json(cls, filename: str, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> Any:
        cache_key = f"{snapshot_id}:{filename}"
        if cache_key in cls._cache:
            return cls._cache[cache_key]

        base_dir = cls._get_base_dir(snapshot_id)

        # Enforce Phase A lock verification before loading
        cls._verify_phase_a_lock(base_dir, snapshot_id)

        filepath = os.path.join(base_dir, filename)
        if not os.path.exists(filepath):
            raise SnapshotIntegrityError(f"Snapshot artifact file missing: {filepath}")

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                cls._cache[cache_key] = data
                return data
        except Exception as e:
            logger.error("failed_to_load_snapshot_file", filename=filename, error=str(e))
            raise SnapshotIntegrityError(f"Failed to parse snapshot artifact '{filename}': {e}") from e

    @classmethod
    def get_proof_candidates(cls, reveal_id: Optional[str] = None, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> List[Dict[str, Any]]:
        candidates = cls._load_json("proof_candidates.json", snapshot_id)
        if reveal_id:
            return [c for c in candidates if c.get("reveal_id") == reveal_id]
        return candidates

    @classmethod
    def get_knowledge_propositions(cls, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> List[Dict[str, Any]]:
        return cls._load_json("knowledge_propositions.json", snapshot_id)

    @classmethod
    def get_claims(cls, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> List[Dict[str, Any]]:
        return cls._load_json("claims.json", snapshot_id)

    @classmethod
    def get_actions(cls, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> List[Dict[str, Any]]:
        return cls._load_json("actions.json", snapshot_id)

    @classmethod
    def get_plan_steps(cls, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> List[Dict[str, Any]]:
        return cls._load_json("plan_steps.json", snapshot_id)

    @classmethod
    def get_causal_edges(cls, snapshot_id: str = DEFAULT_SNAPSHOT_ID) -> List[Dict[str, Any]]:
        return cls._load_json("causal_edges.json", snapshot_id)

    @classmethod
    def clear_cache(cls):
        cls._cache.clear()
        cls._lock_verified.clear()


snapshot_repo = DeepSnapshotRepository()
