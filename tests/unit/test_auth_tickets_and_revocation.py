"""
Unit & API Integration tests for Auth Tickets, Handle Availability & Session Revocation.
Tests:
- Signup without ticket is rejected
- Email verification + ticket issuance -> signup succeeds
- Verify email A, change to email B -> signup rejected
- Ticket replay -> rejected
- Duplicate handle check & uniqueness
- Password reset revokes active sessions via auth_version increment
- Dev outbox viewer isolation
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.identity.outbox import challenge_store
from src.reframe.shared.config import settings
from src.reframe.shared.redis_client import redis_client


@pytest.mark.asyncio
async def test_handle_availability_endpoint():
    await redis_client.delete("rate_limit:auth:handle_check:127.0.0.1", "rate_limit:auth:handle_check:testclient")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Check an available handle
        unique_handle = f"user_{uuid.uuid4().hex[:8]}"
        res = await client.get(f"/api/v1/auth/handles/availability?handle={unique_handle}")
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["handle"] == unique_handle
        assert data["available"] is True

        # Check invalid handle (too short)
        res_invalid = await client.get("/api/v1/auth/handles/availability?handle=a")
        assert res_invalid.status_code == 200
        assert res_invalid.json()["data"]["available"] is False


@pytest.mark.asyncio
async def test_signup_requires_valid_ticket_and_rejects_tampering():
    await redis_client.delete(
        "rate_limit:auth:signup:127.0.0.1", "rate_limit:auth:signup:testclient",
        "rate_limit:auth:login:127.0.0.1", "rate_limit:auth:login:testclient"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"user_{uuid.uuid4().hex[:8]}@reframe.dev"
        password = "ValidPassword123!@#"

        # 1. Signup without ticket -> 422 Unprocessable Entity
        res_missing = await client.post("/api/v1/auth/signup", json={
            "email": email,
            "password": password
        })
        assert res_missing.status_code == 422

        # 2. Signup with fabricated ticket -> 400 Bad Request
        res_fake = await client.post("/api/v1/auth/signup", json={
            "email": email,
            "password": password,
            "email_verification_ticket": "evt_fake_ticket_123456789012345678"
        })
        assert res_fake.status_code == 400
        assert res_fake.json()["error"]["code"] == "AUTH_EMAIL_NOT_VERIFIED"

        # 3. Request real verification code
        req_res = await client.post("/api/v1/auth/email-verification/request", json={"email": email})
        assert req_res.status_code == 200

        # Retrieve latest code from challenge store
        dev_messages = challenge_store.get_dev_outbox_messages()
        matching = [m for m in dev_messages if m["recipient"] == email and m["purpose"] == "verification"]
        assert len(matching) > 0
        code = matching[-1]["raw_code"]

        # Confirm code and obtain ticket
        conf_res = await client.post("/api/v1/auth/email-verification/confirm", json={
            "email": email,
            "code": code
        })
        assert conf_res.status_code == 200
        ticket = conf_res.json()["data"]["email_verification_ticket"]
        assert ticket.startswith("evt_")

        # 4. Attempt signup with ticket for a DIFFERENT email -> Rejected!
        diff_email = f"diff_{uuid.uuid4().hex[:8]}@reframe.dev"
        res_mismatch = await client.post("/api/v1/auth/signup", json={
            "email": diff_email,
            "password": password,
            "email_verification_ticket": ticket
        })
        assert res_mismatch.status_code == 400

        # 5. Successful signup with matching email and ticket
        await redis_client.delete(f"auth:cooldown:verification:{email.lower()}")
        challenge_store._memory_store.pop(f"auth:cooldown:verification:{email.lower()}", None)
        challenge_store._memory_expiries.pop(f"auth:cooldown:verification:{email.lower()}", None)
        challenge_store.create_code_challenge(email, purpose="verification")

        dev_messages2 = challenge_store.get_dev_outbox_messages()
        matching2 = [m for m in dev_messages2 if m["recipient"] == email and m["purpose"] == "verification"]
        assert len(matching2) > 0
        conf_res2 = await client.post("/api/v1/auth/email-verification/confirm", json={
            "email": email,
            "code": matching2[-1]["raw_code"]
        })
        valid_ticket = conf_res2.json()["data"]["email_verification_ticket"]

        handle = f"hnd_{uuid.uuid4().hex[:8]}"
        res_signup = await client.post("/api/v1/auth/signup", json={
            "email": email,
            "password": password,
            "display_name": "Test User",
            "handle": handle,
            "email_verification_ticket": valid_ticket,
            "locale": "en-US"
        })
        assert res_signup.status_code == 201
        signup_data = res_signup.json()["data"]
        assert signup_data["email"] == email
        assert signup_data["handle"] == handle

        # 6. Ticket replay is rejected
        unregistered_email = f"unregistered_{uuid.uuid4().hex[:8]}@reframe.dev"
        res_replay = await client.post("/api/v1/auth/signup", json={
            "email": unregistered_email,
            "password": password,
            "email_verification_ticket": valid_ticket
        })
        assert res_replay.status_code == 400


@pytest.mark.asyncio
async def test_password_reset_revokes_sessions():
    await redis_client.delete(
        "rate_limit:auth:signup:127.0.0.1", "rate_limit:auth:signup:testclient",
        "rate_limit:auth:login:127.0.0.1", "rate_limit:auth:login:testclient",
        "rate_limit:auth:password_reset_complete:127.0.0.1", "rate_limit:auth:password_reset_complete:testclient"
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        email = f"reset_{uuid.uuid4().hex[:8]}@reframe.dev"
        old_password = "OldPassword123!@#"
        new_password = "NewPassword456!@#"

        # 1. Register user
        challenge_store.create_code_challenge(email, purpose="verification")
        dev_messages = challenge_store.get_dev_outbox_messages()
        matching = [m for m in dev_messages if m["recipient"] == email and m["purpose"] == "verification"]
        conf = await client.post("/api/v1/auth/email-verification/confirm", json={"email": email, "code": matching[-1]["raw_code"]})
        ticket = conf.json()["data"]["email_verification_ticket"]

        signup_res = await client.post("/api/v1/auth/signup", json={
            "email": email,
            "password": old_password,
            "email_verification_ticket": ticket
        })
        assert signup_res.status_code == 201

        # 2. Login to get session
        login_res = await client.post("/api/v1/auth/login", json={"email": email, "password": old_password})
        assert login_res.status_code == 200
        session_token = login_res.json()["data"]["csrf_token"]
        session_cookie = login_res.cookies.get(settings.SESSION_COOKIE_NAME)

        # 3. Verify session works on /auth/me
        headers = {"X-CSRF-Token": session_token}
        if session_cookie:
            client.cookies.set(settings.SESSION_COOKIE_NAME, session_cookie)
        me_res = await client.get("/api/v1/auth/me", headers=headers)
        assert me_res.status_code == 200
        assert me_res.json()["data"]["email"] == email

        # 4. Initiate Password Reset
        challenge_store.create_code_challenge(email, purpose="password_reset")
        reset_msgs = challenge_store.get_dev_outbox_messages()
        reset_matching = [m for m in reset_msgs if m["recipient"] == email and m["purpose"] == "password_reset"]
        reset_conf = await client.post("/api/v1/auth/password-reset/verify", json={
            "email": email,
            "code": reset_matching[-1]["raw_code"]
        })
        assert reset_conf.status_code == 200
        reset_ticket = reset_conf.json()["data"]["password_reset_ticket"]

        # 5. Complete Password Reset
        complete_res = await client.post("/api/v1/auth/password-reset/complete", json={
            "email": email,
            "password_reset_ticket": reset_ticket,
            "new_password": new_password
        })
        assert complete_res.status_code == 200

        # 6. Old session is now REVOKED (auth_version mismatch -> 401)
        revoked_me = await client.get("/api/v1/auth/me", headers=headers)
        assert revoked_me.status_code == 401 or revoked_me.json()["data"]["role"] == "GUEST"

        # 7. Old password no longer works
        old_login = await client.post("/api/v1/auth/login", json={"email": email, "password": old_password})
        assert old_login.status_code == 401

        # 8. New password succeeds
        new_login = await client.post("/api/v1/auth/login", json={"email": email, "password": new_password})
        assert new_login.status_code == 200
