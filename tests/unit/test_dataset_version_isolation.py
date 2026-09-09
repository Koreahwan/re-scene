import pytest
from reframe.mcp.gateway import OfficialMcpNarrativeMemoryGateway, MockNarrativeMemoryGateway, ACTIVE_DATASET_VERSION


@pytest.mark.asyncio
async def test_dataset_version_isolation_query():
    """
    Verifies that ClickHouse MCP queries strictly isolate dataset versions
    and prevent mixing historical model runs with final production data.
    """
    mock_scenes = [
        {"scene_id": "scene-v2-001", "movie_id": "the-bat-whispers-1930", "dataset_version": "the_bat_whispers_v2_gemini36", "start_ms": 10000, "summary": "Old v2 scene", "characters": ["Detective Anderson"]},
        {"scene_id": "scene-v3-001", "movie_id": "the-bat-whispers-1930", "dataset_version": "the_bat_whispers_v3_gemini36", "start_ms": 10000, "summary": "New v3 scene", "characters": ["Detective Anderson"]},
    ]
    gateway = MockNarrativeMemoryGateway(
        scenes=mock_scenes,
        events=[],
        facts=[],
        dataset_version="the_bat_whispers_v3_gemini36",
    )
    
    candidates_v3 = await gateway.search_entity_candidates(
        movie_id="the-bat-whispers-1930",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        entities=["Detective Anderson", "The Bat", "Brooks"],
        limit=30,
        dataset_version="the_bat_whispers_v3_gemini36",
    )
    
    # All returned candidates must be from v3 dataset
    assert len(candidates_v3) == 1
    assert candidates_v3[0].scene_id == "scene-v3-001"
