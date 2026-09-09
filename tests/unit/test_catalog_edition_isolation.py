"""
Unit tests for strict Film AND Edition isolation in CatalogService (R2-03).
Covers:
- Registering Movie A with editions A1 & A2 and Movie B with edition B1.
- Query isolation across editions and movies.
- Cross-reveal watch progress validation rejection.
- Edition switching without registry overwrite.
- Prohibition of synthetic default fallbacks for unregistered editions.
- Rejection of duplicate/conflicting reveal IDs across movies/editions.
- Rejection of invalid runtime (0, negative, missing).
Zero paid model calls.
"""
import pytest
from src.reframe.catalog.service import CatalogService
from src.reframe.identity.auth import ViewerContext


def test_film_and_edition_isolation_multi_edition():
    service = CatalogService()
    viewer = ViewerContext(session_id="test-viewer")

    # 1. Register Movie A - Edition A1 (runtime 60,000ms)
    service.register_film_dataset(
        movie_id="movie-a",
        film_entry={
            "movie_id": "movie-a",
            "edition_id": "ed-a1",
            "title": "Movie A - Edition 1",
            "dataset_version": "test-v1", "reveals_count": 1, "scenes_count": 0,
            "year": 1940,
            "synopsis_safe": "A mysterious incident.",
            "runtime_ms": 60000,
            "rights_status": "UNCONFIRMED",
            "analysis_status": "READY"
        },
        reveals=[
            {
                "reveal_id": "rev-a1-twist",
                "movie_id": "movie-a",
                "edition_id": "ed-a1",
                "title": "Twist A1",
                "timestamp_ms": 20000,
                "spoiler_cutoff_ms": 30000,
                "safe_title": "Safe Twist A1",
                "safe_preview": "Preview A1"
            }
        ]
    )

    # 2. Register Movie A - Edition A2 (runtime 90,000ms) with different reveals
    service.register_film_dataset(
        movie_id="movie-a",
        film_entry={
            "movie_id": "movie-a",
            "edition_id": "ed-a2",
            "title": "Movie A - Edition 2 (Director's Cut)",
            "dataset_version": "test-v1", "reveals_count": 1, "scenes_count": 0,
            "year": 1940,
            "synopsis_safe": "A mysterious incident with extended cut.",
            "runtime_ms": 90000,
            "rights_status": "UNCONFIRMED",
            "analysis_status": "READY"
        },
        reveals=[
            {
                "reveal_id": "rev-a2-climax",
                "movie_id": "movie-a",
                "edition_id": "ed-a2",
                "title": "Climax A2",
                "timestamp_ms": 50000,
                "spoiler_cutoff_ms": 60000,
                "safe_title": "Safe Climax A2",
                "safe_preview": "Preview A2"
            }
        ]
    )

    # 3. Register Movie B - Edition B1 (runtime 45,000ms)
    service.register_film_dataset(
        movie_id="movie-b",
        film_entry={
            "movie_id": "movie-b",
            "edition_id": "ed-b1",
            "title": "Movie B",
            "dataset_version": "test-v1", "reveals_count": 1, "scenes_count": 0,
            "year": 1950,
            "synopsis_safe": "Noir detective story.",
            "runtime_ms": 45000,
            "rights_status": "UNCONFIRMED",
            "analysis_status": "READY"
        },
        reveals=[
            {
                "reveal_id": "rev-b1-suspect",
                "movie_id": "movie-b",
                "edition_id": "ed-b1",
                "title": "Suspect B1",
                "timestamp_ms": 15000,
                "spoiler_cutoff_ms": 25000,
                "safe_title": "Safe Suspect B1",
                "safe_preview": "Preview B1"
            }
        ]
    )

    # --- Verification 1: Both editions of Movie A exist and are not overwritten ---
    detail_a1 = service.get_film_detail("movie-a", viewer, edition_id="ed-a1")
    detail_a2 = service.get_film_detail("movie-a", viewer, edition_id="ed-a2")
    detail_b1 = service.get_film_detail("movie-b", viewer, edition_id="ed-b1")

    assert detail_a1 is not None and detail_a1.runtime_ms == 60000
    assert detail_a2 is not None and detail_a2.runtime_ms == 90000
    assert detail_b1 is not None and detail_b1.runtime_ms == 45000

    # Unregistered edition returns None (no synthetic fallback!)
    assert service.get_film_detail("movie-a", viewer, edition_id="ed-unknown") is None

    # --- Verification 2: Query Isolation for Reveals ---
    reveals_a1 = service.get_reveals("movie-a", viewer, edition_id="ed-a1")
    assert len(reveals_a1) == 1
    assert reveals_a1[0].reveal_id == "rev-a1-twist"
    assert reveals_a1[0].edition_id == "ed-a1"

    reveals_a2 = service.get_reveals("movie-a", viewer, edition_id="ed-a2")
    assert len(reveals_a2) == 1
    assert reveals_a2[0].reveal_id == "rev-a2-climax"
    assert reveals_a2[0].edition_id == "ed-a2"

    reveals_b1 = service.get_reveals("movie-b", viewer, edition_id="ed-b1")
    assert len(reveals_b1) == 1
    assert reveals_b1[0].reveal_id == "rev-b1-suspect"
    assert reveals_b1[0].edition_id == "ed-b1"

    # Querying reveals for an unregistered edition returns empty list
    assert service.get_reveals("movie-a", viewer, edition_id="ed-nonexistent") == []

    # --- Verification 3: Cross-reveal watch progress validation rejection ---
    # Valid progress for A1
    service.validate_watch_progress("movie-a", "ed-a1", 25000, ["rev-a1-twist"])

    # Attempting to validate A1 progress with A2's reveal ID must fail
    with pytest.raises(ValueError, match="Invalid completed reveal ID"):
        service.validate_watch_progress("movie-a", "ed-a1", 25000, ["rev-a2-climax"])

    # Attempting to validate A1 progress with B1's reveal ID must fail
    with pytest.raises(ValueError, match="Invalid completed reveal ID"):
        service.validate_watch_progress("movie-a", "ed-a1", 25000, ["rev-b1-suspect"])

    # Attempting to validate A2 progress with A1's reveal ID must fail
    with pytest.raises(ValueError, match="Invalid completed reveal ID"):
        service.validate_watch_progress("movie-a", "ed-a2", 55000, ["rev-a1-twist"])

    # Unregistered edition in watch progress validation must fail
    with pytest.raises(ValueError, match="not registered"):
        service.validate_watch_progress("movie-a", "ed-unknown", 1000, [])


