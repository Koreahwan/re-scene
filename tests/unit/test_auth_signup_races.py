"""
Unit Tests for Signup Uniqueness Races & State Transitions.
Verifies:
1. Duplicate handle / email caught via IntegrityError returns 409 and releases ticket reservation.
2. Released reservation can be safely reused or re-submitted with valid credentials.
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.identity.outbox import challenge_store


@pytest.mark.asyncio
async def test_signup_handle_uniqueness_race_returns_409():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get CSRF
        csrf_res = await client.get("/api/v1/auth/csrf")
        csrf_token = csrf_res.json()["data"]["csrf_token"]

        shared_handle = f"unique_race_{uuid.uuid4().hex[:6]}"
        email1 = f"user1_{uuid.uuid4().hex[:6]}@reframe.dev"
        email2 = f"user2_{uuid.uuid4().hex[:6]}@reframe.dev"
        password = "ValidPassword123!@#"

        # Register User 1
        challenge_store.create_code_challenge(email1, purpose="verification")
        dev_messages = challenge_store.get_dev_outbox_messages()
        msg1 = next(m for m in dev_messages if m["recipient"] == email1 and m["purpose"] == "verification")
        conf1 = await client.post("/api/v1/auth/email-verification/confirm", json={"email": email1, "code": msg1["raw_code"]})
        ticket1 = conf1.json()["data"]["email_verification_ticket"]

        res1 = await client.post("/api/v1/auth/signup", json={
            "email": email1,
            "password": password,
            "handle": shared_handle,
            "email_verification_ticket": ticket1
        })
        assert res1.status_code == 201

        # Attempt to register User 2 with same handle
        challenge_store.create_code_challenge(email2, purpose="verification")
        dev_messages = challenge_store.get_dev_outbox_messages()
        msg2 = next(m for m in dev_messages if m["recipient"] == email2 and m["purpose"] == "verification")
        conf2 = await client.post("/api/v1/auth/email-verification/confirm", json={"email": email2, "code": msg2["raw_code"]})
        ticket2 = conf2.json()["data"]["email_verification_ticket"]

        res2 = await client.post("/api/v1/auth/signup", json={
            "email": email2,
            "password": password,
            "handle": shared_handle,
            "email_verification_ticket": ticket2
        })
        assert res2.status_code == 409
        assert res2.json()["error"]["code"] == "AUTH_HANDLE_UNAVAILABLE"

        # Now User 2 chooses a different handle -> ticket should still be usable since reservation was released!
        res3 = await client.post("/api/v1/auth/signup", json={
            "email": email2,
            "password": password,
            "handle": f"{shared_handle}_diff",
            "email_verification_ticket": ticket2
        })
        assert res3.status_code == 201
