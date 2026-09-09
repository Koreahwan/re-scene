"""
Unit Tests for R3-13, R3-14, R3-15: Centralized CSRF, Stored XSS Mitigation, Community Endpoints & Readiness Observability
Zero Paid Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from apps.api.main import app
from src.reframe.shared.config import settings


@pytest.mark.asyncio
async def test_csrf_enforcement_on_mutating_endpoints():
    """Verify state-mutating requests strictly require valid X-CSRF-Token."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Authenticate
        auth_resp = await client.post(
            "/api/v1/auth/dev-login",
            json={"role": "USER", "email": "csrf_test@reframe.dev"}
        )
        assert auth_resp.status_code == 200
        data = auth_resp.json()["data"]
        csrf_token = data["csrf_token"]
        session_cookie = auth_resp.cookies.get(settings.SESSION_COOKIE_NAME)
        client.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)

        # Request WITHOUT CSRF token -> 403 Forbidden
        bad_resp = await client.post(
            "/api/v1/theories",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity",
                "title": "No CSRF Theory",
                "hypothesis_explanation": "Attempting state modification without CSRF header.",
            }
        )
        assert bad_resp.status_code == 403

        # Request WITH valid CSRF token -> 201 Created
        good_resp = await client.post(
            "/api/v1/theories",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity",
                "title": "Valid CSRF Theory",
                "hypothesis_explanation": "Legitimate state modification with proper CSRF token.",
            },
            headers={"X-CSRF-Token": csrf_token}
        )
        assert good_resp.status_code == 201


@pytest.mark.asyncio
async def test_stored_xss_mitigation():
    """Verify raw HTML and javascript tags are strictly escaped in posts and comments."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Authenticate
        auth_resp = await client.post(
            "/api/v1/auth/dev-login",
            json={"role": "USER", "email": "xss_tester@reframe.dev"}
        )
        data = auth_resp.json()["data"]
        session_cookie = auth_resp.cookies.get(settings.SESSION_COOKIE_NAME)
        client.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)
        headers = {"X-CSRF-Token": data["csrf_token"]}

        # Submit post containing XSS vectors
        xss_payload = "<script>alert('XSS_ATTACK')</script><img src=x onerror=alert(1)>"
        create_resp = await client.post(
            "/api/v1/theories",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-secret-room-location",
                "title": f"Safe Title {xss_payload}",
                "hypothesis_explanation": f"Safe content with payload {xss_payload}",
            },
            headers=headers
        )
        assert create_resp.status_code == 201
        theory_id = create_resp.json()["data"]["theory_id"]

        # Fetch and verify raw scripts were escaped
        get_resp = await client.get(f"/api/v1/theories/{theory_id}", headers=headers)
        assert get_resp.status_code == 200
        theory_data = get_resp.json()["data"]
        assert "<script>" not in theory_data["title"]
        assert "&lt;script&gt;" in theory_data["title"]
        assert "<script>" not in theory_data["body_markdown"]
        assert "&lt;script&gt;" in theory_data["body_markdown"]


@pytest.mark.asyncio
async def test_community_comments_reactions_and_moderation():
    """Verify complete P0 community endpoints: comments, reactions, and moderation reports."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Authenticate regular user
        auth_resp = await client.post(
            "/api/v1/auth/dev-login",
            json={"role": "USER", "email": "fan_commenter@reframe.dev"}
        )
        user_data = auth_resp.json()["data"]
        session_cookie = auth_resp.cookies.get(settings.SESSION_COOKIE_NAME)
        client.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)
        user_headers = {"X-CSRF-Token": user_data["csrf_token"]}

        # 3. Create a community post
        post_resp = await client.post(
            "/api/v1/community/posts",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "content_type": "FAN_THEORY",
                "title": "Community Fireplace Analysis",
                "body_markdown": "Detailed community analysis of the hidden mantel mechanism.",
                "claims": [
                    {
                        "claim_text": "The fireplace mantel contains a secret release lever.",
                        "classification": "STRONG_INTERPRETATION"
                    }
                ],
                "evidence_links": [
                    {
                        "evidence_type": "scene",
                        "evidence_id": "scene-tbw-c023",
                        "relation": "SUPPORTS"
                    }
                ],
                "tagged_reveal_ids": ["reveal-secret-room-location"]
            },
            headers=user_headers
        )
        assert post_resp.status_code == 201
        post_id = post_resp.json()["data"]["post_id"]

        # 4. Add and Delete Reaction
        react_resp = await client.post(
            f"/api/v1/community/posts/{post_id}/reactions",
            json={"reaction_type": "WELL_SUPPORTED"},
            headers=user_headers
        )
        assert react_resp.status_code == 200

        del_react_resp = await client.delete(
            f"/api/v1/community/posts/{post_id}/reactions?reaction_type=WELL_SUPPORTED",
            headers=user_headers
        )
        assert del_react_resp.status_code == 200
        assert del_react_resp.json()["data"]["removed"] is True

        # 5. Create Comment and List Comments
        comment_resp = await client.post(
            f"/api/v1/community/posts/{post_id}/comments",
            json={
                "body_markdown": "Great spot! The stepladder scene directly corroborates this.",
                "comment_type": "COMMENT"
            },
            headers=user_headers
        )
        assert comment_resp.status_code == 201

        list_comm_resp = await client.get(f"/api/v1/community/posts/{post_id}/comments")
        assert list_comm_resp.status_code == 200
        comments = list_comm_resp.json()["data"]
        assert len(comments) >= 1
        assert "stepladder" in comments[0]["body_markdown"]

        # 6. Submit Moderation Report
        report_resp = await client.post(
            "/api/v1/community/moderation/reports",
            json={
                "subject_type": "post",
                "subject_id": post_id,
                "category": "SPOILER",
                "description": "Post contains late-game spoiler."
            },
            headers=user_headers
        )
        assert report_resp.status_code == 201
        assert report_resp.json()["data"]["status"] == "PENDING"

        # 7. Authenticate user, promote to admin in DB, and List Moderation Reports
        admin_auth_resp = await client.post(
            "/api/v1/auth/dev-login",
            json={"email": "admin_audit@reframe.dev"}
        )
        admin_data = admin_auth_resp.json()["data"]
        admin_user_id = admin_data["user_id"]

        from src.reframe.shared.database import AsyncSessionLocal
        from src.reframe.identity.models import User
        from sqlalchemy import update
        import uuid
        async with AsyncSessionLocal() as db_session:
            await db_session.execute(
                update(User).where(User.id == uuid.UUID(admin_user_id)).values(role="ADMIN")
            )
            await db_session.commit()

        admin_cookie = admin_auth_resp.cookies.get(settings.SESSION_COOKIE_NAME)
        client.cookies.set(settings.SESSION_COOKIE_NAME, admin_cookie)
        admin_headers = {"X-CSRF-Token": admin_data["csrf_token"]}

        admin_reports_resp = await client.get("/api/v1/community/moderation/reports", headers=admin_headers)
        assert admin_reports_resp.status_code == 200
        reports = admin_reports_resp.json()["data"]
        assert len(reports) >= 1



@pytest.mark.asyncio
async def test_ready_health_probe_returns_truthful_counts():
    """Verify /ready probe returns real datastore health and exact dataset counts."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/ready")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["postgres"] is True
        assert body["data"]["dataset_ready"] is True

        counts = body["dataset_counts"]
        assert counts["scenes"] == 43
        assert counts["events"] == 187
        assert counts["facts"] == 94
        assert counts["frames"] == 385
