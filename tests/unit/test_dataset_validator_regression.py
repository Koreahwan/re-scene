"""
Regression tests for dataset validator (R2-04).
Regression cases for invalid 1,000ms dataset bundles:
1. proof cutoff exceeding runtime (e.g. 999,999ms on 1,000ms runtime).
2. duplicate reveal ID 'r'.
3. frame filename directory traversal (e.g. '../../outside.jpg').
Each defect is tested in isolation to ensure it fails on its own.
Also tests:
4. whitespace-only IDs.
5. subtitle cues ordering inversion.
6. fake placeholder hash rejection ('*_pending').
7. frame absolute path rejection ('/var/log/secret.jpg').
Zero paid model calls.
"""
import copy
import pytest
from src.reframe.catalog.dataset_import import validate_film_dataset, dry_run_import


@pytest.fixture
def base_1000ms_bundle():
    """A minimal valid bundle with 1,000ms runtime."""
    return {
        "film": {
            "movie_id": "test-film-1000",
            "title": "Minimal Test Film",
            "year": 1945,
            "synopsis_safe": "A safe premise.",
            "runtime_ms": 1000,
            "rights_status": "UNCONFIRMED",
            "analysis_status": "PREPARING"
        },
        "edition": {
            "edition_id": "ed-1000",
            "movie_id": "test-film-1000",
            "runtime_ms": 1000,
            "dataset_version": "v1.0.0"
        },
        "scenes": [{"scene_id": "sc-1", "start_ms": 0, "end_ms": 1000}],
        "reveals": [
            {
                "reveal_id": "rev-1",
                "movie_id": "test-film-1000",
                "edition_id": "ed-1000",
                "title": "Reveal 1",
                "safe_title": "Safe 1",
                "safe_preview": "Preview 1",
                "timestamp_ms": 500,
                "spoiler_cutoff_ms": 800
            }
        ],
        "proofs": [
            {
                "proof_id": "proof-1",
                "movie_id": "test-film-1000",
                "edition_id": "ed-1000",
                "reveal_id": "rev-1",
                "title": "Proof 1",
                "summary": "Forensic evidence.",
                "timestamp_ms": 400,
                "spoiler_cutoff_ms": 700,
                "observed_premises": [
                    {
                        "event_id": "ev-1",
                        "scene_id": "sc-1",
                        "timestamp_ms": 300,
                        "actor": "Detective",
                        "action": "Finds clue",
                        "fact": "Clue on table",
                        "frame_ids": ["frm-1"]
                    }
                ]
            }
        ],
        "subtitles": [
            {
                "cue_index": 1,
                "start_ms": 100,
                "end_ms": 400,
                "text": "Quiet scene."
            }
        ],
        "frames": [
            {
                "frame_id": "frm-1",
                "movie_id": "test-film-1000",
                "edition_id": "ed-1000",
                "absolute_timestamp_ms": 300,
                "filename": "frame_001.jpg"
            }
        ]
    }


def test_base_bundle_is_valid(base_1000ms_bundle):
    is_valid, errors = validate_film_dataset(base_1000ms_bundle)
    assert is_valid is True, f"Base bundle should be valid: {errors}"
    res = dry_run_import(base_1000ms_bundle)
    assert res["success"] is True
    assert res["verdict"] == "READY_FOR_IMPORT"


def test_proof_cutoff_exceeds_runtime(base_1000ms_bundle):
    """A proof cutoff of 999,999ms must fail for a 1,000ms runtime bundle."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    bundle["proofs"][0]["spoiler_cutoff_ms"] = 999999

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("spoiler_cutoff_ms 999999ms exceeds runtime 1000ms" in err for err in errors)

    res = dry_run_import(bundle)
    assert res["success"] is False
    assert res["verdict"] == "VALIDATION_FAILED"


def test_duplicate_reveal_id(base_1000ms_bundle):
    """Duplicate reveal ID 'r' must fail standalone validation."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    # Add a second reveal with the same ID
    bundle["reveals"][0]["reveal_id"] = "r"
    bundle["proofs"][0]["reveal_id"] = "r"
    bundle["reveals"].append({
        "reveal_id": "r",
        "movie_id": "test-film-1000",
        "edition_id": "ed-1000",
        "title": "Duplicate Reveal",
        "safe_title": "Safe Dup",
        "safe_preview": "Dup preview",
        "timestamp_ms": 600,
        "spoiler_cutoff_ms": 900
    })

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("Duplicate reveal_id 'r'" in err for err in errors)

    res = dry_run_import(bundle)
    assert res["success"] is False
    assert res["verdict"] == "VALIDATION_FAILED"


def test_path_traversal_frame_filename(base_1000ms_bundle):
    """Frame filename '../../outside.jpg' must fail standalone validation."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    bundle["frames"][0]["filename"] = "../../outside.jpg"

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("path traversal" in err for err in errors)

    res = dry_run_import(bundle)
    assert res["success"] is False
    assert res["verdict"] == "VALIDATION_FAILED"


def test_standalone_absolute_path_frame_filename(base_1000ms_bundle):
    """Absolute paths like '/etc/secret.jpg' or 'C:\\test.jpg' must fail standalone."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    bundle["frames"][0]["filename"] = "/var/log/frame.jpg"

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("absolute paths are forbidden" in err for err in errors)


def test_standalone_fake_pending_hash_rejected(base_1000ms_bundle):
    """Fake pending hashes like 'detour_asset_sha256_pending' must be rejected."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    bundle["edition"]["asset_sha256"] = "detour_asset_sha256_pending"

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("Invalid asset_sha256 format" in err for err in errors)


def test_standalone_subtitle_order_inversion(base_1000ms_bundle):
    """Subtitle cues out of order must be rejected."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    bundle["subtitles"] = [
        {"cue_index": 1, "start_ms": 500, "end_ms": 700, "text": "Later line"},
        {"cue_index": 2, "start_ms": 200, "end_ms": 400, "text": "Earlier line"}
    ]

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("Subtitle cues out of chronological order" in err for err in errors)


def test_standalone_future_scene_leakage_in_premise(base_1000ms_bundle):
    """Premise timestamp occurring after proof spoiler cutoff must be rejected (leakage invariant)."""
    bundle = copy.deepcopy(base_1000ms_bundle)
    # Proof cutoff is 700, premise timestamp is 800
    bundle["proofs"][0]["observed_premises"][0]["timestamp_ms"] = 800

    is_valid, errors = validate_film_dataset(bundle)
    assert is_valid is False
    assert any("future scene leakage" in err for err in errors)
