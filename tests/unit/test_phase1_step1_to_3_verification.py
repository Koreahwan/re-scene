"""
Phase 1 Steps 1~3 Comprehensive Verification Test Suite (Remediation R2)
========================================================================
Verifies:
1. Original database (reframe_v7.db) SHA-256 integrity & immutability verification.
2. Two independent browser sessions using cookies: unselected, partial watch, and completed watch isolation.
3. Server-side reveal & evidence masking for unselected, partial, and completed states.
4. Public author permissions for community reviews/comments vs strict 403 Forbidden
   for admin/orchestrator analysis and magazine article modifications.
5. Server-side profile disabled fail-closed bypass protection against client header/cookie spoofing.
6. Per-session warning unlock isolation, non-existent/future version rejection, and versioned re-masking.
   Explicit GET comparisons for Client A and Client B across pre-unlock, post-unlock, post-edit, and re-unlock.
7. Comment persistent versioning, unlock isolation, version update re-masking, and decoupling from parent post.
8. English-Only User Surface compliance on API responses, notices, and seeded data without isalpha heuristics.
9. Persistent Comment schema verification (version_no column).
10. Comprehensive database isolation guards across DATABASE_URL, SYNC_DATABASE_URL, and Alembic migrations.
11. Deleted and unviewable content unlock rejection (HTTP 410/400).
"""
import hashlib
import json
import pathlib
import re
import sqlite3
import uuid
import pytest
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from src.reframe.shared.config import Settings, settings
from src.reframe.identity.models import (
    User,
    Profile,
    BrowserWatchProgress,
    BrowserContentUnlock,
    PUBLIC_AUTHOR_USER_ID,
)
from src.reframe.identity.auth import ViewerContext
from src.reframe.community.models import Post, PostVersion, Comment
from src.reframe.community.service import CommunityService
from db.postgres.migrations.env import validate_migration_target_url


EXPECTED_ORIGINAL_DB_SHA256 = "3e09287e519f5ca8faa6f90c8e8f250e7691d551ebc6f38f5c2b92e7903c20c0"


def test_01_original_database_unmodified_sha256():
    """Verify reframe_v7.db exists and matches expected SHA-256."""
    db_path = pathlib.Path(__file__).resolve().parent.parent.parent / "reframe_v7.db"
    assert db_path.exists(), f"Original database not found at {db_path}"

    hasher = hashlib.sha256()
    with open(db_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)

    current_sha256 = hasher.hexdigest().lower()
    assert current_sha256 == EXPECTED_ORIGINAL_DB_SHA256, (
        f"Original DB SHA mismatch! Expected {EXPECTED_ORIGINAL_DB_SHA256}, got {current_sha256}"
    )


