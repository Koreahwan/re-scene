"""
Paid Live ADK Smoke Test (Isolated from Default Pytest Run)
This test file MUST NEVER run during default local or CI test suites.
It only executes when explicitly enabled via PAID_LIVE_TESTS_ENABLED=true and PAID_CALLS_ENABLED=true.
"""
import os
import pytest

PAID_LIVE_ENABLED = (
    os.getenv("PAID_LIVE_TESTS_ENABLED", "").lower() == "true" and
    os.getenv("PAID_CALLS_ENABLED", "").lower() == "true"
)

pytestmark = pytest.mark.skipif(
    not PAID_LIVE_ENABLED,
    reason="Paid live tests are skipped by default to ensure $0.00 spend. Set PAID_LIVE_TESTS_ENABLED=true to run."
)


@pytest.mark.asyncio
async def test_live_adk_agent_smoke():
    """Smoke test for live Google ADK runtime execution."""
    from src.reframe.agents.runtime import agent_runtime
    result = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="paid-live-smoke-test-01"
    )
    assert result is not None
    assert "status" in result
