import time
import pytest
from httpx import AsyncClient, ASGITransport
from apps.api.main import app
from reframe.domain.enums import ReframeRunStatus, RelationType


@pytest.mark.asyncio
async def test_real_production_e2e_against_live_clickhouse():
    """
    Executes full production E2E flow against live ClickHouse:
    1. Real Reveal Lookup
    2. Server derives cutoff strictly
    3. Queries live ClickHouse container
    4. Autonomous Evidence Verifier validates candidates
    5. Returns verified Reframed Moment cards
    """
    start_time = time.time()
    
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Query Reveal
        reveal_id = "reveal-anderson-identity"
        movie_id = "the-bat-whispers-1930"

        # Step 2: Post Analysis Request
        payload = {
            "movie_id": movie_id,
            "reveal_id": reveal_id,
            "top_k": 5,
        }
        resp = await client.post("/reframe", json=payload)
        assert resp.status_code == 200
        result = resp.json()
        elapsed_sec = time.time() - start_time

        # Step 3: Assert Invariants
        assert result["status"] == "COMPLETED"
        assert result["reveal_id"] == reveal_id
        assert result["spoiler_cutoff_ms"] == 4860000

        cards = result["cards"]
        assert len(cards) >= 3

        # Step 4: Prove Zero Future Spoiler Leakage
        for card in cards:
            assert card["start_ms"] < 4860000
            assert card["scene_id"] != "scene-tbw-010"  # Climax scene strictly blocked
            assert card["relation_type"] in [
                "REINTERPRETATION",
                "DIRECT_FORESHADOWING",
                "CHARACTER_MOTIVATION",
            ]
            assert card["before_meaning"] != ""
            assert card["after_meaning"] != ""

        # Step 5: Verify Query Trace
        run_id = result["run_id"]
        trace_resp = await client.get(f"/traces/{run_id}")
        assert trace_resp.status_code == 200
        trace = trace_resp.json()
        assert trace["run_id"] == run_id
        assert trace["spoiler_cutoff_ms"] == 4860000

        print(f"\n[REAL E2E EVIDENCE] run_id={run_id} cards={len(cards)} elapsed={elapsed_sec:.3f}s")