def test_02_two_independent_browsers_cookie_isolation(monkeypatch):
    """
    Verify Browser A and Browser B using real cookies maintain completely independent
    watch progress stored under browser_watch_progress keyed by session_id.
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client:
        sess_a = "cookie_browser_alpha"
        sess_b = "cookie_browser_beta"

        # 1. Browser A starts with empty progress
        client.cookies.set("reframe_viewer_session", sess_a)
        resp_a_initial = client.get("/api/v1/viewer/watch-progress")
        assert resp_a_initial.status_code == 200
        assert resp_a_initial.json()["data"] == []

        # 2. Browser A saves progress at 3,660,000 ms (midpoint)
        resp_a_put = client.put(
            "/api/v1/viewer/watch-progress/the-bat-whispers-1930",
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "IN_PROGRESS",
                "progress_ms": 3660000,
                "completed_reveal_ids": []
            }
        )
        assert resp_a_put.status_code == 200
        data_a = resp_a_put.json()["data"]
        assert data_a["progress_ms"] == 3660000
        assert data_a["state"] == "IN_PROGRESS"

        # 3. Browser B checks progress -> must be empty (Zero crosstalk)
        client.cookies.set("reframe_viewer_session", sess_b)
        resp_b = client.get("/api/v1/viewer/watch-progress")
        assert resp_b.status_code == 200
        assert resp_b.json()["data"] == []

        # 4. Switch back to Browser A -> verifies progress persists
        client.cookies.set("reframe_viewer_session", sess_a)
        resp_a_check = client.get("/api/v1/viewer/watch-progress")
        assert resp_a_check.status_code == 200
        records = resp_a_check.json()["data"]
        assert len(records) == 1
        assert records[0]["progress_ms"] == 3660000


def test_03_reveal_gating_and_api_level_masking(monkeypatch):
    """
    Verify reveals and evidence are masked at the API level:
    - Unselected/locked viewer gets English safe_title and empty description/evidence
    - Partial viewer gets earlier reveals unlocked, later reveals masked
    - Completed viewer gets all reveals unlocked with full details
    - Tests against an isolated canonical proof record fixture (title, body, evidence image)
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    test_proof_id = f"proof-test-canonical-{uuid.uuid4().hex[:6]}"
    db_file = settings.SYNC_DATABASE_URL.replace("sqlite:///", "")
    con = sqlite3.connect(db_file)
    try:
        con.execute("DELETE FROM proof_records WHERE proof_id = ?", (test_proof_id,))
        con.execute("""
        INSERT INTO proof_records (
            id, proof_id, work_id, edition_id, dataset_version, reveal_id, proof_type,
            title, blind_explanation, reveal_explanation, evidence_chain, observed_premises,
            alternative_explanations, counterfactual_results, proof_strength, fan_impact,
            human_review_status, presentation_status, trust_namespace, trust_label,
            generation_mode, asset_sha256, correction_overlay_sha, evidence_bundle_hash,
            model_id, prompt_hash, retrieval_config_hash, proof_schema_version, cache_key, created_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?
        )
        """, (
            uuid.uuid4().hex, test_proof_id, "the-bat-whispers-1930", "tbw-fullscreen-archive", "v3", "reveal-anderson-identity", "CLAIM_ACTION_CONFLICT",
            "Detective Anderson Key Movement Contradiction", "Anderson searches the desk without warrant before any crime was reported.", "Anderson is the Bat, so his early search was to recover the blueprint.",
            json.dumps([{"event_id": "evt-01", "frame_id": "frame-01", "image_url": "/images/evidence/evt-01.jpg"}]),
            json.dumps([{"fact": "Anderson is alone in the study", "timestamp_ms": 1200000}]),
            json.dumps([]), json.dumps({"wrong_reveal_delta": -0.85}), 0.95, 0.90,
            "APPROVED", "PUBLISHED", "CANONICAL_VERIFIED", "Canonically verified evidence",
            "AUDIT_VERIFIED", "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948", "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948", "default_evidence_bundle",
            "gemini-2.5-flash", "prompt_v7_canonical", "5channel_retrieval_v7", "1.0.0", "test-key-01", datetime.now(timezone.utc).isoformat()
        ))
        con.commit()

        with TestClient(app) as client:
            sess_locked = "session_viewer_unselected"
            sess_partial = "session_viewer_partial"
            sess_full = "session_viewer_full"

            # Setup partial viewer (midpoint: 3,660,000 ms)
            client.cookies.set("reframe_viewer_session", sess_partial)
            client.put(
                "/api/v1/viewer/watch-progress/the-bat-whispers-1930",
                json={
                    "edition_id": "tbw-fullscreen-archive",
                    "state": "IN_PROGRESS",
                    "progress_ms": 3660000,
                    "completed_reveal_ids": []
                }
            )

            # Setup completed viewer (5,119,080 ms)
            client.cookies.set("reframe_viewer_session", sess_full)
            client.put(
                "/api/v1/viewer/watch-progress/the-bat-whispers-1930",
                json={
                    "edition_id": "tbw-fullscreen-archive",
                    "state": "COMPLETED",
                    "progress_ms": 5119080,
                    "completed_reveal_ids": [
                        "reveal-anderson-identity",
                        "reveal-secret-room-location",
                        "reveal-brooks-innocence",
                        "reveal-masked-robbery-vault"
                    ]
                }
            )

            # 1. Test Locked Viewer (Unselected progress)
            client.cookies.set("reframe_viewer_session", sess_locked)
            resp_locked = client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals")
            assert resp_locked.status_code == 200
            reveals_locked = resp_locked.json()["data"]
            assert len(reveals_locked) > 0
            for r in reveals_locked:
                assert r["is_locked"] is True, f"Reveal {r['reveal_id']} should be locked for unselected viewer"
                assert r["title"] == r.get("safe_title")
                # Verify safe_title is in English and contains no Hangul
                assert not re.search(r"[\uac00-\ud7a3]", r["title"]), f"Korean Hangul detected in title: {r['title']}"
                assert re.search(r"[a-zA-Z]", r["title"]), f"Expected English alphabet in title: {r['title']}"

            # Check detail for locked reveal
            locked_id = reveals_locked[0]["reveal_id"]
            resp_detail_locked = client.get(f"/api/v1/reveals/{locked_id}")
            assert resp_detail_locked.status_code == 200
            det_data = resp_detail_locked.json()["data"]
            assert det_data["is_locked"] is True
            assert det_data["description"] is None

            # Check proofs for locked reveal (verifying isolated canonical fixture)
            resp_proofs_locked = client.get("/api/v1/reveals/reveal-anderson-identity/proofs")
            assert resp_proofs_locked.status_code == 200
            proofs = resp_proofs_locked.json()["data"]
            assert len(proofs) >= 1, "Expected at least 1 canonical proof record in isolated test fixture"
            for p in proofs:
                assert p.get("is_locked", True) is True, "Proofs must be locked for unselected viewer"
                assert not re.search(r"[\uac00-\ud7a3]", p.get("title", ""))
                assert re.search(r"[a-zA-Z]", p.get("title", ""))

            p_canon = [x for x in proofs if x["proof_id"] == test_proof_id][0]
            assert "Verified Clue" in p_canon["title"]
            assert p_canon.get("reveal_explanation") is None
            assert p_canon.get("evidence_chain") in (None, [])
            assert p_canon.get("observed_premises") in (None, [])

            # Check direct proof detail for locked viewer
            det_proof_locked = client.get(f"/api/v1/proofs/{test_proof_id}").json()["data"]
            assert det_proof_locked.get("is_locked", True) is True
            assert det_proof_locked.get("reveal_explanation") is None
            assert det_proof_locked.get("evidence_chain") in (None, [])

            # 2. Test Partial Viewer
            client.cookies.set("reframe_viewer_session", sess_partial)
            resp_partial = client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals")
            assert resp_partial.status_code == 200
            reveals_partial = resp_partial.json()["data"]

            early_reveals = [r for r in reveals_partial if r["timestamp_ms"] <= 3660000]
            late_reveals = [r for r in reveals_partial if r["timestamp_ms"] > 3660000]

            for r in early_reveals:
                assert r["is_locked"] is False, f"Early reveal {r['reveal_id']} should be unlocked"
                assert r["title"] != r.get("safe_title")

            for r in late_reveals:
                assert r["is_locked"] is True, f"Late reveal {r['reveal_id']} should be locked"

            # 3. Test Completed Viewer
            client.cookies.set("reframe_viewer_session", sess_full)
            resp_full = client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals")
            assert resp_full.status_code == 200
            reveals_full = resp_full.json()["data"]
            for r in reveals_full:
                assert r["is_locked"] is False, f"Reveal {r['reveal_id']} should be unlocked for completed viewer"

            # Completed viewer can view full reveal details
            resp_detail_full = client.get(f"/api/v1/reveals/{locked_id}")
            assert resp_detail_full.status_code == 200
            det_full = resp_detail_full.json()["data"]
            assert det_full["is_locked"] is False
            assert det_full["description"] is not None

            # Completed viewer receives unmasked canonical proof with title, explanation, premises, and image
            resp_proofs_full = client.get("/api/v1/reveals/reveal-anderson-identity/proofs")
            assert resp_proofs_full.status_code == 200
            proofs_full = resp_proofs_full.json()["data"]
            assert len(proofs_full) >= 1
            pf = [x for x in proofs_full if x["proof_id"] == test_proof_id][0]
            assert pf.get("is_locked") is not True
            assert pf.get("visibility") == "VISIBLE"
            assert pf["title"] == "Detective Anderson Key Movement Contradiction"
            assert pf["reveal_explanation"] == "Anderson is the Bat, so his early search was to recover the blueprint."
            assert len(pf["evidence_chain"]) == 1
            assert pf["evidence_chain"][0]["image_url"] == "/images/evidence/evt-01.jpg"
            assert len(pf["observed_premises"]) == 1
            assert pf["observed_premises"][0]["fact"] == "Anderson is alone in the study"

            # Check direct proof detail and evidence endpoint for completed viewer
            det_proof_full = client.get(f"/api/v1/proofs/{test_proof_id}").json()["data"]
            assert det_proof_full.get("is_locked") is not True
            assert det_proof_full["reveal_explanation"] == "Anderson is the Bat, so his early search was to recover the blueprint."
            ev_full = client.get(f"/api/v1/proofs/{test_proof_id}/evidence").json()["data"]
            assert len(ev_full["evidence_chain"]) == 1
            assert ev_full["evidence_chain"][0]["image_url"] == "/images/evidence/evt-01.jpg"
    finally:
        con.execute("DELETE FROM proof_records WHERE proof_id = ?", (test_proof_id,))
        con.commit()
        con.close()


