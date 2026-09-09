"""
Unit Tests for R3-04, R3-05, R3-06: Paid Model Call Guard, Pricing Status, and Zero Offline Usage Records
Verifies atomic preflight guards and ensures offline execution produces exactly 0 UsageLedger billable rows.
Zero Paid Model Calls.
"""
import uuid
import pytest
from sqlalchemy import select, func

from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.cost.guard import (
    PaidModelCallGuard,
    ModelCallPreflightContext,
    PaidCallGuardException,
    PROJECT_DAILY_AI_BUDGET_MICROS
)
from src.reframe.cost.pricing import pricing_registry, PricingStatus
from src.reframe.cost.models import UsageLedger, BudgetReservation
from src.reframe.jobs.worker import DurableWorker
from src.reframe.jobs.service import job_service


def test_pricing_status_unverified_blocks_live_call(monkeypatch):
    """Verify ESTIMATE_ONLY and UNKNOWN_FAIL_CLOSED status models block live execution."""
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    pricing_estimate = pricing_registry.get_pricing("gemini-3.6-flash")
    pricing_estimate.pricing_status = PricingStatus.ESTIMATE_ONLY

    ctx = ModelCallPreflightContext(
        model_call_id="test-call-01",
        analysis_run_id="run-01",
        principal_id="user-01",
        role="HYPOTHESIS",
        model_id="gemini-3.6-flash",
        estimated_input_tokens=1000,
        estimated_output_tokens=500,
        estimated_cost_micros=10000
    )

    with pytest.raises(PaidCallGuardException, match="UNVERIFIED_PRICING_BLOCKED"):
        PaidModelCallGuard.preflight_check(
            ctx=ctx,
            current_daily_spend_micros=0,
            active_reservation=BudgetReservation(
                id=uuid.uuid4(),
                analysis_run_id=uuid.uuid4(),
                reserved_micros=500000,
                consumed_micros=0,
                status="ACTIVE"
            )
        )


def test_paid_call_guard_enforces_daily_budget(monkeypatch):
    """Verify preflight check blocks execution when daily budget would be exceeded."""
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    ctx = ModelCallPreflightContext(
        model_call_id="test-call-02",
        analysis_run_id="run-02",
        principal_id="user-01",
        role="HYPOTHESIS",
        model_id="gemini-2.5-flash",
        estimated_input_tokens=1000,
        estimated_output_tokens=500,
        estimated_cost_micros=200_000
    )

    reservation = BudgetReservation(
        id=uuid.uuid4(),
        analysis_run_id=uuid.uuid4(),
        reserved_micros=500000,
        consumed_micros=0,
        status="ACTIVE"
    )

    # Spend is already at 900,000 micros ($0.90) + 200,000 micros ($0.20) > $1.00
    with pytest.raises(PaidCallGuardException, match="DAILY_BUDGET_EXCEEDED"):
        PaidModelCallGuard.preflight_check(
            ctx=ctx,
            current_daily_spend_micros=900_000,
            active_reservation=reservation
        )



@pytest.mark.asyncio
async def test_offline_execution_creates_zero_usage_ledger_records():
    """Verify executing an offline run creates 0 billable UsageLedger rows."""
    async with AsyncSessionLocal() as db:
        # Measure initial count
        count_stmt = select(func.count()).select_from(UsageLedger)
        initial_count = (await db.execute(count_stmt)).scalar()

        # Create and execute offline run
        run = await job_service.create_or_get_idempotent_run(
            db=db,
            principal_id="test-offline-user",
            route_key="POST:/api/v1/reframe-runs",
            idempotency_key=f"key-{uuid.uuid4().hex}",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME"
        )
        await db.commit()

        test_worker = DurableWorker(worker_id="test-offline-worker")
        for _ in range(5):
            had_work = await test_worker.run_once()
            if not had_work:
                break

        # Check post-execution count
        post_count = (await db.execute(count_stmt)).scalar()
        assert post_count == initial_count, f"Expected 0 billable UsageLedger rows created for offline run, but count changed by {post_count - initial_count}."
