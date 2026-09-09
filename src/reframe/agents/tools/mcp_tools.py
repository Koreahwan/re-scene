"""
Reframe V7 Official MCP Tool Adapters for Google ADK
Enforces fail-closed execution against official mcp-clickhouse run_query tool.
All parameters validated against server-owned CatalogRegistry.
Zero Paid Model Calls.
"""
import os
import time
import json
import hashlib
import asyncio
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException
from src.reframe.agents.telemetry import McpInvocation, telemetry_ledger
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.evidence.catalog_registry import catalog_registry
from src.reframe.mcp.adapter import McpEvidenceResult

logger = structlog.get_logger(__name__)


def _parse_mcp_tabular_result(raw_result: Any) -> List[Dict[str, Any]]:
    if raw_result is None:
        return []
    if hasattr(raw_result, "content") and isinstance(raw_result.content, list):
        for item in raw_result.content:
            if hasattr(item, "text"):
                return _parse_mcp_tabular_result(item.text)
    if isinstance(raw_result, str):
        try:
            parsed = json.loads(raw_result)
        except Exception:
            return []
    elif isinstance(raw_result, (dict, list)):
        parsed = raw_result
    else:
        return []

    if isinstance(parsed, dict):
        if "columns" in parsed and "rows" in parsed:
            cols = parsed["columns"]
            return [dict(zip(cols, row)) for row in parsed["rows"]]
        if "data" in parsed and isinstance(parsed["data"], list):
            return parsed["data"]
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    return []