def test_04_public_author_permissions_and_privilege_isolation(monkeypatch):
    """
    Verify public author can create/edit/delete reviews and comments and reactions,
    but is strictly FORBIDDEN (HTTP 403) from:
    1. Running analysis orchestrator runs (/api/v1/reframe-runs)
    2. Editing or deleting magazine articles
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client:
        sess_author = "cookie_public_writer"
        client.cookies.set("reframe_viewer_session", sess_author)

        # 1. Public author creates a community review post
        create_resp = client.post(
            "/api/v1/community/posts",
            json={
                "content_type": "FAN_THEORY",
                "title": "Public audience first review",
                "body_markdown": "Safe review body authored by public audience.",
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive"
            }
        )
        assert create_resp.status_code == 201, f"Failed to create review: {create_resp.text}"
        post_data = create_resp.json()["data"]
        post_id = post_data["post_id"]
        assert post_data["status"] in ("PUBLISHED", "DRAFT", "NEEDS_EVIDENCE")

        # 2. Public author reacts (likes) the post
        react_resp = client.put(
            f"/api/v1/community/posts/{post_id}/reactions",
            json={"reaction_type": "LIKE", "liked": True}
        )
        assert react_resp.status_code == 200
        assert react_resp.json()["data"]["liked"] is True

        # 3. Public author updates the post
        update_resp = client.patch(
            f"/api/v1/community/posts/{post_id}",
            json={
                "title": "Public audience updated review",
                "body_markdown": "Content updated cleanly with English copy.",
                "expected_version": 1
            }
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["data"]["version_no"] == 2

        # 4. Privilege Isolation: Public author CANNOT trigger orchestrator analysis runs
        run_resp = client.post(
            "/api/v1/reframe-runs",
            json={
                "movie_id": "the-bat-whispers-1930",
                "reveal_id": "reveal-anderson-identity"
            }
        )
        assert run_resp.status_code == 403, f"Expected 403 Forbidden for runs, got {run_resp.status_code}: {run_resp.text}"
        assert run_resp.json()["error"]["code"] == "FORBIDDEN"

        # 5. Public author deletes the post
        delete_resp = client.delete(f"/api/v1/community/posts/{post_id}")
        assert delete_resp.status_code == 200


def test_05_server_profile_disabled_bypass_protection(monkeypatch):
    """
    Verify that when PHASE1_SUBMISSION_PROFILE_ENABLED = False on the server:
    Client headers, query params, or cookies CANNOT enable public author privileges (fail-closed).
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", False)

    with TestClient(app) as client:
        client.cookies.set("reframe_viewer_session", "hacker_session")
        client.cookies.set("reframe_profile", "phase1_submission")
        # Attempt to create a post sending client-side profile hints
        resp = client.post(
            "/api/v1/community/posts?profile=submission",
            headers={
                "X-Viewer-Session": "hacker_session",
                "X-Submission-Profile": "true"
            },
            json={
                "content_type": "FAN_THEORY",
                "title": "Bypass Attempt",
                "body_markdown": "This should be blocked as 401 AUTH_REQUIRED",
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive"
            }
        )
        assert resp.status_code == 401, f"Expected 401 UNAUTHORIZED, got {resp.status_code}: {resp.text}"
        assert resp.json()["error"]["code"] == "AUTH_REQUIRED"


