"""
Unit & contract tests for multi-film media and evidence frame endpoints.
Covers requirements M04, M05, path containment, and spoiler gating.
Zero paid model calls.
"""
import pytest
from fastapi import HTTPException
from src.reframe.identity.auth import ViewerContext
from apps.api.routers.media import evidence_frame, register_evidence_frame


@pytest.mark.asyncio
async def test_m04_unknown_film_or_invalid_frame_returns_404():
    """M04: Unknown work_id, edition_id, or non-existent frame returns 404 without leaking files."""
    viewer = ViewerContext(session_id="viewer-1")

    # 1. Unknown work_id returns 404
    with pytest.raises(HTTPException) as exc_info:
        await evidence_frame(
            work_id="completely-unknown-film-1999",
            edition_id="default-edition",
            frame_id="frame-001",
            viewer=viewer
        )
    assert exc_info.value.status_code == 404

    # 2. Unknown frame_id for valid film returns 404
    with pytest.raises(HTTPException) as exc_info:
        await evidence_frame(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            frame_id="non-existent-frame-xyz",
            viewer=viewer
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_m05_protected_frame_below_cutoff_returns_403():
    """M05: Requesting frame when viewer progress is below timestamp returns 403 with private no-store headers."""
    # Register a dynamic test frame at 60,000ms
    register_evidence_frame(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        frame_id="test-frame-climax",
        timestamp_ms=60000,
        filename="test_frame.jpg"
    )

    # Viewer at 10,000ms (< 60,000ms)
    viewer_below = ViewerContext(
        session_id="viewer-below",
        work_progress_by_edition={
            "the-bat-whispers-1930:tbw-fullscreen-archive": 10000
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        await evidence_frame(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            frame_id="test-frame-climax",
            viewer=viewer_below
        )
    assert exc_info.value.status_code == 403
    assert "Watch progress is below" in exc_info.value.detail
    assert exc_info.value.headers.get("Cache-Control") == "private, no-store"