async def execute_mcp_query(
    query: str,
    phase: str,
    analysis_run_id: str,
    timeout_seconds: float = 0.5,
    allow_mock_fallback: bool = False
) -> List[Dict[str, Any]]:
    """
    Executes a query strictly via official mcp-clickhouse run_query tool.
    Fails closed in production if MCP server is unreachable.
    """
    clean_query = query.strip().rstrip(";")
    t0 = time.perf_counter()
    started_at = datetime.now(timezone.utc)

    # SQL Injection and DDL/DML Protection (R4-03)
    upper_query = clean_query.upper()
    if ";" in clean_query or "--" in clean_query or "/*" in clean_query or any(tok in upper_query for tok in ["DROP ", "INSERT ", "DELETE ", "UPDATE ", "ALTER ", "TRUNCATE ", "UNION "]):
        raise ValueError("MCP_QUERY_REJECTED: SQL injection token or disallowed keyword detected in MCP query.")


    # Configure read-only environment for official mcp-clickhouse
    os.environ["CLICKHOUSE_HOST"] = settings.CLICKHOUSE_HOST
    os.environ["CLICKHOUSE_PORT"] = str(settings.CLICKHOUSE_PORT)
    os.environ["CLICKHOUSE_USER"] = settings.CLICKHOUSE_USER
    os.environ["CLICKHOUSE_PASSWORD"] = settings.CLICKHOUSE_PASSWORD
    os.environ["CLICKHOUSE_DATABASE"] = settings.CLICKHOUSE_DATABASE
    os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "false"

    rows: List[Dict[str, Any]] = []
    transport = "official-mcp-fastmcp"
    success = True
    error_msg: Optional[str] = None

    try:
        from fastmcp import Client
        from mcp_clickhouse.mcp_server import mcp as official_mcp_server

        async with Client(official_mcp_server) as client:
            raw_result = await asyncio.wait_for(
                client.call_tool("run_query", {"query": clean_query}),
                timeout=timeout_seconds,
            )
            rows = _parse_mcp_tabular_result(raw_result)
    except Exception as e:
        error_msg = str(e)
        logger.debug("Official MCP execution failed", phase=phase, error=error_msg)

        # In production, MCP failure MUST fail closed
        if settings.ENVIRONMENT == "production" and not allow_mock_fallback:
            success = False
            elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
            telemetry_ledger.record(
                McpInvocation(
                    analysis_run_id=analysis_run_id,
                    phase=phase,
                    tool_name="run_query",
                    transport="official-mcp-fastmcp",
                    exact_query=clean_query,
                    safe_parameters={"phase": phase},
                    latency_ms=elapsed_ms,
                    returned_rows=0,
                    success=False,
                    error_message=error_msg,
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc)
                )
            )
            raise ReframeException(
                status_code=503,
                code="MCP_UNAVAILABLE",
                message=f"Official MCP ClickHouse tool unavailable during phase '{phase}': {error_msg}"
            )

        # In non-production/test mode, fall back to test adapter only under explicit label
        transport = "test-adapter-mock"
        if "FROM scenes" in clean_query or "FROM reframe.scenes" in clean_query:
            rows = [{"scene_id": s.scene_id, "start_ms": s.start_ms, "end_ms": s.end_ms, "summary": s.summary, "characters": s.characters, "objects": s.objects} for s in v3_adapter.get_scenes()]
        elif "FROM events" in clean_query or "FROM reframe.events" in clean_query:
            rows = [{"event_id": ev.event_id, "scene_id": ev.scene_id, "timestamp_ms": ev.timestamp_ms, "actor": ev.actor, "action": ev.action, "description": ev.description} for ev in v3_adapter.get_events()]
        elif "FROM facts" in clean_query or "FROM reframe.facts" in clean_query:
            rows = [{"fact_id": f.fact_id, "scene_id": f.scene_id, "timestamp_ms": f.timestamp_ms, "subject": f.subject, "predicate": f.predicate, "object": f.object} for f in v3_adapter.get_facts()]
        elif "FROM knowledge_states" in clean_query or "FROM reframe.knowledge_states" in clean_query:
            export_ks = []
            try:
                if v3_adapter.v3_export_path.exists():
                    with open(v3_adapter.v3_export_path, "r", encoding="utf-8") as f:
                        exp_data = json.load(f)
                    export_ks = exp_data.get("knowledge_states", [])
            except Exception:
                export_ks = []
            rows = [
                {
                    "knowledge_id": ks.get("state_id", ks.get("knowledge_id", f"ks-{i}")),
                    "subject": ks.get("entity", ks.get("subject", "")),
                    "predicate": ks.get("predicate", "believes"),
                    "object": ks.get("believed_fact", ks.get("object", "")),
                    "status": ks.get("status", "INFERRED"),
                    "valid_from_ms": ks.get("timestamp_ms", ks.get("valid_from_ms", 0)),
                    "valid_until_ms": ks.get("valid_until_ms"),
                    "source_scene_id": ks.get("grounded_chunk_id", ks.get("source_scene_id", "")),
                    "confidence": ks.get("confidence", 0.90)
                }
                for i, ks in enumerate(export_ks)
            ]
        else:
            rows = []

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    completed_at = datetime.now(timezone.utc)

    # Record truthful telemetry
    invocation = McpInvocation(
        analysis_run_id=analysis_run_id,
        phase=phase,
        tool_name="run_query",
        transport=transport,
        exact_query=clean_query,
        safe_parameters={"phase": phase},
        latency_ms=elapsed_ms,
        returned_rows=len(rows),
        success=success,
        error_message=error_msg,
        started_at=started_at,
        completed_at=completed_at
    )
    telemetry_ledger.record(invocation)
    return rows


