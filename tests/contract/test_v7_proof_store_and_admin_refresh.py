"""
Contract & Integration Tests for Canonical Proof Store and Admin Proof Refresh
Zero Paid Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.identity.auth import create_session_token, generate_csrf_token


@pytest.mark.asyncio
async def test_get_reveal_proofs_zero_model_calls():
    """Public lookup of canonical proofs must return persisted proofs with zero Gemini calls."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # GUEST viewer -> 0 public proofs when development interpretations are HIDDEN_FROM_PUBLIC
        resp = await client.get("/api/v1/reveals/reveal-anderson-identity/proofs")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["paid_model_calls"] == 0
        assert body["meta"]["source"] == "CANONICAL_PRECOMPUTED_STORE"
        assert len(body["data"]) == 0

        # ADMIN viewer -> Full development proofs with proof_strength
        admin_id = uuid.uuid4()
        from src.reframe.identity.models import User, WatchProgress
        from src.reframe.shared.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            admin_user = User(id=admin_id, email_normalized="admin_fan@example.com", role="ADMIN", status="ACTIVE")
            db.add(admin_user)
            wp = WatchProgress(
                user_id=admin_id,
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                state="COMPLETED",
                progress_ms=5000000,
                completed_reveal_ids=["reveal-anderson-identity"]
            )
            db.add(wp)
            await db.commit()

        token = create_session_token(admin_id, "ADMIN")
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        resp_admin = await client.get("/api/v1/reveals/reveal-anderson-identity/proofs")
        assert resp_admin.status_code == 200
        comp_data = resp_admin.json()["data"]
        assert len(comp_data) >= 3
        assert comp_data[0]["visibility"] == "VISIBLE"
        assert "proof_strength" in comp_data[0]
        assert "fan_impact" in comp_data[0]


@pytest.mark.asyncio
async def test_get_proof_by_id_zero_model_calls():
    """Admin proof lookup by proof_id returns development interpretation; unauthenticated returns 404 for hidden proof."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Unauthenticated guest on HIDDEN_FROM_PUBLIC proof -> 404
        resp_guest = await client.get("/api/v1/proofs/proof-anderson-01")
        assert resp_guest.status_code == 404

        # Admin user -> 200 with proof details
        admin_id = uuid.uuid4()
        from src.reframe.identity.models import User
        from src.reframe.shared.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            admin_user = User(id=admin_id, email_normalized="admin_lookup@example.com", role="ADMIN", status="ACTIVE")
            db.add(admin_user)
            await db.commit()

        token = create_session_token(admin_id, "ADMIN")
        client.cookies.set(settings.SESSION_COOKIE_NAME, token)

        resp = await client.get("/api/v1/proofs/proof-anderson-01")
        assert resp.status_code == 200
        body = resp.json()
        assert body["meta"]["paid_model_calls"] == 0
        assert body["data"]["proof_id"] == "proof-anderson-01"


@pytest.mark.asyncio
async def test_admin_refresh_proof_requires_admin_and_csrf(monkeypatch):
    """Non-admin or missing CSRF requests must be forbidden from triggering refresh."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthenticated request -> 401
        resp_unauth = await client.post("/api/v1/admin/reveals/reveal-anderson-identity/refresh-proof")
        assert resp_unauth.status_code in (401, 403)

        # 2. Standard USER login
        user_login = await client.post("/api/v1/auth/dev-login", json={"email": "regular_user@example.com"})
        user_cookie = user_login.cookies.get(settings.SESSION_COOKIE_NAME)
        user_csrf = user_login.json()["data"]["csrf_token"]

        user_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        user_client.cookies.set(settings.SESSION_COOKIE_NAME, user_cookie)

        resp_user = await user_client.post(
            "/api/v1/admin/reveals/reveal-anderson-identity/refresh-proof",
            headers={"X-CSRF-Token": user_csrf, "Idempotency-Key": f"key-{uuid.uuid4().hex}"}
        )
        assert resp_user.status_code == 403, "Standard USER must be forbidden from admin refresh"

        # 3. Authenticated ADMIN session
        admin_id = uuid.uuid4()
        from src.reframe.identity.models import User
        from src.reframe.shared.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            admin_user = User(id=admin_id, email_normalized="admin@reframe.dev", role="ADMIN", status="ACTIVE")
            db.add(admin_user)
            await db.commit()

        admin_token = create_session_token(admin_id, "ADMIN")
        admin_csrf = generate_csrf_token(admin_token)

        admin_client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        admin_client.cookies.set(settings.SESSION_COOKIE_NAME, admin_token)

        # 3a. Admin refresh with spend kill switch active -> 429 BudgetExceeded
        resp_kill = await admin_client.post(
            "/api/v1/admin/reveals/reveal-anderson-identity/refresh-proof",
            headers={"X-CSRF-Token": admin_csrf, "Idempotency-Key": f"key-{uuid.uuid4().hex}"}
        )
        assert resp_kill.status_code == 429

        # 3b. Admin with paid calls unlocked & valid CSRF & Idempotency Key -> 202 Accepted
        monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
        monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

        idemp_key = f"key-{uuid.uuid4().hex}"
        resp_admin = await admin_client.post(
            "/api/v1/admin/reveals/reveal-anderson-identity/refresh-proof",
            headers={"X-CSRF-Token": admin_csrf, "Idempotency-Key": idemp_key}
        )
        assert resp_admin.status_code == 202
        assert resp_admin.json()["data"]["status"] == "QUEUED"

