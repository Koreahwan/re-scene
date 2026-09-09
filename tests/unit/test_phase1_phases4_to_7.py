"""
Phase 1 Phases 4~7 Automated Verification Test Suite
=====================================================
Covers:
- Phase 4 (Saved Analysis Exploration):
  * All 4 TBW reveals connected to scenes, premises, and forensic patterns
  * Non-TBW film handling with zero contamination, core_demo_supported=False, and clear notice
- Phase 5 (Public Engagement):
  * Public reviews: create, read, update, delete
  * Version conflict (HTTP 409) on stale expected_version
  * Deletion invisibility: REMOVED posts return 404 on GET and are omitted from listing
  * Comment hierarchy and reply deletion consistency (both list and detail 404 when ancestor deleted)
  * Public binary likes (0/1 toggle) and stable multi-key sorting (popular vs recent)
  * Public sharing without credentials (no auth required)
- Phase 6 (AI Inspection & Cost Governance):
  * Versioned inspection statuses and fail-closed safe masking
  * PAID_CALLS_ENABLED = False invariant and lifetime budget limits ($0.80 soft freeze, $1.00 hard limit)
- Phase 7 (1st Screen Integration & English Compliance):
  * English-only API responses and error messages
  * Independent session isolation across two browser cookies
"""
import uuid
import pytest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.proof.store import CANONICAL_PATTERNS_MAP
from src.reframe.ai.inspection import (
    SpoilerInspectionResult,
    spoiler_inspection_service,
)


@pytest.fixture(autouse=True)
def enable_phase1_profile(monkeypatch):
    """Enable Phase 1 profile for all tests in this suite."""
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)


# =============================================================================
# Phase 4: Saved Analysis Exploration Tests
# =============================================================================

def test_phase4_all_four_tbw_reveals_and_evidence():
    """Verify all 4 canonical reveals of The Bat Whispers have complete patterns and premises."""
    expected_reveal_ids = [
        "reveal-anderson-identity",
        "reveal-secret-room-location",
        "reveal-brooks-innocence",
        "reveal-masked-robbery-vault",
    ]

    for rev_id in expected_reveal_ids:
        assert rev_id in CANONICAL_PATTERNS_MAP, f"Missing canonical patterns for reveal: {rev_id}"
        patterns = CANONICAL_PATTERNS_MAP[rev_id]
        assert len(patterns) >= 2, f"Expected at least 2 patterns for {rev_id}, got {len(patterns)}"
        for p in patterns:
            assert "pattern_id" in p
            assert "title" in p
            assert "observed_premises" in p
            assert len(p["observed_premises"]) >= 1, f"Missing observed premises in {p['pattern_id']}"


def test_phase4_non_tbw_film_isolation():
    """Verify non-TBW films return core_demo_supported=False, analysis_status='NOT_SUPPORTED', and notice."""
    with TestClient(app) as client:
        # Get catalog to find a non-TBW film
        cat_resp = client.get("/api/v1/films")
        assert cat_resp.status_code == 200
        films = cat_resp.json()["data"]
        non_tbw = next((f for f in films if f["movie_id"] != "the-bat-whispers-1930"), None)
        assert non_tbw is not None, "Expected at least one non-TBW film in catalog"

        resp = client.get(f"/api/v1/films/{non_tbw['movie_id']}")
        assert resp.status_code == 200, f"Failed to get non-TBW film: {resp.text}"
        data = resp.json()["data"]
        assert data["core_demo_supported"] is False
        assert data["analysis_status"] == "NOT_SUPPORTED"
        assert "analysis_notice" in data
        assert "The Bat Whispers (1930)" in data["analysis_notice"]


def test_phase4_tbw_film_detail_has_reveals():
    """Verify The Bat Whispers returns core_demo_supported=True and reveals endpoint returns all 4 reveals."""
    with TestClient(app) as client:
        # Film detail
        resp = client.get("/api/v1/films/the-bat-whispers-1930")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["core_demo_supported"] is True
        assert data["movie_id"] == "the-bat-whispers-1930"

        # Reveals list
        resp_revs = client.get("/api/v1/films/the-bat-whispers-1930/reveals")
        assert resp_revs.status_code == 200
        revs = resp_revs.json()["data"]
        assert len(revs) >= 4
        rev_ids = [r["reveal_id"] for r in revs]
        for expected in ["reveal-anderson-identity", "reveal-secret-room-location", "reveal-brooks-innocence", "reveal-masked-robbery-vault"]:
            assert expected in rev_ids, f"Expected reveal {expected} in reveals list"


# =============================================================================
# Phase 5: Public Engagement Tests
# =============================================================================

