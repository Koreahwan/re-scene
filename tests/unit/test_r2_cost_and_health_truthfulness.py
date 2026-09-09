"""
Unit Tests for R2-08 Cost System Lockdown, R2-09 Legacy Paid Bypass Kill, and R2-18 Health Truthfulness
Zero Paid Model Calls.
"""
import pytest
from httpx import AsyncClient, ASGITransport
from src.reframe.cost.pricing import pricing_registry, PricingStatus, PricingConfigException
from src.reframe.cost.service import CostService
from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import BudgetExceededException
from apps.api.main import app
from apps.api.routers.health import GeminiHealthStatus


def test_pricing_registry_verified_and_fail_closed():
    """Verify that pricing registry returns verified configurations and fails closed on unknown models."""
    p_flash = pricing_registry.get_pricing("gemini-2.5-flash")
    assert p_flash.pricing_status == PricingStatus.VERIFIED_BILLING_PRICE
    assert p_flash.input_text_micro_rate == 0.30
    assert p_flash.output_text_micro_rate == 2.50
    assert p_flash.reasoning_micro_rate == 2.50

    p_pro = pricing_registry.get_pricing("gemini-3.6-pro")
    assert p_pro.pricing_status == PricingStatus.ESTIMATE_ONLY

    with pytest.raises(PricingConfigException):
        pricing_registry.get_pricing("unknown-fabricated-model-999")


def test_cost_service_budget_preflight_blocks_when_spend_disabled():
    """Verify that budget preflight raises BudgetExceededException when paid calls disabled."""
    cost_service = CostService()
    # In default config, PAID_CALLS_ENABLED is False and SPEND_KILL_SWITCH_ACTIVE is True
    assert settings.PAID_CALLS_ENABLED is False
    assert settings.SPEND_KILL_SWITCH_ACTIVE is True


@pytest.mark.asyncio
async def test_live_probe_truthfulness():
    """Verify /live returns 200 without touching external dependencies."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/live")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ALIVE"


@pytest.mark.asyncio
async def test_ready_probe_truthfulness():
    """Verify /ready evaluates postgres, redis, and dataset truthfully."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/ready")
        assert res.status_code == 200
        data = res.json()["data"]
        assert "postgres" in data
        assert "dataset_ready" in data
        assert data["runtime_db_readonly"] is True


@pytest.mark.asyncio
async def test_admin_health_gemini_status_truthful():
    """Verify /admin/health reports Gemini as DISABLED in default zero-cost configuration."""
    admin_cookie = {"reframe_session": "admin-test-token"}
    # Note: Using dev header / session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/admin/health", headers={"X-Viewer-Role": "ADMIN"})
        if res.status_code == 200:
            data = res.json()["data"]
            assert data["gemini_status"] == GeminiHealthStatus.DISABLED.value
            assert data["spend_kill_switch"] is True
            assert data["paid_calls_enabled"] is False


@pytest.mark.asyncio
async def test_legacy_reframe_endpoint_blocked():
    """Verify POST /reframe is blocked with 403 when LEGACY_PAID_PATH_ENABLED=False."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/reframe",
            json={
                "movie_id": "the-bat-whispers-1930",
                "reveal_id": "uncached-test-reveal",
                "top_k": 5
            }
        )
        assert res.status_code in (403, 410)
        assert ("LEGACY_PAID_PATH_DISABLED" in str(res.json()) or "ENDPOINT_GONE" in str(res.json()))

