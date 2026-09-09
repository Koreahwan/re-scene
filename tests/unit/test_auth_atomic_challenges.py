"""
IN_MEMORY_REFERENCE_TEST: Unit & Concurrency Tests for Reference Atomic Challenge Store.
Verifies:
1. 20 simultaneous concurrent consumers of a single ticket -> exactly 1 success, 19 failures.
2. Invalidation of prior active challenge and ticket upon issuing/resending challenge.
3. Code attempt counter & lockout after 5 failed attempts.
4. Fail-closed behavior in production mode when Redis is unavailable.
"""
import asyncio
import pytest
import uuid
from src.reframe.identity.outbox import IdentityChallengeStore
from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException


@pytest.mark.asyncio
async def test_twenty_concurrent_ticket_consumers_exactly_one_success():
    """
    Spawns 20 simultaneous async consumers trying to reserve the exact same verification ticket.
    Exactly 1 consumer must succeed; 19 must fail.
    """
    store = IdentityChallengeStore(allow_in_memory=True)
    email = f"concurrency_{uuid.uuid4().hex[:8]}@reframe.dev"
    ticket = store.issue_verification_ticket(email)

    success_count = 0
    failure_count = 0

    async def consume_attempt(op_id: str):
        nonlocal success_count, failure_count
        # Run in threadpool to simulate concurrent execution
        res = await asyncio.to_thread(store.reserve_verification_ticket, ticket, email, op_id)
        if res:
            success_count += 1
        else:
            failure_count += 1

    # Launch 20 tasks concurrently
    tasks = [consume_attempt(f"op_{i}_{uuid.uuid4().hex[:6]}") for i in range(20)]
    await asyncio.gather(*tasks)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert failure_count == 19, f"Expected 19 failures, got {failure_count}"


def test_issuing_new_challenge_invalidates_prior_active_challenge_and_ticket():
    """
    Issuing or resending a challenge must invalidate any prior active challenge
    and any prior verification ticket for that email + purpose.
    """
    store = IdentityChallengeStore(allow_in_memory=True)
    email = f"invalidate_{uuid.uuid4().hex[:8]}@reframe.dev"

    # 1. Issue first challenge and verify -> get ticket 1
    code1 = store.create_code_challenge(email, purpose="verification")
    assert store.verify_and_consume_code(email, code1, purpose="verification") is True
    ticket1 = store.issue_verification_ticket(email)

    # 2. Resend / request new challenge for same email
    # Clear cooldown for test
    cooldown_key = f"auth:cooldown:verification:{email.lower()}"
    store._memory_store.pop(cooldown_key, None)
    store._memory_expiries.pop(cooldown_key, None)

    code2 = store.create_code_challenge(email, purpose="verification")

    # 3. Old ticket1 must now be invalidated!
    op_id = uuid.uuid4().hex
    assert store.reserve_verification_ticket(ticket1, email, op_id) is False

    # 4. Old code1 must also fail
    assert store.verify_and_consume_code(email, code1, purpose="verification") is False

    # 5. New code2 succeeds
    assert store.verify_and_consume_code(email, code2, purpose="verification") is True
    ticket2 = store.issue_verification_ticket(email)
    assert store.reserve_verification_ticket(ticket2, email, op_id) is True


def test_code_attempt_limit_and_lockout():
    """
    Failing 5 consecutive verification attempts burns the challenge and blocks further attempts.
    """
    store = IdentityChallengeStore(allow_in_memory=True)
    email = f"lockout_{uuid.uuid4().hex[:8]}@reframe.dev"
    code = store.create_code_challenge(email, purpose="verification")

    # 4 incorrect attempts -> returns False
    for _ in range(4):
        assert store.verify_and_consume_code(email, "000000", purpose="verification") is False

    # 5th incorrect attempt -> raises 400 AUTH_CODE_INVALID (max attempts exceeded)
    with pytest.raises(ReframeException) as exc_info:
        store.verify_and_consume_code(email, "000000", purpose="verification")
    assert exc_info.value.code == "AUTH_CODE_INVALID"

    # 6th attempt (even with correct code) must fail because challenge was burned
    assert store.verify_and_consume_code(email, code, purpose="verification") is False


def test_fail_closed_in_production_when_redis_unavailable(monkeypatch):
    """
    In production mode, if Redis is unavailable, challenge store must fail-closed with 503.
    """
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    store = IdentityChallengeStore(redis_client=None, allow_in_memory=False)

    email = "prod_user@reframe.dev"
    with pytest.raises(ReframeException) as exc_info:
        store.create_code_challenge(email, purpose="verification")
    assert exc_info.value.status_code == 503
    assert exc_info.value.code == "AUTH_CHALLENGE_STORE_UNAVAILABLE"
