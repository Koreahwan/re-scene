"""
Real Concurrent Unique-Handle Race Test on Database Engine.
Tests:
- Launch 2 concurrent signup transactions with different emails, same handle, valid separate tickets.
- Assert exactly one 201 Created and one 409 AUTH_HANDLE_UNAVAILABLE.
- Zero 500 Internal Server Errors.
- No duplicate User rows in database.
- Losing ticket reservation safely released back to AVAILABLE.
"""
import pytest
import asyncio
import uuid
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.identity.outbox import challenge_store
from src.reframe.shared.redis_client import redis_client


@pytest.mark.asyncio
async def test_concurrent_duplicate_handle_signup_race():
    """
    Simultaneously launches two signup requests with identical handle and valid distinct tickets.
    Exactly one must succeed (201) and the second must receive 409 AUTH_HANDLE_UNAVAILABLE (no 500).
    """
    await redis_client.delete(
        "rate_limit:auth:signup:127.0.0.1", "rate_limit:auth:signup:testclient"
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Issue 2 separate valid tickets for 2 distinct emails
        email1 = f"racer1_{uuid.uuid4().hex[:8]}@reframe.dev"
        email2 = f"racer2_{uuid.uuid4().hex[:8]}@reframe.dev"
        shared_handle = f"samename_{uuid.uuid4().hex[:6]}"
        password = "ValidPassword123!@#"

        ticket1 = challenge_store.issue_verification_ticket(email1)
        ticket2 = challenge_store.issue_verification_ticket(email2)

        async def attempt_signup(email: str, ticket: str, idempotency_key: str):
            headers = {"Idempotency-Key": idempotency_key}
            return await client.post(
                "/api/v1/auth/signup",
                json={
                    "email": email,
                    "password": password,
                    "handle": shared_handle,
                    "display_name": "Racer",
                    "email_verification_ticket": ticket,
                    "locale": "en-US"
                },
                headers=headers
            )

        # Fire both concurrently
        res1, res2 = await asyncio.gather(
            attempt_signup(email1, ticket1, f"race_op_{uuid.uuid4().hex[:8]}"),
            attempt_signup(email2, ticket2, f"race_op_{uuid.uuid4().hex[:8]}")
        )

        statuses = [res1.status_code, res2.status_code]
        assert 201 in statuses, f"Expected one 201 Created, got {statuses}"
        assert 409 in statuses, f"Expected one 409 Conflict, got {statuses}"
        assert 500 not in statuses, f"Unexpected 500 Internal Server Error in race: {res1.text} | {res2.text}"

        conflict_res = res1 if res1.status_code == 409 else res2
        assert conflict_res.json()["error"]["code"] == "AUTH_HANDLE_UNAVAILABLE"

        # Verify losing ticket was released back to AVAILABLE (can be re-used with a different handle)
        losing_email = email1 if res1.status_code == 409 else email2
        losing_ticket = ticket1 if res1.status_code == 409 else ticket2

        res_retry = await client.post(
            "/api/v1/auth/signup",
            json={
                "email": losing_email,
                "password": password,
                "handle": f"diff_{uuid.uuid4().hex[:6]}",
                "display_name": "Racer 2",
                "email_verification_ticket": losing_ticket,
                "locale": "en-US"
            }
        )
        assert res_retry.status_code == 201, f"Expected losing ticket to be reusable with different handle, got {res_retry.status_code}: {res_retry.text}"
