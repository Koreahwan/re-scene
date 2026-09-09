"""
Reframe V7 Cost Guards & Token Budget Enforcement Unit Tests (Zero Paid Calls)
"""
import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import BudgetExceededException
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.cost.pricing import pricing_registry, PricingConfigException
from src.reframe.cost.service import cost_service


def test_default_cost_settings_are_zero_call():
    """Default settings must fail-closed and disable paid model calls out of the box."""
    assert settings.PAID_CALLS_ENABLED is False, "PAID_CALLS_ENABLED must default to False"
    assert settings.SPEND_KILL_SWITCH_ACTIVE is True, "SPEND_KILL_SWITCH_ACTIVE must default to True"
    assert settings.LIVE_AGENT_ENABLED is False, "LIVE_AGENT_ENABLED must default to False"
    assert settings.LIVE_EVAL_ENABLED is False, "LIVE_EVAL_ENABLED must default to False"
    assert settings.LEGACY_PAID_PATH_ENABLED is False, "LEGACY_PAID_PATH_ENABLED must default to False"


def test_pricing_registry_known_and_unknown_models():
    """Pricing registry must return verified rates for approved models and fail-closed on unknown models."""
    # Approved models
    cost_25, ver_25 = pricing_registry.calculate_estimated_cost_micros(
        model_id="gemini-2.5-flash",
        input_text_tokens=1000,
        output_tokens=500
    )
    assert cost_25 > 0
    assert "gemini-2.5" in ver_25

    cost_36, ver_36 = pricing_registry.calculate_estimated_cost_micros(
        model_id="gemini-3.6-flash",
        input_text_tokens=1000,
        output_tokens=500
    )
    assert cost_36 > cost_25  # Gemini 3.6 rates are higher

    # Unknown model must fail closed
    with pytest.raises(PricingConfigException):
        pricing_registry.get_pricing("unapproved-model")


@pytest.mark.asyncio
async def test_budget_preflight_blocks_when_spend_kill_switch_active():
    """Preflight check must raise BudgetExceededException when kill switch is active."""
    async with AsyncSessionLocal() as db:
        with pytest.raises(BudgetExceededException) as exc_info:
            await cost_service.check_budget_preflight(db=db)
        assert "kill switch" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_budget_preflight_blocks_when_paid_calls_disabled(monkeypatch):
    """Preflight check must raise BudgetExceededException when paid calls are disabled even if kill switch is deactivated."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", False)

    async with AsyncSessionLocal() as db:
        with pytest.raises(BudgetExceededException) as exc_info:
            await cost_service.check_budget_preflight(db=db)
        assert "disabled" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_budget_reservation_overrun_raises_and_blocks(monkeypatch):
    """Recording usage that exceeds run reservation must raise BudgetExceededException."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    run_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        # Reserve a tiny budget of 100 micros ($0.0001)
        await cost_service.reserve_budget(db=db, analysis_run_id=run_id, reserved_micros=100)

        # Record huge usage that exceeds 100 micros
        with pytest.raises(BudgetExceededException) as exc_info:
            await cost_service.record_usage(
                db=db,
                analysis_run_id=run_id,
                model_call_id=f"call-{uuid.uuid4().hex}",
                model_id="gemini-2.5-flash",
                purpose="HYPOTHESIS",
                input_text_tokens=50000,
                output_tokens=10000
            )
        assert "budget exceeded" in str(exc_info.value.message).lower()


@pytest.mark.asyncio
async def test_duplicate_model_call_id_deduplication(monkeypatch):
    """Submitting the same model_call_id must not double count token charges."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    run_id = uuid.uuid4()
    call_id = f"call-dedupe-{uuid.uuid4().hex[:8]}"

    async with AsyncSessionLocal() as db:
        await cost_service.reserve_budget(db=db, analysis_run_id=run_id, reserved_micros=500_000)

        # First recording
        rec1 = await cost_service.record_usage(
            db=db,
            analysis_run_id=run_id,
            model_call_id=call_id,
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=100,
            output_tokens=50
        )
        assert rec1 is not None

        # Duplicate recording with same model_call_id
        rec2 = await cost_service.record_usage(
            db=db,
            analysis_run_id=run_id,
            model_call_id=call_id,
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=100,
            output_tokens=50
        )
        assert rec2.id == rec1.id, "Duplicate model_call_id should return existing record"


@pytest.mark.asyncio
async def test_campaign_cumulative_spend_freeze_and_hard_ceiling(monkeypatch):
    """Cumulative spend across the entire campaign must freeze at $0.80 and hard-fail at $1.00."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    import src.reframe.identity.models
    import src.reframe.jobs.models
    from src.reframe.cost.models import UsageLedger

    async with AsyncSessionLocal() as db:
        # 1. Below freeze: 700_000 micros ($0.70)
        ledger_70 = UsageLedger(
            id=uuid.uuid4(),
            model_call_id=f"call-{uuid.uuid4().hex[:8]}",
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=1000,
            output_tokens=1000,
            total_tokens=2000,
            estimated_cost_micros=700_000
        )
        db.add(ledger_70)
        await db.flush()

        # Reservation that pushes over $0.80 freeze must fail
        with pytest.raises(BudgetExceededException) as exc_freeze:
            await cost_service.reserve_budget(db=db, analysis_run_id=uuid.uuid4(), reserved_micros=150_000)
        assert "0.80" in str(exc_freeze.value.message)

        # 2. Add ledger pushing past $0.80 freeze threshold
        ledger_freeze = UsageLedger(
            id=uuid.uuid4(),
            model_call_id=f"call-{uuid.uuid4().hex[:8]}",
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=1000,
            output_tokens=1000,
            total_tokens=2000,
            estimated_cost_micros=150_000
        )
        db.add(ledger_freeze)
        await db.flush()

        # Preflight must fail on $0.80 freeze limit
        with pytest.raises(BudgetExceededException) as exc_preflight:
            await cost_service.check_budget_preflight(db=db)
        assert "0.80" in str(exc_preflight.value.message)

        # 3. Add ledger pushing past $1.00 hard limit (total: 700k + 150k + 200k = 1.05M micros)
        ledger_hard = UsageLedger(
            id=uuid.uuid4(),
            model_call_id=f"call-{uuid.uuid4().hex[:8]}",
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=1000,
            output_tokens=1000,
            total_tokens=2000,
            estimated_cost_micros=200_000
        )
        db.add(ledger_hard)
        await db.flush()

        with pytest.raises(BudgetExceededException) as exc_hard:
            await cost_service.check_budget_preflight(db=db)
        assert "1.00" in str(exc_hard.value.message)

        await db.rollback()


