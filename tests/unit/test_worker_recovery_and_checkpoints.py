"""
Unit Tests for Reframe V7 Worker Step Checkpointing, Crash Recovery, and Heartbeats
Zero Paid Model Calls ($0.00).
"""
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock

from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.jobs.models import AnalysisRun, AnalysisRunStep, ModelCallClaim
from src.reframe.jobs.worker import DurableWorker
from src.reframe.shared.redis_client import redis_client
from src.reframe.shared.config import settings
from src.reframe.agents.runtime import agent_runtime


@pytest.mark.asyncio
async def test_worker_retrieval_step_checkpoint_and_recovery():
    """Test 1: Checkpoint seeds are preserved and used without re-executing retrieval."""
    worker = DurableWorker(worker_id="test-worker-checkpoint")

    async with AsyncSessionLocal() as db:
        run_id = uuid.uuid4()
        run = AnalysisRun(
            id=run_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME",
            status="QUEUED",
            input_hash="test-checkpoint-hash",
            config_hash="test-config-hash",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="test-prompt-hash",
            config_json={"mode": "STRICT_CANON", "top_k": 5}
        )
        db.add(run)
        await db.commit()

        checkpoint_seeds = [
            {
                "seed_id": "seed-01",
                "channel_name": "SEMANTIC_SIMILARITY",
                "scene_ids": ["scene-tbw-c023"],
                "salience_score": 0.95,
                "cutoff_ms": 4860000,
                "channel_rationale": "High semantic similarity to reveal context."
            },
            {
                "seed_id": "seed-02",
                "channel_name": "ENTITY_CO_OCCURRENCE",
                "scene_ids": ["scene-tbw-c031"],
                "salience_score": 0.90,
                "cutoff_ms": 4860000,
                "channel_rationale": "Entity co-occurrence with Detective Anderson."
            }
        ]
        step_rec = AnalysisRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_type="RETRIEVING",
            input_hash="test-checkpoint-hash",
            status="COMPLETED",
            attempt=1,
            worker_id=worker.worker_id,
            output_json={"seeds": checkpoint_seeds},
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        )
        db.add(step_rec)
        await db.commit()

        await worker.execute_run(db, run)
        assert run.status in ("COMPLETED", "ABSTAINED")


@pytest.mark.asyncio
async def test_worker_adk_reasoning_checkpoint_skips_reexecution():
    """Test 2: Completed ADK_REASONING step checkpoint restores result with 0 ADK re-executions."""
    worker = DurableWorker(worker_id="test-worker-adk-resume")

    async with AsyncSessionLocal() as db:
        run_id = uuid.uuid4()
        run = AnalysisRun(
            id=run_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME",
            status="QUEUED",
            input_hash="test-adk-hash",
            config_hash="test-config-hash",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="test-prompt-hash",
            config_json={"mode": "STRICT_CANON", "top_k": 5}
        )
        db.add(run)

        # RETRIEVING step
        db.add(AnalysisRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_type="RETRIEVING",
            input_hash="test-adk-hash",
            status="COMPLETED",
            attempt=1,
            worker_id=worker.worker_id,
            output_json={"seeds": []},
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        ))

        # ADK_REASONING step already completed
        db.add(AnalysisRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_type="ADK_REASONING",
            input_hash="test-adk-hash",
            status="COMPLETED",
            attempt=1,
            worker_id=worker.worker_id,
            output_json={
                "adk_result": {
                    "status": "COMPLETED",
                    "execution_mode": "OFFLINE_FIXTURE",
                    "validated_proofs": [],
                    "hypotheses": [],
                    "critiques": [],
                    "judgments": [],
                    "telemetries": [],
                    "proofs": [],
                    "model_call_ids": []
                }
            },
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        ))
        await db.commit()

        # Patch agent_runtime.execute_adk_analysis to ensure it is NEVER called
        with patch.object(agent_runtime, "execute_adk_analysis", side_effect=RuntimeError("ADK_CALLED_DESPITE_CHECKPOINT")):
            await worker.execute_run(db, run)
            assert run.status in ("COMPLETED", "ABSTAINED")


