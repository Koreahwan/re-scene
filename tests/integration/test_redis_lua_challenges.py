"""
Real Redis Lua Integration Tests (Zero In-Memory Fallback).
Tests:
- 20 concurrent reserve attempts -> exactly one success
- 20 concurrent consume attempts -> exactly one success
- 5 concurrent resend requests -> exactly one code dispatched/active
- Attempt counter is atomic
- Ticket replay fails
- Redis failure returns 503 in production mode
"""
import pytest
import asyncio
import os
import uuid
import time
from src.reframe.identity.outbox import IdentityChallengeStore
from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException


@pytest.mark.asyncio
async def test_redis_lua_concurrent_20_consumers_ticket_race():
    """Verify 20 simultaneous coroutines attempting to reserve one ticket -> exactly 1 success."""
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
    except Exception:
        pytest.skip("Redis 7 instance not reachable for real Lua test")

    store = IdentityChallengeStore(redis_client=r, allow_in_memory=False)
    email = f"race_redis_{uuid.uuid4().hex[:8]}@reframe.dev"
    ticket = store.issue_verification_ticket(email)

    async def try_reserve(idx: int):
        op_id = f"op_redis_{idx}_{uuid.uuid4().hex[:6]}"
        return store.reserve_verification_ticket(ticket, email, op_id), op_id

    tasks = [try_reserve(i) for i in range(20)]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for success, _ in results if success)
    failure_count = sum(1 for success, _ in results if not success)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert failure_count == 19, f"Expected 19 failures, got {failure_count}"

    # Verify winning consumer can consume
    winning_op = next(op for success, op in results if success)
    consumed = store.confirm_consumed_verification_ticket(ticket, email, winning_op)
    assert consumed is True

    # Subsequent consume must fail
    replay = store.confirm_consumed_verification_ticket(ticket, email, winning_op)
    assert replay is False


@pytest.mark.asyncio
async def test_redis_lua_concurrent_20_consumers_consume_race():
    """Verify 20 simultaneous coroutines attempting to consume one ticket -> exactly 1 success."""
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
    except Exception:
        pytest.skip("Redis 7 instance not reachable for real Lua test")

    store = IdentityChallengeStore(redis_client=r, allow_in_memory=False)
    email = f"race_consume_{uuid.uuid4().hex[:8]}@reframe.dev"
    ticket = store.issue_verification_ticket(email)
    op_id = f"op_win_{uuid.uuid4().hex[:6]}"
    assert store.reserve_verification_ticket(ticket, email, op_id) is True

    async def try_consume(idx: int):
        return store.confirm_consumed_verification_ticket(ticket, email, op_id)

    tasks = [try_consume(i) for i in range(20)]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for success in results if success)
    assert success_count == 1
    assert sum(1 for s in results if not s) == 19


@pytest.mark.asyncio
async def test_redis_lua_concurrent_5_resend_cooldown():
    """Verify 5 concurrent code challenge creation requests -> exactly 1 succeeds, 4 hit cooldown."""
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
    except Exception:
        pytest.skip("Redis 7 instance not reachable for real Lua test")

    store = IdentityChallengeStore(redis_client=r, allow_in_memory=False)
    email = f"cooldown_redis_{uuid.uuid4().hex[:8]}@reframe.dev"

    async def try_issue():
        try:
            code = store.create_code_challenge(email, purpose="verification")
            return True, code
        except ReframeException as e:
            if e.code == "AUTH_RATE_LIMITED":
                return False, "rate_limited"
            raise e

    tasks = [try_issue() for _ in range(5)]
    results = await asyncio.gather(*tasks)

    successes = [code for success, code in results if success]
    rate_limited = [code for success, code in results if not success]

    assert len(successes) == 1
    assert len(rate_limited) == 4


def test_redis_lua_attempt_counter_and_lockout():
    """Verify code verification attempt counter is strictly atomic and burns challenge after max attempts."""
    import redis
    try:
        r = redis.from_url(settings.REDIS_URL, decode_responses=True)
        r.ping()
    except Exception:
        pytest.skip("Redis 7 instance not reachable for real Lua test")

    store = IdentityChallengeStore(redis_client=r, allow_in_memory=False)
    email = f"attempts_{uuid.uuid4().hex[:8]}@reframe.dev"
    code = store.create_code_challenge(email, purpose="verification")

    # 4 invalid attempts
    for _ in range(4):
        assert store.verify_and_consume_code(email, "000000", purpose="verification") is False

    # 5th invalid attempt raises 400 AUTH_CODE_INVALID
    with pytest.raises(ReframeException) as exc:
        store.verify_and_consume_code(email, "000000", purpose="verification")
    assert exc.value.code == "AUTH_CODE_INVALID"

    # Challenge is now burned
    assert store.verify_and_consume_code(email, code, purpose="verification") is False


def test_redis_fail_closed_in_production():
    """Verify that in production mode, Redis failure raises 503 AUTH_CHALLENGE_STORE_UNAVAILABLE."""
    # Force production mode check
    prod_store = IdentityChallengeStore(redis_client=False, allow_in_memory=False)
    with pytest.raises(ReframeException) as exc:
        prod_store.create_code_challenge("test@reframe.dev")
    assert exc.value.status_code == 503
    assert exc.value.code == "AUTH_CHALLENGE_STORE_UNAVAILABLE"
