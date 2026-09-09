"""
Contract Tests for Theory Lab and Evidence-Native Community Endpoints
Zero Paid Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.identity.auth import create_session_token, generate_csrf_token
from src.reframe.identity.models import User
from src.reframe.shared.database import AsyncSessionLocal


@pytest.mark.asyncio
async def test_theory_lab_full_lifecycle(monkeypatch):
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        user = User(id=user_id, email_normalized="theorist@example.com", role="USER", status="ACTIVE")
        db.add(user)
        await db.commit()

    token = create_session_token(user_id, "USER")
    csrf = generate_csrf_token(token)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        # 1. Create Theory Draft
        create_resp = await client.post(
            "/api/v1/theories",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity",
                "title": "Anderson Blueprint Pre-Inspection Theory",
                "hypothesis_explanation": "Detective Anderson inspected the fireplace because he had secret knowledge of the blueprint.",
                "cited_premise_scenes": ["scene-tbw-c017", "scene-tbw-c021"],
                "cited_event_ids": ["ev-01"],
                "alternative_explanations": ["Accidental positioning"]
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert create_resp.status_code == 201
        theory_data = create_resp.json()["data"]
        theory_id = theory_data["theory_id"]
        assert theory_data["status"] == "DRAFT"

        # 2. Update Theory Draft
        patch_resp = await client.patch(
            f"/api/v1/theories/{theory_id}",
            json={"title": "Updated Anderson Blueprint Theory"},
            headers={"X-CSRF-Token": csrf}
        )
        assert patch_resp.status_code == 200

        # 3. Create Theory Validation Run (Requires Idempotency-Key)
        run_resp = await client.post(
            "/api/v1/theory-runs",
            json={
                "theory_id": theory_id,
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity"
            },
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": f"key-{uuid.uuid4().hex}"}
        )
        assert run_resp.status_code == 202
        run_id = run_resp.json()["data"]["run_id"]

        # 4. Check Theory Run Detail
        get_run = await client.get(f"/api/v1/theory-runs/{run_id}")
        assert get_run.status_code == 200
        assert get_run.json()["data"]["target_reveal_id"] == "reveal-anderson-identity"

        # 5. Publish Theory
        pub_resp = await client.post(
            f"/api/v1/theories/{theory_id}/publish",
            headers={"X-CSRF-Token": csrf}
        )
        assert pub_resp.status_code == 200
        assert pub_resp.json()["data"]["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_community_post_creation_and_listing():
    user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        user = User(id=user_id, email_normalized="community_user@example.com", role="USER", status="ACTIVE")
        db.add(user)
        await db.commit()

    token = create_session_token(user_id, "USER")
    csrf = generate_csrf_token(token)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        # 1. Create Post
        post_resp = await client.post(
            "/api/v1/community/posts",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "content_type": "FAN_THEORY",
                "title": "Evidence of Anderson's early manipulation",
                "body_markdown": "Look at the way Anderson touches the portrait in scene 28.",
                "claims": [
                    {
                        "text": "Anderson moved the portrait to search for the hidden latch.",
                        "classification": "STRONG_INTERPRETATION",
                        "evidence_links": []
                    }
                ],
                "ai_disclosure": "HUMAN"
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert post_resp.status_code == 201
        post_id = post_resp.json()["data"]["post_id"]

        # 2. List Posts
        list_resp = await client.get("/api/v1/community/posts")
        assert list_resp.status_code == 200
        assert len(list_resp.json()["data"]) >= 1

        # 3. Add Reaction
        react_resp = await client.post(
            f"/api/v1/community/posts/{post_id}/reactions",
            json={"reaction_type": "WELL_SUPPORTED"},
            headers={"X-CSRF-Token": csrf}
        )
        assert react_resp.status_code == 200


@pytest.mark.asyncio
async def test_theory_draft_idor_protection():
    """Theory draft validation submission by non-owner is blocked with 403 Forbidden."""
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(User(id=owner_id, email_normalized="owner@example.com", role="USER", status="ACTIVE"))
        db.add(User(id=attacker_id, email_normalized="attacker@example.com", role="USER", status="ACTIVE"))
        await db.commit()

    owner_token = create_session_token(owner_id, "USER")
    owner_csrf = generate_csrf_token(owner_token)
    attacker_token = create_session_token(attacker_id, "USER")
    attacker_csrf = generate_csrf_token(attacker_token)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Owner creates draft
        client.cookies.set(settings.SESSION_COOKIE_NAME, owner_token)
        create_resp = await client.post(
            "/api/v1/theories",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity",
                "title": "Private Owner Theory",
                "hypothesis_explanation": "Private forensic notes."
            },
            headers={"X-CSRF-Token": owner_csrf}
        )
        assert create_resp.status_code == 201
        theory_id = create_resp.json()["data"]["theory_id"]

        # Attacker attempts to submit validation run on owner's draft -> 403 Forbidden
        client.cookies.set(settings.SESSION_COOKIE_NAME, attacker_token)
        attack_run = await client.post(
            "/api/v1/theory-runs",
            json={
                "theory_id": theory_id,
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "target_reveal_id": "reveal-anderson-identity"
            },
            headers={"X-CSRF-Token": attacker_csrf, "Idempotency-Key": f"key-atk-{uuid.uuid4().hex}"}
        )
        assert attack_run.status_code == 403


@pytest.mark.asyncio
async def test_counterclaim_evidence_links_roundtrip():
    """Counterclaims persist attached evidence links and expose them in post detail."""
    user_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(User(id=user_id, email_normalized="debater@example.com", role="USER", status="ACTIVE"))
        await db.commit()

    token = create_session_token(user_id, "USER")
    csrf = generate_csrf_token(token)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        # 1. Create Post with Claim
        post_resp = await client.post(
            "/api/v1/community/posts",
            json={
                "work_id": "the-bat-whispers-1930",
                "edition_id": "tbw-fullscreen-archive",
                "content_type": "FAN_THEORY",
                "title": "Premise on Anderson's movements",
                "body_markdown": "Detailed analysis.",
                "claim_text": "Anderson locked the door from outside.",
                "evidence_links": [
                    {
                        "evidence_type": "scene",
                        "evidence_id": "scene-tbw-c023",
                        "relation": "SUPPORTS"
                    }
                ]
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert post_resp.status_code == 201
        post_id = post_resp.json()["data"]["post_id"]

        # Fetch post detail to get claim_id
        detail_res = await client.get(f"/api/v1/community/posts/{post_id}")
        assert detail_res.status_code == 200
        claims = detail_res.json()["data"]["claims"]
        assert len(claims) >= 1
        claim_id = claims[0]["claim_id"]

        # 2. Post Counterclaim with Evidence Links
        cc_resp = await client.post(
            f"/api/v1/community/posts/{post_id}/counterclaims",
            json={
                "target_claim_id": claim_id,
                "challenged_premise": "The door was locked from outside",
                "alternative_explanation": "Scene 23 shows the bolt engaged from the interior",
                "evidence_links": [
                    {
                        "evidence_type": "scene",
                        "evidence_id": "scene-tbw-c023"
                    }
                ]
            },
            headers={"X-CSRF-Token": csrf}
        )
        assert cc_resp.status_code == 201

        # 3. Verify Counterclaim Evidence Link round-trip in post detail
        detail_after = await client.get(f"/api/v1/community/posts/{post_id}")
        assert detail_after.status_code == 200
        post_data = detail_after.json()["data"]
        counterclaims = post_data["counterclaims"]
        assert len(counterclaims) >= 1
        matched_cc = next(c for c in counterclaims if c["challenged_premise"] == "The door was locked from outside")
        assert len(matched_cc["evidence_links"]) >= 1
        assert matched_cc["evidence_links"][0]["evidence_id"] == "scene-tbw-c023"