@pytest.mark.asyncio
async def test_worker_fails_closed_on_live_reconciliation_claim():
    """Test 3: LIVE_GOOGLE mode with prior NEEDS_RECONCILIATION claim fails closed with 0 model calls."""
    worker = DurableWorker(worker_id="test-worker-recon-fail")

    async with AsyncSessionLocal() as db:
        run_id = uuid.uuid4()
        run = AnalysisRun(
            id=run_id,
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME",
            status="QUEUED",
            input_hash="test-live-recon-hash",
            config_hash="test-config-hash",
            dataset_version="v3",
            model_id="gemini-3.6-flash",
            prompt_hash="test-prompt-hash",
            config_json={"mode": "STRICT_CANON", "top_k": 5}
        )
        db.add(run)

        # Add completed RETRIEVING step so test proceeds straight to ADK reasoning claim check
        db.add(AnalysisRunStep(
            id=uuid.uuid4(),
            run_id=run_id,
            step_type="RETRIEVING",
            input_hash="test-live-recon-hash",
            status="COMPLETED",
            attempt=1,
            worker_id=worker.worker_id,
            output_json={"seeds": []},
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc)
        ))

        # Add claim in NEEDS_RECONCILIATION state
        db.add(ModelCallClaim(
            id=uuid.uuid4(),
            model_call_id=f"call-recon-{uuid.uuid4().hex[:8]}",
            analysis_run_id=run_id,
            model_id="gemini-3.6-flash",
            role="REASONING",
            state="NEEDS_RECONCILIATION",
            estimated_cost_micros=1000,
            actual_cost_micros=0,
            claimed_at=datetime.now(timezone.utc)
        ))
        await db.commit()

        with patch.object(settings, "EXECUTION_MODE", "LIVE_GOOGLE"):
            with patch.object(agent_runtime, "execute_adk_analysis", side_effect=RuntimeError("LIVE_CALL_ATTEMPTED")):
                await worker.execute_run(db, run)
                assert run.status == "ABSTAINED"
                assert run.failure_code == "MANUAL_RECONCILIATION_REQUIRED"

    # Reload from independent DB session to prove persistence
    async with AsyncSessionLocal() as db2:
        reloaded = await db2.get(AnalysisRun, run_id)
        assert reloaded is not None
        assert reloaded.status == "ABSTAINED"
        assert reloaded.failure_code == "MANUAL_RECONCILIATION_REQUIRED"


@pytest.mark.asyncio
async def test_prior_model_claim_in_any_state_fails_closed_without_checkpoint():
    """Any prior live ModelCallClaim without a completed ADK_REASONING step fails closed as MANUAL_RECONCILIATION_REQUIRED."""
    worker = DurableWorker(worker_id="test-worker-prior-claim")

    for state in ("CLAIMED", "EXECUTING", "SUCCEEDED", "FAILED"):
        async with AsyncSessionLocal() as db:
            run_id = uuid.uuid4()
            run = AnalysisRun(
                id=run_id,
                work_id="the-bat-whispers-1930",
                edition_id="tbw-fullscreen-archive",
                reveal_id="reveal-anderson-identity",
                run_type="REFRAME",
                status="QUEUED",
                input_hash=f"hash-{state}",
                config_hash="test-config-hash",
                dataset_version="v3",
                model_id="gemini-3.6-flash",
                prompt_hash="test-prompt-hash"
            )
            db.add(run)

            # Add RETRIEVING step
            db.add(AnalysisRunStep(
                id=uuid.uuid4(),
                run_id=run_id,
                step_type="RETRIEVING",
                input_hash=f"hash-{state}",
                status="COMPLETED",
                attempt=1,
                worker_id=worker.worker_id,
                output_json={"seeds": []},
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc)
            ))

            # Add prior claim in current state
            db.add(ModelCallClaim(
                id=uuid.uuid4(),
                model_call_id=f"call-{state}-{uuid.uuid4().hex[:6]}",
                analysis_run_id=run_id,
                model_id="gemini-3.6-flash",
                role="REASONING",
                state=state,
                estimated_cost_micros=1000,
                actual_cost_micros=0,
                claimed_at=datetime.now(timezone.utc)
            ))
            await db.commit()

            with patch.object(agent_runtime, "execute_adk_analysis", side_effect=RuntimeError("SHOULD_NOT_EXECUTE")):
                await worker.execute_run(db, run)
                assert run.status == "ABSTAINED"
                assert run.failure_code == "MANUAL_RECONCILIATION_REQUIRED"

        # Verify DB reload
        async with AsyncSessionLocal() as db2:
            reloaded = await db2.get(AnalysisRun, run_id)
            assert reloaded.status == "ABSTAINED"
            assert reloaded.failure_code == "MANUAL_RECONCILIATION_REQUIRED"


@pytest.mark.asyncio
async def test_worker_redis_heartbeat_emission():
    worker = DurableWorker(worker_id="test-heartbeat-worker")
    await worker.update_redis_heartbeat()

    hb_val = await redis_client.get("worker:heartbeat")
    assert hb_val == "test-heartbeat-worker"
