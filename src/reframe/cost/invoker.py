"""
Reframe V7 Guarded Gemini Invoker (GuardedGeminiInvoker) & ADK LLM Adapter (GuardedGeminiAdkLlm)
The SINGLE normative live invocation primitive for all Google Gemini API / Vertex AI calls.
Enforces the 24-step atomic preflight check, database-backed ModelCallClaim reservation,
real token usage extraction, and immediate ledger settlement.
Zero Paid Model Calls in default configuration ($0.00).
"""
import uuid
import time
import asyncio
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, Tuple, AsyncGenerator, Set
import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

import google.adk as adk
from google.adk.models import BaseLlm, LlmRequest, LlmResponse, LLMRegistry
from google.genai import types

from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.cost.guard import (
    PaidModelCallGuard,
    ModelCallPreflightContext,
    PaidCallGuardException,
    PROJECT_DAILY_AI_BUDGET_MICROS,
    MAX_CONCURRENT_PAID_RUNS
)
from src.reframe.cost.pricing import pricing_registry, PricingStatus
from src.reframe.cost.models import BudgetReservation, UsageLedger
from src.reframe.jobs.models import ModelCallClaim, AnalysisRun
from src.reframe.agents.roles import ExecutionMode, AgentCallTelemetry

logger = structlog.get_logger(__name__)


from contextvars import ContextVar
from dataclasses import dataclass

@dataclass(frozen=True)
class LiveModelInvocationContext:
    analysis_run_id: uuid.UUID
    principal_id: uuid.UUID
    run_type: str = "DEEP_NARRATIVE_ANALYSIS"
    is_admin: bool = False
    allowed_call_count: int = 1
    budget_reservation_id: Optional[uuid.UUID] = None
    request_id: Optional[str] = None


live_invocation_ctx: ContextVar[Optional[LiveModelInvocationContext]] = ContextVar("live_invocation_ctx", default=None)


ALLOWED_LIVE_MODEL_IDS: Set[str] = {"gemini-3.6-flash"}


def ensure_model_location_supported(model_id, location):
    # Google deployment support table checked 2026-09-10. Metadata lookup
    # can succeed even when generation is unsupported at a regional endpoint.
    if model_id == "gemini-3.6-flash" and location not in {"global", "us", "eu"}:
        raise PaidCallGuardException("MODEL_LOCATION_UNSUPPORTED",
            "Gemini 3.6 Flash requires global, us, or eu; choose a supported endpoint explicitly.")


def verified_sdk_usage(response):
    """Never substitute a reservation estimate for actual provider token usage."""
    usage = getattr(response, "usage_metadata", None)
    counts = (getattr(usage, "prompt_token_count", None),
              getattr(usage, "candidates_token_count", None),
              getattr(usage, "thoughts_token_count", None) or 0)
    if any(type(value) is not int or value < 0 for value in counts):
        raise RuntimeError("SDK_USAGE_MISSING: Keep the claim reserved for manual reconciliation")
    return counts


