"""
Unit Tests for R3-02 & R3-03: MCP Evidence Pipeline, Seed Adapter, and Catalog Registry
Verifies that official MCP results are the evidence source and catalog prevents arbitrary SQL injection.
Zero Paid Model Calls.
"""
import pytest
from src.reframe.evidence.catalog_registry import catalog_registry, CatalogRegistryError
from src.reframe.mcp.adapter import McpEvidenceResult, mcp_seed_adapter
from src.reframe.narrative.bundle import bundle_builder
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.agents.roles import ExecutionMode


def test_catalog_registry_validation_and_rejections():
    """Verify CatalogRegistry validates canonical work/edition/reveal and rejects unknown keys."""
    # Valid lookups
    work = catalog_registry.require_work("the-bat-whispers-1930")
    assert work["title"] == "The Bat Whispers"

    ed = catalog_registry.require_edition("the-bat-whispers-1930", "tbw-fullscreen-archive")
    assert ed == "tbw-fullscreen-archive"

    rev = catalog_registry.require_reveal("the-bat-whispers-1930", "reveal-anderson-identity")
    assert rev.reveal_id == "reveal-anderson-identity"

    # Rejections
    with pytest.raises(CatalogRegistryError, match="UNKNOWN_WORK"):
        catalog_registry.require_work("nonexistent-film-9999")

    with pytest.raises(CatalogRegistryError, match="UNKNOWN_EDITION"):
        catalog_registry.require_edition("the-bat-whispers-1930", "illegal-4k-remaster")

    with pytest.raises(CatalogRegistryError, match="UNKNOWN_REVEAL"):
        catalog_registry.require_reveal("the-bat-whispers-1930", "fake-reveal-id")


def test_mcp_evidence_seed_adapter_transformation():
    """Verify McpEvidenceSeedAdapter transforms raw McpEvidenceResult rows into typed EvidenceSeed."""
    sample_result = McpEvidenceResult(
        analysis_run_id="run-test-01",
        phase="candidate_retrieval",
        transport="official-mcp-fastmcp",
        query_hash="hash-12345",
        dataset_version="v3",
        cutoff_ms=4860000,
        raw_rows=[
            {
                "scene_id": "scene-tbw-c017",
                "start_ms": 2010000,
                "end_ms": 2130000,
                "summary": "Anderson inspects hallway alone.",
                "characters": ["Detective Anderson"],
                "objects": ["Flashlight"]
            },
            {
                "scene_id": "scene-tbw-c021",
                "start_ms": 2490000,
                "end_ms": 2610000,
                "summary": "Anderson unrolls blueprints before Dale.",
                "characters": ["Detective Anderson", "Dale Ogden"],
                "objects": ["Blueprints"]
            }
        ]
    )

    seeds = mcp_seed_adapter.from_mcp_results([sample_result])
    assert len(seeds) == 1
    seed = seeds[0]
    assert seed.channel_name == "MCP_CLICKHOUSE_RETRIEVAL"
    assert "scene-tbw-c017" in seed.scene_ids
    assert "scene-tbw-c021" in seed.scene_ids
    assert len(seed.evidence_hashes) == 2


def test_bundle_builder_live_mode_requires_mcp_seeds():
    """Verify bundle_builder strictly rejects live mode execution without provided MCP seeds."""
    reveal = v3_adapter.get_reveal("reveal-anderson-identity")
    with pytest.raises(RuntimeError, match="MCP_EVIDENCE_REQUIRED"):
        bundle_builder.build_bundle(
            reveal=reveal,
            cutoff_ms=4860000,
            provided_seeds=None,
            execution_mode=ExecutionMode.LIVE_GOOGLE
        )
