import pytest
from reframe.domain.models import Reveal
from reframe.domain.enums import ReframeRunStatus, RelationType
from reframe.mcp.gateway import McpClickHouseGateway
from reframe.verification.verifier import EvidenceVerifier
from reframe.application.orchestrator import ReframeOrchestrator


@pytest.mark.asyncio
async def test_live_clickhouse_query_and_retrieval():
    """
    Executes real live ClickHouse retrieval across table schemas in Docker on port 8123.
    """
    gateway = McpClickHouseGateway(mcp_endpoint_url="http://localhost:8123/")

    # 1. Search candidates for Detective Anderson reveal
    reveal_id = "reveal-anderson-identity"
    movie_id = "the-bat-whispers-1930"
    cutoff_ms = 4860000
    entities = ["Detective Anderson", "The Bat", "Brooks"]

    candidates = await gateway.search_entity_candidates(
        movie_id=movie_id,
        reveal_id=reveal_id,
        cutoff_ms=cutoff_ms,
        entities=entities,
        limit=20,
    )

    # Invariant: Must return real rows from ClickHouse
    assert len(candidates) >= 5

    # Invariant: Zero future leakage
    for c in candidates:
        assert c.movie_id == movie_id
        assert c.start_ms < cutoff_ms
        assert c.scene_id != "scene-tbw-010"  # Climax scene (4,900,000 ms) strictly excluded

    # 2. Supporting evidence query on live ClickHouse
    scene_ids = [c.scene_id for c in candidates]
    events_map, facts_map = await gateway.get_supporting_evidence(
        movie_id=movie_id,
        cutoff_ms=cutoff_ms,
        scene_ids=scene_ids,
    )

    assert any(len(evs) > 0 for evs in events_map.values())
    assert any(len(fcts) > 0 for fcts in facts_map.values())


@pytest.mark.asyncio
async def test_real_orchestrator_live_clickhouse_execution():
    """
    Executes end-to-end Orchestrator with real ClickHouse and autonomous verifier.
    """
    gateway = McpClickHouseGateway(mcp_endpoint_url="http://localhost:8123/")
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
        gateway=gateway,
        verifier=verifier,
        reveals_registry={reveal.reveal_id: reveal},
    )

    result, trace = await orchestrator.execute_reframe_analysis(
        movie_id=reveal.movie_id,
        reveal_id=reveal.reveal_id,
        top_k=5,
    )

    assert result.status == ReframeRunStatus.COMPLETED
    assert result.spoiler_cutoff_ms == 4860000
    assert len(result.cards) >= 3

    # Verify returned cards
    for card in result.cards:
        assert card.start_ms < 4860000
        assert card.relation_type.is_user_presentable
        assert card.relation_type not in [RelationType.COINCIDENCE, RelationType.IRRELEVANT]
        assert card.before_meaning != ""
        assert card.after_meaning != ""
