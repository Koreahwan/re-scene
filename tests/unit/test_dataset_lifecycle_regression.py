"""Imported editions survive restart without leaking state on failed publication."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.routers import catalog, media
from src.reframe.catalog import dataset_import as importer
from src.reframe.catalog.service import catalog_service
from src.reframe.identity.auth import ViewerContext, get_authenticated_user, get_viewer_context
from src.reframe.proof import store
from src.reframe.shared.database import get_db


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    for name, value in catalog_service.__dict__.items():
        monkeypatch.setattr(catalog_service, name, copy.deepcopy(value))
    monkeypatch.setattr(importer, "_APPLIED_BUNDLE_HASHES", {})
    monkeypatch.setattr(store, "_DYNAMIC_PROOFS_BY_ID", {})
    monkeypatch.setattr(store, "_DYNAMIC_PROOFS_BY_REVEAL", {})
    monkeypatch.setattr(media, "_DYNAMIC_FRAME_REGISTRY", {})


@pytest.fixture
def bundle(tmp_path):
    video = tmp_path / "data/external/raw/test/clip.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(bytes(range(128)))
    frame = tmp_path / "data/production/evidence_frames/test.jpg"
    frame.parent.mkdir(parents=True)
    frame.write_bytes(b"test image bytes")
    return {
        "film": {"movie_id": "lifecycle-film", "title": "Lifecycle Film", "year": 1940,
            "synopsis_safe": "Safe synopsis", "runtime_ms": 60000, "rights_status": "APPROVED", "analysis_status": "READY"},
        "edition": {"movie_id": "lifecycle-film", "edition_id": "edition-one", "runtime_ms": 60000,
            "dataset_version": "test-v1", "source_url": "https://example.invalid/fixture",
            "asset_sha256": hashlib.sha256(video.read_bytes()).hexdigest(), "rights_review_status": "APPROVED"},
        "media": {"filename": "test/clip.mp4", "asset_status": "APPROVED"},
        "scenes": [{"scene_id": "scene-one", "start_ms": 0, "end_ms": 20000}],
        "reveals": [{"reveal_id": "lifecycle-reveal", "movie_id": "lifecycle-film", "edition_id": "edition-one",
            "title": "Reveal sentinel", "safe_title": "Protected reveal", "safe_preview": "Watch to unlock",
            "timestamp_ms": 25000, "spoiler_cutoff_ms": 30000}],
        "proofs": [{"proof_id": "lifecycle-proof", "movie_id": "lifecycle-film", "edition_id": "edition-one",
            "reveal_id": "lifecycle-reveal", "title": "Proof sentinel", "summary": "Interpretation sentinel",
            "timestamp_ms": 10000, "spoiler_cutoff_ms": 30000,
            "human_review_status": "APPROVED", "presentation_status": "PUBLIC",
            "observed_premises": [{"event_id": "event-one", "scene_id": "scene-one", "timestamp_ms": 10000,
                "actor": "Actor", "action": "Action", "fact": "Fact", "frame_ids": ["frame-one"]}]}],
        "frames": [{"frame_id": "frame-one", "movie_id": "lifecycle-film", "edition_id": "edition-one",
            "absolute_timestamp_ms": 10000, "filename": "test.jpg"}],
    }


def apply(bundle, root):
    return importer.apply_film_dataset(bundle, False, root / "bundles", asset_root=root)


def test_release_restore_does_not_require_writable_dataset_storage(bundle, tmp_path, monkeypatch):
    def forbidden_lock(_):
        raise AssertionError("Read-only restore must not open a writer lock file")
    monkeypatch.setattr(importer, "_storage_lock", forbidden_lock)
    storage = tmp_path / "not-created-by-restore"
    result = importer.apply_film_dataset(bundle, False, storage, asset_root=tmp_path, persist=False)
    assert result['success'], result
    assert not storage.exists()


def test_ai_binding_requires_this_bundles_unreviewed_hidden_proof(bundle):
    candidate = copy.deepcopy(bundle)
    candidate['ai_publications'] = [{'proof_id': 'foreign-proof', 'record_sha256': 'a' * 64}]
    assert not importer.validate_film_dataset(candidate)[0]
    candidate['ai_publications'][0]['proof_id'] = candidate['proofs'][0]['proof_id']
    assert not importer.validate_film_dataset(candidate)[0]
    candidate['proofs'][0].update(human_review_status='NOT_REVIEWED', presentation_status='HIDDEN_FROM_PUBLIC')
    assert importer.validate_film_dataset(candidate)[0]
    candidate['ai_publications'].append(candidate['ai_publications'][0])
    assert not importer.validate_film_dataset(candidate)[0]


def empty_db():
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    result.scalar_one_or_none.return_value = None
    db = AsyncMock()
    db.execute.return_value = result
    return db


@pytest.mark.parametrize("stage", ["catalog", "frame", "proof", "persist"])
def test_each_failed_stage_restores_all_registries(bundle, tmp_path, stage):
    states = [catalog_service.__dict__, media._DYNAMIC_FRAME_REGISTRY,
        store._DYNAMIC_PROOFS_BY_ID, store._DYNAMIC_PROOFS_BY_REVEAL, importer._APPLIED_BUNDLE_HASHES]
    before = copy.deepcopy(states)
    target = {"catalog": "src.reframe.catalog.service.CatalogService.register_film_dataset",
        "frame": "apps.api.routers.media.register_evidence_frame",
        "proof": "src.reframe.proof.store.register_dynamic_proof",
        "persist": "src.reframe.catalog.dataset_import.os.replace"}[stage]
    with patch(target, side_effect=OSError("injected failure")):
        outcome = apply(bundle, tmp_path)
    assert outcome["verdict"] == "APPLICATION_FAILED"
    assert states == before
    assert not list((tmp_path / "bundles").glob("*.json"))
    assert not list((tmp_path / "bundles").glob("*.tmp"))
    assert apply(bundle, tmp_path)["success"]
    assert apply(bundle, tmp_path)["verdict"] == "ALREADY_APPLIED"
    assert len(store._DYNAMIC_PROOFS_BY_REVEAL["lifecycle-reveal"]) == 1


def test_disk_conflict_survives_empty_hash_registry(bundle, tmp_path):
    assert apply(bundle, tmp_path)["success"]
    target = tmp_path / "bundles/lifecycle-film_edition-one.json"
    original = target.read_bytes()
    importer._APPLIED_BUNDLE_HASHES.clear()
    bundle["film"]["title"] = "Conflicting title"
    assert apply(bundle, tmp_path)["verdict"] == "CONFLICT_DETECTED"
    assert target.read_bytes() == original


@pytest.mark.parametrize("value", ["../escape", "bad/dir", "C:\\outside", "../..", " "])
def test_storage_identifier_rejects_path_components(bundle, tmp_path, value):
    bundle["edition"]["edition_id"] = value
    assert apply(bundle, tmp_path)["verdict"] == "VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_dynamic_list_and_detail_preserve_edition_and_cutoff(bundle, tmp_path):
    assert apply(bundle, tmp_path)["success"]
    second = copy.deepcopy(bundle)
    second["edition"]["edition_id"] = "edition-two"
    second["film"]["runtime_ms"] = second["edition"]["runtime_ms"] = 90000
    for section, identifier in (("reveals", "reveal_id"), ("proofs", "proof_id"), ("frames", "frame_id")):
        for item in second[section]:
            item["edition_id"] = "edition-two"
            item[identifier] += "-two"
    second["proofs"][0]["reveal_id"] += "-two"
    second["proofs"][0]["observed_premises"][0]["frame_ids"] = ["frame-one-two"]
    assert apply(second, tmp_path)["success"]
    viewer = ViewerContext(session_id="reader", work_progress_by_edition={
        "the-bat-whispers-1930:tbw-fullscreen-archive": 5119080, "lifecycle-film:edition-two": 90000})
    db = empty_db()
    first = await store.canonical_proof_store.get_proof_by_id(db, "lifecycle-proof", viewer)
    assert first["movie_id"] == "lifecycle-film" and first["edition_id"] == "edition-one"
    assert first["is_locked"] and "Interpretation sentinel" not in json.dumps(first)
    assert first["unlock_metadata"]["minimum_progress_ms"] == 30000
    viewer.work_progress_by_edition["lifecycle-film:edition-one"] = 30000
    detail = await store.canonical_proof_store.get_proof_by_id(db, "lifecycle-proof", viewer)
    listing = await store.canonical_proof_store.get_proofs_for_reveal(db, "lifecycle-reveal", viewer)
    assert listing == [detail]
    assert detail["spoiler_cutoff_ms"] == 30000
    assert detail["asset_sha256"] == bundle["edition"]["asset_sha256"]
    assert detail["reveal_explanation"] == "Interpretation sentinel"
    assert detail["verification_status"] != "VERIFIED_CANON"


def test_imported_video_disabled_while_scene_and_frame_routes_remain(bundle, tmp_path):
    assert apply(bundle, tmp_path)["success"]
    viewer = ViewerContext(session_id="route-reader", work_progress_by_edition={"lifecycle-film:edition-one": 60000})
    app = FastAPI()
    app.include_router(catalog.router, prefix="/api/v1")
    app.include_router(media.router, prefix="/api/v1")
    app.dependency_overrides[get_authenticated_user] = lambda: viewer
    app.dependency_overrides[get_viewer_context] = lambda: viewer
    app.dependency_overrides[get_db] = empty_db
    with TestClient(app) as client:
        response = client.get("/api/v1/films/lifecycle-film/media?edition_id=edition-one", headers={"Range": "bytes=0-9"})
        assert response.status_code == 410
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/api/v1/films/lifecycle-film/media?edition_id=unknown").status_code == 410
        scenes = client.get("/api/v1/films/lifecycle-film/scene-index?edition_id=edition-one").json()["data"]
        assert scenes == bundle["scenes"]
        viewer.work_progress_by_edition["lifecycle-film:edition-one"] = 0
        assert client.get("/api/v1/films/lifecycle-film/scene-index").json()["data"] == []
        assert client.get("/api/v1/media/lifecycle-film/edition-one/frames/frame-one").status_code == 403
        viewer.work_progress_by_edition["lifecycle-film:edition-one"] = 60000
        assert client.get("/api/v1/media/lifecycle-film/edition-one/frames/frame-one").content == b"test image bytes"
        with patch.object(catalog.FilmCatalogRepository, "get_film_by_id", return_value=None), patch.object(
                catalog.FilmCatalogRepository, "list_films", return_value=([], 0)):
            detail = client.get("/api/v1/films/lifecycle-film").json()["data"]
            assert detail["scenes_count"] == len(scenes)
            response = client.get("/api/v1/films?limit=5")
            assert "lifecycle-film" in [f["movie_id"] for f in response.json()["data"]]


def test_restart_runs_real_startup_restore_in_new_process(bundle, tmp_path):
    assert apply(bundle, tmp_path)["success"]
    source = r'''
import asyncio, json, sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from apps.api import main
from src.reframe.catalog.dataset_import import load_imported_datasets_from_disk
from src.reframe.catalog.service import catalog_service
from src.reframe.proof import store
from src.reframe.identity.auth import ViewerContext
root = Path(sys.argv[1])
assert not catalog_service.is_film_registered('lifecycle-film')
async def run():
    main.settings.SCHEMA_INIT_MODE = 'MIGRATIONS_ONLY'
    main.settings.EMBEDDED_WORKER_ENABLED = False
    with patch('src.reframe.shared.database.AsyncSessionLocal'), \
         patch.object(store.canonical_proof_store, 'seed_canonical_proofs', new=AsyncMock()), \
         patch.object(main.redis_client, 'connect', new=AsyncMock()), \
         patch.object(main.redis_client, 'close', new=AsyncMock()), \
         patch('src.reframe.catalog.dataset_import.load_imported_datasets_from_disk',
               side_effect=lambda path: load_imported_datasets_from_disk(root / 'bundles', asset_root=root)):
        async with main.lifespan(main.app):
            detail = catalog_service.get_film_detail('lifecycle-film', ViewerContext(session_id='restart'))
            assert detail.edition_id == 'edition-one' and detail.scenes_count == 1
            assert 'lifecycle-proof' in store._DYNAMIC_PROOFS_BY_ID
            print('RESTORED')
asyncio.run(run())
'''
    target = tmp_path / "bundles/lifecycle-film_edition-one.json"
    previous_mtime = target.stat().st_mtime_ns
    completed = subprocess.run([sys.executable, "-c", source, str(tmp_path)], cwd=Path(__file__).resolve().parents[2],
        text=True, capture_output=True, timeout=30)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "RESTORED" in completed.stdout
    assert target.stat().st_mtime_ns == previous_mtime


def test_corrupt_restore_is_reported(bundle, tmp_path):
    assert apply(bundle, tmp_path)["success"]
    (tmp_path / "bundles/broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(RuntimeError, match="broken.json"):
        importer.load_imported_datasets_from_disk(tmp_path / "bundles", asset_root=tmp_path)