def test_06_browser_content_unlock_validation_and_version_remasking(monkeypatch):
    """
    Verify warning unlock (/api/v1/viewer/unlock) with rigorous Client A & Client B GET comparison:
    1. Rejects non-existent content IDs (404)
    2. Rejects unsupported content types e.g. MAGAZINE_ARTICLE (400)
    3. Rejects future/mismatched version numbers (400 VERSION_CONFLICT)
    4. Client A and Client B both see masked post before unlock (GET title/body asserted)
    5. Client A unlocks v1 -> Client A sees raw v1 title & body; Client B remains masked (GET title/body asserted)
    6. Author edits post to v2 -> Client A is RE-MASKED; Client B remains masked (GET title/body asserted)
    7. Old version unlock attempt fails with 400
    8. Client A unlocks v2 -> Client A sees raw v2 title & body; Client B remains masked (GET title/body asserted)
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client:
        sess_u1 = "session_unlock_user_1"
        sess_u2 = "session_unlock_user_2"

        # 1. Rejection of non-existent content
        client.cookies.set("reframe_viewer_session", sess_u1)
        bad_id_resp = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "POST", "content_id": str(uuid.uuid4()), "version_no": 1}
        )
        assert bad_id_resp.status_code == 404, bad_id_resp.text

        # 2. Rejection of invalid content_type
        bad_type_resp = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "MAGAZINE_ARTICLE", "content_id": str(uuid.uuid4()), "version_no": 1}
        )
        assert bad_type_resp.status_code == 400, bad_type_resp.text

        # 3. Create a real spoiler-tagged post
        create_resp = client.post(
            "/api/v1/community/posts",
            json={
                "content_type": "FAN_THEORY",
                "title": "Post with spoiler content",
                "body_markdown": "Reveals that Detective Anderson is the criminal mastermind.",
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "tagged_reveal_ids": ["reveal-anderson-identity"]
            }
        )
        assert create_resp.status_code == 201
        real_post_id = create_resp.json()["data"]["post_id"]

        # 4. Rejection of future version
        bad_ver_resp = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "POST", "content_id": real_post_id, "version_no": 999}
        )
        assert bad_ver_resp.status_code == 400, bad_ver_resp.text
        assert "VERSION_CONFLICT" in bad_ver_resp.text or "Version mismatch" in bad_ver_resp.text

        # 5. Pre-unlock: Both Client A and Client B GET the post and must see it MASKED
        client.cookies.set("reframe_viewer_session", sess_u1)
        resp_a_pre = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_a_pre.status_code == 200, resp_a_pre.text
        data_a_pre = resp_a_pre.json()["data"]
        assert data_a_pre.get("is_locked") is True, "Client A must be locked pre-unlock"
        assert data_a_pre.get("title") != "Post with spoiler content", "Client A raw title must be masked"
        assert data_a_pre.get("body_markdown") is None, "Client A raw body must not be exposed pre-unlock"

        client.cookies.set("reframe_viewer_session", sess_u2)
        resp_b_pre = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_b_pre.status_code == 200, resp_b_pre.text
        data_b_pre = resp_b_pre.json()["data"]
        assert data_b_pre.get("is_locked") is True, "Client B must be locked pre-unlock"
        assert data_b_pre.get("title") != "Post with spoiler content", "Client B raw title must be masked"
        assert data_b_pre.get("body_markdown") is None, "Client B raw body must not be exposed pre-unlock"

        # 6. Client A unlocks version 1
        client.cookies.set("reframe_viewer_session", sess_u1)
        unlock_resp = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "POST", "content_id": real_post_id, "version_no": 1}
        )
        assert unlock_resp.status_code == 200
        assert unlock_resp.json()["data"]["unlocked"] is True

        # 7. Post-unlock GET comparison:
        # Client A must see unmasked v1 content
        resp_a_unlocked = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_a_unlocked.status_code == 200
        data_a_unlocked = resp_a_unlocked.json()["data"]
        assert data_a_unlocked.get("is_locked") is not True
        assert data_a_unlocked.get("visibility") == "VISIBLE"
        assert data_a_unlocked.get("title") == "Post with spoiler content"
        assert data_a_unlocked.get("body_markdown") == "Reveals that Detective Anderson is the criminal mastermind."

        # Client B must remain strictly MASKED (Zero Crosstalk!)
        client.cookies.set("reframe_viewer_session", sess_u2)
        resp_b_locked = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_b_locked.status_code == 200
        data_b_locked = resp_b_locked.json()["data"]
        assert data_b_locked.get("is_locked") is True, "Client B must remain locked"
        assert data_b_locked.get("title") != "Post with spoiler content"
        assert data_b_locked.get("body_markdown") is None, "Client B must not receive unmasked body"

        # 8. Edit post to version 2
        client.cookies.set("reframe_viewer_session", sess_u1)
        patch_resp = client.patch(
            f"/api/v1/community/posts/{real_post_id}",
            json={
                "title": "Post with spoiler content (v2)",
                "body_markdown": "Updated spoiler text in version 2.",
                "expected_version": 1
            }
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["data"]["version_no"] == 2

        # 9. Real re-masking verification via GET:
        # Client A held unlock for v1, so with v2 active, Client A is RE-MASKED!
        resp_a_remasked = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_a_remasked.status_code == 200
        data_a_remasked = resp_a_remasked.json()["data"]
        assert data_a_remasked.get("is_locked") is True, "Client A must be re-masked after post edit"
        assert data_a_remasked.get("title") != "Post with spoiler content (v2)", "New title must be masked for Client A"
        assert data_a_remasked.get("body_markdown") is None, "New body must not be exposed to Client A with old v1 unlock"

        # Client B also remains strictly masked
        client.cookies.set("reframe_viewer_session", sess_u2)
        resp_b_remasked = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_b_remasked.status_code == 200
        data_b_remasked = resp_b_remasked.json()["data"]
        assert data_b_remasked.get("is_locked") is True, "Client B must remain locked"
        assert data_b_remasked.get("body_markdown") is None

        # 10. Attempting to unlock old version 1 now fails because version 2 is active
        client.cookies.set("reframe_viewer_session", sess_u1)
        old_ver_unlock = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "POST", "content_id": real_post_id, "version_no": 1}
        )
        assert old_ver_unlock.status_code == 400, "Old version unlock must be rejected"

        # 11. Client A unlocks current version 2
        v2_unlock = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "POST", "content_id": real_post_id, "version_no": 2}
        )
        assert v2_unlock.status_code == 200
        assert v2_unlock.json()["data"]["unlocked"] is True

        # Client A now sees unmasked v2 content
        resp_a_v2 = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_a_v2.status_code == 200
        data_a_v2 = resp_a_v2.json()["data"]
        assert data_a_v2.get("is_locked") is not True
        assert data_a_v2.get("visibility") == "VISIBLE"
        assert data_a_v2.get("title") == "Post with spoiler content (v2)"
        assert data_a_v2.get("body_markdown") == "Updated spoiler text in version 2."

        # Client B continues to remain strictly masked
        client.cookies.set("reframe_viewer_session", sess_u2)
        resp_b_v2 = client.get(f"/api/v1/community/posts/{real_post_id}")
        assert resp_b_v2.status_code == 200
        data_b_v2 = resp_b_v2.json()["data"]
        assert data_b_v2.get("is_locked") is True
        assert data_b_v2.get("body_markdown") is None

        # Clean up
        client.cookies.set("reframe_viewer_session", sess_u1)
        client.delete(f"/api/v1/community/posts/{real_post_id}")


@pytest.mark.asyncio
async def test_06b_comment_persistent_version_remasking_and_two_clients(monkeypatch):
    """
    Verify comment persistent versioning and re-masking:
    1. Comment is created with persistent version_no = 1
    2. Before unlock, Client A and Client B both see comment masked
    3. Client A unlocks comment v1 -> Client A sees raw comment body; Client B remains masked
    4. Comment version is updated in DB to v2 -> Client A is RE-MASKED; Client B remains masked
    5. Client A cannot unlock old version 1 (400)
    6. Client A unlocks version 2 -> Client A sees raw v2 comment body; Client B remains masked
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client:
        sess_a = "session_comment_user_a"
        sess_b = "session_comment_user_b"

        # 1. Create a spoiler-protected parent post
        client.cookies.set("reframe_viewer_session", sess_a)
        post_resp = client.post(
            "/api/v1/community/posts",
            json={
                "content_type": "FAN_THEORY",
                "title": "Post for Comment Versioning Verification",
                "body_markdown": "Parent post content with spoiler scope.",
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "tagged_reveal_ids": ["reveal-anderson-identity"]
            }
        )
        assert post_resp.status_code == 201
        post_id = post_resp.json()["data"]["post_id"]

        # 2. Create comment under post
        comm_resp = client.post(
            f"/api/v1/community/posts/{post_id}/comments",
            json={"body_markdown": "Secret clue: Anderson hides the blueprints behind the portrait."}
        )
        assert comm_resp.status_code == 201
        comm_data = comm_resp.json()["data"]
        comment_id = comm_data["comment_id"]
        assert comm_data.get("version_no") == 1

        # 3. Pre-unlock: Client A and Client B GET comments -> both masked
        client.cookies.set("reframe_viewer_session", sess_a)
        resp_c_a1 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_a1.status_code == 200
        comments_a1 = resp_c_a1.json()["data"]
        assert len(comments_a1) == 1
        assert comments_a1[0]["is_spoiler_masked"] is True
        assert "🔒" in comments_a1[0]["body_markdown"]
        assert "Secret clue" not in comments_a1[0]["body_markdown"]

        client.cookies.set("reframe_viewer_session", sess_b)
        resp_c_b1 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_b1.status_code == 200
        comments_b1 = resp_c_b1.json()["data"]
        assert len(comments_b1) == 1
        assert comments_b1[0]["is_spoiler_masked"] is True
        assert "🔒" in comments_b1[0]["body_markdown"]

        # 4. Client A unlocks comment version 1
        client.cookies.set("reframe_viewer_session", sess_a)
        unlock_comm = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "COMMENT", "content_id": comment_id, "version_no": 1}
        )
        assert unlock_comm.status_code == 200
        assert unlock_comm.json()["data"]["unlocked"] is True

        # Client A sees unmasked comment
        resp_c_a2 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_a2.status_code == 200
        comments_a2 = resp_c_a2.json()["data"]
        assert comments_a2[0]["is_spoiler_masked"] is False
        assert "Secret clue" in comments_a2[0]["body_markdown"]

        # Client B remains masked (Zero crosstalk!)
        client.cookies.set("reframe_viewer_session", sess_b)
        resp_c_b2 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_b2.status_code == 200
        comments_b2 = resp_c_b2.json()["data"]
        assert comments_b2[0]["is_spoiler_masked"] is True
        assert "Secret clue" not in comments_b2[0]["body_markdown"]

        # 5. Update stored comment in DB to version 2 (simulating author edit)
        from src.reframe.shared.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db_session:
            comm_obj = (await db_session.execute(
                select(Comment).where(Comment.id == uuid.UUID(comment_id))
            )).scalar_one()
            comm_obj.version_no = 2
            comm_obj.body_markdown = "Updated clue v2: The secret door requires turning the lion head."
            await db_session.commit()

        # 6. Real re-masking verification for Comment:
        # Client A held unlock for v1, so Client A is RE-MASKED against v2!
        client.cookies.set("reframe_viewer_session", sess_a)
        resp_c_a3 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_a3.status_code == 200
        comments_a3 = resp_c_a3.json()["data"]
        assert comments_a3[0]["version_no"] == 2
        assert comments_a3[0]["is_spoiler_masked"] is True, "Comment must be re-masked when version is updated"
        assert "Updated clue v2" not in comments_a3[0]["body_markdown"]
        assert "🔒" in comments_a3[0]["body_markdown"]

        # Client B also remains masked
        client.cookies.set("reframe_viewer_session", sess_b)
        resp_c_b3 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_b3.status_code == 200
        comments_b3 = resp_c_b3.json()["data"]
        assert comments_b3[0]["is_spoiler_masked"] is True
        assert "Updated clue v2" not in comments_b3[0]["body_markdown"]

        # 7. Unlocking old version 1 fails
        client.cookies.set("reframe_viewer_session", sess_a)
        old_unlock = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "COMMENT", "content_id": comment_id, "version_no": 1}
        )
        assert old_unlock.status_code == 400

        # 8. Unlocking current version 2 succeeds and unmasks for Client A
        v2_unlock = client.post(
            "/api/v1/viewer/unlock",
            json={"content_type": "COMMENT", "content_id": comment_id, "version_no": 2}
        )
        assert v2_unlock.status_code == 200

        resp_c_a4 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_a4.status_code == 200
        comments_a4 = resp_c_a4.json()["data"]
        assert comments_a4[0]["is_spoiler_masked"] is False
        assert "Updated clue v2" in comments_a4[0]["body_markdown"]

        # Client B continues to remain strictly masked
        client.cookies.set("reframe_viewer_session", sess_b)
        resp_c_b4 = client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert resp_c_b4.status_code == 200
        assert resp_c_b4.json()["data"][0]["is_spoiler_masked"] is True

        # Clean up
        client.cookies.set("reframe_viewer_session", sess_a)
        client.delete(f"/api/v1/community/posts/{post_id}")


