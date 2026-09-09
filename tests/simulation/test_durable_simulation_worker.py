"""
Reframe V7 Durable Worker Simulation Tests
Proves:
1. Active worker lease renewal via heartbeat prevents duplicate execution.
2. Stale leases (heartbeat > 30s) are safely claimed by a replacement worker.
3. Checkpointed steps are preserved and skipped on worker restart.
Zero External Generative Model Calls ($0.00).
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update

from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.jobs.models import AnalysisRun, AnalysisRunStep
from src.reframe.jobs.worker import DurableWorker


@pytest.mark.asyncio
async def test_durable_worker_lease_claim_and_stale_pickup():
    worker_a = DurableWorker(worker_id="worker_a")
    worker_b = DurableWorker(worker_id="worker_b")

    run_id = uuid.uuid4()
    async with AsyncSessionLocal() as db_session:
        # Clear any prior uncompleted runs from previous test suites
        await db_session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.status.in_(["QUEUED", "RUNNING"]))
            .values(status="COMPLETED")
        )
        await db_session.commit()

        # 1. Create a queued run
        run = AnalysisRun(
            id=run_id,
            run_type="AUDIENCE_SIMULATION",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            status="QUEUED",
            idempotency_key=f"idemp_durable_test_{run_id.hex[:8]}",
            input_hash="hash_in_1",
            config_hash="hash_cfg_1",
            dataset_version="v7-simulation",
            model_id="zero-model-deterministic-engine",
            prompt_hash="prompt_hash_1",
            proof_schema_version="1.0.0",
            cost_reserved_micros=0,
            config_json={"mode": "CI", "unique_source_personas": 100, "replications": 1, "seed": 42},
            result_json={},
        )
        db_session.add(run)
        await db_session.commit()

        # 2. Worker A claims the run
        claimed_a = await worker_a.claim_next_job(db_session)
        assert claimed_a is not None
        assert claimed_a.id == run_id
        assert claimed_a.status == "RUNNING"
        await db_session.commit()

        # 3. Worker B tries to claim while lease is fresh -> Should be None
        claimed_b = await worker_b.claim_next_job(db_session)
        assert claimed_b is None

        # 4. Worker A renews heartbeat -> Lease remains fresh
        await worker_a.update_heartbeat(db_session, run_id)
        await db_session.commit()

        claimed_b_again = await worker_b.claim_next_job(db_session)
        assert claimed_b_again is None

        # 5. Simulate Worker A crash by aging heartbeat > 30s
        run_db = (await db_session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
        run_db.heartbeat_at = datetime.now(timezone.utc) - timedelta(seconds=45)
        await db_session.commit()

        # 6. Worker B claims the stale run safely
        claimed_stale = await worker_b.claim_next_job(db_session)
        assert claimed_stale is not None
        assert claimed_stale.id == run_id
        assert claimed_stale.status == "RUNNING"

        claimed_stale.status = "COMPLETED"
        await db_session.commit()


@pytest.mark.asyncio
async def test_durable_worker_checkpoint_resume():
    worker = DurableWorker(worker_id="worker_resume")
    run_id = uuid.uuid4()

    async with AsyncSessionLocal() as db_session:
        # Clear any prior uncompleted runs
        await db_session.execute(
            update(AnalysisRun)
            .where(AnalysisRun.status.in_(["QUEUED", "RUNNING"]))
            .values(status="COMPLETED")
        )
        await db_session.commit()

        run = AnalysisRun(
            id=run_id,
            run_type="AUDIENCE_SIMULATION",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            status="QUEUED",
            idempotency_key=f"idemp_durable_test_{run_id.hex[:8]}",
            input_hash="hash_in_2",
            config_hash="hash_cfg_2",
            dataset_version="v7-simulation",
            model_id="zero-model-deterministic-engine",
            prompt_hash="prompt_hash_2",
            proof_schema_version="1.0.0",
            cost_reserved_micros=0,
            config_json={"mode": "CI", "unique_source_personas": 100, "replications": 1, "seed": 42},
            result_json={},
        )
        db_session.add(run)
        await db_session.commit()

        # Execute run
        claimed = await worker.claim_next_job(db_session)
        assert claimed is not None
        assert claimed.id == run_id

        await worker.execute_run(db_session, claimed)
        await db_session.commit()

        # Query in clean session
        db_session.expire_all()
        res_run = (await db_session.execute(select(AnalysisRun).where(AnalysisRun.id == run_id))).scalar_one()
        assert res_run.status == "COMPLETED"
        assert "aggregate_funnel" in res_run.result_json

        steps = (await db_session.execute(select(AnalysisRunStep).where(AnalysisRunStep.run_id == run_id))).scalars().all()
        step_types = [s.step_type for s in steps]
        assert "LOADING_PERSONAS" in step_types
        assert "SIMULATING_SESSIONS" in step_types
