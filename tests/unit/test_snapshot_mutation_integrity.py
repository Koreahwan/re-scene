"""
Unit Tests for Deep Snapshot Load-Time Mutation Integrity
Proves that DeepSnapshotRepository fails closed with SnapshotIntegrityError
whenever any locked, normalized, or provenance file is mutated.
Zero Paid Model Calls ($0.00).
"""
import os
import tempfile
import shutil
import pytest
from src.reframe.narrative.snapshot_repo import DeepSnapshotRepository, SnapshotIntegrityError


@pytest.fixture
def isolated_snapshot_dir():
    """Creates a temporary isolated copy of deep_snapshot_v1_1 for mutation testing."""
    real_snapshot_dir = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1_1")
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_snapshot = os.path.join(temp_dir, "deep_snapshot_v1_1")
        shutil.copytree(real_snapshot_dir, temp_snapshot)
        DeepSnapshotRepository.clear_cache()
        yield temp_snapshot
        DeepSnapshotRepository.clear_cache()


def test_mutation_rejects_altered_knowledge_propositions(isolated_snapshot_dir, monkeypatch):
    """Mutating normalized knowledge_propositions.json must raise SnapshotIntegrityError."""
    target_file = os.path.join(isolated_snapshot_dir, "knowledge_propositions.json")
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(" ")

    monkeypatch.setattr(DeepSnapshotRepository, "_get_base_dir", lambda snapshot_id="deep_snapshot_v1_1": isolated_snapshot_dir)
    DeepSnapshotRepository.clear_cache()

    with pytest.raises(SnapshotIntegrityError) as exc_info:
        DeepSnapshotRepository.get_knowledge_propositions()
    assert "Normalized output file hash mismatch" in str(exc_info.value)


def test_mutation_rejects_altered_proof_candidates(isolated_snapshot_dir, monkeypatch):
    """Mutating normalized proof_candidates.json must raise SnapshotIntegrityError."""
    target_file = os.path.join(isolated_snapshot_dir, "proof_candidates.json")
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(" ")

    monkeypatch.setattr(DeepSnapshotRepository, "_get_base_dir", lambda snapshot_id="deep_snapshot_v1_1": isolated_snapshot_dir)
    DeepSnapshotRepository.clear_cache()

    with pytest.raises(SnapshotIntegrityError) as exc_info:
        DeepSnapshotRepository.get_proof_candidates()
    assert "Normalized output file hash mismatch" in str(exc_info.value)


def test_mutation_rejects_altered_phase_a_original(isolated_snapshot_dir, monkeypatch):
    """Mutating phase_a_original/phase_a_knowledge.json must raise SnapshotIntegrityError."""
    target_file = os.path.join(isolated_snapshot_dir, "phase_a_original", "phase_a_knowledge.json")
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(" ")

    monkeypatch.setattr(DeepSnapshotRepository, "_get_base_dir", lambda snapshot_id="deep_snapshot_v1_1": isolated_snapshot_dir)
    DeepSnapshotRepository.clear_cache()

    with pytest.raises(SnapshotIntegrityError) as exc_info:
        DeepSnapshotRepository.get_knowledge_propositions()
    assert "Original Phase A file hash mismatch" in str(exc_info.value)


def test_mutation_rejects_altered_corpus_corrections(isolated_snapshot_dir, monkeypatch):
    """Mutating corpus_corrections.json must raise SnapshotIntegrityError against manifest anchor."""
    target_file = os.path.join(isolated_snapshot_dir, "corpus_corrections.json")
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(" ")

    monkeypatch.setattr(DeepSnapshotRepository, "_get_base_dir", lambda snapshot_id="deep_snapshot_v1_1": isolated_snapshot_dir)
    DeepSnapshotRepository.clear_cache()

    with pytest.raises(SnapshotIntegrityError) as exc_info:
        DeepSnapshotRepository.get_knowledge_propositions()
    assert "Corpus corrections hash mismatch against manifest anchor" in str(exc_info.value)