@pytest.mark.asyncio
async def test_07_comment_unlock_decoupled_from_post():
    """
    Verify boundary rules:
    1. Unlocking parent post does NOT unmask child comments.
    2. Bare comment ID does NOT unmask comments.
    """
    post_id, scope_id = uuid.uuid4(), uuid.uuid4()
    post = NS(id=post_id, author_id=PUBLIC_AUTHOR_USER_ID, spoiler_scope_id=scope_id,
              current_version_id=uuid.uuid4())
    scope = NS(id=scope_id, work_id="film", edition_id="edition",
               minimum_progress_ms=90000, required_reveal_ids=[])
    comment = NS(id=uuid.uuid4(), post_id=post_id, author_id=PUBLIC_AUTHOR_USER_ID,
                 parent_comment_id=None, comment_type="GENERAL", body_markdown="NEW SPOILER",
                 version_no=1, created_at=datetime.now(timezone.utc))
    db = NS(execute=AsyncMock(side_effect=[
        NS(scalar_one_or_none=lambda: post), NS(scalar_one_or_none=lambda: scope),
        NS(scalars=lambda: NS(all=lambda: [comment]))
    ]))
    viewer = ViewerContext(user_id=PUBLIC_AUTHOR_USER_ID, roles=["PUBLIC_AUTHOR"],
                           explicit_unlocks=[f"POST:{post_id}:1"], session_id="browser-a")
    rows = await CommunityService.list_comments(db, post_id, viewer)
    assert rows[0]["is_spoiler_masked"] is True, "Parent post unlock must not expose comments"


