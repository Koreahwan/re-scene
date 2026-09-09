"""
Unit Tests for Model Call Claim Atomicity, Single Billing Ledger Writer, and Legacy Store Reconciliation
Zero Paid Model Calls ($0.00 spend).
"""
import uuid
import pytest
import asyncio
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock
from sqlalchemy import select, func, update

from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.identity.models import User
from src.reframe.jobs.models import AnalysisRun, ModelCallClaim
from src.reframe.cost.models import BudgetReservation, UsageLedger
from src.reframe.cost.invoker import GuardedGeminiInvoker, PaidCallGuardException
from src.reframe.proof.models import ProofRecord
from src.reframe.proof.store import CanonicalProofStore, LEGACY_FIXTURE_PROOF_IDS


@pytest.mark.asyncio
async def test_concurrent_live_claim_atomicity_allows_only_one(monkeypatch):
    """
    Task 2 & 13: Row-level lock on AnalysisRun serializes concurrent invocation attempts.
    Under MAX_MODEL_CALLS_PER_ANALYSIS_RUN=1, exactly one claim succeeds; all concurrent attempts fail closed.
    """
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    user_id = uuid.uuid4()
    run_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        # Clean up prior running runs
        await db.execute(update(AnalysisRun).where(AnalysisRun.status == "RUNNING").values(status="COMPLETED"))
        # Create User
        db.add(User(id=user_id, email_normalized="concur_test@example.com", role="USER", status="ACTIVE"))

        # Create AnalysisRun
        run = AnalysisRun(
            id=run_id,
            owner_user_id=user_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME",
            status="RUNNING",
            input_hash="hash-concur",
            config_hash="cfg-concur",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="p-concur"
        )
        db.add(run)

        # Create Active BudgetReservation
        res = BudgetReservation(
            id=uuid.uuid4(),
            analysis_run_id=run_id,
            scope="USER",
            reserved_micros=100_000,
            consumed_micros=0,
            status="ACTIVE",
            expires_at=datetime.now(timezone.utc)
        )
        db.add(res)
        await db.commit()

    # Mock the external Gemini client
    mock_gen_response = AsyncMock()
    mock_gen_response.text = '{"hypotheses": []}'
    mock_gen_response.usage_metadata = AsyncMock()
    mock_gen_response.usage_metadata.prompt_token_count = 100
    mock_gen_response.usage_metadata.candidates_token_count = 50
    mock_gen_response.usage_metadata.thinking_token_count = 0
    mock_gen_response.usage_metadata.thoughts_token_count = 0
    mock_gen_response.usage_metadata.reasoning_token_count = 0
    mock_gen_response.usage_metadata.cached_content_token_count = 0
    mock_gen_response.usage_metadata.total_token_count = 150

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.aio.models.generate_content = AsyncMock(return_value=mock_gen_response)
        mock_client_cls.return_value = mock_instance

        # Run 3 concurrent invocation attempts
        results = await asyncio.gather(
            GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(user_id),
                role="REASONING",
                model_id="gemini-3.6-flash",
                prompt_text="Test concurrent prompt 1"
            ),
            GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(user_id),
                role="REASONING",
                model_id="gemini-3.6-flash",
                prompt_text="Test concurrent prompt 2"
            ),
            GuardedGeminiInvoker.invoke_guarded_generation(
                analysis_run_id=str(run_id),
                principal_id=str(user_id),
                role="REASONING",
                model_id="gemini-3.6-flash",
                prompt_text="Test concurrent prompt 3"
            ),
            return_exceptions=True
        )

    succeeded = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(succeeded) == 1
    assert len(failures) == 2
    for f in failures:
        assert isinstance(f, PaidCallGuardException)
        assert f.code in ("RUN_CALL_LIMIT_EXCEEDED", "MANUAL_RECONCILIATION_REQUIRED")

    # Verify only 1 ModelCallClaim and 1 UsageLedger record exists in DB
    async with AsyncSessionLocal() as db:
        claim_count_stmt = select(func.count(ModelCallClaim.id)).where(ModelCallClaim.analysis_run_id == run_id)
        claim_count = (await db.execute(claim_count_stmt)).scalar()
        assert claim_count == 1

        ledger_count_stmt = select(func.count(UsageLedger.id)).where(UsageLedger.analysis_run_id == run_id)
        ledger_count = (await db.execute(ledger_count_stmt)).scalar()
        assert ledger_count == 1


