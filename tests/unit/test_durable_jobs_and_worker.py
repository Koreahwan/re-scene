"""
Unit Tests for Durable Job Worker, Lease Heartbeats, and Cost Settlements
"""
import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select

from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.jobs.models import AnalysisRun, AnalysisRunStep
from src.reframe.jobs.service import job_service
from src.reframe.jobs.worker import DurableWorker
from src.reframe.cost.models import BudgetReservation
from src.reframe.audit.models import OutboxEvent



@pytest.mark.asyncio
async def test_durable_job_creation_and_worker_execution(monkeypatch):
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", False)
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", True)

    async with AsyncSessionLocal() as db:
        # 1. Create a run via job_service
        run = await job_service.create_or_get_idempotent_run(
            db=db,
            principal_id="test-user-01",
            route_key="POST:/api/v1/reframe-runs",
            idempotency_key=f"key-{uuid.uuid4().hex}",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            run_type="REFRAME"
        )
        await db.commit()
        run_id = run.id

        # Verify initial state and reservation
        res_stmt = select(BudgetReservation).where(BudgetReservation.analysis_run_id == run_id)
        res_res = await db.execute(res_stmt)
        reservation = res_res.scalar_one_or_none()
        assert reservation is not None
        assert reservation.status == "ACTIVE"

    # 2. Worker executes run
    test_worker = DurableWorker(worker_id="test-worker-unit-01")
    for _ in range(5):
        had_work = await test_worker.run_once()
        if not had_work:
            break

    # 3. Check post-execution state
    async with AsyncSessionLocal() as db:
        run_stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
        run_res = await db.execute(run_stmt)
        completed_run = run_res.scalar_one_or_none()
        assert completed_run is not None
        assert completed_run.status in ("COMPLETED", "ABSTAINED")
        assert completed_run.completed_at is not None


        # Check steps
        steps_stmt = select(AnalysisRunStep).where(AnalysisRunStep.run_id == run_id)
        steps_res = await db.execute(steps_stmt)
        steps = steps_res.scalars().all()
        assert len(steps) >= 2

        # Check budget settlement
        res_stmt = select(BudgetReservation).where(BudgetReservation.analysis_run_id == run_id)
        res_res = await db.execute(res_stmt)
        settled_res = res_res.scalar_one_or_none()
        assert settled_res.status == "SETTLED"

        # Check outbox events
        outbox_stmt = select(OutboxEvent).where(OutboxEvent.aggregate_id == str(run_id))
        outbox_res = await db.execute(outbox_stmt)
        outbox_event = outbox_res.scalar_one_or_none()
        assert outbox_event is not None
        assert outbox_event.event_type == "PROOF_COMPLETED"


@pytest.mark.asyncio
async def test_worker_crash_recovery_stale_lease(monkeypatch):
    monkeypatch.setattr(settings, "EXECUTION_MODE", "OFFLINE_FIXTURE")
    monkeypatch.setattr(settings, "PAID_CALLS_ENABLED", False)
    monkeypatch.setattr(settings, "SPEND_KILL_SWITCH_ACTIVE", True)


    async with AsyncSessionLocal() as db:
        # Create a run marked RUNNING but with expired heartbeat (crashed worker)
        stale_run = AnalysisRun(
            id=uuid.uuid4(),
            run_type="REFRAME",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            status="RUNNING",
            input_hash="stale_hash",
            config_hash="stale_config",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="prompt_hash",
            proof_schema_version="1.0.0",
            cost_reserved_micros=500000,
            proof_ids=[],
            created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            claimed_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            heartbeat_at=datetime.now(timezone.utc) - timedelta(minutes=5)  # 5 mins ago (> 30s cutoff)
        )
        db.add(stale_run)
        await db.commit()
        stale_id = stale_run.id


    # New worker should claim and recover the stale run
    recovery_worker = DurableWorker(worker_id="recovery-worker-01")
    claimed = await recovery_worker.run_once()
    assert claimed is True

    async with AsyncSessionLocal() as db:
        check_stmt = select(AnalysisRun).where(AnalysisRun.id == stale_id)
        check_res = await db.execute(check_stmt)
        recovered_run = check_res.scalar_one_or_none()
        assert recovered_run.status in ("COMPLETED", "ABSTAINED")
        assert recovered_run.completed_at is not None


@pytest.mark.asyncio
async def test_sse_streaming_replay_and_clean_termination():
    """SSE streaming must replay past events and terminate cleanly when a run is completed."""
    run_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        run = AnalysisRun(
            id=run_id,
            run_type="REFRAME",
            work_id="the-bat-whispers-1930",
            edition_id="tbw-fullscreen-archive",
            reveal_id="reveal-anderson-identity",
            status="COMPLETED",
            input_hash="hash_123",
            config_hash="cfg_123",
            dataset_version="v3",
            model_id="gemini-2.5-flash",
            prompt_hash="p_hash",
            proof_schema_version="1.0.0",
            created_at=datetime.now(timezone.utc)
        )
        db.add(run)
        await job_service.emit_run_event(db, run_id, "status", {"status": "QUEUED"})
        await job_service.emit_run_event(db, run_id, "step", {"step": "RETRIEVING"})
        await job_service.emit_run_event(db, run_id, "completed", {"status": "COMPLETED", "proof_ids": ["proof-01"]})
        await db.commit()

    # Stream events with last_event_id=None (replay all)
    async with AsyncSessionLocal() as db:
        stream_chunks = []
        async for chunk in job_service.stream_run_events(db, run_id, last_event_id=None):
            stream_chunks.append(chunk)

        assert len(stream_chunks) == 3
        assert "event: status" in stream_chunks[0]
        assert "event: step" in stream_chunks[1]
        assert "event: completed" in stream_chunks[2]

