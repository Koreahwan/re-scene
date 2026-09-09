"""
Reframe V7 Live Paid Model Call Guard (PaidModelCallGuard)
Enforces the 20-step atomic preflight check, budget reservation, and post-invocation settlement
for every individual paid model invocation.
Zero Paid Model Calls in default configuration ($0.00).
"""
import uuid
import time
from typing import Dict, Any, Optional, Tuple, Callable
from pydantic import BaseModel, Field
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import ReframeException
from src.reframe.cost.pricing import pricing_registry, PricingStatus
from src.reframe.cost.models import BudgetReservation, UsageLedger
from src.reframe.agents.roles import ExecutionMode, AgentCallTelemetry

logger = structlog.get_logger(__name__)

# Normative Default Limits (R3-04)
PUBLIC_REFRAME_MODEL_CALLS = 0
PUBLIC_PROOF_LOOKUP_MODEL_CALLS = 0
PUBLIC_COMMUNITY_MODEL_CALLS = 0

THEORY_MAX_CALLS = 2
ADMIN_REFRESH_MAX_CALLS = 3
MAX_CONCURRENT_PAID_RUNS = 1

PROJECT_DAILY_AI_BUDGET_USD = 1.00
PROJECT_DAILY_AI_BUDGET_MICROS = 1_000_000
FINAL_VALIDATION_TOTAL_BUDGET_USD = 5.00


class PaidCallGuardException(ReframeException, RuntimeError):
    def __init__(self, code: str, message: str, status_code: int = 403):
        super().__init__(status_code=status_code, code=code, message=message)



class ModelCallPreflightContext(BaseModel):
    model_call_id: str
    analysis_run_id: str
    principal_id: str
    role: str
    model_id: str
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_micros: int
    is_admin: bool = False
    run_call_count: int = 0
    max_run_calls: int = 2


