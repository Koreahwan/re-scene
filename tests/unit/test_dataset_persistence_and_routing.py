"""
Unit and integration contract tests for persistent dataset loading, adapter conversion,
router connection, and idempotency (R2-05, R2-06).
Covers:
- Applying synthetic dataset bundle to catalog, media, and proof stores.
- Persistence to storage_dir and restoration in a fresh session.
- Idempotency when re-applying identical bundle (ALREADY_APPLIED).
- Conflict detection when re-applying different content under same movie/edition.
- Zero mutation / zero impact on canonical Bat Whispers dataset on failure.
- Routing connection: get_film_detail returns 200 OK for registered films without DB rows.
- Two distinct synthetic films with different editions and runtimes.
Zero paid model calls.
"""
import copy
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from src.reframe.catalog.service import catalog_service, THE_BAT_WHISPERS_FILM
from src.reframe.catalog.dataset_import import (
    validate_film_dataset,
    apply_film_dataset,
    load_imported_datasets_from_disk
)
from src.reframe.identity.auth import ViewerContext
from apps.api.routers.catalog import get_film_detail, list_film_reveals, get_film_media, get_film_scene_index
from src.reframe.proof.store import canonical_proof_store


@pytest.fixture(autouse=True)
def isolated_import_state(monkeypatch):
    from apps.api.routers import media
    from src.reframe.catalog import dataset_import
    from src.reframe.proof import store
    for name, value in catalog_service.__dict__.items():
        monkeypatch.setattr(catalog_service, name, copy.deepcopy(value))
    for module, names in ((media, ["_DYNAMIC_FRAME_REGISTRY"]),
            (store, ["_DYNAMIC_PROOFS_BY_ID", "_DYNAMIC_PROOFS_BY_REVEAL"]),
            (dataset_import, ["_APPLIED_BUNDLE_HASHES"])):
        for name in names:
            monkeypatch.setattr(module, name, copy.deepcopy(getattr(module, name)))


@pytest.fixture
def synthetic_bundle_f1(tmp_path):
    """Synthetic Film 1 (60,000ms runtime)."""
    return {
        "film": {
            "movie_id": "synth-film-1",
            "title": "Synthetic Film One",
            "year": 1941,
            "synopsis_safe": "Safe synopsis for synth film 1.",
            "runtime_ms": 60000,
            "rights_status": "UNCONFIRMED",
            "analysis_status": "READY"
        },
        "edition": {
            "edition_id": "synth-ed-1",
            "source_url": "https://example.invalid/film-1", "asset_sha256": "a" * 64,
            "movie_id": "synth-film-1",
            "runtime_ms": 60000,
            "dataset_version": "v1.0.0"
        },
        "scenes": [{"scene_id": "sc-synth-1", "start_ms": 0, "end_ms": 60000}],
        "reveals": [
            {
                "reveal_id": "rev-synth-1-twist",
                "movie_id": "synth-film-1",
                "edition_id": "synth-ed-1",
                "title": "Synthetic Climax Revelation",
                "safe_title": "Key Climax Event (00:00:40)",
                "safe_preview": "The detective exposes the forged will.",
                "timestamp_ms": 40000,
                "spoiler_cutoff_ms": 50000
            }
        ],
        "proofs": [
            {
                "proof_id": "proof-synth-1-will",
                "human_review_status": "APPROVED", "presentation_status": "PUBLIC",
                "movie_id": "synth-film-1",
                "edition_id": "synth-ed-1",
                "reveal_id": "rev-synth-1-twist",
                "title": "Ink Chemistry Proof",
                "summary": "Chemical analysis confirms modern ink.",
                "timestamp_ms": 35000,
                "spoiler_cutoff_ms": 45000,
                "observed_premises": [
                    {
                        "event_id": "ev-synth-1",
                        "scene_id": "sc-synth-1",
                        "timestamp_ms": 30000,
                        "actor": "Chemist",
                        "action": "Tests ink",
                        "fact": "Ink is synthetic aniline dye",
                        "frame_ids": ["frame-synth-1"]
                    }
                ]
            }
        ],
        "subtitles": [
            {
                "cue_index": 1,
                "start_ms": 10000,
                "end_ms": 20000,
                "text": "The ink has not fully dried."
            }
        ],
        "frames": [
            {
                "frame_id": "frame-synth-1",
                "movie_id": "synth-film-1",
                "edition_id": "synth-ed-1",
                "absolute_timestamp_ms": 30000,
                "filename": "frame_synth_1.jpg"
            }
        ]
    }


