"""
Phase A Lock Pipeline
Computes SHA256 hashes of all Phase A artifacts and produces phase_a_lock.json.
After locking, Phase A outputs are immutable.
Enforces strict immutability: will NOT overwrite an existing lock.
"""
import os
import json
import hashlib
from datetime import datetime, timezone

SNAPSHOT_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1_1")

PHASE_A_FILES = [
    "clean_room_manifest.json",
    "media_review.json",
    "phase_a_observations.json",
    "phase_a_knowledge.json",
    "phase_a_claims.json",
    "phase_a_actions.json",
    "phase_a_access.json",
    "phase_a_goals.json",
    "phase_a_plan_hypotheses.json",
    "phase_a_candidate_proofs.json"
]


def sha256_file(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def lock_phase_a(snapshot_dir: str = SNAPSHOT_DIR):
    lock_path = os.path.join(snapshot_dir, "phase_a_lock.json")

    # If lock already exists, verify immutability and never overwrite
    if os.path.exists(lock_path):
        with open(lock_path, "r", encoding="utf-8") as f:
            existing_lock = json.load(f)

        mismatches = []
        for filename in PHASE_A_FILES:
            filepath = os.path.join(snapshot_dir, filename)
            if not os.path.exists(filepath):
                mismatches.append(f"Missing locked file: {filename}")
                continue
            curr_sha = sha256_file(filepath)
            exp_meta = existing_lock.get("files_locked", {}).get(filename, {})
            exp_sha = exp_meta.get("sha256")
            if curr_sha != exp_sha:
                mismatches.append(f"{filename}: expected {exp_sha}, got {curr_sha}")

        if mismatches:
            err_msg = (
                f"PHASE_A_IMMUTABILITY_VIOLATION: Existing Phase A lock for snapshot cannot be modified or re-locked.\n"
                f"Mismatches detected:\n" + "\n".join(f"  - {m}" for m in mismatches) + "\n"
                f"A new analytical snapshot requires a new snapshot version, not re-locking Phase A."
            )
            raise RuntimeError(err_msg)

        print(f"Phase A lock verified: all {len(PHASE_A_FILES)} files match immutable lock.")
        return existing_lock

    # Lock does not exist: create initial immutable lock
    file_hashes = {}
    for filename in PHASE_A_FILES:
        filepath = os.path.join(snapshot_dir, filename)
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Missing Phase A file: {filepath}")
        file_hashes[filename] = {
            "sha256": sha256_file(filepath),
            "size_bytes": os.path.getsize(filepath)
        }

    lock_payload = {
        "lock_version": "1.0",
        "snapshot_id": "the_bat_whispers_deep_snapshot_v1_1",
        "lock_timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "phase_a_status": "LOCKED_IMMUTABLE",
        "files_locked": file_hashes,
        "total_files_locked": len(file_hashes)
    }

    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock_payload, f, indent=2)

    print(f"Phase A successfully locked: {lock_path} ({len(file_hashes)} files).")
    return lock_payload


if __name__ == "__main__":
    lock_phase_a()
