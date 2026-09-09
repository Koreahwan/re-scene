"""
Reframe V7 Evidence-Native Community API Contract Tests
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings


@pytest.mark.asyncio
async def test_community_post_creation_and_evidence_pinning():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Unauthenticated creation fails (401)
        res_unauth = await client.post("/api/v1/community/posts", json={
            "title": "Unauthenticated Theory",
            "body_markdown": "Some body without login"
        })
        assert res_unauth.status_code == 401

        # 2. Login
        login_res = await client.post("/api/v1/auth/dev-login", json={
            "email": "sleuth@reframe.dev",
            "display_name": "Senior Sleuth"
        })
        token = login_res.cookies.get(settings.SESSION_COOKIE_NAME)
        csrf = login_res.json()["data"]["csrf_token"]
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        # 3. Post with non-existent evidence fails (400)
        res_bad_ev = await client.post(
            "/api/v1/community/posts",
            headers={"X-CSRF-Token": csrf},
            json={
                "title": "Fake Evidence Theory",
                "body_markdown": "Claims something with hallucinated evidence",
                "evidence_links": [
                    {"evidence_type": "event", "evidence_id": "ev-non-existent-999"}
                ]
            }
        )
        assert res_bad_ev.status_code == 400

        # 4. Post with valid canonical evidence succeeds
        res_post = await client.post(
            "/api/v1/community/posts",
            headers={"X-CSRF-Token": csrf},
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "content_type": "FAN_THEORY",
                "title": "Anderson Knew The House Blueprint Early",
                "body_markdown": "In scene c011, Anderson goes straight to the secret study.",
                "claim_text": "Anderson was intentionally misdirecting the household",
                "claim_classification": "STRONG_INTERPRETATION",
                "evidence_links": [
                    {"evidence_type": "scene", "evidence_id": "scene-tbw-c011", "relation": "SUPPORTS"},
                    {"evidence_type": "event", "evidence_id": "ev-c011-01", "relation": "SUPPORTS"}
                ],
                "tagged_reveal_ids": ["reveal-anderson-identity"]
            }
        )
        assert res_post.status_code == 201
        post_id = res_post.json()["data"]["post_id"]

        # 5. Unverified posts require an explicit warning confirmation for guests.
        guest_client = AsyncClient(transport=transport, base_url="http://test")
        res_list_guest = await guest_client.get("/api/v1/community/posts")
        assert res_list_guest.status_code == 200
        posts_guest = res_list_guest.json()["data"]
        target_guest = next(p for p in posts_guest if p["post_id"] == post_id)
        assert target_guest["visibility"] == "MASKED"
        assert target_guest["is_locked"] is True
        assert target_guest["can_edit"] is False
        assert "body_markdown" not in target_guest
        assert "Anderson" not in target_guest["title"]

        # 6. The authenticated author can read their own published post.
        await client.put(
            "/api/v1/me/watch-progress/the-bat-whispers-1930",
            headers={"X-CSRF-Token": csrf},
            json={
                "edition_id": "tbw-fullscreen-archive",
                "state": "COMPLETED",
                "progress_ms": 5040000,
                "completed_reveal_ids": ["reveal-anderson-identity"]
            }
        )

        res_list_auth = await client.get("/api/v1/community/posts")
        assert res_list_auth.status_code == 200
        posts_auth = res_list_auth.json()["data"]
        target_auth = next(p for p in posts_auth if p["post_id"] == post_id)
        assert target_auth["visibility"] == "VISIBLE"
        assert "Anderson Knew The House Blueprint" in target_auth["title"]
        assert target_auth["can_edit"] is True

        # 7. Get Post Detail
        res_detail = await client.get(f"/api/v1/community/posts/{post_id}")
        assert res_detail.status_code == 200
        detail = res_detail.json()["data"]
        assert len(detail["evidence_links"]) == 2
        assert detail["author_name"] == "Senior Sleuth"

        # 8. Post a Counterclaim
        from src.reframe.shared.database import AsyncSessionLocal
        from src.reframe.community.models import Claim
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            c_stmt = select(Claim).where(Claim.post_id == uuid.UUID(post_id))
            c_res = await db.execute(c_stmt)
            claim_obj = c_res.scalar_one()
            claim_id = str(claim_obj.id)

        cc_res = await client.post(
            f"/api/v1/community/posts/{post_id}/counterclaims",
            headers={"X-CSRF-Token": csrf},
            json={
                "target_claim_id": claim_id,
                "challenged_premise": "Anderson was simply following standard police sweep protocol.",
                "alternative_explanation": "He checked the study because the call originated from that wing."
            }
        )
        assert cc_res.status_code == 201

        # 9. Add Reaction
        rx_res = await client.post(
            f"/api/v1/community/posts/{post_id}/reactions",
            headers={"X-CSRF-Token": csrf},
            json={"reaction_type": "WELL_SUPPORTED"}
        )
        assert rx_res.status_code == 200
        assert rx_res.json()["data"]["reaction_type"] == "WELL_SUPPORTED"
        await guest_client.aclose()
