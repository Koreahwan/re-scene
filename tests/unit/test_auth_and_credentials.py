"""
Unit Tests for Reframe V7 Identity, Argon2id Crypto, UserCredentials, and Rate Limiting
Zero Paid Model Calls ($0.00).
"""
import pytest
import uuid
from httpx import AsyncClient, ASGITransport

from src.reframe.identity.crypto import hash_password, verify_password, validate_password_strength
from src.reframe.identity.rate_limit import check_auth_rate_limit
from src.reframe.shared.exceptions import ReframeException
from apps.api.main import app


@pytest.mark.asyncio
async def test_argon2id_hashing_and_verification():
    raw_pw = "CinemaNoirSecret#1930"
    pw_hash = hash_password(raw_pw)

    assert pw_hash.startswith("$argon2id$")
    assert verify_password(raw_pw, pw_hash) is True
    assert verify_password("WrongPassword#123", pw_hash) is False
    assert verify_password("", pw_hash) is False


def test_password_strength_policy():
    # Valid passwords
    valid, _ = validate_password_strength("ValidPass123")
    assert valid is True
    valid, _ = validate_password_strength("BatWhispers#1930")
    assert valid is True

    # Invalid passwords (too short, no digits)
    invalid, _ = validate_password_strength("short1")
    assert invalid is False
    invalid, _ = validate_password_strength("NoDigitsHereAtAll")
    assert invalid is False
    invalid, _ = validate_password_strength("")
    assert invalid is False


class MockClient:
    def __init__(self, host: str):
        self.host = host


class MockRequest:
    def __init__(self, host: str = "127.0.0.1"):
        self.client = MockClient(host)


@pytest.mark.asyncio
async def test_auth_rate_limiter_allows_under_limit():
    client_ip = f"192.168.1.{uuid.uuid4().hex[:4]}"
    req = MockRequest(client_ip)

    for _ in range(5):
        # Should not raise
        await check_auth_rate_limit(req, action="test_login", max_requests=10, window_seconds=60)


@pytest.mark.asyncio
async def test_auth_rate_limiter_blocks_over_limit():
    client_ip = f"10.0.0.{uuid.uuid4().hex[:4]}"
    req = MockRequest(client_ip)

    # Exhaust limit
    for _ in range(10):
        await check_auth_rate_limit(req, action="test_block", max_requests=10, window_seconds=60)

    # 11th should raise 429
    with pytest.raises(ReframeException) as exc_info:
        await check_auth_rate_limit(req, action="test_block", max_requests=10, window_seconds=60)
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_auth_signup_and_login_flow():
    from src.reframe.identity.outbox import challenge_store
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Get CSRF
        csrf_res = await client.get("/api/v1/auth/csrf")
        assert csrf_res.status_code == 200
        csrf_token = csrf_res.json()["data"]["csrf_token"]

        test_email = f"detective_{uuid.uuid4().hex[:6]}@reframe.dev"
        test_pw = "Detective#1930"

        # Verification code & ticket
        await client.post(
            "/api/v1/auth/email-verification/request",
            headers={"X-CSRF-Token": csrf_token},
            json={"email": test_email}
        )
        msg = next(m for m in challenge_store.get_dev_outbox_messages() if m["recipient"] == test_email)
        confirm_res = await client.post(
            "/api/v1/auth/email-verification/confirm",
            headers={"X-CSRF-Token": csrf_token},
            json={"email": test_email, "code": msg["raw_code"]}
        )
        assert confirm_res.status_code == 200
        ticket = confirm_res.json()["data"]["email_verification_ticket"]

        # 1. Signup
        signup_res = await client.post(
            "/api/v1/auth/signup",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "email": test_email,
                "password": test_pw,
                "email_verification_ticket": ticket,
                "display_name": "Detective Anderson Test",
                "handle": f"det_{uuid.uuid4().hex[:6]}"
            }
        )
        assert signup_res.status_code == 201
        signup_data = signup_res.json()["data"]
        assert signup_data["email"] == test_email
        assert signup_data["role"] == "USER"
        assert "reframe_session" in signup_res.cookies

        # Attach cookie to client
        client.cookies.set("reframe_session", signup_res.cookies.get("reframe_session"))

        # 2. Whoami (GET /auth/me)
        me_res = await client.get("/api/v1/auth/me")
        assert me_res.status_code == 200
        assert me_res.json()["data"]["email"] == test_email

        # 3. Login with wrong password
        wrong_login = await client.post(
            "/api/v1/auth/login",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "email": test_email,
                "password": "WrongPassword#123"
            }
        )
        assert wrong_login.status_code == 401

        # 4. Login with correct password
        login_res = await client.post(
            "/api/v1/auth/login",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "email": test_email,
                "password": test_pw
            }
        )
        assert login_res.status_code == 200
        assert login_res.json()["data"]["email"] == test_email
        login_data = login_res.json()["data"]
        client.cookies.set("reframe_session", login_res.cookies.get("reframe_session"))

        # 5. Logout using fresh CSRF token from login
        logout_res = await client.post(
            "/api/v1/auth/logout",
            headers={"X-CSRF-Token": login_data["csrf_token"]}
        )
        assert logout_res.status_code == 200


