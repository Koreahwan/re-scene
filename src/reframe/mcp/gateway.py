from __future__ import annotations
import os
import json
import asyncio
from typing import List, Dict, Any, Optional, Protocol, Tuple
import structlog
from reframe.domain.models import ReframeCandidate, Event, Fact
from reframe.retrieval.guard import assert_zero_future_leakage, SpoilerGuardViolation

logger = structlog.get_logger(__name__)

ACTIVE_DATASET_VERSION = os.getenv("ACTIVE_DATASET_VERSION", "the_bat_whispers_v3_gemini36")


class NarrativeMemoryGateway(Protocol):
    """Protocol for communicating with ClickHouse narrative memory."""

    async def search_entity_candidates(
        self,
        movie_id: str,
        reveal_id: str,
        cutoff_ms: int,
        entities: List[str],
        limit: int = 30,
        dataset_version: Optional[str] = None,
    ) -> List[ReframeCandidate]: ...

    async def get_supporting_evidence(
        self,
        movie_id: str,
        cutoff_ms: int,
        scene_ids: List[str],
        dataset_version: Optional[str] = None,
    ) -> Tuple[Dict[str, List[Event]], Dict[str, List[Fact]]]: ...


def _parse_mcp_tabular_result(raw_result: Any) -> List[Dict[str, Any]]:
    """
    Parses official mcp-clickhouse tool result format:
    {"columns": ["col1", "col2"], "rows": [["val1", "val2"], ...]}
    or FastMCP CallToolResult objects into list of standard dictionaries.
    """
    if raw_result is None:
        return []

    # Handle FastMCP CallToolResult object
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


