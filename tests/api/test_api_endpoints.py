import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_dataset_version"] == "the_bat_whispers_v3_gemini36"
        assert data["mcp_backend"] == "ClickHouse/mcp-clickhouse"


@pytest.mark.asyncio
async def test_films_and_reveals_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Legacy endpoint returns 410 GONE
        film_resp = await client.get("/films/the-bat-whispers-1930")
        assert film_resp.status_code == 410

        # V7 Catalog endpoint returns 200 OK
        v7_film_resp = await client.get("/api/v1/catalog/works/the-bat-whispers-1930")
        assert v7_film_resp.status_code == 200
        assert v7_film_resp.json()["data"]["title"] == "The Bat Whispers"

        # Legacy reveals endpoint returns 410 GONE
        revs_resp = await client.get("/films/the-bat-whispers-1930/reveals")
        assert revs_resp.status_code == 410

        # V7 reveals endpoint returns 200 OK
        v7_revs_resp = await client.get("/api/v1/catalog/works/the-bat-whispers-1930/reveals")
        assert v7_revs_resp.status_code == 200
        revs = v7_revs_resp.json()["data"]
        assert len(revs) >= 2


@pytest.mark.asyncio
async def test_post_reframe_analysis_flow():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Legacy synchronous /reframe returns 410 GONE
        payload = {
            "movie_id": "the-bat-whispers-1930",
            "reveal_id": "reveal-anderson-identity",
            "top_k": 5,
        }
        resp = await client.post("/reframe", json=payload)
        assert resp.status_code == 410


@pytest.mark.asyncio
async def test_post_reframe_rejects_client_cutoff_override():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Legacy synchronous /reframe returns 410 GONE
        malicious_payload = {
            "movie_id": "the-bat-whispers-1930",
            "reveal_id": "reveal-anderson-identity",
            "spoiler_cutoff_ms": 1000,
        }
        resp = await client.post("/reframe", json=malicious_payload)
        assert resp.status_code == 410