# ADK Callable Tools
async def retrieve_entity_evidence(
    work_id: str,
    edition_id: str,
    reveal_id: str,
    cutoff_ms: int,
    entity_names: List[str],
    analysis_run_id: str = "adk-run-001"
) -> List[Dict[str, Any]]:
    """
    ADK Tool: Retrieves evidence seeds for specific entities prior to cutoff_ms via official MCP.
    Validates work, edition, reveal, and canonical entities against CatalogRegistry.
    Fails closed on any unknown identifier or SQL injection attempt.
    """
    # 1. Server Catalog Validation (R4-03)
    catalog_registry.require_work(work_id)
    catalog_registry.require_edition(work_id, edition_id)
    catalog_registry.require_reveal(work_id, reveal_id)
    validated_entities = catalog_registry.validate_entities(work_id, entity_names)

    # 2. Deterministic Template Query Generation (R4-03)
    safe_cutoff = int(cutoff_ms)
    query = f"""
    SELECT scene_id, start_ms, end_ms, summary, characters, objects
    FROM reframe.scenes
    WHERE movie_id = '{work_id}' AND start_ms < {safe_cutoff}
    ORDER BY start_ms ASC
    """
    raw_rows = await execute_mcp_query(
        query,
        phase="candidate_retrieval",
        analysis_run_id=analysis_run_id,
        allow_mock_fallback=settings.ENVIRONMENT != "production"
    )

    filtered = []
    for r in raw_rows:
        if int(r.get("start_ms", 0)) < safe_cutoff:
            chars = r.get("characters", [])
            objs = r.get("objects", [])
            if any(e in chars or e in objs for e in validated_entities):
                filtered.append(r)
    return filtered[:10]


async def retrieve_character_states(
    character_name: str,
    cutoff_ms: int,
    work_id: str = "the-bat-whispers-1930",
    analysis_run_id: str = "adk-run-001"
) -> List[Dict[str, Any]]:
    """
    ADK Tool: Retrieves character epistemic states prior to cutoff_ms via official MCP.
    Validates character_name against CatalogRegistry before query building.
    Fails closed on injection tokens, comment syntax, wildcards, or unknown entities.
    """
    # Reject dangerous SQL characters
    forbidden_tokens = ["'", '"', ";", "--", "/*", "*/", "%", "_", "UNION", "SELECT", "DROP", "INSERT", "DELETE"]
    if any(tok in character_name.upper() for tok in forbidden_tokens):
        logger.error("mcp_query_injection_attempt_blocked", character_name=character_name)
        raise ValueError(f"DANGEROUS_MCP_QUERY_INPUT: Character name contains forbidden tokens: {character_name}")

    # Server Catalog Entity Validation (R4-03)
    validated_entities = catalog_registry.validate_entities(work_id, [character_name.strip()])
    canonical_char = validated_entities[0]

    safe_cutoff = int(cutoff_ms)
    query = f"SELECT knowledge_id, subject, predicate, object, status, valid_from_ms, valid_until_ms, source_scene_id, confidence FROM reframe.knowledge_states WHERE movie_id = '{work_id}' AND subject = '{canonical_char}' AND valid_from_ms < {safe_cutoff} ORDER BY valid_from_ms ASC"

    mcp_rows = await execute_mcp_query(
        query,
        phase="character_state",
        analysis_run_id=analysis_run_id,
        allow_mock_fallback=settings.ENVIRONMENT != "production"
    )

    # Filter to ensure cutoff guarantee and return typed epistemic rows
    filtered = []
    for r in mcp_rows:
        ts = int(r.get("valid_from_ms", r.get("timestamp_ms", 0)))
        if ts < safe_cutoff:
            row_dict = dict(r)
            row_dict["source_table"] = "knowledge_states"
            filtered.append(row_dict)
    return filtered[:10]


async def retrieve_narrative_evidence(
    work_id: str,
    edition_id: str,
    reveal_id: str,
    cutoff_ms: int,
    analysis_run_id: str = "adk-run-001"
) -> List[Dict[str, Any]]:
    """
    ADK Tool: Executes the complete 5-channel narrative retrieval program (ENTITY, KNOWLEDGE_CONFLICT,
    CLAIM_ACTION, ACCESS_OPPORTUNITY, PLAN_CAUSAL) strictly via official mcp-clickhouse run_query tool.
    Validates work, edition, and reveal against CatalogRegistry.
    Returns structured evidence seeds.
    """
    from src.reframe.mcp.program import narrative_mcp_program
    mcp_results, seeds = await narrative_mcp_program.execute_program(
        work_id=work_id,
        edition_id=edition_id,
        reveal_id=reveal_id,
        cutoff_ms=cutoff_ms,
        analysis_run_id=analysis_run_id
    )
    return [seed.model_dump() for seed in seeds]