def test_argon2_exact_parameters_truthfulness():
    """Verify exact Argon2 parameters in source: 64MiB memory, 2 iterations, 4 parallelism, 16-byte salt."""
    from src.reframe.identity.crypto import (
        ARGON2_MEMORY_COST,
        ARGON2_ITERATIONS,
        ARGON2_LANES,
        ARGON2_KEY_LENGTH,
        ARGON2_SALT_LENGTH
    )
    assert ARGON2_MEMORY_COST == 65536  # 64 MiB
    assert ARGON2_ITERATIONS == 2
    assert ARGON2_LANES == 4
    assert ARGON2_KEY_LENGTH == 32
    assert ARGON2_SALT_LENGTH == 16


@pytest.mark.asyncio
async def test_account_lockout_after_five_failed_attempts():
    """Verify account lockout kicks in after 5 failed login attempts and blocks subsequent logins with 403."""
    from src.reframe.identity.outbox import challenge_store
    from src.reframe.shared.redis_client import redis_client
    await redis_client.delete("rate_limit:auth:login:127.0.0.1", "rate_limit:auth:login:testclient")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        csrf_res = await client.get("/api/v1/auth/csrf")
        csrf_token = csrf_res.json()["data"]["csrf_token"]

        test_email = f"lockout_{uuid.uuid4().hex[:6]}@reframe.dev"
        test_pw = "ValidLockoutPass#1930"

        # Verification code & ticket
        await client.post(
            "/api/v1/auth/email-verification/request",
            headers={"X-CSRF-Token": csrf_token},
            json={"email": test_email}
        )
        msg = next(m for m in challenge_store.get_dev_outbox_messages() if m["recipient"] == test_email)
        confirm_res = await client.post(
            "/api/v1/auth/email-verification/confirm",
            headers={"X-CSRF-Token": csrf_token},
            json={"email": test_email, "code": msg["raw_code"]}
        )
        assert confirm_res.status_code == 200
        ticket = confirm_res.json()["data"]["email_verification_ticket"]

        # 1. Signup
        signup_res = await client.post(
            "/api/v1/auth/signup",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "email": test_email,
                "password": test_pw,
                "email_verification_ticket": ticket,
                "display_name": "Lockout Test User",
                "handle": f"lock_{uuid.uuid4().hex[:6]}"
            }
        )
        assert signup_res.status_code == 201

        # 2. Perform 5 failed login attempts
        for _ in range(5):
            wrong_res = await client.post(
                "/api/v1/auth/login",
                headers={"X-CSRF-Token": csrf_token},
                json={
                    "email": test_email,
                    "password": "WrongPassword#999"
                }
            )
            assert wrong_res.status_code == 401

        # 3. 6th attempt (even with correct password) must be rejected with 403 Forbidden
        locked_res = await client.post(
            "/api/v1/auth/login",
            headers={"X-CSRF-Token": csrf_token},
            json={
                "email": test_email,
                "password": test_pw
            }
        )
        assert locked_res.status_code == 403
        assert "locked" in locked_res.json()["error"]["message"].lower()

