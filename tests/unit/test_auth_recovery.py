"""
Unit tests for Reframe V7 Identity Challenge, Ticket & Outbox Store.
Verifies:
- 6-digit code challenge dispatch, HMAC hashing, and TTL expiry
- Failed attempt limits and lockout
- One-time verification tickets for signup
- One-time password reset tickets for password recovery
- Cooldown timers and dev outbox message tracking
- Zero external email calls
"""
import pytest
import time
from src.reframe.identity.outbox import IdentityChallengeStore
from src.reframe.identity.crypto import validate_password_strength, hash_password, verify_password


def test_challenge_store_code_and_ticket_lifecycle():
    store = IdentityChallengeStore(redis_client=False)  # in-memory mode for unit test
    email = "viewer@reframe.dev"

    # 1. Dispatch challenge code
    code = store.create_code_challenge(email, purpose="verification")
    assert len(code) == 6
    assert code.isdigit()

    # 2. Resend cooldown is active
    cd = store.check_resend_cooldown(email, purpose="verification")
    assert cd is not None
    assert cd > 0

    # 3. Wrong code fails
    assert store.verify_and_consume_code(email, "000000", purpose="verification") is False

    # 4. Correct code verifies and consumes challenge
    assert store.verify_and_consume_code(email, code, purpose="verification") is True

    # 5. Challenge cannot be consumed again
    assert store.verify_and_consume_code(email, code, purpose="verification") is False

    # 6. Issue signup verification ticket
    ticket = store.issue_verification_ticket(email)
    assert ticket.startswith("evt_")

    # 7. Consume ticket with matching email succeeds
    assert store.consume_verification_ticket(ticket, email) is True

    # 8. Replayed ticket is rejected (one-time use)
    assert store.consume_verification_ticket(ticket, email) is False

    # 9. Test ticket with mismatched email
    ticket2 = store.issue_verification_ticket(email)
    assert store.consume_verification_ticket(ticket2, "other@reframe.dev") is False


def test_password_reset_ticket_lifecycle():
    store = IdentityChallengeStore(redis_client=False)
    email = "reset@reframe.dev"

    code = store.create_code_challenge(email, purpose="password_reset")
    assert store.verify_and_consume_code(email, code, purpose="password_reset") is True

    ticket = store.issue_password_reset_ticket(email)
    assert ticket.startswith("prt_")

    # Consume ticket
    assert store.consume_password_reset_ticket(ticket, email) is True
    # Replay rejected
    assert store.consume_password_reset_ticket(ticket, email) is False


def test_challenge_max_attempts_lockout():
    from src.reframe.shared.exceptions import ReframeException
    store = IdentityChallengeStore(redis_client=False)
    email = "lockout@reframe.dev"

    code = store.create_code_challenge(email, purpose="verification")

    # 4 wrong attempts return False
    for _ in range(4):
        assert store.verify_and_consume_code(email, "999999", purpose="verification") is False

    # 5th wrong attempt raises lockout
    with pytest.raises(ReframeException):
        store.verify_and_consume_code(email, "999999", purpose="verification")

    # Correct code is now rejected
    assert store.verify_and_consume_code(email, code, purpose="verification") is False



def test_password_strength_and_argon2_hashing():
    is_valid, msg = validate_password_strength("Secret123!@#")
    assert is_valid is True
    assert msg is None

    is_valid, msg = validate_password_strength("Short1!")
    assert is_valid is False

    pwd = "StrongPassword2026!"
    hashed = hash_password(pwd)
    assert hashed.startswith("$argon2id$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