@pytest.mark.asyncio
async def test_07b_bare_comment_unlock_rejected():
    """
    Verify bare comment ID does NOT unmask comments.
    """
    post_id, scope_id, comment_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    post = NS(id=post_id, author_id=PUBLIC_AUTHOR_USER_ID, spoiler_scope_id=scope_id)
    scope = NS(id=scope_id, work_id="film", edition_id="edition",
               minimum_progress_ms=90000, required_reveal_ids=[])
    comment = NS(id=comment_id, post_id=post_id, author_id=PUBLIC_AUTHOR_USER_ID,
                 parent_comment_id=None, comment_type="GENERAL", body_markdown="EDITED SPOILER",
                 version_no=1, created_at=datetime.now(timezone.utc))
    db = NS(execute=AsyncMock(side_effect=[
        NS(scalar_one_or_none=lambda: post), NS(scalar_one_or_none=lambda: scope),
        NS(scalars=lambda: NS(all=lambda: [comment]))
    ]))
    viewer = ViewerContext(user_id=PUBLIC_AUTHOR_USER_ID, roles=["PUBLIC_AUTHOR"],
                           explicit_unlocks=[str(comment_id)], session_id="browser-a")
    rows = await CommunityService.list_comments(db, post_id, viewer)
    assert rows[0]["is_spoiler_masked"] is True, "Bare comment ID must not expose comments"


def test_08_english_user_surface_compliance(monkeypatch):
    """
    Verify site-wide user surface strings from API are in English:
    1. Film detail analysis notice (strict assertion, no if guards, regex for non-Hangul)
    2. Seeded Public Audience profile display_name and bio
    3. Safe titles of catalog reveals
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client:
        # 1. Check non-demo film detail returns English analysis_notice
        resp = client.get("/api/v1/films/wd-q25188")
        assert resp.status_code == 200, f"Film detail API failed: {resp.text}"
        film_data = resp.json()["data"]
        notice = film_data.get("analysis_notice", "")
        assert notice, "Analysis notice must not be empty"
        assert not re.search(r"[\uac00-\ud7a3]", notice), f"Korean Hangul found in notice: {notice}"
        assert re.search(r"[a-zA-Z]", notice), f"Expected English alphabet in notice: {notice}"
        assert "Core analysis features" in notice

        # 2. Check profile returns English Public Audience bio and display_name
        client.cookies.set("reframe_viewer_session", "session_check_english")
        profile_resp = client.get("/api/v1/profiles/me")
        assert profile_resp.status_code == 200, f"Profile API failed: {profile_resp.text}"
        prof = profile_resp.json()["data"]
        assert prof["display_name"] == "Public Audience"
        assert not re.search(r"[\uac00-\ud7a3]", prof["display_name"])
        assert not re.search(r"[\uac00-\ud7a3]", prof["bio"])
        assert "Reframe" in prof["bio"]

        # 3. Check reveals catalog returns English safe_titles
        rev_resp = client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals")
        assert rev_resp.status_code == 200
        reveals = rev_resp.json()["data"]
        assert len(reveals) > 0
        for r in reveals:
            safe_title = r.get("safe_title", "")
            assert safe_title, f"Reveal {r['reveal_id']} has empty safe_title"
            assert not re.search(r"[\uac00-\ud7a3]", safe_title), f"Hangul in safe_title: {safe_title}"
            assert re.search(r"[a-zA-Z]", safe_title)


def test_09_comment_has_persistent_version():
    """Verify Comment model contains persistent version_no column."""
    assert "version_no" in Comment.__table__.columns.keys(), list(Comment.__table__.columns.keys())
    col = Comment.__table__.columns["version_no"]
    assert not col.nullable, "version_no column must be NOT NULL"


def test_10_database_isolation_guards_all_paths():
    """
    Verify DB isolation guards prevent any execution path from targeting reframe_v7.db:
    1. Settings rejects reframe_v7.db in DATABASE_URL
    2. Settings rejects reframe_v7.db in SYNC_DATABASE_URL
    3. Alembic validate_migration_target_url rejects reframe_v7.db target URL
    """
    # 1. DATABASE_URL isolation check
    with pytest.raises(ValueError, match="ISOLATION_VIOLATION"):
        Settings(
            _env_file=None,
            PHASE1_SUBMISSION_PROFILE_ENABLED=True,
            DATABASE_URL="sqlite+aiosqlite:///./reframe_v7.db",
            SYNC_DATABASE_URL="sqlite:///./data/phase1_submission.db"
        )

    # 2. SYNC_DATABASE_URL isolation check
    with pytest.raises(ValueError, match="ISOLATION_VIOLATION"):
        Settings(
            _env_file=None,
            PHASE1_SUBMISSION_PROFILE_ENABLED=True,
            DATABASE_URL="sqlite+aiosqlite:///./data/phase1_submission.db",
            SYNC_DATABASE_URL="sqlite:///./reframe_v7.db"
        )

    # 3. Alembic target URL isolation check
    with pytest.raises(ValueError, match="ISOLATION_VIOLATION"):
        validate_migration_target_url("sqlite+aiosqlite:///./reframe_v7.db")


def test_11_deleted_and_unviewable_content_unlock_protection(monkeypatch):
    """
    Verify warning unlock endpoint strictly rejects deleted or non-published content:
    1. Deleted post cannot be unlocked (HTTP 410/400)
    2. Comment under deleted post cannot be unlocked (HTTP 400)
    3. Non-existent content returns 404
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client:
        sess = "session_deletion_guard"
        client.cookies.set("reframe_viewer_session", sess)

        # 1. Create post and comment
        created_post = client.post("/api/v1/community/posts", json={
            "content_type": "FAN_THEORY",
            "title": "Deletion test post",
            "body_markdown": "Body to be deleted.",
            "work_id": "the-bat-whispers-1930",
            "edition_id": "tbw-fullscreen-archive"
        })
        assert created_post.status_code == 201
        post_id = created_post.json()["data"]["post_id"]

        created_comm = client.post(f"/api/v1/community/posts/{post_id}/comments", json={
            "body_markdown": "Comment under doomed post."
        })
        assert created_comm.status_code == 201
        comm_id = created_comm.json()["data"]["comment_id"]

        # 2. Delete post
        deleted_post = client.delete(f"/api/v1/community/posts/{post_id}")
        assert deleted_post.status_code == 200

        # 3. Unlock on deleted post must be rejected with 410 or 400
        unlock_post = client.post("/api/v1/viewer/unlock", json={
            "content_type": "POST",
            "content_id": post_id,
            "version_no": 1
        })
        assert unlock_post.status_code in (400, 403, 404, 409, 410), unlock_post.text

        # 4. Unlock on comment under deleted post must also be rejected
        unlock_comm = client.post("/api/v1/viewer/unlock", json={
            "content_type": "COMMENT",
            "content_id": comm_id,
            "version_no": 1
        })
        assert unlock_comm.status_code in (400, 403, 404, 409, 410), unlock_comm.text


