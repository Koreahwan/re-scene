import json
from pathlib import Path
import pytest
from reframe.mcp.gateway import MockNarrativeMemoryGateway, ACTIVE_DATASET_VERSION


def test_checkpoint_model_version_provenance():
    """
    Asserts that the production checkpoint is 100% uniform gemini-3.6-flash
    and dataset version is the_bat_whispers_v3_gemini36.
    """
    v3_path = Path("data/manifests/preprocessing_checkpoint_v3_gemini36.json")
    if v3_path.exists():
        with open(v3_path, "r", encoding="utf-8") as f:
            v3_data = json.load(f)
        
        assert v3_data.get("model_id") == "gemini-3.6-flash"
        assert v3_data.get("dataset_version") == "the_bat_whispers_v3_gemini36"
        assert v3_data.get("canonical_asset_sha256") == "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"
        
        for chunk_id, chunk_meta in v3_data.get("processed_chunks", {}).items():
            assert chunk_meta.get("model_id") == "gemini-3.6-flash", f"Chunk {chunk_id} has non-3.6 model!"
            assert chunk_meta.get("dataset_version") == "the_bat_whispers_v3_gemini36"


@pytest.mark.asyncio
async def test_runtime_retrieval_model_isolation():
    """
    Verifies that retrieval returns only rows with dataset_version = 'the_bat_whispers_v3_gemini36'
    and never mixes historical or unversioned rows.
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
    
    candidates = await gateway.search_entity_candidates(
        movie_id="the-bat-whispers-1930",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        entities=["Detective Anderson", "The Bat"],
        limit=20,
        dataset_version="the_bat_whispers_v3_gemini36",
    )
    
    for c in candidates:
        assert c.scene_id == "scene-v3-001"
        assert c.start_ms < 4860000
