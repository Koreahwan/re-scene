"""
Reframe V7 MCP Telemetry & Tool Invariant Tracking
Enforces transport distinction, call IDs, and success/failure logging.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class McpInvocation(BaseModel):
    call_id: str = Field(default_factory=lambda: f"mcp-call-{uuid.uuid4().hex[:12]}")
    analysis_run_id: str
    phase: str  # candidate_retrieval, character_state, anomaly_retrieval, event_evidence, fact_evidence, graph_expansion, motif_retrieval
    tool_name: str = "run_query"
    transport: str = "official-mcp-fastmcp"  # official-mcp-fastmcp or test-adapter-mock
    exact_query: str
    safe_parameters: Dict[str, Any] = Field(default_factory=dict)
    latency_ms: float
    returned_rows: int
    success: bool = True
    error_message: Optional[str] = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)


class TelemetryLedger:
    def __init__(self):
        self._history: List[McpInvocation] = []

    def record(self, invocation: McpInvocation):
        self._history.append(invocation)

    def get_run_invocations(self, analysis_run_id: str) -> List[McpInvocation]:
        return [inv for inv in self._history if inv.analysis_run_id == analysis_run_id]

    def clear(self):
        self._history.clear()


telemetry_ledger = TelemetryLedger()
