"""
Reframe V7 Cost Guard & Token Usage Tracking Service
Enforces strict hard budget ceilings, pricing registry calculations, and fail-closed spend controls.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import BudgetExceededException
from src.reframe.cost.models import UsageLedger, BudgetReservation
from src.reframe.jobs.models import AnalysisRun
from src.reframe.cost.pricing import pricing_registry

logger = structlog.get_logger(__name__)


class CostService:
    @staticmethod
    def calculate_estimated_cost_micros(
        model_id: str,
        input_text_tokens: int,
        input_image_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_input_tokens: int = 0
    ) -> Tuple[int, str]:
        return pricing_registry.calculate_estimated_cost_micros(
            model_id=model_id,
            input_text_tokens=input_text_tokens,
            input_image_tokens=input_image_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens
        )

    async def get_campaign_total_liability(self, db: AsyncSession) -> int:
        """
        Calculate total campaign AI spend liability:
        Settled ledger costs + outstanding unconsumed balance of ACTIVE reservations.
        """
        ledger_stmt = select(func.coalesce(func.sum(UsageLedger.estimated_cost_micros), 0))
        ledger_res = await db.execute(ledger_stmt)
        settled_spend = ledger_res.scalar_one()

        active_res_stmt = select(
            func.coalesce(
                func.sum(BudgetReservation.reserved_micros - BudgetReservation.consumed_micros),
                0
            )
        ).where(
            and_(
                BudgetReservation.status == "ACTIVE",
                BudgetReservation.reserved_micros > BudgetReservation.consumed_micros
            )
        )
        active_res = await db.execute(active_res_stmt)
        active_liability = active_res.scalar_one()

        return int(settled_spend + active_liability)

    async def check_budget_preflight(
        self,
        db: AsyncSession,
        analysis_run_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        model_id: Optional[str] = None
    ) -> None:
        """
        Hard budget preflight validation:
        1. Global kill switch check
        2. Paid calls enabled flag
        3. Pricing registry check
        4. Run reservation check
        5. Daily project & user quota check
        6. Campaign cumulative liability check (settled + active reservations)
        """
        if settings.SPEND_KILL_SWITCH_ACTIVE:
            logger.error("Spend kill switch is active; rejecting model invocation")
            raise BudgetExceededException("Global AI spend kill switch is active. AI analysis temporarily suspended.")

        if not settings.PAID_CALLS_ENABLED:
            logger.error("Paid calls are disabled; rejecting model invocation")
            raise BudgetExceededException("Paid Gemini model calls are disabled in current environment.")

        if model_id:
            # Validates model exists in registry or fails closed
            pricing_registry.get_pricing(model_id)

        # Check Active Reservation for this run if provided
        if analysis_run_id:
            stmt = select(BudgetReservation).where(
                BudgetReservation.analysis_run_id == analysis_run_id,
                BudgetReservation.status == "ACTIVE"
            )
            res = await db.execute(stmt)
            reservation = res.scalar_one_or_none()
            if reservation and reservation.consumed_micros >= reservation.reserved_micros:
                logger.error(
                    "Analysis run budget reservation exhausted",
                    run_id=str(analysis_run_id),
                    consumed=reservation.consumed_micros,
                    reserved=reservation.reserved_micros
                )
                raise BudgetExceededException("Budget reservation for this analysis run has been exhausted.")

        # Check Campaign-wide Cumulative Budget (all ledgers across all time + active uncommitted reservations)
        campaign_total_spend = await self.get_campaign_total_liability(db)

        if campaign_total_spend >= settings.CAMPAIGN_BUDGET_MICROS:
            logger.error("Campaign-wide hard budget ceiling exceeded", spend=campaign_total_spend, limit=settings.CAMPAIGN_BUDGET_MICROS)
            raise BudgetExceededException("Campaign total AI spend hard ceiling exceeded ($1.00 limit reached).")

        if campaign_total_spend >= settings.CAMPAIGN_FREEZE_MICROS:
            logger.warning("Campaign spend freeze threshold reached; halting new paid calls", spend=campaign_total_spend, limit=settings.CAMPAIGN_FREEZE_MICROS)
            raise BudgetExceededException("Campaign total AI spend warning threshold reached ($0.80 freeze limit reached).")

        # Check Daily Project Budget
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_stmt = select(func.coalesce(func.sum(UsageLedger.estimated_cost_micros), 0)).where(
            UsageLedger.created_at >= today_start
        )
        daily_res = await db.execute(daily_stmt)
        project_daily_spend = daily_res.scalar_one()

        if project_daily_spend >= settings.DAILY_BUDGET_MICROS:
            logger.error("Daily project hard budget exceeded", spend=project_daily_spend, limit=settings.DAILY_BUDGET_MICROS)
            raise BudgetExceededException("Daily project AI spend limit exceeded.")

        # Check User Daily Quota if user_id present
        if user_id:
            user_stmt = select(func.coalesce(func.sum(UsageLedger.estimated_cost_micros), 0)).where(
                and_(
                    UsageLedger.user_id == user_id,
                    UsageLedger.created_at >= today_start
                )
            )
            user_res = await db.execute(user_stmt)
            user_daily_spend = user_res.scalar_one()
            if user_daily_spend >= settings.USER_DAILY_BUDGET_MICROS:
                logger.error("User daily budget quota exceeded", user_id=str(user_id), spend=user_daily_spend)
                raise BudgetExceededException("Your daily AI analysis quota has been exceeded.")

    async def reserve_budget(
        self,
        db: AsyncSession,
        analysis_run_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        reserved_micros: int = settings.MAX_BUDGET_MICROS_PER_RUN
    ) -> BudgetReservation:
        if settings.PAID_CALLS_ENABLED and settings.SPEND_KILL_SWITCH_ACTIVE:
            logger.error("Global spend kill switch is active; rejecting paid analysis run", run_id=str(analysis_run_id))
            raise BudgetExceededException("Global AI spend kill switch is active. AI analysis temporarily suspended.")

        if settings.PAID_CALLS_ENABLED:
            current_liability = await self.get_campaign_total_liability(db)
            if current_liability + reserved_micros > settings.CAMPAIGN_BUDGET_MICROS:
                logger.error("Campaign spend exceeds hard budget ceiling", current=current_liability, reserved=reserved_micros, limit=settings.CAMPAIGN_BUDGET_MICROS)
                raise BudgetExceededException("Campaign total AI spend hard ceiling ($1.00) exceeded.")
            if current_liability + reserved_micros > settings.CAMPAIGN_FREEZE_MICROS:
                logger.error("Campaign spend exceeds reservation freeze limit", current=current_liability, reserved=reserved_micros, limit=settings.CAMPAIGN_FREEZE_MICROS)
                raise BudgetExceededException("Campaign budget reservation freeze limit ($0.80) exceeded.")

        effective_reservation = reserved_micros if settings.PAID_CALLS_ENABLED else 0

        # Ensure AnalysisRun exists to satisfy database foreign key constraints
        run_stmt = select(AnalysisRun.id).where(AnalysisRun.id == analysis_run_id)
        run_res = await db.execute(run_stmt)
        if not run_res.scalar_one_or_none():
            db.add(AnalysisRun(
                id=analysis_run_id,
                run_type="INSPECTION",
                owner_user_id=user_id,
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                status="RUNNING",
                input_hash="inspection",
                config_hash="inspection",
                dataset_version="v3.0.0",
                model_id="gemini-2.5-flash",
                prompt_hash="inspection",
                cost_reserved_micros=effective_reservation
            ))
            await db.flush()

        reservation = BudgetReservation(
            id=uuid.uuid4(),
            analysis_run_id=analysis_run_id,
            scope="USER" if user_id else "PROJECT",
            reserved_micros=effective_reservation,
            released_micros=0,
            consumed_micros=0,
            status="ACTIVE",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15)
        )
        db.add(reservation)
        await db.flush()
        return reservation

    async def cancel_reservation(
        self,
        db: AsyncSession,
        analysis_run_id: uuid.UUID
    ) -> None:
        """Release any unconsumed reservation for a cancelled/failed run."""
        stmt = select(BudgetReservation).where(
            BudgetReservation.analysis_run_id == analysis_run_id,
            BudgetReservation.status == "ACTIVE"
        )
        res = await db.execute(stmt)
        reservation = res.scalar_one_or_none()
        if reservation:
            reservation.released_micros = max(0, reservation.reserved_micros - reservation.consumed_micros)
            reservation.status = "CANCELLED"
            await db.flush()


    async def record_usage(
        self,
        db: AsyncSession,
        analysis_run_id: uuid.UUID,
        model_call_id: str,
        model_id: str,
        purpose: str,
        input_text_tokens: int,
        input_image_tokens: int = 0,
        output_tokens: int = 0,
        reasoning_tokens: int = 0,
        cached_input_tokens: int = 0,
        user_id: Optional[uuid.UUID] = None,
        billing_reference: Optional[str] = None
    ) -> UsageLedger:
        # Check uniqueness of model_call_id
        existing_stmt = select(UsageLedger).where(UsageLedger.model_call_id == model_call_id)
        existing_res = await db.execute(existing_stmt)
        existing_record = existing_res.scalar_one_or_none()
        if existing_record:
            logger.warning("Duplicate model_call_id detected in usage ledger; skipping duplicate charge", call_id=model_call_id)
            return existing_record


        estimated_micros, pricing_ver = self.calculate_estimated_cost_micros(
            model_id=model_id,
            input_text_tokens=input_text_tokens,
            input_image_tokens=input_image_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            cached_input_tokens=cached_input_tokens
        )

        record = UsageLedger(
            id=uuid.uuid4(),
            user_id=user_id,
            analysis_run_id=analysis_run_id,
            model_call_id=model_call_id,
            model_id=model_id,
            purpose=purpose,
            input_text_tokens=input_text_tokens,
            input_image_tokens=input_image_tokens,
            output_tokens=output_tokens,
            reasoning_tokens=reasoning_tokens,
            total_tokens=input_text_tokens + input_image_tokens + output_tokens + reasoning_tokens + cached_input_tokens,
            estimated_cost_micros=estimated_micros,
            pricing_version=pricing_ver,
            billing_reference=billing_reference,
            created_at=datetime.now(timezone.utc)
        )
        db.add(record)

        # Update budget reservation
        stmt = select(BudgetReservation).where(
            BudgetReservation.analysis_run_id == analysis_run_id,
            BudgetReservation.status == "ACTIVE"
        )
        res = await db.execute(stmt)
        reservation = res.scalar_one_or_none()
        if reservation:
            reservation.consumed_micros += estimated_micros
            if reservation.consumed_micros > reservation.reserved_micros:
                logger.error(
                    "Analysis run exceeded reserved budget limit",
                    run_id=str(analysis_run_id),
                    consumed=reservation.consumed_micros,
                    reserved=reservation.reserved_micros
                )
                raise BudgetExceededException(
                    f"Analysis run budget exceeded: consumed {reservation.consumed_micros} > reserved {reservation.reserved_micros} micros."
                )

        await db.flush()
        return record

    async def settle_reservation(
        self,
        db: AsyncSession,
        analysis_run_id: uuid.UUID
    ):
        stmt = select(BudgetReservation).where(
            BudgetReservation.analysis_run_id == analysis_run_id,
            BudgetReservation.status == "ACTIVE"
        )
        res = await db.execute(stmt)
        reservation = res.scalar_one_or_none()
        if reservation:
            reservation.released_micros = max(0, reservation.reserved_micros - reservation.consumed_micros)
            reservation.status = "SETTLED"
            await db.flush()


cost_service = CostService()