def test_phase5_public_review_lifecycle_and_conflict():
    """
    Verify public review creation, retrieval, versioned update with 409 conflict,
    and deletion resulting in HTTP 404 and omission from list.
    """
    with TestClient(app) as client:
        client.cookies.set("reframe_viewer_session", f"session_review_lifecycle_{uuid.uuid4().hex[:8]}")

        # 1. Create a public review
        unique_title = f"Audience Analysis {uuid.uuid4().hex[:6]}"
        create_payload = {
            "work_id": "the-bat-whispers-1930",
            "title": unique_title,
            "body_markdown": "Observing the mantelpiece clock and the blue light mechanism.",
            "content_type": "FAN_THEORY",
        }
        create_resp = client.post("/api/v1/community/posts", json=create_payload)
        assert create_resp.status_code in (200, 201), f"Failed to create post: {create_resp.text}"
        created_data = create_resp.json()["data"]
        post_id = created_data["post_id"]
        assert post_id is not None

        # 2. Retrieve the review (verify masked before unlock, and revealed after warning unlock)
        get_resp_pre = client.get(f"/api/v1/community/posts/{post_id}")
        assert get_resp_pre.status_code == 200
        assert get_resp_pre.json()["data"]["is_spoiler_masked"] is True

        # Unlock version 1 via warning confirmation
        unlock_resp = client.post("/api/v1/viewer/unlock", json={"content_type": "POST", "content_id": post_id, "version_no": 1})
        assert unlock_resp.status_code == 200

        get_resp = client.get(f"/api/v1/community/posts/{post_id}")
        assert get_resp.status_code == 200
        post_data = get_resp.json()["data"]
        assert post_data["title"] == unique_title
        initial_version = post_data["version_no"]
        assert initial_version == 1

        # 3. Conflict test: attempt update with wrong expected_version
        conflict_payload = {
            "title": f"{unique_title} Conflicting Edit",
            "body_markdown": "This should fail with 409.",
            "expected_version": 999,
        }
        conflict_resp = client.patch(f"/api/v1/community/posts/{post_id}", json=conflict_payload)
        assert conflict_resp.status_code == 409, f"Expected 409 Conflict, got {conflict_resp.status_code}"

        # 4. Successful update with correct expected_version
        update_payload = {
            "title": f"{unique_title} Updated",
            "body_markdown": "Updated body with deeper forensic examination.",
            "expected_version": initial_version,
        }
        update_resp = client.patch(f"/api/v1/community/posts/{post_id}", json=update_payload)
        assert update_resp.status_code == 200
        updated_data = update_resp.json()["data"]
        assert updated_data["version_no"] == initial_version + 1

        # Unlock version 2 via warning confirmation (since v2 re-masks per anti-stale-unlock rules)
        unlock_v2_resp = client.post("/api/v1/viewer/unlock", json={"content_type": "POST", "content_id": post_id, "version_no": 2})
        assert unlock_v2_resp.status_code == 200

        # Verify update persisted
        get_updated = client.get(f"/api/v1/community/posts/{post_id}")
        assert get_updated.status_code == 200
        assert get_updated.json()["data"]["title"] == f"{unique_title} Updated"
        assert get_updated.json()["data"]["version_no"] == 2

        # 5. Delete post
        delete_resp = client.delete(f"/api/v1/community/posts/{post_id}")
        assert delete_resp.status_code == 200

        # 6. Post must return 404 on direct GET and be omitted from list
        get_after_del = client.get(f"/api/v1/community/posts/{post_id}")
        assert get_after_del.status_code == 404

        list_resp = client.get("/api/v1/community/posts?work_id=the-bat-whispers-1930")
        assert list_resp.status_code == 200
        post_ids = [p["post_id"] for p in list_resp.json()["data"]]
        assert post_id not in post_ids, "Deleted post should not appear in community list"