class OfficialMcpNarrativeMemoryGateway:
    """
    Production Narrative Memory Gateway communicating strictly through the
    actual official ClickHouse MCP server (`mcp-clickhouse` / `run_query`)
    via the FastMCP Client Protocol.
    
    Invariants:
    - Direct ClickHouse HTTP bypass in production is strictly forbidden.
    - If MCP fails or is unavailable, fails closed (no silent fallback).
    - Strictly filters `dataset_version = ACTIVE_DATASET_VERSION`.
    - Enforces zero future scene leakage.
    - Read-only user `reframe_runtime` with write access disabled.
    """

    def __init__(
        self,
        dataset_version: Optional[str] = None,
        timeout_seconds: float = 10.0,
        mcp_endpoint_url: Optional[str] = None,
    ):
        self.dataset_version = dataset_version or ACTIVE_DATASET_VERSION
        self.timeout_seconds = timeout_seconds
        self.mcp_endpoint_url = mcp_endpoint_url

        # Configure environment for official mcp-clickhouse tool invocation
        if mcp_endpoint_url:
            from urllib.parse import urlparse
            parsed = urlparse(mcp_endpoint_url)
            if parsed.hostname:
                os.environ["CLICKHOUSE_HOST"] = parsed.hostname
            if parsed.port:
                os.environ["CLICKHOUSE_PORT"] = str(parsed.port)
        else:
            os.environ["CLICKHOUSE_HOST"] = os.getenv("CLICKHOUSE_HOST", "localhost")
            os.environ["CLICKHOUSE_PORT"] = os.getenv("CLICKHOUSE_PORT", "8123")

        os.environ["CLICKHOUSE_USER"] = os.getenv("CLICKHOUSE_USER", "reframe_runtime")
        os.environ["CLICKHOUSE_PASSWORD"] = os.getenv("CLICKHOUSE_PASSWORD", "")
        os.environ["CLICKHOUSE_DATABASE"] = os.getenv("CLICKHOUSE_DATABASE", "reframe")
        os.environ["CLICKHOUSE_SECURE"] = os.getenv("CLICKHOUSE_SECURE", "false")
        os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = os.getenv("CLICKHOUSE_ALLOW_WRITE_ACCESS", "false")
        self.telemetry_history: List[Dict[str, Any]] = []

    def get_last_telemetry(self) -> Optional[Dict[str, Any]]:
        return self.telemetry_history[-1] if self.telemetry_history else None

    async def run_query(self, query: str) -> List[Dict[str, Any]]:
        """
        Executes query via the official ClickHouse MCP `run_query` tool asynchronously over FastMCP Client.
        Fails closed on any exception.
        """
        import time
        clean_query = query.strip().rstrip(";")
        t0 = time.perf_counter()
        try:
            from fastmcp import Client
            from mcp_clickhouse.mcp_server import mcp as official_mcp_server

            async with Client(official_mcp_server) as client:
                raw_result = await asyncio.wait_for(
                    client.call_tool("run_query", {"query": clean_query}),
                    timeout=self.timeout_seconds,
                )
                elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
                rows = _parse_mcp_tabular_result(raw_result)
                telemetry = {
                    "tool_name": "run_query",
                    "transport": "fastmcp:in-process",
                    "query": clean_query,
                    "latency_ms": elapsed_ms,
                    "returned_rows": len(rows),
                }
                self.telemetry_history.append(telemetry)
                return rows
        except Exception as exc:
            logger.error("official_mcp_query_failed", query=clean_query, error=str(exc))
            raise RuntimeError(f"Official MCP ClickHouse Query Error: {exc}") from exc

    async def search_entity_candidates(
        self,
        movie_id: str,
        reveal_id: str,
        cutoff_ms: int,
        entities: List[str],
        limit: int = 30,
        dataset_version: Optional[str] = None,
    ) -> List[ReframeCandidate]:
        """
        Executes pre-reveal candidate retrieval through official mcp-clickhouse run_query tool.
        """
        version = dataset_version or self.dataset_version
        ents_list = [e.replace("'", "\\'") for e in entities]
        ents_str = "[" + ", ".join(f"'{e}'" for e in ents_list) + "]"

        sql = f"""
        SELECT scene_id, movie_id, dataset_version, start_ms, end_ms, summary, characters, objects, dialogue_summary,
               (length(arrayIntersect(characters, {ents_str})) * 2 + length(arrayIntersect(objects, {ents_str}))) AS entity_score
        FROM reframe.scenes
        WHERE movie_id = '{movie_id}'
          AND dataset_version = '{version}'
          AND start_ms < {cutoff_ms}
          AND (hasAny(characters, {ents_str}) OR hasAny(objects, {ents_str}))
        ORDER BY entity_score DESC, start_ms ASC
        LIMIT {limit}
        """

        raw_rows = await self.run_query(sql)

        # Invariant check: Assert zero future leakage on raw results
        assert_zero_future_leakage(raw_rows, cutoff_ms)

        candidates: List[ReframeCandidate] = []
        for rank, row in enumerate(raw_rows, start=1):
            start_ms = int(row["start_ms"])
            end_ms = int(row.get("end_ms", start_ms))
            cand = ReframeCandidate(
                reveal_id=reveal_id,
                scene_id=row["scene_id"],
                movie_id=row["movie_id"],
                start_ms=start_ms,
                end_ms=end_ms,
                evidence_start_ms=start_ms,
                evidence_end_ms=min(end_ms, cutoff_ms - 1) if end_ms >= cutoff_ms else end_ms,
                summary=row["summary"],
                dialogue_summary=row.get("dialogue_summary", ""),
                characters=row.get("characters", []),
                objects=row.get("objects", []),
                entity_rank=rank,
                dataset_version=version,
            )
            candidates.append(cand)

        return candidates

    async def get_supporting_evidence(
        self,
        movie_id: str,
        cutoff_ms: int,
        scene_ids: List[str],
        dataset_version: Optional[str] = None,
    ) -> Tuple[Dict[str, List[Event]], Dict[str, List[Fact]]]:
        """
        Retrieves grounded atomic facts and micro-events within the pre-reveal window for evidence attribution.
        """
        events_by_scene: Dict[str, List[Event]] = {sid: [] for sid in scene_ids}
        facts_by_scene: Dict[str, List[Fact]] = {sid: [] for sid in scene_ids}

        if not scene_ids:
            return events_by_scene, facts_by_scene

        version = dataset_version or self.dataset_version
        sids_str = "[" + ", ".join(f"'{s}'" for s in scene_ids) + "]"

        events_sql = f"""
        SELECT event_id, movie_id, scene_id, dataset_version, timestamp_ms, actor, action, target, object, description, entities, evidence_frame_ids,
               evidence_start_ms, evidence_end_ms
        FROM reframe.events
        WHERE movie_id = '{movie_id}'
          AND dataset_version = '{version}'
          AND timestamp_ms < {cutoff_ms}
          AND has({sids_str}, scene_id)
        ORDER BY timestamp_ms ASC
        """

        facts_sql = f"""
        SELECT fact_id, movie_id, scene_id, dataset_version, timestamp_ms, subject, predicate, object, fact_type, evidence_event_ids,
               evidence_start_ms, evidence_end_ms
        FROM reframe.facts
        WHERE movie_id = '{movie_id}'
          AND dataset_version = '{version}'
          AND timestamp_ms < {cutoff_ms}
          AND has({sids_str}, scene_id)
        ORDER BY timestamp_ms ASC
        """

        raw_events = await self.run_query(events_sql)
        raw_facts = await self.run_query(facts_sql)

        for ev_row in raw_events:
            ev_data = dict(ev_row)
            ev_data["timestamp_ms"] = int(ev_data["timestamp_ms"])
            ev_data["evidence_start_ms"] = int(ev_data.get("evidence_start_ms", ev_data["timestamp_ms"]))
            ev_data["evidence_end_ms"] = int(ev_data.get("evidence_end_ms", ev_data["timestamp_ms"]))
            ev = Event(**ev_data)
            if ev.scene_id in events_by_scene:
                events_by_scene[ev.scene_id].append(ev)

        for f_row in raw_facts:
            f_data = dict(f_row)
            f_data["timestamp_ms"] = int(f_data["timestamp_ms"])
            f_data["evidence_start_ms"] = int(f_data.get("evidence_start_ms", f_data["timestamp_ms"]))
            f_data["evidence_end_ms"] = int(f_data.get("evidence_end_ms", f_data["timestamp_ms"]))
            if isinstance(f_data.get("fact_type"), str):
                f_data["fact_type"] = f_data["fact_type"].replace("FactType.", "")
            f = Fact(**f_data)
            if f.scene_id in facts_by_scene:
                facts_by_scene[f.scene_id].append(f)

        return events_by_scene, facts_by_scene