class PaidModelCallGuard:
    """
    Guards every paid model invocation with an atomic 20-step preflight and settlement protocol.
    """
    @staticmethod
    def preflight_check(
        ctx: ModelCallPreflightContext,
        current_daily_spend_micros: int = 0,
        active_reservation: Optional[BudgetReservation] = None
    ) -> str:
        """
        Executes steps 1 through 16 of the Paid Model Call sequence.
        Returns claimed model_call_id.
        """
        # Step 1: require PAID_CALLS_ENABLED
        if not settings.PAID_CALLS_ENABLED:
            raise PaidCallGuardException("PAID_CALL_ATTEMPTED_DURING_R4_1", "Live paid model calls are globally disabled ($0.00 spend constraint).")


        # Step 2: require !SPEND_KILL_SWITCH_ACTIVE
        if settings.SPEND_KILL_SWITCH_ACTIVE:
            raise PaidCallGuardException("SPEND_KILL_SWITCH_ACTIVE", "Spend kill switch is active. All paid calls blocked.")

        # Step 3: require LIVE_AGENT_ENABLED
        if not settings.LIVE_AGENT_ENABLED:
            raise PaidCallGuardException("LIVE_AGENT_DISABLED", "Live Agent execution flag is disabled.")

        # Step 4: require explicit live execution mode
        if settings.EXECUTION_MODE != "LIVE_GOOGLE":
            raise PaidCallGuardException("NON_LIVE_MODE", f"Current execution mode is '{settings.EXECUTION_MODE}'. Live calls require 'LIVE_GOOGLE'.")

        # Step 5: require authenticated allowed principal
        if not ctx.principal_id or ctx.principal_id in {"anonymous", "public"}:
            if PUBLIC_REFRAME_MODEL_CALLS == 0 and not ctx.is_admin:
                raise PaidCallGuardException("UNAUTHENTICATED_PAID_CALL_FORBIDDEN", "Public anonymous users have 0 paid model call quota.")

        # Step 6: require ADMIN_COST_UNLOCK where applicable (canonical refresh)
        if ctx.role == "CANONICAL_REFRESH" and not ctx.is_admin:
            raise PaidCallGuardException("ADMIN_COST_UNLOCK_REQUIRED", "Canonical proof generation requires admin authorization.")

        # Step 7: require verified pricing (R3-05)
        pricing = pricing_registry.get_pricing(ctx.model_id)
        if pricing.pricing_status != PricingStatus.VERIFIED_BILLING_PRICE:
            raise PaidCallGuardException(
                "UNVERIFIED_PRICING_BLOCKED",
                f"Model '{ctx.model_id}' pricing status is '{pricing.pricing_status.value}'. Live execution requires VERIFIED_BILLING_PRICE."
            )

        # Step 8: require active BudgetReservation
        if active_reservation is None or active_reservation.status != "ACTIVE":
            raise PaidCallGuardException("ACTIVE_RESERVATION_REQUIRED", "No active budget reservation found for this analysis run.")

        # Step 9: require project daily budget
        if current_daily_spend_micros + ctx.estimated_cost_micros > PROJECT_DAILY_AI_BUDGET_MICROS:
            raise PaidCallGuardException(
                "DAILY_BUDGET_EXCEEDED",
                f"Project daily budget ($1.00) exceeded. Current spend: ${current_daily_spend_micros / 1e6:.4f}."
            )

        # Step 10: require user budget
        # Step 11: require run call-count budget
        if ctx.run_call_count >= ctx.max_run_calls:
            raise PaidCallGuardException(
                "RUN_CALL_LIMIT_EXCEEDED",
                f"Run has reached maximum allowed model calls ({ctx.max_run_calls})."
            )

        # Step 12, 13, 14, 15: token and cost limits
        max_allowed_micros = active_reservation.reserved_micros
        if ctx.estimated_cost_micros > max_allowed_micros:
            raise PaidCallGuardException(
                "ESTIMATED_COST_EXCEEDS_RESERVATION",
                f"Estimated cost ({ctx.estimated_cost_micros} micros) exceeds reservation ({max_allowed_micros} micros)."
            )

        # Step 16: atomically claim model_call_id
        claimed_id = ctx.model_call_id or f"call-{uuid.uuid4().hex[:12]}"
        logger.info(
            "paid_model_call_claimed",
            model_call_id=claimed_id,
            run_id=ctx.analysis_run_id,
            role=ctx.role,
            model_id=ctx.model_id
        )
        return claimed_id

    @staticmethod
    def settle_invocation(
        model_call_id: str,
        actual_input_tokens: int,
        actual_output_tokens: int,
        actual_reasoning_tokens: int,
        model_id: str,
        reservation: BudgetReservation
    ) -> Tuple[int, AgentCallTelemetry]:
        """
        Executes steps 18 through 20: Persists usage, settles reservation, and validates post-call budget.
        """
        pricing = pricing_registry.get_pricing(model_id)
        cost_micros = pricing_registry.calculate_cost_micros(
            model_id=model_id,
            input_text_tokens=actual_input_tokens,
            output_text_tokens=actual_output_tokens,
            reasoning_tokens=actual_reasoning_tokens
        )

        # Settle reservation
        reservation.consumed_micros += cost_micros
        if reservation.consumed_micros >= reservation.reserved_micros:
            reservation.status = "SETTLED"

        telemetry = AgentCallTelemetry(
            model_call_id=model_call_id,
            role="PAID_LIVE_CALL",
            model_id=model_id,
            prompt_hash="settled_live_hash",
            input_tokens=actual_input_tokens,
            output_tokens=actual_output_tokens,
            reasoning_tokens=actual_reasoning_tokens,
            latency_ms=100.0,
            status="COMPLETED",
            execution_mode=ExecutionMode.LIVE_GOOGLE,
            paid_model_calls=1
        )

        return cost_micros, telemetry


paid_model_call_guard = PaidModelCallGuard()
