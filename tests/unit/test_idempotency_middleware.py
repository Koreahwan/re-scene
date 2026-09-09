"""
Unit Tests for Idempotency Record Storage and Replay
"""
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from src.reframe.shared.config import settings


@pytest.mark.asyncio
async def test_reframe_run_idempotency(monkeypatch):
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        idempotency_key = f"test-idemp-{uuid.uuid4().hex}"
        payload = {
            "movie_id": "the-bat-whispers-1930",
            "edition_id": "tbw-fullscreen-archive",
            "reveal_id": "reveal-anderson-identity",
            "mode": "STRICT_CANON",
            "top_k": 5
        }

        # First request
        res1 = await client.post(
            "/api/v1/reframe-runs",
            json=payload,
            headers={"Idempotency-Key": idempotency_key}
        )
        assert res1.status_code == 202
        run_id_1 = res1.json()["data"]["run_id"]

        # Duplicate request with identical payload -> should return same run_id
        res2 = await client.post(
            "/api/v1/reframe-runs",
            json=payload,
            headers={"Idempotency-Key": idempotency_key}
        )
        assert res2.status_code == 202
        run_id_2 = res2.json()["data"]["run_id"]
        assert run_id_1 == run_id_2

        # Conflicting request with same idempotency key but different reveal_id -> 409
        conflicting_payload = dict(payload)
        conflicting_payload["reveal_id"] = "reveal-secret-room-location"
        res3 = await client.post(
            "/api/v1/reframe-runs",
            json=conflicting_payload,
            headers={"Idempotency-Key": idempotency_key}
        )
        assert res3.status_code == 409
        assert res3.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