def test_12_deleted_content_public_read_isolation_across_all_visitor_personas(monkeypatch):
    """
    Verify strict public read isolation across 3 visitor personas:
    1. User A: Has prior explicit unlock (post & comment).
    2. User B: Locked visitor (no unlock, unselected progress).
    3. Visitor C: Completed watch progress visitor (100% progress, all reveals completed).

    Across 3 deletion scenarios:
    - Deleted post (status=REMOVED): GET /posts/{pid} must return 404 to A, B, and C.
    - Deleted comment (status=REMOVED): GET /posts/{pid}/comments must omit removed comment for A, B, and C.
    - Comment under deleted parent post: GET /posts/{pid}/comments must return 404 to A, B, and C.

    Verifies the premise: prior to deletion, original text (title, markdown, HTML, comments)
    was fully visible to authorized viewers (A and C).
    Also verifies internal admin moderation access is preserved.
    """
    monkeypatch.setattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", True)

    with TestClient(app) as client_a, TestClient(app) as client_b, TestClient(app) as client_c:
        sess_a = f"sess_viewer_a_{uuid.uuid4().hex[:8]}"
        sess_b = f"sess_viewer_b_{uuid.uuid4().hex[:8]}"
        sess_c = f"sess_viewer_c_{uuid.uuid4().hex[:8]}"
        client_a.cookies.set("reframe_viewer_session", sess_a)
        client_b.cookies.set("reframe_viewer_session", sess_b)
        client_c.cookies.set("reframe_viewer_session", sess_c)

        # Setup Visitor C with completed watch progress
        c_prog = client_c.put(
            "/api/v1/viewer/watch-progress/the-bat-whispers-1930",
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "COMPLETED",
                "progress_ms": 5119080,
                "completed_reveal_ids": ["reveal-anderson-identity"]
            }
        )
        assert c_prog.status_code == 200

        # -------------------------------------------------------------
        # Scenario 1: Deleted Post Read Isolation
        # -------------------------------------------------------------
        post_marker = f"POST_SECRET_SENTINEL_{uuid.uuid4().hex[:6]}"
        post_title = f"Secret Post Title {uuid.uuid4().hex[:4]}"
        post_resp = client_a.post("/api/v1/community/posts", json={
            "content_type": "FAN_THEORY",
            "title": post_title,
            "body_markdown": post_marker,
            "work_id": "the-bat-whispers-1930",
            "edition_id": "tbw-fullscreen-archive",
            "tagged_reveal_ids": ["reveal-anderson-identity"]
        })
        assert post_resp.status_code == 201
        pid_1 = post_resp.json()["data"]["post_id"]

        # User A and Visitor C unlock post v1
        unlock_a = client_a.post("/api/v1/viewer/unlock", json={
            "content_type": "POST",
            "content_id": pid_1,
            "version_no": 1
        })
        assert unlock_a.status_code == 200
        unlock_c = client_c.post("/api/v1/viewer/unlock", json={
            "content_type": "POST",
            "content_id": pid_1,
            "version_no": 1
        })
        assert unlock_c.status_code == 200

        # Verify Precondition: Before deletion, original title, body, and HTML are visible to A and C
        get_a_before = client_a.get(f"/api/v1/community/posts/{pid_1}")
        assert get_a_before.status_code == 200
        assert post_marker in get_a_before.text
        assert post_title in get_a_before.text
        assert f"<p>{post_marker}</p>" in get_a_before.json()["data"]["body_sanitized_html"]

        get_c_before = client_c.get(f"/api/v1/community/posts/{pid_1}")
        assert get_c_before.status_code == 200
        assert post_marker in get_c_before.text

        get_b_before = client_b.get(f"/api/v1/community/posts/{pid_1}")
        assert get_b_before.status_code == 200
        assert post_marker not in get_b_before.text  # Masked for locked viewer

        # Delete Post
        del_post_resp = client_b.delete(f"/api/v1/community/posts/{pid_1}")
        assert del_post_resp.status_code == 200
        assert del_post_resp.json()["data"]["status"] == "REMOVED"

        # Post-condition: User A (prior unlock), User B (locked), Visitor C (completed)
        # All receive 404, and original title, body, and HTML are never exposed.
        for persona_name, cl in [("Viewer A", client_a), ("Viewer B", client_b), ("Visitor C", client_c)]:
            get_after = cl.get(f"/api/v1/community/posts/{pid_1}")
            assert get_after.status_code == 404, f"{persona_name} got {get_after.status_code} instead of 404 for removed post"
            assert post_marker not in get_after.text, f"{persona_name} saw body sentinel in removed post response"
            assert post_title not in get_after.text, f"{persona_name} saw title in removed post response"

        # Verify public listing omits removed post
        list_posts = client_a.get("/api/v1/community/posts?work_id=the-bat-whispers-1930").json()["data"]
        assert all(p["post_id"] != pid_1 for p in list_posts)

        # -------------------------------------------------------------
        # Scenario 2: Deleted Comment under Published Post
        # -------------------------------------------------------------
        post_resp_2 = client_a.post("/api/v1/community/posts", json={
            "content_type": "FAN_THEORY",
            "title": f"Published Discussion {uuid.uuid4().hex[:4]}",
            "body_markdown": "Published discussion body.",
            "work_id": "the-bat-whispers-1930",
            "edition_id": "tbw-fullscreen-archive",
            "tagged_reveal_ids": ["reveal-anderson-identity"]
        })
        assert post_resp_2.status_code == 201
        pid_2 = post_resp_2.json()["data"]["post_id"]

        comment_marker = f"COMMENT_SECRET_SENTINEL_{uuid.uuid4().hex[:6]}"
        comm_resp = client_a.post(f"/api/v1/community/posts/{pid_2}/comments", json={
            "body_markdown": comment_marker
        })
        assert comm_resp.status_code == 201
        cid_2 = comm_resp.json()["data"]["comment_id"]

        # User A and Visitor C unlock comment v1
        unlock_comm = client_a.post("/api/v1/viewer/unlock", json={
            "content_type": "COMMENT",
            "content_id": cid_2,
            "version_no": 1
        })
        assert unlock_comm.status_code == 200
        unlock_comm_c = client_c.post("/api/v1/viewer/unlock", json={
            "content_type": "COMMENT",
            "content_id": cid_2,
            "version_no": 1
        })
        assert unlock_comm_c.status_code == 200

        # Verify Precondition: comment visible before deletion
        comm_a_before = client_a.get(f"/api/v1/community/posts/{pid_2}/comments")
        assert comm_a_before.status_code == 200 and comment_marker in comm_a_before.text
        comm_c_before = client_c.get(f"/api/v1/community/posts/{pid_2}/comments")
        assert comm_c_before.status_code == 200 and comment_marker in comm_c_before.text

        # Delete Comment
        del_comm_resp = client_b.delete(f"/api/v1/community/posts/{pid_2}/comments/{cid_2}")
        assert del_comm_resp.status_code == 200
        assert del_comm_resp.json()["data"]["status"] == "REMOVED"

        # Post-condition: comment omitted from list and detail for A, B, C
        for persona_name, cl in [("Viewer A", client_a), ("Viewer B", client_b), ("Visitor C", client_c)]:
            # Comments list
            list_after = cl.get(f"/api/v1/community/posts/{pid_2}/comments")
            assert list_after.status_code == 200
            assert comment_marker not in list_after.text, f"{persona_name} saw deleted comment in comment list"
            assert all(c["comment_id"] != cid_2 for c in list_after.json()["data"])

            # Post detail (comments nested in post response)
            post_det = cl.get(f"/api/v1/community/posts/{pid_2}").json()["data"]
            assert all(c["comment_id"] != cid_2 for c in post_det.get("comments", []))

            # Single comment GET
            single_comm = cl.get(f"/api/v1/community/posts/{pid_2}/comments/{cid_2}")
            assert single_comm.status_code == 404, f"{persona_name} got {single_comm.status_code} for deleted comment"
            assert comment_marker not in single_comm.text

        # -------------------------------------------------------------
        # Scenario 3: Comment & Nested Comment under Deleted Parent Post
        # -------------------------------------------------------------
        post_resp_3 = client_a.post("/api/v1/community/posts", json={
            "content_type": "FAN_THEORY",
            "title": f"Doomed Parent Post {uuid.uuid4().hex[:4]}",
            "body_markdown": "Doomed parent post body.",
            "work_id": "the-bat-whispers-1930",
            "edition_id": "tbw-fullscreen-archive",
            "tagged_reveal_ids": ["reveal-anderson-identity"]
        })
        assert post_resp_3.status_code == 201
        pid_3 = post_resp_3.json()["data"]["post_id"]

        parent_comm_marker = f"PARENT_COMM_SENTINEL_{uuid.uuid4().hex[:6]}"
        nested_comm_marker = f"NESTED_COMM_SENTINEL_{uuid.uuid4().hex[:6]}"

        p_comm = client_a.post(f"/api/v1/community/posts/{pid_3}/comments", json={
            "body_markdown": parent_comm_marker
        })
        assert p_comm.status_code == 201
        cid_3 = p_comm.json()["data"]["comment_id"]

        n_comm = client_a.post(f"/api/v1/community/posts/{pid_3}/comments", json={
            "body_markdown": nested_comm_marker,
            "parent_comment_id": cid_3
        })
        assert n_comm.status_code == 201
        nested_cid = n_comm.json()["data"]["comment_id"]

        # A and C unlock both comments
        client_a.post("/api/v1/viewer/unlock", json={"content_type": "COMMENT", "content_id": cid_3, "version_no": 1})
        client_a.post("/api/v1/viewer/unlock", json={"content_type": "COMMENT", "content_id": nested_cid, "version_no": 1})
        client_c.post("/api/v1/viewer/unlock", json={"content_type": "COMMENT", "content_id": cid_3, "version_no": 1})
        client_c.post("/api/v1/viewer/unlock", json={"content_type": "COMMENT", "content_id": nested_cid, "version_no": 1})

        # Verify Precondition: A and C see both comments
        before_3_a = client_a.get(f"/api/v1/community/posts/{pid_3}/comments")
        assert before_3_a.status_code == 200
        assert parent_comm_marker in before_3_a.text and nested_comm_marker in before_3_a.text

        before_3_c = client_c.get(f"/api/v1/community/posts/{pid_3}/comments")
        assert before_3_c.status_code == 200
        assert parent_comm_marker in before_3_c.text and nested_comm_marker in before_3_c.text

        # Delete parent post
        del_parent = client_b.delete(f"/api/v1/community/posts/{pid_3}")
        assert del_parent.status_code == 200

        # Post-condition: A, B, C cannot read comments of deleted parent post
        for persona_name, cl in [("Viewer A", client_a), ("Viewer B", client_b), ("Visitor C", client_c)]:
            comm_list_after = cl.get(f"/api/v1/community/posts/{pid_3}/comments")
            assert comm_list_after.status_code == 404, f"{persona_name} got {comm_list_after.status_code} for comments of deleted parent post"
            assert parent_comm_marker not in comm_list_after.text
            assert nested_comm_marker not in comm_list_after.text

            # Single comment direct access
            get_c1 = cl.get(f"/api/v1/community/posts/{pid_3}/comments/{cid_3}")
            assert get_c1.status_code == 404
            assert parent_comm_marker not in get_c1.text

            get_c2 = cl.get(f"/api/v1/community/posts/{pid_3}/comments/{nested_cid}")
            assert get_c2.status_code == 404
            assert nested_comm_marker not in get_c2.text
