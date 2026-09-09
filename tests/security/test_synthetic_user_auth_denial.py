"""
Reframe V7 Synthetic User Authentication Denial Tests
Verifies that synthetic demo users (account_origin='SYNTHETIC_DEMO', status='DISABLED')
are strictly rejected on all authentication, login, dev-login, and token generation paths.
Zero External Generative Model Calls.
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User, Profile, UserCredential
from src.reframe.identity.auth import create_session_token, decode_session_token
from src.reframe.simulation.service import audience_lab_service


@pytest.mark.asyncio
async def test_synthetic_user_status_disabled():
    """Verify that seeded synthetic users are stored with status=DISABLED and zero credentials."""
    async with AsyncSessionLocal() as db:
        res = await audience_lab_service.seed_synthetic_demo_content(
            db=db,
            post_target_count=2,
            comment_target_count=2,
            counterclaim_target_count=2,
            reaction_target_count=2,
            enable_magazine=True,
        )
        assert res["personas_enrolled"] >= 1

        users_stmt = select(User).where(User.account_origin == "SYNTHETIC_DEMO")
        users = (await db.execute(users_stmt)).scalars().all()
        assert len(users) >= 1

        for u in users:
            assert u.status == "DISABLED"
            assert u.account_origin == "SYNTHETIC_DEMO"
            assert u.email_normalized.endswith("@example.invalid")

            # Verify no credential rows exist
            cred_stmt = select(UserCredential).where(UserCredential.user_id == u.id)
            creds = (await db.execute(cred_stmt)).scalars().all()
            assert len(creds) == 0

        # Clean up
        await audience_lab_service.purge_synthetic_demo_content(db=db)


@pytest.mark.asyncio
async def test_synthetic_user_cannot_authenticate_via_api():
    """Verify that attempting to login or authenticate as a synthetic user fails."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Dev login attempt with synthetic user email
        res = await client.post(
            "/api/v1/auth/dev-login",
            json={"email": "demo_synthetic_us_pers_0001@example.invalid"},
        )
        # Should be rejected
        assert res.status_code in [400, 401, 403, 404]

        # 2. Token created for disabled synthetic user
        synthetic_id = uuid.uuid4()
        token = create_session_token(user_id=synthetic_id, role="USER")
        assert token is not None

        decoded = decode_session_token(token)
        assert decoded is not None
        assert decoded["sub"] == str(synthetic_id)

        # Verify against disabled user in DB
        async with AsyncSessionLocal() as db:
            synth_user = User(
                id=synthetic_id,
                email_normalized="demo_synthetic_test@example.invalid",
                role="USER",
                status="DISABLED",
                account_origin="SYNTHETIC_DEMO",
            )
            db.add(synth_user)
            await db.commit()

            # Calling /auth/me with this token must resolve to unauthenticated GUEST because user status is DISABLED
            client.cookies.set(settings.SESSION_COOKIE_NAME, token)
            api_res = await client.get("/api/v1/auth/me")
            assert api_res.status_code == 200
            assert api_res.json()["meta"]["is_authenticated"] is False
            assert api_res.json()["data"]["role"] == "GUEST"

            # Password login attempt for synthetic user must fail with 401
            login_res = await client.post(
                "/api/v1/auth/login",
                json={
                    "email": "demo_synthetic_test@example.invalid",
                    "password": "Password123!",
                }
            )
            assert login_res.status_code == 401

            # Cleanup
            await db.delete(synth_user)
            await db.commit()
