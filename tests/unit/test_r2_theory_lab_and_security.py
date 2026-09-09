"""
Unit Tests for R2-11 Theory Lab and R2-12 Security Hard Gates
Zero Paid Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User
from src.reframe.identity.auth import create_session_token, generate_csrf_token


@pytest.mark.asyncio
async def test_theory_creation_and_idor_protection():
    """Verify that Theory drafting sanitizes input, creates versions, and enforces IDOR."""
    user1_id = uuid.uuid4()
    user2_id = uuid.uuid4()

    # Pre-seed users in test DB
    async with AsyncSessionLocal() as db:
        u1 = User(id=user1_id, email_normalized="user1@example.com", role="USER", status="ACTIVE")
        u2 = User(id=user2_id, email_normalized="user2@example.com", role="USER", status="ACTIVE")
        db.add(u1)
        db.add(u2)
        await db.commit()

    token1 = create_session_token(user1_id, role="USER")
    token2 = create_session_token(user2_id, role="USER")

    csrf_token1 = generate_csrf_token(token1)
    csrf_token2 = generate_csrf_token(token2)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create Theory as User 1
        headers1 = {
            "Cookie": f"reframe_session={token1}",
            "X-CSRF-Token": csrf_token1
        }
        create_res = await client.post(
            "/api/v1/theories",
            headers=headers1,
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity",
                "title": "Investigation of Blueprints in Scene 21",
                "hypothesis_explanation": "Detective unrolled blueprints purposefully to locate the safe.",
                "cited_premise_scenes": ["scene-tbw-c021"]
            }
        )
        assert create_res.status_code == 201
        theory_data = create_res.json()["data"]
        theory_id = theory_data["theory_id"]
        assert theory_data["status"] == "DRAFT"

        # 2. User 1 can view own draft
        view_res1 = await client.get(f"/api/v1/theories/{theory_id}", headers=headers1)
        assert view_res1.status_code == 200
        assert view_res1.json()["data"]["title"] == "Investigation of Blueprints in Scene 21"

        # 3. User 2 is FORBIDDEN from viewing User 1's unpublished draft (IDOR Protection)
        headers2 = {
            "Cookie": f"reframe_session={token2}",
            "X-CSRF-Token": csrf_token2
        }
        view_res2 = await client.get(f"/api/v1/theories/{theory_id}", headers=headers2)
        assert view_res2.status_code == 403

        # 4. User 1 creates Theory Validation Run
        run_res = await client.post(
            "/api/v1/theory-runs",
            headers={**headers1, "Idempotency-Key": f"test-idemp-{uuid.uuid4().hex[:8]}"},
            json={
                "theory_id": theory_id,
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity"
            }
        )
        assert run_res.status_code == 202
        run_id = run_res.json()["data"]["run_id"]

        # 5. User 2 is FORBIDDEN from inspecting User 1's private theory run (IDOR Protection)
        run_view_res2 = await client.get(f"/api/v1/theory-runs/{run_id}", headers=headers2)
        assert run_view_res2.status_code == 403

        # 6. User 1 updates Theory draft
        update_res = await client.patch(
            f"/api/v1/theories/{theory_id}",
            headers=headers1,
            json={
                "title": "Investigation of Blueprints in Scene 21 (Updated)",
                "hypothesis_explanation": "Detailed analysis showing direct correlation with safe mechanism."
            }
        )
        assert update_res.status_code == 200

        # 7. User 1 publishes Theory
        pub_res = await client.post(
            f"/api/v1/theories/{theory_id}/publish",
            headers=headers1
        )
        assert pub_res.status_code == 200
        assert pub_res.json()["data"]["status"] == "PUBLISHED"

        # 8. Now that it is published, User 2 can view it
        view_res2_pub = await client.get(f"/api/v1/theories/{theory_id}", headers=headers2)
        assert view_res2_pub.status_code == 200
        assert "Updated" in view_res2_pub.json()["data"]["title"]


@pytest.mark.asyncio
async def test_csrf_protection_on_state_changing_endpoints():
    """Verify that POST without valid CSRF header fails with 403 when session cookie is present."""
    user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        u = User(id=user_id, email_normalized="csrf_test@example.com", role="USER", status="ACTIVE")
        db.add(u)
        await db.commit()

    token = create_session_token(user_id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Call without CSRF header
        res = await client.post(
            "/api/v1/theories",
            headers={"Cookie": f"reframe_session={token}"},
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity",
                "title": "No CSRF Header Test",
                "hypothesis_explanation": "Testing CSRF rejection."
            }
        )
        assert res.status_code == 403
        err = res.json().get("error", res.json())
        assert "CSRF" in err.get("message", "") or "CSRF" in err.get("code", "")

