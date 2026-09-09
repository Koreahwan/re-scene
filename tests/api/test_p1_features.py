import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app


@pytest.mark.asyncio
async def test_fan_insights_legacy_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/films/the-bat-whispers-1930/insights")
        assert resp.status_code == 410


@pytest.mark.asyncio
async def test_execution_trace_legacy_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/traces/fake-run-id")
        assert resp.status_code == 410


@pytest.mark.asyncio
async def test_v7_fan_scene_and_catalog():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/v1/fan/scenes/scene-tbw-c017")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["scene_id"] == "scene-tbw-c017"
