"""
Reframe V7 MCP Evidence Result & Seed Adapter (McpEvidenceSeedAdapter)
Guarantees official MCP ClickHouse rows become the actual production evidence source.
Zero Paid Model Calls.
"""
import uuid
import hashlib
import json
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import structlog

from src.reframe.narrative.channels import EvidenceSeed
from src.reframe.evidence.adapter import v3_adapter, compute_content_hash

logger = structlog.get_logger(__name__)


class McpEvidenceResult(BaseModel):
    """
    Carries complete provenance and raw row data returned from official mcp-clickhouse queries.
    """
    mcp_call_id: str = Field(default_factory=lambda: f"mcp-call-{uuid.uuid4().hex[:8]}")
    analysis_run_id: str
    phase: str = "RETRIEVAL"
    transport: str = "OFFICIAL_MCP_CLICKHOUSE_STDIO"
    query_hash: str
    dataset_version: str = "v3"
    cutoff_ms: int
    returned_row_hashes: List[str] = Field(default_factory=list)
    scene_ids: List[str] = Field(default_factory=list)
    event_ids: List[str] = Field(default_factory=list)
    fact_ids: List[str] = Field(default_factory=list)
    raw_rows: List[Dict[str, Any]] = Field(default_factory=list)
    query_text: str = ""


class McpEvidenceSeedAdapter:
    """
    Converts validated McpEvidenceResult objects from ClickHouse into typed EvidenceSeed instances.
    """
    @staticmethod
    def from_mcp_results(mcp_results: List[McpEvidenceResult]) -> List[EvidenceSeed]:
        seeds: List[EvidenceSeed] = []

        for res in mcp_results:
            # Extract scene_ids, event_ids, fact_ids from rows if not already populated
            scene_ids = list(res.scene_ids)
            event_ids = list(res.event_ids)
            fact_ids = list(res.fact_ids)
            hashes = list(res.returned_row_hashes)

            for row in res.raw_rows:
                sc_id = row.get("scene_id")
                if sc_id and sc_id not in scene_ids:
                    scene_ids.append(sc_id)

                ev_id = row.get("event_id")
                if ev_id and ev_id not in event_ids:
                    event_ids.append(ev_id)

                f_id = row.get("fact_id")
                if f_id and f_id not in fact_ids:
                    fact_ids.append(f_id)

                # Compute content hash for row
                row_hash = hashlib.sha256(json.dumps(row, sort_keys=True).encode("utf-8")).hexdigest()[:16]
                if row_hash not in hashes:
                    hashes.append(row_hash)

            seed = EvidenceSeed(
                source_call_id=res.mcp_call_id,
                phase=res.phase,
                dataset_version=res.dataset_version,
                channel_name="MCP_CLICKHOUSE_RETRIEVAL",
                scene_ids=scene_ids,
                event_ids=event_ids,
                fact_ids=fact_ids,
                evidence_hashes=hashes,
                cutoff_ms=res.cutoff_ms,
                salience_score=0.90,
                channel_rationale=f"Official MCP ClickHouse retrieval returning {len(res.raw_rows)} rows across {len(scene_ids)} scenes.",
                structured_payload={
                    "query_hash": res.query_hash,
                    "transport": res.transport,
                    "row_count": len(res.raw_rows),
                    "raw_rows": res.raw_rows,
                    "phase": res.phase
                }
            )
            seeds.append(seed)

        return seeds


mcp_seed_adapter = McpEvidenceSeedAdapter()
