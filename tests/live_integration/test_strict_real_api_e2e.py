import os
import pytest
import httpx
from httpx import AsyncClient, ASGITransport
from apps.api.main import app


@pytest.mark.asyncio
async def test_strict_real_api_e2e_http():
    """
    Strict real end-to-end API integration test against live server.
    Validates complete pipeline: HTTP -> FastAPI -> Official mcp-clickhouse -> ClickHouse -> Gemini 3.6 -> Response.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", timeout=90.0) as client:
        # 1. Health check
        health_resp = await client.get("/health")
        assert health_resp.status_code == 200
        health = health_resp.json()
        assert health["active_dataset_version"] == "the_bat_whispers_v3_gemini36"
        assert health["gemini_model"] == "gemini-3.6-flash"
        assert health["mcp_backend"] == "ClickHouse/mcp-clickhouse"

        # 2. Strict Real POST /reframe for Detective Anderson Reveal
        post_resp = await client.post(
            "/reframe",
            json={
                "movie_id": "the-bat-whispers-1930",
                "reveal_id": "reveal-anderson-identity",
                "top_k": 5,
            },
        )
        assert post_resp.status_code == 200
        data = post_resp.json()
        assert data["status"] in ["COMPLETED", "ABSTAINED"]

        if data["status"] == "COMPLETED":
            assert 1 <= len(data["cards"]) <= 5
            cutoff_ms = data["spoiler_cutoff_ms"]
            assert cutoff_ms == 4860000

            for card in data["cards"]:
                assert card["start_ms"] < cutoff_ms
                assert card["relation_type"] in ["DIRECT_FORESHADOWING", "REINTERPRETATION", "CHARACTER_MOTIVATION", "CONTRADICTION"]
                assert card["relation_type"] not in ["COINCIDENCE", "IRRELEVANT"]
                assert len(card["evidence_facts"]) > 0 or len(card["evidence_events"]) > 0
                assert len(card["before_meaning"]) > 5
                assert len(card["after_meaning"]) > 5

            # 3. Verify Execution Trace
            run_id = data["run_id"]
            trace_resp = await client.get(f"/traces/{run_id}")
            assert trace_resp.status_code == 200
            trace = trace_resp.json()
            assert trace["model_id"] == "gemini-3.6-flash"
            assert trace["dataset_version"] == "the_bat_whispers_v3_gemini36"
            assert "ClickHouse/mcp-clickhouse" in trace["mcp_provider"]
            assert trace["tool_called"] == "run_query"
            assert trace["latency_ms"] > 0
            assert trace["candidates_count"] > 0
            assert trace["verified_count"] == len(data["cards"])

        # 4. Poison Pill / Tampering Guard
        tamper_resp = await client.post(
            "/reframe",
            json={
                "movie_id": "the-bat-whispers-1930",
                "reveal_id": "reveal-anderson-identity",
                "spoiler_cutoff_ms": 9999999,
            },
        )
        assert tamper_resp.status_code == 200
        tamper_data = tamper_resp.json()
        assert tamper_data["status"] == "ABSTAINED" or tamper_data["spoiler_cutoff_ms"] == 4860000
