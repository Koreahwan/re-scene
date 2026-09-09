import os
import pytest
from reframe.domain.models import Reveal
from reframe.domain.enums import ReframeRunStatus, AbstainReason
from reframe.mcp.gateway import McpClickHouseGateway, MockNarrativeMemoryGateway
from reframe.verification.verifier import EvidenceVerifier
from reframe.application.orchestrator import ReframeOrchestrator


@pytest.mark.asyncio
async def test_official_mcp_server_jsonrpc_tool_call_flow():
    """
    Proves that Reframe communicates over official MCP protocol
    invoking `tools/call` with tool name `run_query` against the live ClickHouse MCP server.
    """
    mcp_gateway = McpClickHouseGateway()
    verifier = EvidenceVerifier()

    reveal = Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=4860000,
        title="Detective Anderson is Unmasked as 'The Bat'",
        reveal_type="IDENTITY",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective Anderson is a dedicated police officer.",
        revealed_fact="Detective Anderson is himself 'The Bat'.",
        affected_entities=["Detective Anderson", "The Bat", "Brooks"],
    )

    # 1. Direct MCP Search Candidates
    candidates = await mcp_gateway.search_entity_candidates(
        movie_id=reveal.movie_id,
        reveal_id=reveal.reveal_id,
        cutoff_ms=4860000,
        entities=reveal.affected_entities,
        limit=10,
    )
    assert len(candidates) >= 5
    assert all(c.start_ms < 4860000 for c in candidates)
    assert "scene-tbw-010" not in [c.scene_id for c in candidates]

    # 2. Direct MCP Evidence Query
    events_map, facts_map = await mcp_gateway.get_supporting_evidence(
        movie_id=reveal.movie_id,
        cutoff_ms=4860000,
        scene_ids=[c.scene_id for c in candidates],
    )
    assert any(len(evs) > 0 for evs in events_map.values())

    # 3. Full Orchestration over Official MCP
    orchestrator = ReframeOrchestrator(
        gateway=mcp_gateway,
        verifier=verifier,
        reveals_registry={reveal.reveal_id: reveal},
    )

    result, trace = await orchestrator.execute_reframe_analysis(
        movie_id=reveal.movie_id,
        reveal_id=reveal.reveal_id,
        top_k=5,
    )
    assert result.status == ReframeRunStatus.COMPLETED
    assert len(result.cards) >= 3
    for card in result.cards:
        assert card.start_ms < 4860000


@pytest.mark.asyncio
async def test_mcp_breakage_causes_fail_closed_abstain():
    """
    Deliberately breaks MCP endpoint to verify that production orchestrator
    fails closed with structured ABSTAINED rather than crashing or leaking unverified claims.
    """
    broken_gateway = McpClickHouseGateway(mcp_endpoint_url="http://127.0.0.1:9999/broken_mcp")
    verifier = EvidenceVerifier()

    reveal = Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=4860000,
        title="Detective Anderson is Unmasked as 'The Bat'",
        reveal_type="IDENTITY",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective Anderson is a dedicated police officer.",
        revealed_fact="Detective Anderson is himself 'The Bat'.",
        affected_entities=["Detective Anderson", "The Bat", "Brooks"],
    )

    orchestrator = ReframeOrchestrator(
        gateway=broken_gateway,
        verifier=verifier,
        reveals_registry={reveal.reveal_id: reveal},
    )

    try:
        result, trace = await orchestrator.execute_reframe_analysis(
            movie_id=reveal.movie_id,
            reveal_id=reveal.reveal_id,
            top_k=5,
        )

        # Invariant: Must return ABSTAINED with MCP_UNAVAILABLE reason and zero cards
        assert result.status == ReframeRunStatus.ABSTAINED
        assert result.abstain_reason == AbstainReason.MCP_UNAVAILABLE
        assert len(result.cards) == 0
    finally:
        # Restore environment
        os.environ["CLICKHOUSE_HOST"] = "localhost"
        os.environ["CLICKHOUSE_PORT"] = "8123"


@pytest.mark.asyncio
async def test_real_integration_validation_mode_forbids_mock_gateway():
    """
    Verifies that when REAL_INTEGRATION_VALIDATION=true, any instantiation of
    MockNarrativeMemoryGateway raises an immediate RuntimeError.
    """
    os.environ["REAL_INTEGRATION_VALIDATION"] = "true"
    try:
        with pytest.raises(RuntimeError, match="MOCK_GATEWAY_FORBIDDEN_IN_REAL_VALIDATION"):
            _ = MockNarrativeMemoryGateway(scenes=[], events=[], facts=[])
    finally:
        os.environ["REAL_INTEGRATION_VALIDATION"] = "false"
