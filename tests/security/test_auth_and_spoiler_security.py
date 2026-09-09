"""
Reframe V7 Security & Authorization Unit Tests (Zero Paid Model Calls)
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.identity.auth import create_session_token, generate_csrf_token, ViewerContext
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility


@pytest.mark.asyncio
async def test_dev_login_always_assigns_user_role():
    """Dev login must always create/return USER role, never allowing client-requested role escalation."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "email": f"investigator_{uuid.uuid4().hex[:6]}@example.com",
            "display_name": "Test Investigator"
        }
        resp = await client.post("/api/v1/auth/dev-login", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["role"] == "USER"
        assert "session_token" not in data, "Session token must not be leaked in response JSON"


@pytest.mark.asyncio
async def test_dev_login_fails_when_auth_dev_mode_disabled(monkeypatch):
    """When AUTH_DEV_MODE is false (production default), /auth/dev-login must be forbidden."""
    monkeypatch.setattr(settings, "AUTH_DEV_MODE", False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/auth/dev-login", json={"email": "hacker@example.com"})
        assert resp.status_code == 403
        err = resp.json()["error"]
        assert "disabled" in err["message"].lower()


@pytest.mark.asyncio
async def test_csrf_rejection_on_cookie_authenticated_put():
    """State-changing cookie-authenticated requests without valid CSRF header must be rejected with 403."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create valid authenticated session
        login_resp = await client.post(
            "/api/v1/auth/dev-login",
            json={"email": f"csrf_test_{uuid.uuid4().hex[:6]}@example.com"}
        )
        assert login_resp.status_code == 200
        csrf_token = login_resp.json()["data"]["csrf_token"]
        session_cookie = login_resp.cookies.get(settings.SESSION_COOKIE_NAME)

        # 1. Request with session cookie but missing X-CSRF-Token -> 403
        client_no_csrf = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        client_no_csrf.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)
        resp = await client_no_csrf.put(
            "/api/v1/me/spoiler-preferences",
            json={"default_mode": "STRICT", "mask_titles": True}
        )
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "CSRF_REJECTED"

        # 2. Request with forged / invalid CSRF token -> 403
        resp_invalid = await client_no_csrf.put(
            "/api/v1/me/spoiler-preferences",
            json={"default_mode": "STRICT", "mask_titles": True},
            headers={"X-CSRF-Token": "forged_csrf_token_value"}
        )
        assert resp_invalid.status_code == 403
        assert resp_invalid.json()["error"]["code"] == "CSRF_REJECTED"

        # 3. Request with valid CSRF token header -> 200
        resp_valid = await client_no_csrf.put(
            "/api/v1/me/spoiler-preferences",
            json={"default_mode": "STRICT", "mask_titles": True},
            headers={"X-CSRF-Token": csrf_token}
        )
        assert resp_valid.status_code == 200



@pytest.mark.asyncio
async def test_locked_payload_strips_all_raw_spoilers():
    """LOCKED visibility must never return raw titles, explanations, evidence IDs, or sensitive character actions."""
    raw_payload = {
        "moment_id": "moment-anderson-001",
        "title": "Detective Anderson Unmasked as The Bat",
        "before_understanding": "Normal detective investigation",
        "after_understanding": "Anderson is secretly The Bat",
        "blind_explanation": "Searching room for clues",
        "reveal_explanation": "Anderson accessing his secret vault",
        "clue_description": "Anderson examines the fireplace latch without asking",
        "evidence_frame_ids": ["tbw_v3_frame_0012", "tbw_v3_frame_0013"],
        "graph_path": ["scene-tbw-c011", "REQUIRES_KNOWLEDGE_OF", "scene-tbw-c041"],
        "counterfactual_delta": -0.85
    }

    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=SpoilerVisibility.LOCKED,
        safe_title="Classified Investigative Clue",
        safe_preview="Unlocked after viewing the reveal."
    )

    assert sanitized["visibility"] == "LOCKED"
    assert sanitized["is_locked"] is True
    assert sanitized["title"] == "Classified Investigative Clue"
    assert sanitized["safe_preview"]["title"] == "Classified Investigative Clue"

    # Verify no raw spoiler fields exist in sanitized payload
    forbidden_keys = [
        "before_understanding", "after_understanding", "blind_explanation",
        "reveal_explanation", "clue_description", "evidence_frame_ids",
        "graph_path", "counterfactual_delta"
    ]
    for key in forbidden_keys:
        assert key not in sanitized, f"Key '{key}' must be stripped in LOCKED state"


@pytest.mark.asyncio
async def test_masked_payload_does_not_attach_raw_payload_beside_safe_preview():
    """MASKED visibility must return safe title/preview + unlock metadata, NOT raw spoiler fields."""
    raw_payload = {
        "moment_id": "moment-secret-room-001",
        "title": "Grand Fireplace Secret Mechanism",
        "before_understanding": "Admiring the fireplace",
        "after_understanding": "Opening the hidden passage",
        "clue_description": "Fleming operates the concealed lever"
    }

    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=SpoilerVisibility.MASKED,
        safe_title="Masked Clue Preview",
        safe_preview="Click to reveal clue description.",
        unlock_metadata={"minimum_progress_ms": 3660000}
    )

    assert sanitized["visibility"] == "MASKED"
    assert sanitized["is_locked"] is True
    assert sanitized["safe_preview"]["title"] == "Masked Clue Preview"
    assert sanitized["unlock_metadata"]["minimum_progress_ms"] == 3660000

    # Ensure raw spoiler text is NOT included beside safe_preview
    assert "before_understanding" not in sanitized
    assert "after_understanding" not in sanitized
    assert "clue_description" not in sanitized


@pytest.mark.asyncio
async def test_trust_label_respects_viewer_context():
    """Unwatched viewers must receive sanitized trust label without raw spoiler graph details on public proofs."""
    from src.reframe.shared.database import AsyncSessionLocal
    from src.reframe.proof.models import ProofRecord

    # 1. Verify hidden pattern alias returns 404 for unauthenticated guest
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp_hidden = await client.get("/api/v1/moments/moment-anderson-knowledge-leak/trust-label")
        assert resp_hidden.status_code == 404

        # 2. Create a public ProofRecord in DB to test spoiler sanitization on public items
        proof_id = f"proof-public-{uuid.uuid4().hex[:6]}"
        async with AsyncSessionLocal() as db:
            record = ProofRecord(
                proof_id=proof_id,
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                reveal_id="reveal-anderson-identity",
                proof_type="MULTI_SCENE_PATTERN",
                title="Grounded Search Pattern",
                blind_explanation="Zealous inspection",
                reveal_explanation="Anderson is searching for the safe",
                evidence_chain=[{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
                observed_premises=[{"fact": "Anderson looks around", "event_id": "ev-c017-05"}],
                alternative_explanations=["Routine activity"],
                presentation_status="PUBLIC",
                human_review_status="APPROVED",
                trust_namespace="CANONICAL_VERIFIED",
                trust_label="Verified Canon",
                counterfactual_results={"wrong_reveal_delta": -0.85},
                proof_strength=0.90,
                fan_impact=0.88
            )
            db.add(record)
            await db.commit()

        try:
            # GUEST / Unwatched request on public proof -> 200 with LOCKED spoiler visibility
            resp = await client.get(f"/api/v1/moments/{proof_id}/trust-label")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["visibility"] == "LOCKED"
            assert data["is_locked"] is True
            assert "counterfactual_robustness" not in data
            assert "grounding_metrics" not in data
        finally:
            async with AsyncSessionLocal() as db:
                await db.delete(record)
                await db.commit()