@pytest.mark.asyncio
async def test_single_usage_ledger_record_per_synthetic_live_call(monkeypatch):
    """
    Task 3 & 13: GuardedGeminiInvoker is the sole billing/UsageLedger writer.
    A complete run produces exactly 1 UsageLedger record.
    """
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "LIVE_AGENT_ENABLED", True)
    monkeypatch.setattr(settings, "EXECUTION_MODE", "LIVE_GOOGLE")

    user_id = uuid.uuid4()
    run_id = uuid.uuid4()

    async with AsyncSessionLocal() as db:
        await db.execute(update(AnalysisRun).where(AnalysisRun.status == "RUNNING").values(status="COMPLETED"))
        db.add(User(id=user_id, email_normalized="single_test@example.com", role="USER", status="ACTIVE"))

        run = AnalysisRun(
            id=run_id,
            owner_user_id=user_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME",
            status="RUNNING",
            input_hash="hash-single-ledger",
            config_hash="cfg-single",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="p-single"
        )
        db.add(run)

        res = BudgetReservation(
            id=uuid.uuid4(),
            analysis_run_id=run_id,
            scope="USER",
            reserved_micros=100_000,
            consumed_micros=0,
            status="ACTIVE",
            expires_at=datetime.now(timezone.utc)
        )
        db.add(res)
        await db.commit()

    mock_gen_response = AsyncMock()
    mock_gen_response.text = '{"hypotheses": []}'
    mock_gen_response.usage_metadata = AsyncMock()
    mock_gen_response.usage_metadata.prompt_token_count = 120
    mock_gen_response.usage_metadata.candidates_token_count = 60
    mock_gen_response.usage_metadata.thinking_token_count = 0
    mock_gen_response.usage_metadata.thoughts_token_count = 0
    mock_gen_response.usage_metadata.reasoning_token_count = 0
    mock_gen_response.usage_metadata.cached_content_token_count = 0
    mock_gen_response.usage_metadata.total_token_count = 180

    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.aio.models.generate_content = AsyncMock(return_value=mock_gen_response)
        mock_client_cls.return_value = mock_instance

        resp_text, telemetry = await GuardedGeminiInvoker.invoke_guarded_generation(
            analysis_run_id=str(run_id),
            principal_id=str(user_id),
            role="REASONING",
            model_id="gemini-3.6-flash",
            prompt_text="Test single writer"
        )

        assert telemetry.model_call_id is not None
        assert telemetry.input_tokens == 120
        assert telemetry.output_tokens == 60

    async with AsyncSessionLocal() as db:
        ledger_stmt = select(UsageLedger).where(UsageLedger.analysis_run_id == run_id)
        records = (await db.execute(ledger_stmt)).scalars().all()
        assert len(records) == 1
        assert records[0].model_call_id == telemetry.model_call_id
        assert records[0].total_tokens == 180


@pytest.mark.asyncio
async def test_legacy_fixture_reconciliation_only_targets_known_fixture_provenance():
    """
    Task 12 & 13: Reconcile legacy fixtures only when:
    proof_id in LEGACY_FIXTURE_PROOF_IDS AND legacy generation_mode matches.
    Non-fixture or user-generated proofs are NEVER modified.
    """
    async with AsyncSessionLocal() as db:
        # 1. Matching legacy fixture
        legacy_proof = ProofRecord(
            proof_id="proof-anderson-01",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            proof_type="KNOWLEDGE_LEAK",
            title="Legacy Anderson Clue",
            blind_explanation="Blind explanation of legacy clue",
            reveal_explanation="Reveal explanation of legacy clue",
            evidence_chain=[],
            observed_premises=[],
            alternative_explanations=[],
            counterfactual_results={"wrong_reveal_delta": -0.8},
            generation_mode="OFFLINE_CANONICAL_FIXTURE",
            presentation_status="VISIBLE",
            human_review_status="APPROVED",
            trust_namespace="CANONICAL_VERIFIED"
        )
        db.add(legacy_proof)

        # 2. Non-legacy proof with different ID
        user_proof = ProofRecord(
            proof_id="proof-user-custom-99",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            proof_type="KNOWLEDGE_LEAK",
            title="User Generated Clue",
            blind_explanation="Blind explanation of custom clue",
            reveal_explanation="Reveal explanation of custom clue",
            evidence_chain=[],
            observed_premises=[],
            alternative_explanations=[],
            counterfactual_results={"wrong_reveal_delta": -0.8},
            generation_mode="USER_SUBMISSION",
            presentation_status="VISIBLE",
            human_review_status="APPROVED",
            trust_namespace="CANONICAL_VERIFIED"
        )
        db.add(user_proof)
        await db.commit()

        # Run reconciliation
        reconciled = await CanonicalProofStore.reconcile_superseded_fixture_proofs(db)
        await db.commit()

        # Check legacy proof was reconciled
        rec_legacy = await db.get(ProofRecord, legacy_proof.id)
        assert rec_legacy.presentation_status == "HIDDEN_FROM_PUBLIC"
        assert rec_legacy.human_review_status == "NEEDS_CORRECTION"
        assert rec_legacy.trust_namespace == "ENGINE_INFERENCE"

        # Check user proof was untouched
        rec_user = await db.get(ProofRecord, user_proof.id)
        assert rec_user.presentation_status == "VISIBLE"
        assert rec_user.human_review_status == "APPROVED"
        assert rec_user.trust_namespace == "CANONICAL_VERIFIED"

        # Clean up test rows
        await db.delete(rec_user)
        await db.delete(rec_legacy)
        await db.commit()