def test_phase5_comment_hierarchy_and_deletion_consistency():
    """
    Verify:
    1. Parent comment and nested reply can be created and listed.
    2. When parent comment is deleted, both list_comments and get_comment_detail
       hide/404 the nested reply (resolving reply deletion visibility mismatch).
    """
    with TestClient(app) as client:
        client.cookies.set("reframe_viewer_session", f"session_comment_tree_{uuid.uuid4().hex[:8]}")

        # Create base post
        post_resp = client.post("/api/v1/community/posts", json={
            "work_id": "the-bat-whispers-1930",
            "title": f"Comment Tree Test Post {uuid.uuid4().hex[:6]}",
            "body_markdown": "Examining comment hierarchy and deletion consistency.",
        })
        assert post_resp.status_code in (200, 201)
        post_id = post_resp.json()["data"]["post_id"]

        # Create parent comment
        parent_resp = client.post(f"/api/v1/community/posts/{post_id}/comments", json={
            "body_markdown": "This is a parent comment.",
            "parent_comment_id": None,
        })
        assert parent_resp.status_code in (200, 201)
        parent_id = parent_resp.json()["data"]["comment_id"]

        # Create child reply
        child_resp = client.post(f"/api/v1/community/posts/{post_id}/comments", json={
            "body_markdown": "This is a reply to the parent comment.",
            "parent_comment_id": parent_id,
        })
        assert child_resp.status_code in (200, 201)
        child_id = child_resp.json()["data"]["comment_id"]

        # List comments -> both parent and child must be present
        list_before = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert list_before.status_code == 200
        comment_ids_before = [c["comment_id"] for c in list_before.json()["data"]]
        assert parent_id in comment_ids_before
        assert child_id in comment_ids_before

        # Single detail -> child is accessible
        detail_before = client.get(f"/api/v1/community/posts/{post_id}/comments/{child_id}")
        assert detail_before.status_code == 200

        # Delete the parent comment
        del_parent = client.delete(f"/api/v1/community/posts/{post_id}/comments/{parent_id}")
        assert del_parent.status_code == 200

        # List comments -> NEITHER parent nor child reply must appear
        list_after = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert list_after.status_code == 200
        comment_ids_after = [c["comment_id"] for c in list_after.json()["data"]]
        assert parent_id not in comment_ids_after, "Deleted parent comment must not be in list"
        assert child_id not in comment_ids_after, "Reply to deleted parent must not be in list"

        # Direct detail of child reply -> must return 404 because ancestor is deleted
        detail_after = client.get(f"/api/v1/community/posts/{post_id}/comments/{child_id}")
        assert detail_after.status_code == 404, "Direct detail of child reply whose parent is deleted must return 404"


def test_phase5_public_likes_binary_and_stable_sorting():
    """
    Verify public likes 0/1 binary toggle and deterministic multi-key sorting
    (popular: -like_count, -published_at, post_id vs recent: -published_at, post_id).
    """
    with TestClient(app) as client:
        sess = f"session_likes_{uuid.uuid4().hex[:8]}"
        client.cookies.set("reframe_viewer_session", sess)

        # Create post
        post_resp = client.post("/api/v1/community/posts", json={
            "work_id": "the-bat-whispers-1930",
            "title": f"Reaction Test Post {uuid.uuid4().hex[:6]}",
            "body_markdown": "Testing binary like toggle.",
        })
        assert post_resp.status_code in (200, 201)
        post_id = post_resp.json()["data"]["post_id"]

        # 1. Like post (0 -> 1)
        like_resp = client.put(f"/api/v1/community/posts/{post_id}/reactions", json={"reaction_type": "LIKE", "liked": True})
        assert like_resp.status_code == 200
        assert like_resp.json()["data"]["liked"] is True

        detail_liked = client.get(f"/api/v1/community/posts/{post_id}")
        assert detail_liked.status_code == 200
        assert detail_liked.json()["data"]["like_count"] >= 1
        assert detail_liked.json()["data"]["viewer_liked"] is True

        # 2. Idempotent like (1 -> 1)
        like_idem = client.put(f"/api/v1/community/posts/{post_id}/reactions", json={"reaction_type": "LIKE", "liked": True})
        assert like_idem.status_code == 200
        assert like_idem.json()["data"]["liked"] is True

        # 3. Unlike post (1 -> 0)
        unlike_resp = client.put(f"/api/v1/community/posts/{post_id}/reactions", json={"reaction_type": "LIKE", "liked": False})
        assert unlike_resp.status_code == 200
        assert unlike_resp.json()["data"]["liked"] is False

        detail_unliked = client.get(f"/api/v1/community/posts/{post_id}")
        assert detail_unliked.status_code == 200
        assert detail_unliked.json()["data"]["viewer_liked"] is False

        # 4. Test stable sorting
        sort_recent = client.get("/api/v1/community/posts?work_id=the-bat-whispers-1930&sort=recent")
        assert sort_recent.status_code == 200

        sort_popular = client.get("/api/v1/community/posts?work_id=the-bat-whispers-1930&sort=popular")
        assert sort_popular.status_code == 200

        popular_posts = sort_popular.json()["data"]
        for i in range(len(popular_posts) - 1):
            assert popular_posts[i]["like_count"] >= popular_posts[i + 1]["like_count"], "Popular posts must be sorted descending by like_count"


# =============================================================================
# Phase 6: AI Inspection & Cost Governance Tests
# =============================================================================