class GuardedGeminiInvoker:
    """
    GuardedGeminiInvoker is the sole authorized gateway for executing live Google Gemini model calls.
    Enforces a strict 24-step preflight checklist, durable claiming, zero-leak telemetry,
    and automatic reconciliation in compliance with Section 5 and R2-08.
    """
    _claim_locks: Dict[uuid.UUID, asyncio.Lock] = {}

    @classmethod
    def _get_claim_lock(cls, run_id: uuid.UUID) -> asyncio.Lock:
        if run_id not in cls._claim_locks:
            cls._claim_locks[run_id] = asyncio.Lock()
        return cls._claim_locks[run_id]

    @classmethod
    async def invoke_guarded_generation(
        cls,
        analysis_run_id: str,
        principal_id: str,
        role: str,
        model_id: str,
        prompt_text: str,
        estimated_input_tokens: int = 1000,
        estimated_output_tokens: int = 500,
        db_session: Optional[AsyncSession] = None,
        is_admin: bool = False,
        media_parts: Optional[list[types.Part]] = None,
        json_output: bool = False,
    ) -> Tuple[str, AgentCallTelemetry]:
        """
        Executes the atomic 24-step preflight, database claim, live invocation, and settlement sequence.
        """
        # 1-4. Strict Configuration & Flag Preflight Check
        if not settings.PAID_CALLS_ENABLED:
            raise PaidCallGuardException("PAID_CALL_ATTEMPTED_DURING_R4_2", "Paid model calls are disabled ($0.00 spend constraint).")
        if settings.SPEND_KILL_SWITCH_ACTIVE:
            raise PaidCallGuardException("SPEND_KILL_SWITCH_ACTIVE", "Spend kill switch is active. All paid calls blocked.")
        if not settings.LIVE_AGENT_ENABLED:
            raise PaidCallGuardException("LIVE_AGENT_DISABLED", "Live Agent execution flag is disabled.")
        if settings.EXECUTION_MODE != "LIVE_GOOGLE":
            raise PaidCallGuardException("NON_LIVE_MODE", f"Execution mode '{settings.EXECUTION_MODE}' cannot make live calls.")

        ensure_model_location_supported(model_id, settings.GOOGLE_CLOUD_LOCATION or "global")

        # An offline intake worker can supply bounded, inline media. Public callers
        # still use text only. Reserve the entire model context for media requests,
        # not the much smaller prompt's character count.
        if media_parts:
            if not is_admin or estimated_input_tokens < 1_048_576:
                raise PaidCallGuardException("MEDIA_RESERVATION_REQUIRED", "Media requires admin invocation and a full-context reservation.")
            if any(not isinstance(part, types.Part) or part.file_data is not None for part in media_parts):
                raise PaidCallGuardException("INLINE_MEDIA_REQUIRED", "Intake accepts inline media only, not externally fetched URLs.")
            if sum(len(part.inline_data.data or b"") for part in media_parts if part.inline_data) > 18_000_000:
                raise PaidCallGuardException("MEDIA_SIZE_EXCEEDED", "Inline intake media exceeds the request size cap.")

        # 5. Parse UUIDs strictly (No random fallbacks in production live mode)
        run_uuid = None
        if isinstance(analysis_run_id, str):
            try:
                run_uuid = uuid.UUID(analysis_run_id)
            except Exception:
                raise PaidCallGuardException("INVALID_INVOCATION_CONTEXT", f"Invalid analysis_run_id UUID: '{analysis_run_id}'")
        elif isinstance(analysis_run_id, uuid.UUID):
            run_uuid = analysis_run_id
        else:
            raise PaidCallGuardException("INVALID_INVOCATION_CONTEXT", "Missing or invalid analysis_run_id")

        user_uuid = None
        if isinstance(principal_id, str):
            try:
                user_uuid = uuid.UUID(principal_id)
            except Exception:
                raise PaidCallGuardException("INVALID_INVOCATION_CONTEXT", f"Invalid principal_id UUID: '{principal_id}'")
        elif isinstance(principal_id, uuid.UUID):
            user_uuid = principal_id
        else:
            raise PaidCallGuardException("INVALID_INVOCATION_CONTEXT", "Missing or invalid principal_id")

        # 6. Database Verification: AnalysisRun, Run Owner, and BudgetReservation
        model_call_id = f"call-{uuid.uuid4().hex[:12]}"
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:16]

        async with AsyncSessionLocal() as session:
            # Check for duplicate model_call_id (unique constraint)
            dup_stmt = select(ModelCallClaim).where(ModelCallClaim.model_call_id == model_call_id)
            dup_res = await session.execute(dup_stmt)
            if dup_res.scalar_one_or_none():
                raise PaidCallGuardException("DUPLICATE_MODEL_CALL_ID", f"Model call ID '{model_call_id}' already claimed.")

            # Section 5 Pre-call Requirement: Real AnalysisRun must exist
            run_stmt = select(AnalysisRun).where(AnalysisRun.id == run_uuid)
            run_res = await session.execute(run_stmt)
            db_run = run_res.scalar_one_or_none()
            if not db_run:
                raise PaidCallGuardException("ANALYSIS_RUN_REQUIRED", f"AnalysisRun '{run_uuid}' does not exist in database.")

            # Blocker A: Verify Run Owner matches principal
            if not db_run.owner_user_id and not is_admin:
                raise PaidCallGuardException("OWNER_REQUIRED", f"AnalysisRun '{run_uuid}' has no owner_user_id.")
            if db_run.owner_user_id and db_run.owner_user_id != user_uuid and not is_admin:
                raise PaidCallGuardException(
                    "RUN_OWNER_MISMATCH",
                    f"Principal '{user_uuid}' does not match run owner '{db_run.owner_user_id}'."
                )

            # Section 5 Pre-call Requirement: Real ACTIVE BudgetReservation must exist
            res_stmt = select(BudgetReservation).where(
                BudgetReservation.analysis_run_id == run_uuid,
                BudgetReservation.status == "ACTIVE"
            )
            res_res = await session.execute(res_stmt)
            db_res = res_res.scalar_one_or_none()
            if not db_res:
                raise PaidCallGuardException(
                    "ACTIVE_RESERVATION_REQUIRED",
                    f"Active BudgetReservation for analysis_run '{run_uuid}' is required before model call."
                )

        # 7. Frozen Live Model Allowlist & Pricing Verification (Blocker B)
        effective_model_id = settings.GEMINI_MODEL_ID if model_id in ("reframe-live-guarded", "reframe-live-root") else model_id
        if effective_model_id not in ALLOWED_LIVE_MODEL_IDS and not is_admin:
            raise PaidCallGuardException(
                "LIVE_MODEL_NOT_ALLOWED",
                f"Model '{effective_model_id}' is not in the frozen live allowlist: {ALLOWED_LIVE_MODEL_IDS}."
            )

        pricing = pricing_registry.get_pricing(effective_model_id)
        if pricing.pricing_status != PricingStatus.VERIFIED_BILLING_PRICE:
            raise PaidCallGuardException(
                "UNVERIFIED_PRICING_BLOCKED",
                f"Model '{effective_model_id}' status is '{pricing.pricing_status.value}'. Live calls require VERIFIED_BILLING_PRICE."
            )

        estimated_cost_micros, pricing_version = pricing_registry.calculate_estimated_cost_micros(
            model_id=effective_model_id,
            input_text_tokens=estimated_input_tokens,
            output_tokens=estimated_output_tokens
        )

        now_utc = datetime.now(timezone.utc)
        start_of_day = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)

        async with cls._get_claim_lock(run_uuid):
            async with AsyncSessionLocal() as session:
                # 1. Lock AnalysisRun row to strictly serialize concurrent claim attempts
                run_lock_stmt = select(AnalysisRun).where(AnalysisRun.id == run_uuid).with_for_update()
                run_lock_res = await session.execute(run_lock_stmt)
                db_run = run_lock_res.scalar_one_or_none()
                if not db_run:
                    raise PaidCallGuardException("ANALYSIS_RUN_REQUIRED", f"AnalysisRun '{run_uuid}' not found for row lock.")

                # Re-verify reservation balance
                res_stmt = select(BudgetReservation).where(
                    BudgetReservation.analysis_run_id == run_uuid,
                    BudgetReservation.status == "ACTIVE"
                )
                res_res = await session.execute(res_stmt)
                db_res = res_res.scalar_one_or_none()
                if not db_res:
                    raise PaidCallGuardException("ACTIVE_RESERVATION_REQUIRED", "BudgetReservation no longer active.")

                remaining_reservation = db_res.reserved_micros - db_res.consumed_micros
                if remaining_reservation < estimated_cost_micros:
                    raise PaidCallGuardException(
                        "INSUFFICIENT_RESERVATION",
                        f"Remaining reservation ({remaining_reservation} micros) < estimated cost ({estimated_cost_micros} micros)."
                    )

                # Compute project daily spend from UsageLedger
                proj_spend_stmt = select(func.coalesce(func.sum(UsageLedger.estimated_cost_micros), 0)).where(
                    UsageLedger.created_at >= start_of_day
                )
                proj_spend_res = await session.execute(proj_spend_stmt)
                daily_project_spend = proj_spend_res.scalar() or 0

                if daily_project_spend + estimated_cost_micros > PROJECT_DAILY_AI_BUDGET_MICROS:
                    raise PaidCallGuardException(
                        "DAILY_BUDGET_EXCEEDED",
                        f"Project daily AI budget ($1.00) exceeded. Current spend: ${daily_project_spend / 1e6:.4f}."
                    )

                # Compute user daily spend
                user_spend_stmt = select(func.coalesce(func.sum(UsageLedger.estimated_cost_micros), 0)).where(
                    UsageLedger.user_id == user_uuid,
                    UsageLedger.created_at >= start_of_day
                )
                user_spend_res = await session.execute(user_spend_stmt)
                user_daily_spend = user_spend_res.scalar() or 0
                if user_daily_spend + estimated_cost_micros > PROJECT_DAILY_AI_BUDGET_MICROS and not is_admin:
                    raise PaidCallGuardException(
                        "USER_DAILY_BUDGET_EXCEEDED",
                        f"User daily budget exceeded: ${user_daily_spend / 1e6:.4f}."
                    )

                # Verify no prior claim in NEEDS_RECONCILIATION state (automatic retry forbidden)
                recon_stmt = select(func.count(ModelCallClaim.id)).where(
                    ModelCallClaim.analysis_run_id == run_uuid,
                    ModelCallClaim.state == "NEEDS_RECONCILIATION"
                )
                recon_res = await session.execute(recon_stmt)
                if (recon_res.scalar() or 0) > 0:
                    raise PaidCallGuardException(
                        "MANUAL_RECONCILIATION_REQUIRED",
                        "AnalysisRun has claims in NEEDS_RECONCILIATION state. Automatic retry is strictly blocked."
                    )

                # Compute run call count across all attempts that may have consumed or attempted a real request:
                # CLAIMED, EXECUTING, SUCCEEDED, FAILED, NEEDS_RECONCILIATION
                run_calls_stmt = select(func.count(ModelCallClaim.id)).where(
                    ModelCallClaim.analysis_run_id == run_uuid,
                    ModelCallClaim.state.in_(["CLAIMED", "EXECUTING", "SUCCEEDED", "FAILED", "NEEDS_RECONCILIATION"])
                )
                run_calls_res = await session.execute(run_calls_stmt)
                run_call_count = run_calls_res.scalar() or 0
                max_allowed_calls = settings.MAX_MODEL_CALLS_PER_ANALYSIS_RUN
                if run_call_count >= max_allowed_calls:
                    raise PaidCallGuardException(
                        "RUN_CALL_LIMIT_EXCEEDED",
                        f"Run has reached or exceeded maximum allowed model calls ({run_call_count}/{max_allowed_calls}). P0 allows exactly {max_allowed_calls} call."
                    )

                # Check concurrent live runs (excluding the current run itself)
                active_runs_stmt = select(func.count(AnalysisRun.id)).where(
                    AnalysisRun.status == "RUNNING",
                    AnalysisRun.id != run_uuid
                )
                active_runs_res = await session.execute(active_runs_stmt)
                active_runs_count = active_runs_res.scalar() or 0
                if active_runs_count >= MAX_CONCURRENT_PAID_RUNS and not is_admin:
                    raise PaidCallGuardException(
                        "CONCURRENT_RUNS_EXCEEDED",
                        f"Maximum concurrent live runs exceeded ({active_runs_count} other runs currently active)."
                    )

                # Insert ModelCallClaim with CLAIMED state
                claim = ModelCallClaim(
                    model_call_id=model_call_id,
                    analysis_run_id=run_uuid,
                    model_id=model_id,
                    role=role,
                    state="CLAIMED",
                    estimated_cost_micros=estimated_cost_micros,
                    actual_cost_micros=0,
                    claimed_at=now_utc
                )
                session.add(claim)
                await session.commit()

        # 24-25. Set State to EXECUTING & Execute External Call
        async with AsyncSessionLocal() as session:
            stmt = select(ModelCallClaim).where(ModelCallClaim.model_call_id == model_call_id)
            res = await session.execute(stmt)
            db_claim = res.scalar_one_or_none()
            if db_claim:
                db_claim.state = "EXECUTING"
                await session.commit()

        t0 = time.perf_counter()
        request_sent = False
        target_project = settings.GOOGLE_CLOUD_PROJECT or None
        target_location = settings.GOOGLE_CLOUD_LOCATION or "global"
        try:
            from google import genai

            logger.info(
                "guarded_gemini_invoking_vertex",
                project_id=target_project,
                location=target_location,
                model_id=model_id,
                model_call_id=model_call_id,
                role=role
            )
            client = genai.Client(
                vertexai=True,
                project=target_project,
                location=target_location,
                # The durable claim represents one request, never hidden SDK retries.
                http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
            )
            request_sent = True
            response = await client.aio.models.generate_content(
                model=model_id,
                contents=[prompt_text, *media_parts] if media_parts else prompt_text,
                config=types.GenerateContentConfig(
                    temperature=None if model_id == "gemini-3.6-flash" else 0.0,
                    max_output_tokens=estimated_output_tokens,
                    response_mime_type="application/json" if json_output else None,
                    thinking_config=(types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
                        if model_id == "gemini-3.6-flash" and role == "LIVE_SERVICE_VALIDATION" else None),
                )
            )
            latency_ms = round((time.perf_counter() - t0) * 1000, 2)
            response_text = response.text or ""

            # 26-27. Extract Real SDK Usage Metadata & Compute Actual Cost
            actual_input, actual_output, actual_reasoning = verified_sdk_usage(response)

            actual_cost, p_ver = pricing_registry.calculate_estimated_cost_micros(
                model_id=effective_model_id,
                input_text_tokens=actual_input,
                output_tokens=actual_output,
                reasoning_tokens=actual_reasoning
            )

            # 28-32. Transaction 2: Post-Call Ledger Persistence and Settle Claim
            async with AsyncSessionLocal() as session:
                # 28. Insert UsageLedger immediately
                ledger_entry = UsageLedger(
                    user_id=user_uuid,
                    analysis_run_id=run_uuid,
                    model_call_id=model_call_id,
                    model_id=model_id,
                    purpose=role,
                    input_text_tokens=actual_input,
                    input_image_tokens=0,
                    output_tokens=actual_output,
                    reasoning_tokens=actual_reasoning,
                    total_tokens=actual_input + actual_output + actual_reasoning,
                    estimated_cost_micros=actual_cost,
                    pricing_version=p_ver,
                    created_at=datetime.now(timezone.utc)
                )
                session.add(ledger_entry)

                # 29-31. Update ModelCallClaim to SUCCEEDED
                stmt = select(ModelCallClaim).where(ModelCallClaim.model_call_id == model_call_id)
                res = await session.execute(stmt)
                db_claim = res.scalar_one_or_none()
                if db_claim:
                    db_claim.state = "SUCCEEDED"
                    db_claim.actual_cost_micros = actual_cost
                    db_claim.settled_at = datetime.now(timezone.utc)

                # Consume BudgetReservation
                res_stmt = select(BudgetReservation).where(
                    BudgetReservation.analysis_run_id == run_uuid,
                    BudgetReservation.status == "ACTIVE"
                )
                res_res = await session.execute(res_stmt)
                db_res = res_res.scalar_one_or_none()
                if db_res:
                    db_res.consumed_micros += actual_cost
                    if db_res.consumed_micros >= db_res.reserved_micros:
                        db_res.status = "SETTLED"

                await session.commit()

            telemetry = AgentCallTelemetry(
                model_call_id=model_call_id,
                provider_call_id=response.response_id if isinstance(getattr(response, "response_id", None), str) else None,
                output_hash=hashlib.sha256(response_text.encode("utf-8")).hexdigest(),
                role=role,
                model_id=model_id,
                prompt_hash=prompt_hash,
                input_tokens=actual_input,
                output_tokens=actual_output,
                reasoning_tokens=actual_reasoning,
                latency_ms=latency_ms,
                status="COMPLETED",
                execution_mode=ExecutionMode.LIVE_GOOGLE,
                paid_model_calls=1
            )
            return response_text, telemetry

        except Exception as e:
            # Uncertain failure state handling
            uncertain_state = request_sent
            new_state = "NEEDS_RECONCILIATION" if uncertain_state else "FAILED"

            async with AsyncSessionLocal() as session:
                stmt = select(ModelCallClaim).where(ModelCallClaim.model_call_id == model_call_id)
                res = await session.execute(stmt)
                db_claim = res.scalar_one_or_none()
                if db_claim:
                    db_claim.state = new_state
                    await session.commit()

            logger.error("guarded_gemini_call_failed", model_call_id=model_call_id, state=new_state, error=str(e))
            raise e

    @classmethod
    async def invoke(
        cls,
        analysis_run_id: str = "",
        principal_id: str = "",
        role: str = "REASONING",
        model_id: str = "reframe-live-guarded",
        prompt: str = "",
        prompt_text: str = "",
        db: Optional[AsyncSession] = None,
        db_session: Optional[AsyncSession] = None,
        purpose: Optional[str] = None,
        **kwargs
    ) -> Tuple[str, AgentCallTelemetry]:
        """Convenience invocation wrapper."""
        return await cls.invoke_guarded_generation(
            analysis_run_id=analysis_run_id,
            principal_id=principal_id,
            role=purpose or role,
            model_id=model_id,
            prompt_text=prompt or prompt_text,
            db_session=db or db_session
        )


