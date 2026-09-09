"""
Unit Tests for R3-01: Real Google ADK Execution Gateway & Lifecycle Wiring
Proves Agent + Tools + Session + Runner lifecycle wiring without paid model calls.
Zero Paid Model Calls.
"""
import pytest
import google.adk as adk
from google.adk.sessions import InMemorySessionService

from src.reframe.shared.config import settings
from src.reframe.agents.root_agent import reframe_root_agent
from src.reframe.agents.adk_gateway import (
    OfflineAdkExecutionGateway,
    LiveGoogleAdkExecutionGateway,
    get_adk_execution_gateway,
    AdkExecutionResult
)
from src.reframe.agents.roles import ExecutionMode


def test_adk_root_agent_and_tools_discovery():
    """Verify reframe_root_agent is an official google.adk.Agent with registered MCP tools."""
    assert isinstance(reframe_root_agent, adk.Agent)
    assert reframe_root_agent.name == "reframe_root_agent"
    tools = getattr(reframe_root_agent, "tools", None)
    assert tools is not None
    tool_names = [getattr(t, "__name__", str(t)) for t in tools]
    assert "retrieve_entity_evidence" in tool_names
    assert "retrieve_character_states" in tool_names



def test_offline_adk_gateway_runner_and_session_lifecycle():
    """Verify OfflineAdkExecutionGateway creates genuine ADK Runner and SessionService."""
    gw = OfflineAdkExecutionGateway()
    assert isinstance(gw.runner, adk.Runner)
    assert isinstance(gw.session_service, InMemorySessionService)
    assert gw.runner.agent.name in ("reframe_offline_root_agent", "reframe_root_agent")


@pytest.mark.asyncio
async def test_offline_adk_gateway_run_analysis_zero_network_calls():
    """Verify offline ADK analysis executes with 0 paid model calls and structured output."""
    gw = OfflineAdkExecutionGateway()
    result = await gw.run_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="test-r3-adk-01"
    )

    assert isinstance(result, AdkExecutionResult)
    assert result.status in ("COMPLETED", "ABSTAINED")
    assert result.reveal_id == "reveal-anderson-identity"
    assert result.execution_mode == ExecutionMode.OFFLINE_FIXTURE
    assert len(result.hypotheses) >= 1
    assert len(result.telemetries) == 3
    for telem in result.telemetries:
        assert telem.paid_model_calls == 0
        assert telem.status == "SKIPPED_OFFLINE"


@pytest.mark.asyncio
async def test_live_adk_gateway_blocked_by_default_flags():
    """Verify LiveGoogleAdkExecutionGateway fails closed with PAID_CALL_ATTEMPTED under default flags."""
    gw = LiveGoogleAdkExecutionGateway()
    with pytest.raises(RuntimeError, match="PAID_CALL_ATTEMPTED"):
        await gw.run_analysis(
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            cutoff_ms=4860000,
            analysis_run_id="test-r3-adk-live-blocked"
        )