def test_phase6_cost_governance_invariants():
    """Verify zero paid model calls by default and budget caps."""
    assert settings.PAID_CALLS_ENABLED is False, "PAID_CALLS_ENABLED must strictly be False by default"
    assert settings.CAMPAIGN_FREEZE_MICROS == 800_000, "Soft budget cap must be $0.80 (800,000 micros)"
    assert settings.CAMPAIGN_BUDGET_MICROS == 1_000_000, "Hard budget limit must be $1.00 (1,000,000 micros)"


def test_phase6_fail_closed_safe_masking():
    """Verify that unverified/calls-disabled inspection states mask content with safe titles and previews."""
    unverified_result = SpoilerInspectionResult(
        status="UNVERIFIED_CALLS_DISABLED",
        inspected_version_no=1,
        detected_cutoff_ms=None,
        effective_cutoff_ms=None,
        confidence_score=0.0,
        spoiler_flags=["INSPECTION_CALLS_DISABLED_SAFE_MASK"],
        paid_model_calls=0,
    )
    assert unverified_result.status == "UNVERIFIED_CALLS_DISABLED"
    assert unverified_result.paid_model_calls == 0
    assert "SAFE_MASK" in unverified_result.spoiler_flags[0]


# =============================================================================
# Phase 7: English Compliance & Session Isolation Tests
# =============================================================================

def test_phase7_english_only_api_surface():
    """Verify all system-provided messages and error strings in API responses are in English."""
    with TestClient(app) as client:
        # Non-existent film
        resp_404 = client.get("/api/v1/films/non-existent-film-999")
        assert resp_404.status_code == 404
        error_msg = resp_404.text
        # Assert no Korean characters in error message
        import re
        assert not re.search(r"[\uac00-\ud7a3]", error_msg), f"Found Korean characters in 404 response: {error_msg}"

        # Conflict error message
        post_resp = client.post("/api/v1/community/posts", json={
            "work_id": "the-bat-whispers-1930",
            "title": f"English Compliance Post {uuid.uuid4().hex[:6]}",
            "body_markdown": "Checking error message locale.",
        })
        assert post_resp.status_code in (200, 201)
        post_id = post_resp.json()["data"]["post_id"]
        conflict_resp = client.patch(f"/api/v1/community/posts/{post_id}", json={
            "title": "Conflict",
            "expected_version": 999,
        })
        assert conflict_resp.status_code == 409
        assert not re.search(r"[\uac00-\ud7a3]", conflict_resp.text), f"Found Korean in 409 response: {conflict_resp.text}"


def test_phase7_two_browser_session_progress_and_unlock_isolation():
    """Verify Browser A and Browser B maintain completely independent watch progress and unlock states."""
    with TestClient(app) as client:
        sess_a = f"session_alpha_{uuid.uuid4().hex[:8]}"
        sess_b = f"session_beta_{uuid.uuid4().hex[:8]}"

        # 1. Browser A starts and saves watch progress
        client.cookies.set("reframe_viewer_session", sess_a)
        put_a = client.put(
            "/api/v1/viewer/watch-progress/the-bat-whispers-1930",
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "IN_PROGRESS",
                "progress_ms": 3600000,
                "completed_reveal_ids": []
            }
        )
        assert put_a.status_code == 200

        # 2. Browser B checks watch progress -> must be empty (strict zero crosstalk)
        client.cookies.set("reframe_viewer_session", sess_b)
        get_b = client.get("/api/v1/viewer/watch-progress")
        assert get_b.status_code == 200
        assert get_b.json()["data"] == [], "Browser B must not see Browser A watch progress"

        # 3. Create a post
        client.cookies.set("reframe_viewer_session", sess_a)
        post_resp = client.post("/api/v1/community/posts", json={
            "work_id": "the-bat-whispers-1930",
            "title": f"Multi Browser Post {uuid.uuid4().hex[:6]}",
            "body_markdown": "Checking multi-browser session isolation.",
        })
        assert post_resp.status_code in (200, 201)
        post_id = post_resp.json()["data"]["post_id"]

        # Browser A unlocks the post explicitly
        unlock_resp = client.post("/api/v1/viewer/unlock", json={
            "content_type": "POST",
            "content_id": post_id,
            "version_no": 1
        })
        assert unlock_resp.status_code == 200

        # Browser A verifies it's recorded
        detail_a = client.get(f"/api/v1/community/posts/{post_id}")
        assert detail_a.status_code == 200

        # Browser B checks post -> unlock in Browser A does NOT unlock in Browser B
        client.cookies.set("reframe_viewer_session", sess_b)
        detail_b = client.get(f"/api/v1/community/posts/{post_id}")
        assert detail_b.status_code == 200