class GuardedGeminiAdkLlm(BaseLlm):
    """
    Official Google ADK BaseLlm implementation that routes all ADK Agent model calls through GuardedGeminiInvoker.
    Guarantees that ADK Runner execution is governed by the 24-step preflight and spend ledger.
    """
    model: str = "reframe-live-guarded"

    @classmethod
    def supported_models(cls) -> list[str]:
        return [r"reframe-live-guarded", r"reframe-live-.*"]

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False) -> AsyncGenerator[LlmResponse, None]:
        ctx = live_invocation_ctx.get()
        if ctx is None or not isinstance(ctx.analysis_run_id, uuid.UUID) or not isinstance(ctx.principal_id, uuid.UUID):
            raise PaidCallGuardException(
                "MISSING_INVOCATION_CONTEXT",
                "GuardedGeminiAdkLlm requires an active LiveModelInvocationContext with valid UUIDs."
            )

        prompt_parts = []
        if hasattr(llm_request, "contents") and llm_request.contents:
            for content in llm_request.contents:
                if hasattr(content, "parts"):
                    for part in content.parts:
                        if hasattr(part, "text") and part.text:
                            prompt_parts.append(part.text)
        prompt_text = "\n".join(prompt_parts) if prompt_parts else "Generate retrospective narrative analysis"

        effective_model = settings.GEMINI_MODEL_ID if self.model == "reframe-live-guarded" else self.model

        response_text, telemetry = await GuardedGeminiInvoker.invoke_guarded_generation(
            analysis_run_id=str(ctx.analysis_run_id),
            principal_id=str(ctx.principal_id),
            role=ctx.run_type,
            model_id=effective_model,
            prompt_text=prompt_text,
            is_admin=ctx.is_admin
        )

        yield LlmResponse(
            content=types.Content(parts=[types.Part.from_text(text=response_text)])
        )


# Register GuardedGeminiAdkLlm in ADK LLMRegistry with dedicated alias
try:
    LLMRegistry.register(GuardedGeminiAdkLlm)
except Exception as e:
    logger.debug("GuardedGeminiAdkLlm already registered or registration skipped", error=str(e))


guarded_invoker = GuardedGeminiInvoker()