@pytest.mark.asyncio
async def test_budget_cancellation_releases_liability(monkeypatch):
    """Cancelling a failed or abandoned run releases its reservation, unblocking new runs."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    import src.reframe.jobs.models
    from src.reframe.jobs.models import AnalysisRun

    async with AsyncSessionLocal() as db:
        run1 = AnalysisRun(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            input_hash="hash1",
            config_hash="conf1",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="p1"
        )
        run2 = AnalysisRun(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            input_hash="hash2",
            config_hash="conf2",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="p2"
        )
        db.add_all([run1, run2])
        await db.flush()

        # Reserve 500,000 micros on run1
        await cost_service.reserve_budget(db=db, analysis_run_id=run1.id, reserved_micros=500_000)

        # Attempting to reserve 400,000 on run2 would push to 900,000 (> 800,000 freeze limit)
        with pytest.raises(BudgetExceededException) as exc:
            await cost_service.reserve_budget(db=db, analysis_run_id=run2.id, reserved_micros=400_000)
        assert "0.80" in str(exc.value.message)

        # Cancel run1 reservation (e.g. run aborted or failed)
        await cost_service.cancel_reservation(db=db, analysis_run_id=run1.id)

        # Now reserving 400,000 on run2 must succeed because liability was released
        res2 = await cost_service.reserve_budget(db=db, analysis_run_id=run2.id, reserved_micros=400_000)
        assert res2.status == "ACTIVE"
        assert res2.reserved_micros == 400_000

        await db.rollback()


@pytest.mark.asyncio
async def test_budget_settlement_avoids_double_counting(monkeypatch):
    """Settling a reservation converts active liability to recorded ledger without double counting."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    from src.reframe.jobs.models import AnalysisRun

    async with AsyncSessionLocal() as db:
        run = AnalysisRun(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            input_hash="h1",
            config_hash="c1",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="pr1"
        )
        db.add(run)
        await db.flush()

        # 1. Reserve 500k
        await cost_service.reserve_budget(db=db, analysis_run_id=run.id, reserved_micros=500_000)

        # 2. Record 150k usage
        await cost_service.record_usage(
            db=db,
            analysis_run_id=run.id,
            model_call_id=f"call-settle-{uuid.uuid4().hex[:8]}",
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=1000,
            output_tokens=1000
        )

        # Total liability is still bounded: settled (approx 375 micros) + active remainder
        total_during = await cost_service.get_campaign_total_liability(db)
        assert total_during == 500_000, f"Expected total liability to remain 500,000 during run, got {total_during}"

        # 3. Settle reservation
        await cost_service.settle_reservation(db=db, analysis_run_id=run.id)

        # After settlement, active liability drops to 0, only actual consumed ledger remains
        total_after = await cost_service.get_campaign_total_liability(db)
        assert total_after < 500_000, f"Expected post-settlement liability to reflect only actual spend, got {total_after}"

        await db.rollback()


@pytest.mark.asyncio
async def test_date_change_resets_daily_spend_while_campaign_liability_persists(monkeypatch):
    """Yesterday's spend counts toward campaign-wide cap but does not exhaust today's daily limit."""
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    from datetime import datetime, timezone, timedelta
    from src.reframe.cost.models import UsageLedger

    yesterday = datetime.now(timezone.utc) - timedelta(days=2)

    async with AsyncSessionLocal() as db:
        # Create a ledger from 2 days ago of 500,000 micros
        old_ledger = UsageLedger(
            id=uuid.uuid4(),
            model_call_id=f"call-old-{uuid.uuid4().hex[:8]}",
            model_id="gemini-2.5-flash",
            purpose="HYPOTHESIS",
            input_text_tokens=1000,
            output_tokens=1000,
            total_tokens=2000,
            estimated_cost_micros=500_000,
            created_at=yesterday
        )
        db.add(old_ledger)
        await db.flush()

        # Campaign liability must include the old ledger (500k total)
        total_campaign = await cost_service.get_campaign_total_liability(db)
        assert total_campaign == 500_000

        # Reserving 350,000 micros must fail campaign freeze limit (500k + 350k = 850k > 800k)
        with pytest.raises(BudgetExceededException) as exc:
            await cost_service.reserve_budget(db=db, analysis_run_id=uuid.uuid4(), reserved_micros=350_000)
        assert "0.80" in str(exc.value.message)

        await db.rollback()


