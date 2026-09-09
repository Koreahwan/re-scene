import pytest
from reframe.retrieval.queries import (
    get_entity_candidates_sql,
    get_events_for_scenes_sql,
    get_facts_for_scenes_sql,
    build_entity_query_params,
)
from reframe.mcp.gateway import McpClickHouseGateway


def test_query_template_generation():
    sql1 = get_entity_candidates_sql()
    assert "reframe.scenes" in sql1
    assert "start_ms < {cutoff_ms:UInt64}" in sql1

    sql2 = get_events_for_scenes_sql()
    assert "reframe.events" in sql2
    assert "timestamp_ms < {cutoff_ms:UInt64}" in sql2

    sql3 = get_facts_for_scenes_sql()
    assert "reframe.facts" in sql3
    assert "timestamp_ms < {cutoff_ms:UInt64}" in sql3

    params = build_entity_query_params(
        movie_id="tbw-1930",
        cutoff_ms=4800000,
        entities=["Detective Anderson", "The Bat"],
        limit=100,  # exceeds 50 cap
    )
    assert params["movie_id"] == "tbw-1930"
    assert params["cutoff_ms"] == 4800000
    assert params["limit"] == 50  # capped at 50


@pytest.mark.asyncio
async def test_mcp_query_malformed_handling():
    gateway = McpClickHouseGateway(mcp_endpoint_url="http://localhost:8123/", timeout_seconds=1.0)
    # Test invalid SQL execution fails gracefully
    with pytest.raises(Exception):
        await gateway.run_query("SELECT * FROM invalid_table_does_not_exist_123")
