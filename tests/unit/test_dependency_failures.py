from unittest.mock import AsyncMock
import pytest
from reframe.domain.models import Reveal
from reframe.domain.enums import ReframeRunStatus, AbstainReason
from reframe.application.orchestrator import ReframeOrchestrator
from reframe.mcp.gateway import McpClickHouseGateway


@pytest.mark.asyncio
async def test_fail_closed_when_mcp_port_dead():
    """Verifies that if official MCP server is unreachable, system honestly returns ABSTAINED without fake fallback."""
    dead_gateway = McpClickHouseGateway()
    dead_gateway.search_entity_candidates = AsyncMock(side_effect=RuntimeError("Connection refused: MCP server offline"))
    
    reveal = Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=4860000,
        title="Detective Anderson is Unmasked as 'The Bat'",
        reveal_type="IDENTITY",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective Anderson is a dedicated police officer investigating the robbery.",
        revealed_fact="Detective Anderson is himself 'The Bat', the criminal mastermind.",
        affected_entities=["Detective Anderson", "The Bat"],
    )
    orchestrator = ReframeOrchestrator(
        gateway=dead_gateway,
        reveals_registry={reveal.reveal_id: reveal},
    )
    result, _ = await orchestrator.execute_reframe_analysis(
        movie_id=reveal.movie_id,
        reveal_id=reveal.reveal_id,
        top_k=5,
    )
    assert result.status == ReframeRunStatus.ABSTAINED
    assert result.abstain_reason == AbstainReason.MCP_UNAVAILABLE
    assert len(result.cards) == 0


@pytest.mark.asyncio
async def test_fail_closed_on_client_spoiler_tampering():
    """Verifies that if client attempts to pass spoiler cutoff overrides, request is blocked."""
    gateway = McpClickHouseGateway()
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
        affected_entities=["Detective Anderson"],
    )
    orchestrator = ReframeOrchestrator(
        gateway=gateway,
        reveals_registry={reveal.reveal_id: reveal},
    )
    result, _ = await orchestrator.execute_reframe_analysis(
        movie_id=reveal.movie_id,
        reveal_id=reveal.reveal_id,
        top_k=5,
        client_request_params={"spoiler_cutoff_ms": 99999999},  # Tamper attempt!
    )
    assert result.status == ReframeRunStatus.ABSTAINED
    assert result.abstain_reason == AbstainReason.SPOILER_GUARD_BLOCKED
    assert len(result.cards) == 0


@pytest.mark.asyncio
async def test_fail_closed_on_missing_reveal():
    """Verifies that if reveal is not registered, system returns ABSTAINED."""
    gateway = McpClickHouseGateway()
    orchestrator = ReframeOrchestrator(
        gateway=gateway,
        reveals_registry={},
    )
    result, _ = await orchestrator.execute_reframe_analysis(
        movie_id="the-bat-whispers-1930",
        reveal_id="non-existent-reveal",
        top_k=5,
    )
    assert result.status == ReframeRunStatus.ABSTAINED
    assert result.abstain_reason == AbstainReason.REVEAL_NOT_FOUND
    assert len(result.cards) == 0