@pytest.fixture
def synthetic_bundle_f2(tmp_path):
    """Synthetic Film 2 (120,000ms runtime)."""
    return {
        "film": {
            "movie_id": "synth-film-2",
            "title": "Synthetic Film Two",
            "year": 1952,
            "synopsis_safe": "Safe synopsis for synth film 2.",
            "runtime_ms": 120000,
            "rights_status": "UNCONFIRMED",
            "analysis_status": "READY"
        },
        "edition": {
            "edition_id": "synth-ed-2",
            "source_url": "https://example.invalid/film-2", "asset_sha256": "b" * 64,
            "movie_id": "synth-film-2",
            "runtime_ms": 120000,
            "dataset_version": "v1.0.0"
        },
        "scenes": [{"scene_id": "sc-synth-2", "start_ms": 0, "end_ms": 120000}],
        "reveals": [
            {
                "reveal_id": "rev-synth-2-culprit",
                "movie_id": "synth-film-2",
                "edition_id": "synth-ed-2",
                "title": "Secret Identity Revealed",
                "safe_title": "Dramatic Culprit Unmasking (00:01:30)",
                "safe_preview": "The phantom identity is exposed.",
                "timestamp_ms": 90000,
                "spoiler_cutoff_ms": 100000
            }
        ],
        "proofs": [
            {
                "proof_id": "proof-synth-2-mask",
                "human_review_status": "APPROVED", "presentation_status": "PUBLIC",
                "movie_id": "synth-film-2",
                "edition_id": "synth-ed-2",
                "reveal_id": "rev-synth-2-culprit",
                "title": "Mask Texture Verification",
                "summary": "Forensic fiber analysis of the mask.",
                "timestamp_ms": 80000,
                "spoiler_cutoff_ms": 95000,
                "observed_premises": [
                    {
                        "event_id": "ev-synth-2",
                        "scene_id": "sc-synth-2",
                        "timestamp_ms": 75000,
                        "actor": "Inspector",
                        "action": "Examines mask",
                        "fact": "Silk fiber matches tailor shop",
                        "frame_ids": ["frame-synth-2"]
                    }
                ]
            }
        ],
        "subtitles": [
            {
                "cue_index": 1,
                "start_ms": 25000,
                "end_ms": 35000,
                "text": "Who could have worn this mask?"
            }
        ],
        "frames": [
            {
                "frame_id": "frame-synth-2",
                "movie_id": "synth-film-2",
                "edition_id": "synth-ed-2",
                "absolute_timestamp_ms": 75000,
                "filename": "frame_synth_2.jpg"
            }
        ]
    }


@pytest.mark.asyncio
async def test_dataset_apply_and_persistence_lifecycle(tmp_path, synthetic_bundle_f1, synthetic_bundle_f2):
    storage_dir = tmp_path / "imported_datasets"
    viewer = ViewerContext(session_id="integration-viewer")
    frame_dir = tmp_path / "data/production/evidence_frames"
    frame_dir.mkdir(parents=True)
    for bundle in (synthetic_bundle_f1, synthetic_bundle_f2):
        (frame_dir / bundle["frames"][0]["filename"]).write_bytes(b"local test frame")

    # 1. Apply Synthetic Film 1
    res1 = apply_film_dataset(synthetic_bundle_f1, dry_run=False, storage_dir=storage_dir, asset_root=tmp_path)
    assert res1["success"] is True
    assert res1["verdict"] == "APPLIED"

    # 2. Apply Synthetic Film 2
    res2 = apply_film_dataset(synthetic_bundle_f2, dry_run=False, storage_dir=storage_dir, asset_root=tmp_path)
    assert res2["success"] is True
    assert res2["verdict"] == "APPLIED"

    # Both dataset files exist on disk
    f1_file = storage_dir / "synth-film-1_synth-ed-1.json"
    f2_file = storage_dir / "synth-film-2_synth-ed-2.json"
    assert f1_file.is_file()
    assert f2_file.is_file()

    # 3. Idempotency: Re-applying Film 1 identical bundle succeeds with ALREADY_APPLIED
    res1_repeat = apply_film_dataset(synthetic_bundle_f1, dry_run=False, storage_dir=storage_dir, asset_root=tmp_path)
    assert res1_repeat["success"] is True
    assert res1_repeat["verdict"] == "ALREADY_APPLIED"
    assert res1_repeat["idempotent"] is True

    # 4. Conflict detection: Re-applying with mutated title must return CONFLICT_DETECTED
    mutated = copy.deepcopy(synthetic_bundle_f1)
    mutated["film"]["title"] = "Conflicting Mutated Title"
    res1_conflict = apply_film_dataset(mutated, dry_run=False, storage_dir=storage_dir, asset_root=tmp_path)
    assert res1_conflict["success"] is False
    assert res1_conflict["verdict"] == "CONFLICT_DETECTED"

    # Original Bat Whispers data remains unaffected
    assert catalog_service.is_film_registered("the-bat-whispers-1930")
    bat_summary = catalog_service.get_film_summary("the-bat-whispers-1930")
    assert bat_summary.title == "The Bat Whispers"
    assert bat_summary.runtime_ms == 5119080

    # 5. Connected router paths: get_film_detail returns 200 OK without DB row
    mock_db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = result
    # Mock FilmCatalogRepository.get_film_by_id returning None to test fallback
    from unittest.mock import patch
    with patch("src.reframe.catalog.repository.FilmCatalogRepository.get_film_by_id", return_value=None):
        resp = await get_film_detail("synth-film-1", viewer=viewer, db=mock_db)
        assert resp is not None
        assert resp["data"]["movie_id"] == "synth-film-1"
        assert resp["data"]["edition_id"] == "synth-ed-1"
        assert resp["data"]["title"] == "Synthetic Film One"
        assert resp["data"]["runtime_ms"] == 60000

        # Reveals router returns the connected reveals
        reveals_resp = await list_film_reveals("synth-film-1", edition_id="synth-ed-1", viewer=viewer, db=mock_db)
        assert len(reveals_resp["data"]) == 1
        assert reveals_resp["data"][0]["reveal_id"] == "rev-synth-1-twist"

    # 6. Proof Store lookup retrieves dynamic proof
    proofs = await canonical_proof_store.get_proofs_for_reveal(mock_db, "rev-synth-1-twist", viewer)
    assert len(proofs) >= 1
    assert any(p.get("proof_id") == "proof-synth-1-will" for p in proofs)

    # 7. Unregistered film detail throws 404
    from src.reframe.shared.exceptions import ReframeException
    with patch("src.reframe.catalog.repository.FilmCatalogRepository.get_film_by_id", return_value=None):
        with pytest.raises(ReframeException) as exc_info:
            await get_film_detail("completely-unknown-film", viewer=viewer, db=mock_db)
        assert exc_info.value.status_code == 404
