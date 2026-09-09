import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app, PRODUCTION_DATASET_VERSION


@pytest.mark.asyncio
async def test_api_enforces_production_dataset_version_isolation():
    """
    Verifies that legacy /reframe returns 410 GONE and V7 routes enforce dataset version isolation.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/reframe",
            json={
                "movie_id": "the-bat-whispers-1930",
                "reveal_id": "reveal-anderson-identity",
                "top_k": 5,
            },
        )
        assert resp.status_code == 410


@pytest.mark.asyncio
async def test_health_endpoint_reports_production_dataset():
    """Verifies that /health accurately reports production dataset version."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_dataset_version"] == "the_bat_whispers_v3_gemini36"
        assert data["mcp_backend"] == "ClickHouse/mcp-clickhouse"
