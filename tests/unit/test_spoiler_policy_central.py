"""
Unit Tests for Central Spoiler Policy, ViewerContext, and Payload Redaction
"""
import uuid
import pytest

from src.reframe.identity.auth import ViewerContext
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import (
    evaluate_spoiler_visibility,
    sanitize_payload_for_viewer,
    SpoilerVisibility
)


def test_spoiler_policy_unwatched_guest_is_locked():
    scope = SpoilerScope(
        id=uuid.uuid4(),
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        minimum_progress_ms=4860000,
        required_reveal_ids=["reveal-anderson-identity"],
        severity="ENDING",
        safe_title="The unmasking of the true killer",
        safe_preview="The truth of who committed the murders."
    )
    guest_viewer = ViewerContext(roles=["GUEST"])
    visibility = evaluate_spoiler_visibility(scope, guest_viewer)
    assert visibility == SpoilerVisibility.LOCKED


def test_spoiler_policy_completed_viewer_is_visible():
    scope = SpoilerScope(
        id=uuid.uuid4(),
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        minimum_progress_ms=4860000,
        required_reveal_ids=["reveal-anderson-identity"],
        severity="ENDING"
    )
    completed_viewer = ViewerContext(
        user_id=uuid.uuid4(),
        roles=["USER"],
        work_progress_by_edition={"the-bat-whispers-1930:tbw-fullscreen-archive": 5000000},
        completed_reveal_ids=["reveal-anderson-identity"]
    )
    visibility = evaluate_spoiler_visibility(scope, completed_viewer)
    assert visibility == SpoilerVisibility.VISIBLE


def test_spoiler_policy_admin_override_always_visible():
    scope = SpoilerScope(
        id=uuid.uuid4(),
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        minimum_progress_ms=4860000,
        required_reveal_ids=["reveal-anderson-identity"]
    )
    admin_viewer = ViewerContext(
        user_id=uuid.uuid4(),
        roles=["ADMIN"]
    )
    assert evaluate_spoiler_visibility(scope, admin_viewer) == SpoilerVisibility.VISIBLE


def test_locked_payload_redaction_strips_sensitive_data():
    raw_payload = {
        "title": "Detective Anderson is secretly The Bat",
        "body_markdown": "In scene c011, Anderson operates the switch...",
        "body_sanitized_html": "<p>Anderson operates the switch</p>",
        "claim": "Anderson was guilty from the opening scene",
        "supporting_evidence": ["ev-c011-01", "ev-c017-02"]
    }
    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=SpoilerVisibility.LOCKED,
        safe_title="Key suspect analysis"
    )

    assert sanitized["visibility"] == "LOCKED"
    assert sanitized["title"] == "Key suspect analysis"
    assert "Anderson" not in sanitized["title"]
    assert "body_markdown" not in sanitized or sanitized["body_markdown"] is None
    assert "claim" not in sanitized or sanitized["claim"] is None
    assert "supporting_evidence" not in sanitized or sanitized["supporting_evidence"] == []

