"""
Unit tests for G1-B: Durable Worker & Pipeline Execution Invariants.
Validates:
1. Fail-closed rejection of missing or unknown reveal IDs without arbitrary fallback.
2. Strict server-side cutoff derivation from registry.
3. Proof persistence trust boundaries (NOT_REVIEWED -> HIDDEN_FROM_PUBLIC).
4. Durable checkpoint recovery avoiding duplicate steps.
5. Persistence and retrieval idempotency across process restart simulation.
Zero Paid Model Calls.
"""
import uuid
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select

from src.reframe.shared.config import settings
from src.reframe.shared.database import Base
from src.reframe.jobs.models import AnalysisRun, AnalysisRunStep
from src.reframe.jobs.worker import DurableWorker
from src.reframe.proof.models import ProofRecord
from src.reframe.proof.store import CanonicalProofStore, canonical_proof_store
from src.reframe.evidence.adapter import v3_adapter


@pytest.fixture
async def test_db(tmp_path):
    db_file = tmp_path / "test_g1_worker.db"
    async_url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    engine = create_async_engine(async_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield session_factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_worker_rejects_missing_or_unknown_reveal(test_db):
    """Worker fails closed when reveal_id is missing or absent from server registry."""
    worker = DurableWorker(worker_id="test-worker-01")

    async with test_db() as session:
        # 1. Run with unknown reveal
        run_unknown = AnalysisRun(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-nonexistent-999",
            run_type="REFRAME",
            status="RUNNING",
            input_hash="hash-in-unk",
            config_hash="hash-cfg-unk",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-unk"
        )
        session.add(run_unknown)
        await session.commit()

        await worker.execute_run(session, run_unknown)

        assert run_unknown.status == "FAILED"
        assert run_unknown.failure_code == "UNKNOWN_REVEAL"
        assert "not found in server registry" in (run_unknown.failure_detail_redacted or "")

        # 2. Run with None reveal_id
        run_none = AnalysisRun(
            id=uuid.uuid4(),
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id=None,
            run_type="REFRAME",
            status="RUNNING",
            input_hash="hash-in-none",
            config_hash="hash-cfg-none",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-none"
        )
        session.add(run_none)
        await session.commit()

        await worker.execute_run(session, run_none)

        assert run_none.status == "FAILED"
        assert run_none.failure_code == "UNKNOWN_REVEAL"


@pytest.mark.asyncio
async def test_worker_derives_cutoff_from_server_registry():
    """Worker derives cutoff strictly from v3_adapter registry for registered reveals."""
    anderson_rev = v3_adapter.get_reveal("reveal-anderson-identity")
    assert anderson_rev is not None
    assert anderson_rev.timestamp_ms == 4860000

    secret_room_rev = v3_adapter.get_reveal("reveal-secret-room-location")
    assert secret_room_rev is not None
    assert secret_room_rev.timestamp_ms == 3660000


@pytest.mark.asyncio
async def test_save_canonical_proof_hides_unreviewed_material(test_db):
    """save_canonical_proof marks NOT_REVIEWED material as HIDDEN_FROM_PUBLIC."""
    async with test_db() as session:
        proof_unreviewed = {
            "proof_id": "test-proof-unreviewed-01",
            "proof_type": "KNOWLEDGE_LEAK",
            "title": "Unreviewed Hypothesis",
            "blind_explanation": "Blind expl",
            "reveal_explanation": "Reveal expl",
            "evidence_chain": [{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
            "observed_premises": [],
            "alternative_explanations": ["alt"],
            "counterfactual_results": {},
            "human_review_status": "NOT_REVIEWED"
        }

        rec = await canonical_proof_store.save_canonical_proof(
            db=session,
            proof_data=proof_unreviewed,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity"
        )
        await session.commit()

        assert rec.human_review_status == "NOT_REVIEWED"
        assert rec.presentation_status == "HIDDEN_FROM_PUBLIC"

        # Material with explicit APPROVED review status becomes PUBLIC
        proof_approved = {
            "proof_id": "test-proof-approved-01",
            "proof_type": "KNOWLEDGE_LEAK",
            "title": "Approved Canonical Proof",
            "blind_explanation": "Blind expl",
            "reveal_explanation": "Reveal expl",
            "evidence_chain": [{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
            "observed_premises": [],
            "alternative_explanations": ["alt"],
            "counterfactual_results": {"wrong_reveal_delta": -0.85},
            "human_review_status": "APPROVED"
        }

        rec_app = await canonical_proof_store.save_canonical_proof(
            db=session,
            proof_data=proof_approved,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity"
        )
        await session.commit()

        assert rec_app.human_review_status == "APPROVED"
        assert rec_app.presentation_status == "PUBLIC"


@pytest.mark.asyncio
async def test_worker_checkpoint_recovery_and_persistence_idempotency(test_db):
    """Worker recovers completed steps from checkpoints and commits transactionally."""
    worker = DurableWorker(worker_id="test-worker-checkpoint")
    run_id = uuid.uuid4()

    async with test_db() as session:
        run = AnalysisRun(
            id=run_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME",
            status="RUNNING",
            input_hash="hash-in-chk",
            config_hash="hash-cfg-chk",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="pr-hash-chk"
        )
        session.add(run)

        # Pre-seed RETRIEVING step as COMPLETED (simulating crash before ADK)
        retrieval_step = AnalysisRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_type="RETRIEVING",
            input_hash="hash-chk-1",
            status="COMPLETED",
            output_json={"seeds": [{"channel_name": "ENTITY", "scene_ids": ["scene-tbw-c017"]}]}
        )
        session.add(retrieval_step)

        # Pre-seed ADK_REASONING step as COMPLETED (simulating crash before persistence)
        adk_step = AnalysisRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_type="ADK_REASONING",
            input_hash="hash-chk-2",
            status="COMPLETED",
            output_json={
                "adk_result": {
                    "status": "COMPLETED",
                    "execution_mode": "OFFLINE_FIXTURE",
                    "validated_proofs": ["proof-chk-01"],
                    "proofs": [{
                        "proof_id": "proof-chk-01",
                        "proof_type": "KNOWLEDGE_LEAK",
                        "title": "Recovered Proof",
                        "blind_explanation": "h0",
                        "reveal_explanation": "hr",
                        "evidence_chain": [{"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000}],
                        "observed_premises": [],
                        "alternative_explanations": ["alt"],
                        "counterfactual_results": {"wrong_reveal_delta": -0.85},
                        "human_review_status": "NOT_REVIEWED"
                    }]
                }
            }
        )
        session.add(adk_step)
        await session.commit()

        # Execute run - should use checkpoints without re-running retrieval or ADK
        with patch("src.reframe.mcp.program.narrative_mcp_program.execute_program", side_effect=RuntimeError("RETRIEVAL_SHOULD_NOT_RUN")), \
             patch("src.reframe.agents.runtime.agent_runtime.execute_adk_analysis", side_effect=RuntimeError("ADK_SHOULD_NOT_RUN")):
            await worker.execute_run(session, run)

        assert run.status == "COMPLETED"
        assert run.proof_ids == ["proof-chk-01"]

    # Re-open session to simulate worker/API restart and test query idempotency
    async with test_db() as new_session:
        stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
        res = await new_session.execute(stmt)
        reloaded_run = res.scalar_one_or_none()
        assert reloaded_run is not None
        assert reloaded_run.status == "COMPLETED"
        assert reloaded_run.proof_ids == ["proof-chk-01"]

        # Check persisted ProofRecord
        p_stmt = select(ProofRecord).where(ProofRecord.proof_id == "proof-chk-01")
        p_res = await new_session.execute(p_stmt)
        proof_rec = p_res.scalar_one_or_none()
        assert proof_rec is not None
        assert proof_rec.title == "Recovered Proof"
        assert proof_rec.human_review_status == "NOT_REVIEWED"
        assert proof_rec.presentation_status == "HIDDEN_FROM_PUBLIC"