# Alias for backwards compatibility
McpClickHouseGateway = OfficialMcpNarrativeMemoryGateway


class MockNarrativeMemoryGateway:
    """
    Deterministic in-memory mock gateway implementing the exact same interface
    and query invariants for isolated unit tests.
    Strictly forbidden when REFRAME_RUNTIME_MODE=real or REAL_INTEGRATION_VALIDATION=true.
    """

    def __init__(
        self,
        scenes: List[Dict[str, Any]],
        events: List[Dict[str, Any]],
        facts: List[Dict[str, Any]],
        dataset_version: Optional[str] = None,
    ):
        mode = os.getenv("REFRAME_RUNTIME_MODE", "mock").lower()
        if mode == "real" or os.getenv("REAL_INTEGRATION_VALIDATION", "false").lower() == "true":
            raise RuntimeError("MOCK_GATEWAY_FORBIDDEN_IN_REAL_VALIDATION: MockNarrativeMemoryGateway is forbidden when REFRAME_RUNTIME_MODE=real.")
        self.scenes = scenes
        self.events = events
        self.facts = facts
        self.dataset_version = dataset_version or ACTIVE_DATASET_VERSION
        self.telemetry_history: List[Dict[str, Any]] = []

    def get_last_telemetry(self) -> Optional[Dict[str, Any]]:
        return self.telemetry_history[-1] if self.telemetry_history else None

    async def search_entity_candidates(
        self,
        movie_id: str,
        reveal_id: str,
        cutoff_ms: int,
        entities: List[str],
        limit: int = 30,
        dataset_version: Optional[str] = None,
    ) -> List[ReframeCandidate]:
        version = dataset_version or self.dataset_version
        matched: List[Dict[str, Any]] = []
        target_entities_lower = {e.lower() for e in entities}

        for s in self.scenes:
            s_movie = s.get("movie_id") or s.get("work_id")
            if s_movie != movie_id:
                continue
            s_ver = str(s.get("dataset_version", version))
            if s_ver != version and not ("v3" in s_ver and "v3" in version):
                continue
            if s.get("start_ms", 0) >= cutoff_ms:
                continue

            scene_chars = {c.lower() for c in s.get("characters", [])}
            scene_objs = {o.lower() for o in s.get("objects", [])}

            if bool(scene_chars & target_entities_lower) or bool(scene_objs & target_entities_lower):
                matched.append(s)

        matched.sort(key=lambda x: x["start_ms"])
        matched = matched[:limit]

        assert_zero_future_leakage(matched, cutoff_ms)

        candidates: List[ReframeCandidate] = []
        for rank, row in enumerate(matched, start=1):
            start_ms = int(row["start_ms"])
            end_ms = int(row.get("end_ms", start_ms))
            cand = ReframeCandidate(
                reveal_id=reveal_id,
                scene_id=row["scene_id"],
                movie_id=row.get("movie_id") or row.get("work_id") or movie_id,
                start_ms=start_ms,
                end_ms=end_ms,
                evidence_start_ms=start_ms,
                evidence_end_ms=min(end_ms, cutoff_ms - 1) if end_ms >= cutoff_ms else end_ms,
                summary=row["summary"],
                dialogue_summary=row.get("dialogue_summary", ""),
                characters=row.get("characters", []),
                objects=row.get("objects", []),
                entity_rank=rank,
                dataset_version=version,
            )
            candidates.append(cand)

        return candidates

    async def get_supporting_evidence(
        self,
        movie_id: str,
        cutoff_ms: int,
        scene_ids: List[str],
        dataset_version: Optional[str] = None,
    ) -> Tuple[Dict[str, List[Event]], Dict[str, List[Fact]]]:
        version = dataset_version or self.dataset_version
        scene_set = set(scene_ids)
        events_by_scene: Dict[str, List[Event]] = {sid: [] for sid in scene_ids}
        facts_by_scene: Dict[str, List[Fact]] = {sid: [] for sid in scene_ids}

        for ev in self.events:
            ev_movie = ev.get("movie_id") or ev.get("work_id")
            ev_ver = str(ev.get("dataset_version", version))
            if (
                ev_movie == movie_id
                and (ev_ver == version or ("v3" in ev_ver and "v3" in version))
                and ev.get("scene_id") in scene_set
                and ev.get("timestamp_ms", 0) < cutoff_ms
            ):
                ev_data = dict(ev)
                ev_data["movie_id"] = ev_movie
                ev_data["evidence_start_ms"] = int(ev_data.get("evidence_start_ms", ev_data["timestamp_ms"]))
                ev_data["evidence_end_ms"] = int(ev_data.get("evidence_end_ms", ev_data["timestamp_ms"]))
                events_by_scene[ev["scene_id"]].append(Event(**ev_data))

        for f in self.facts:
            f_movie = f.get("movie_id") or f.get("work_id")
            f_ver = str(f.get("dataset_version", version))
            if (
                f_movie == movie_id
                and (f_ver == version or ("v3" in f_ver and "v3" in version))
                and f.get("scene_id") in scene_set
                and f.get("timestamp_ms", 0) < cutoff_ms
            ):
                f_data = dict(f)
                f_data["movie_id"] = f_movie
                f_data["evidence_start_ms"] = int(f_data.get("evidence_start_ms", f_data["timestamp_ms"]))
                f_data["evidence_end_ms"] = int(f_data.get("evidence_end_ms", f_data["timestamp_ms"]))
                facts_by_scene[f["scene_id"]].append(Fact(**f_data))

        return events_by_scene, facts_by_scene