def test_registration_validation_and_conflict_rejection():
    service = CatalogService()

    # 1. Rejection of whitespace-only / empty IDs
    with pytest.raises(ValueError, match="movie_id cannot be empty"):
        service.register_film_dataset("   ", {"edition_id": "ed-1", "runtime_ms": 10000})

    with pytest.raises(ValueError, match="edition_id cannot be empty"):
        service.register_film_dataset("test-film", {"edition_id": "  ", "runtime_ms": 10000})

    # 2. Rejection of invalid / non-positive runtime
    with pytest.raises(ValueError, match="runtime_ms must be a positive integer"):
        service.register_film_dataset("test-film", {"edition_id": "ed-1", "runtime_ms": 0})

    with pytest.raises(ValueError, match="runtime_ms must be a positive integer"):
        service.register_film_dataset("test-film", {"edition_id": "ed-1", "runtime_ms": -500})

    # 3. Rejection of mismatched movie_id between argument and film_entry
    with pytest.raises(ValueError, match="does not match registered movie_id"):
        service.register_film_dataset("film-x", {"movie_id": "film-y", "edition_id": "ed-1", "runtime_ms": 5000})

    # 4. Register a valid dataset
    service.register_film_dataset(
        movie_id="film-x",
        film_entry={"edition_id": "ed-1", "runtime_ms": 50000},
        reveals=[
            {
                "reveal_id": "rev-shared-id",
                "movie_id": "film-x",
                "edition_id": "ed-1",
                "title": "Secret",
                "timestamp_ms": 10000,
                "spoiler_cutoff_ms": 20000
            }
        ]
    )

    # 5. Attempting to register another film/edition with the identical reveal_id must be rejected
    with pytest.raises(ValueError, match="conflicts with existing registration"):
        service.register_film_dataset(
            movie_id="film-z",
            film_entry={"edition_id": "ed-1", "runtime_ms": 50000},
            reveals=[
                {
                    "reveal_id": "rev-shared-id",
                    "movie_id": "film-z",
                    "edition_id": "ed-1",
                    "title": "Colliding Reveal",
                    "timestamp_ms": 10000,
                    "spoiler_cutoff_ms": 20000
                }
            ]
        )

    # 6. Reveal movie_id mismatch must be rejected
    with pytest.raises(ValueError, match="does not match target movie"):
        service.register_film_dataset(
            movie_id="film-safe",
            film_entry={"edition_id": "ed-1", "runtime_ms": 50000},
            reveals=[
                {
                    "reveal_id": "rev-safe-1",
                    "movie_id": "foreign-movie",
                    "edition_id": "ed-1",
                    "title": "Foreign",
                    "timestamp_ms": 10000
                }
            ]
        )

    # 7. Reveal edition_id mismatch must be rejected
    with pytest.raises(ValueError, match="does not match target edition"):
        service.register_film_dataset(
            movie_id="film-safe",
            film_entry={"edition_id": "ed-1", "runtime_ms": 50000},
            reveals=[
                {
                    "reveal_id": "rev-safe-2",
                    "movie_id": "film-safe",
                    "edition_id": "ed-foreign",
                    "title": "Foreign Edition",
                    "timestamp_ms": 10000
                }
            ]
        )
