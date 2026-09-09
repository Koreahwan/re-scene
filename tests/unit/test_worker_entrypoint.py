"""
Unit Tests for Reframe V7 Worker Entrypoint Lifecycle & Redis Connection
Ensures connect() -> run_loop() -> close() order and fail-closed exception propagation.
Zero Paid Model Calls ($0.00). No real Redis/DB/network calls.
"""
import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from apps.worker.worker import main
from src.reframe.shared.redis_client import redis_client
import apps.worker.worker as worker_module


@pytest.mark.asyncio
async def test_worker_entrypoint_normal_lifecycle_order():
    """Verify normal lifecycle: connect() -> run_loop() -> close() in exact sequence and count."""
    call_order = []

    async def mock_connect():
        call_order.append("connect")

    async def mock_run_loop():
        call_order.append("run_loop")

    async def mock_close():
        call_order.append("close")

    with patch.object(redis_client, "connect", side_effect=mock_connect) as mock_conn, \
         patch.object(worker_module.worker, "run_loop", side_effect=mock_run_loop) as mock_loop, \
         patch.object(redis_client, "close", side_effect=mock_close) as mock_cls:

        await main()

        assert call_order == ["connect", "run_loop", "close"]
        assert mock_conn.await_count == 1
        assert mock_loop.await_count == 1
        assert mock_cls.await_count == 1


@pytest.mark.asyncio
async def test_worker_entrypoint_propagates_runtime_error_and_closes():
    """Verify that if run_loop raises RuntimeError, close() is called in finally and error is propagated."""
    call_order = []

    async def mock_connect():
        call_order.append("connect")

    async def mock_run_loop():
        call_order.append("run_loop")
        raise RuntimeError("Worker loop fatal database connection drop")

    async def mock_close():
        call_order.append("close")

    with patch.object(redis_client, "connect", side_effect=mock_connect) as mock_conn, \
         patch.object(worker_module.worker, "run_loop", side_effect=mock_run_loop), \
         patch.object(redis_client, "close", side_effect=mock_close) as mock_cls:

        with pytest.raises(RuntimeError, match="Worker loop fatal database connection drop"):
            await main()

        assert call_order == ["connect", "run_loop", "close"]
        assert mock_conn.await_count == 1
        assert mock_cls.await_count == 1


@pytest.mark.asyncio
async def test_worker_entrypoint_propagates_cancelled_error_and_closes():
    """Verify that if run_loop is cancelled (asyncio.CancelledError), close() is executed in finally."""
    call_order = []

    async def mock_connect():
        call_order.append("connect")

    async def mock_run_loop():
        call_order.append("run_loop")
        raise asyncio.CancelledError()

    async def mock_close():
        call_order.append("close")

    with patch.object(redis_client, "connect", side_effect=mock_connect) as mock_conn, \
         patch.object(worker_module.worker, "run_loop", side_effect=mock_run_loop), \
         patch.object(redis_client, "close", side_effect=mock_close) as mock_cls:

        with pytest.raises(asyncio.CancelledError):
            await main()

        assert call_order == ["connect", "run_loop", "close"]
        assert mock_conn.await_count == 1
        assert mock_cls.await_count == 1


@pytest.mark.asyncio
async def test_worker_entrypoint_connect_failure_does_not_execute_run_loop():
    """Verify that if connect() fails, run_loop is never called, close() is called, and the exception propagates."""
    call_order = []

    async def mock_connect():
        call_order.append("connect")
        raise ConnectionError("Redis connection refused")

    async def mock_close():
        call_order.append("close")

    with patch.object(redis_client, "connect", side_effect=mock_connect) as mock_conn, \
         patch.object(worker_module.worker, "run_loop", new_callable=AsyncMock) as mock_loop, \
         patch.object(redis_client, "close", side_effect=mock_close) as mock_cls:

        with pytest.raises(ConnectionError, match="Redis connection refused"):
            await main()

        assert call_order == ["connect", "close"]
        assert mock_conn.await_count == 1
        assert mock_loop.await_count == 0
        assert mock_cls.await_count == 1


def test_worker_uses_shared_redis_client_instance():
    """Verify that worker module references the global redis_client singleton."""
    assert worker_module.redis_client is redis_client
