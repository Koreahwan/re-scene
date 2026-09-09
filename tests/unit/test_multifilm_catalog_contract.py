"""
Unit & contract tests for multi-film catalog, reveal isolation, and watch progress validation.
Covers requirements M01, M02, M03, M06, D01, D02.
Zero paid model calls.
"""
import pytest
from src.reframe.catalog.service import catalog_service, THE_BAT_WHISPERS_FILM
from src.reframe.catalog.dataset_import import validate_film_dataset, dry_run_import
from src.reframe.identity.auth import ViewerContext


def test_m01_reveals_filtered_strictly_by_movie_and_edition():
    """M01: Reveals query for a registered movie returns only its reveals, not Bat Whispers or other films."""
    viewer = ViewerContext(session_id="test-session-1")

    # The Bat Whispers has 4 reveals
    bat_reveals = catalog_service.get_reveals("the-bat-whispers-1930", viewer)
    assert len(bat_reveals) == 4
    for r in bat_reveals:
        assert r.work_id == "the-bat-whispers-1930"
        assert r.edition_id == "tbw-fullscreen-archive"

    # Detour (candidate demo film without ingested reveals) must return 0 reveals, NOT Bat Whispers reveals!
    detour_reveals = catalog_service.get_reveals("detour-1945", viewer)
    assert len(detour_reveals) == 0

    # D.O.A. must return 0 reveals
    doa_reveals = catalog_service.get_reveals("doa-1950", viewer)
    assert len(doa_reveals) == 0


def test_m02_watch_progress_rejects_foreign_edition_or_reveal_ids():
    """M02: Watch progress validation rejects foreign edition, out-of-bounds progress, or foreign reveal IDs."""
    # 1. Foreign edition for Bat Whispers must be rejected
    with pytest.raises(ValueError, match="is not registered"):
        catalog_service.validate_watch_progress(
            work_id="the-bat-whispers-1930",
            edition_id="foreign-edition-id",
            progress_ms=10000,
            completed_reveal_ids=[]
        )

    # 2. Out-of-bounds progress for Bat Whispers (> 5119080 ms) must be rejected
    with pytest.raises(ValueError, match="out of valid bounds"):
        catalog_service.validate_watch_progress(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            progress_ms=99999999,
            completed_reveal_ids=[]
        )

    # 3. Foreign/hallucinated reveal ID must be rejected
    with pytest.raises(ValueError, match="Invalid completed reveal ID"):
        catalog_service.validate_watch_progress(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            progress_ms=10000,
            completed_reveal_ids=["non-existent-or-foreign-reveal-id"]
        )

    # 4. Valid progress within bounds must succeed
    catalog_service.validate_watch_progress(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        progress_ms=2500000,
        completed_reveal_ids=["reveal-masked-robbery-vault"]
    )


def test_m03_known_candidate_film_returns_preparing_without_bat_fallback():
    """M03: Known candidate film returns preparing metadata, not Bat Whispers data or fake analysis."""
    viewer = ViewerContext(session_id="test-session-2")

    detail = catalog_service.get_film_detail("detour-1945", viewer)
    assert detail is not None
    assert detail.movie_id == "detour-1945"
    assert detail.edition_id == "detour-ia-Detour-mp4"
    assert detail.title == "Detour"
    assert detail.runtime_ms == 4058320
    assert detail.analysis_status == "PREPARING"
    assert detail.reveals_count == 0


def test_m06_dataset_import_validation_and_dry_run():
    """M06: Dataset import utility strictly validates bundle contracts without database mutations."""
    valid_bundle = {
        "film": {
            "movie_id": "test-film-1940",
            "title": "Test Film",
            "year": 1940,
            "synopsis_safe": "Safe synopsis.",
            "runtime_ms": 3600000,
            "rights_status": "PUBLIC_DOMAIN",
            "analysis_status": "READY"
        },
        "edition": {
            "edition_id": "test-edition-v1",
            "asset_sha256": "a" * 64,
            "source_url": "https://example.invalid/test-source",
            "movie_id": "test-film-1940",
            "runtime_ms": 3600000,
            "dataset_version": "v1.0.0"
        },
        "reveals": [
            {
                "reveal_id": "rev-01",
                "movie_id": "test-film-1940",
                "edition_id": "test-edition-v1",
                "title": "Secret Reveal",
                "safe_title": "Safe Twist",
                "safe_preview": "A dramatic turn of events.",
                "timestamp_ms": 1200000,
                "spoiler_cutoff_ms": 1800000
            }
        ],
        "proofs": [
            {
                "proof_id": "prf-01",
                "movie_id": "test-film-1940",
                "edition_id": "test-edition-v1",
                "reveal_id": "rev-01",
                "title": "Proof of identity",
                "summary": "Forensic evidence summary.",
                "timestamp_ms": 1200000,
                "spoiler_cutoff_ms": 1800000
            }
        ],
        "subtitles": [
            {
                "cue_index": 1,
                "start_ms": 1000,
                "end_ms": 5000,
                "text": "Hello world"
            }
        ],
        "frames": [
            {
                "frame_id": "frame-001",
                "movie_id": "test-film-1940",
                "edition_id": "test-edition-v1",
                "absolute_timestamp_ms": 1200000,
                "filename": "frame-001.jpg"
            }
        ]
    }

    # Dry run should pass
    result = dry_run_import(valid_bundle)
    assert result["success"] is True
    assert result["verdict"] == "READY_FOR_IMPORT"
    assert result["counts"]["reveals"] == 1
    assert result["counts"]["proofs"] == 1

    # Invalid bundle: timestamp exceeds runtime
    invalid_bundle = dict(valid_bundle)
    invalid_bundle["reveals"] = [
        dict(valid_bundle["reveals"][0], timestamp_ms=9999999)
    ]
    is_valid, errors = validate_film_dataset(invalid_bundle)
    assert is_valid is False
    assert any("exceeds edition runtime" in err for err in errors)
