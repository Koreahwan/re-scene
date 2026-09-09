import json
import os
import hashlib
import pytest
from src.reframe.narrative.snapshot_repo import DeepSnapshotRepository

BASE_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1_1")

def sha256_file(filepath):
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def test_phase_a_lock_integrity():
    """1. phase_a_lock.json의 모든 files_locked raw SHA가 실제 파일과 일치"""
    lock_path = os.path.join(BASE_DIR, "phase_a_lock.json")
    with open(lock_path, "r", encoding="utf-8") as f:
        lock_data = json.load(f)
    for locked_file, meta in lock_data.get("files_locked", {}).items():
        actual_sha = sha256_file(os.path.join(BASE_DIR, locked_file))
        assert actual_sha == meta.get("sha256"), f"Mismatch in {locked_file}"

def test_original_phase_a_file_hashes():
    """2. original_phase_a_file_hashes가 phase_a_original 파일과 일치"""
    corrections_path = os.path.join(BASE_DIR, "corpus_corrections.json")
    with open(corrections_path, "r", encoding="utf-8") as f:
        corr_data = json.load(f)
    orig_dir = os.path.join(BASE_DIR, "phase_a_original")
    for orig_file, exp_sha in corr_data.get("original_phase_a_file_hashes", {}).items():
        actual_sha = sha256_file(os.path.join(orig_dir, orig_file))
        assert actual_sha == exp_sha, f"Mismatch in {orig_file}"

def test_normalized_output_hashes():
    """3. normalized_output_hashes 전체가 실제 파일과 일치"""
    corrections_path = os.path.join(BASE_DIR, "corpus_corrections.json")
    with open(corrections_path, "r", encoding="utf-8") as f:
        corr_data = json.load(f)
    for norm_file, exp_sha in corr_data.get("normalized_output_hashes", {}).items():
        actual_sha = sha256_file(os.path.join(BASE_DIR, norm_file))
        assert actual_sha == exp_sha, f"Mismatch in {norm_file}"

def test_manifest_anchor():
    """4. manifest의 corpus_corrections_sha256가 실제 corpus_corrections.json SHA와 일치"""
    manifest_path = os.path.join(BASE_DIR, "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    expected_sha = manifest_data.get("corpus_corrections_sha256")
    actual_sha = sha256_file(os.path.join(BASE_DIR, "corpus_corrections.json"))
    assert actual_sha == expected_sha, "Manifest anchor mismatch"

def test_snapshot_repo_load_success():
    """5. DeepSnapshotRepository.clear_cache() 후 deep_snapshot_v1_1 Proof candidate가 SnapshotIntegrityError 없이 로드"""
    DeepSnapshotRepository.clear_cache()
    candidates = DeepSnapshotRepository.get_proof_candidates()
    assert isinstance(candidates, list)
    assert len(candidates) > 0
