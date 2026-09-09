"""
Reframe V7 Durable Jobs & SSE Streaming Service
Implements durable state tracking, idempotency hashing, and multi-channel SSE event replay and streaming.
"""
import uuid
import hashlib
import json
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.exceptions import IdempotencyConflictException, ReframeException, ReframeErrorCodes
from src.reframe.shared.redis_client import redis_client
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.jobs.models import AnalysisRun, AnalysisRunStep, AnalysisRunEvent, IdempotencyRecord
from src.reframe.cost.service import cost_service
from src.reframe.audit.service import audit_service

logger = structlog.get_logger(__name__)


def compute_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class JobService:
    async def create_or_get_idempotent_run(
        self,
        db: AsyncSession,
        principal_id: str,
        route_key: str,
        idempotency_key: Optional[str],
        work_id: str,
        edition_id: str,
        reveal_id: Optional[str],
        run_type: str = "REFRAME",
        owner_user_id: Optional[uuid.UUID] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> AnalysisRun:
        input_payload = {
            "work_id": work_id,
            "edition_id": edition_id,
            "reveal_id": reveal_id,
            "run_type": run_type,
            "config": config or {}
        }
        input_hash = compute_hash(input_payload)
        config_hash = compute_hash(config or {})

        # Check idempotency record if key provided
        if idempotency_key:
            stmt = select(IdempotencyRecord).where(
                and_(
                    IdempotencyRecord.principal_id == principal_id,
                    IdempotencyRecord.route_key == route_key,
                    IdempotencyRecord.idempotency_key == idempotency_key
                )
            )
            res = await db.execute(stmt)
            existing_record = res.scalar_one_or_none()

            if existing_record:
                if existing_record.request_hash != input_hash:
                    raise IdempotencyConflictException(
                        f"Idempotency key '{idempotency_key}' was previously used with different request parameters"
                    )
                try:
                    run_uuid = uuid.UUID(existing_record.response_body_ref)
                    run_stmt = select(AnalysisRun).where(AnalysisRun.id == run_uuid)
                    run_res = await db.execute(run_stmt)
                    existing_run = run_res.scalar_one_or_none()
                    if existing_run:
                        return existing_run
                except ValueError:
                    pass

        # Create new AnalysisRun
        new_run_id = uuid.uuid4()
        run = AnalysisRun(
            id=new_run_id,
            run_type=run_type,
            owner_user_id=owner_user_id,
            work_id=work_id,
            edition_id=edition_id,
            reveal_id=reveal_id,
            status="QUEUED",
            idempotency_key=idempotency_key,
            input_hash=input_hash,
            config_hash=config_hash,
            dataset_version=settings.DEFAULT_DATASET_VERSION,
            model_id=settings.GEMINI_MODEL_ID,
            prompt_hash=compute_hash({"model": settings.GEMINI_MODEL_ID, "version": "v7"}),
            proof_schema_version="1.0.0",
            cost_reserved_micros=settings.MAX_BUDGET_MICROS_PER_RUN,
            proof_ids=[],
            config_json=config or {},
            result_json={},
            created_at=datetime.now(timezone.utc)

        )
        db.add(run)
        # The reservation lookup uses autoflush=False; persist this real run first.
        await db.flush()

        # Reserve cost preflight
        await cost_service.reserve_budget(
            db=db,
            analysis_run_id=new_run_id,
            user_id=owner_user_id
        )

        # Store initial event
        initial_event = AnalysisRunEvent(
            run_id=new_run_id,
            sequence=1,
            event_type="status",
            safe_payload={"status": "QUEUED", "work_id": work_id, "reveal_id": reveal_id},
            created_at=datetime.now(timezone.utc)
        )
        db.add(initial_event)

        # Save Idempotency Record if key provided
        if idempotency_key:
            idemp_rec = IdempotencyRecord(
                principal_id=principal_id,
                route_key=route_key,
                idempotency_key=idempotency_key,
                request_hash=input_hash,
                response_status=202,
                response_body_ref=str(new_run_id),
                expires_at=datetime.now(timezone.utc) + timedelta(seconds=settings.IDEMPOTENCY_EXPIRY_SECONDS)
            )
            db.add(idemp_rec)

        await db.flush()
        return run

    async def emit_run_event(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        event_type: str,
        payload: Dict[str, Any]
    ) -> AnalysisRunEvent:
        stmt = (
            select(AnalysisRunEvent.sequence)
            .where(AnalysisRunEvent.run_id == run_id)
            .order_by(AnalysisRunEvent.sequence.desc())
            .limit(1)
        )
        res = await db.execute(stmt)
        last_seq = res.scalar_one_or_none() or 0

        event = AnalysisRunEvent(
            run_id=run_id,
            sequence=last_seq + 1,
            event_type=event_type,
            safe_payload=payload,
            created_at=datetime.now(timezone.utc)
        )
        db.add(event)
        await db.flush()

        # Publish to Redis channel for live listeners
        channel = f"run_events:{run_id}"
        msg = json.dumps({
            "sequence": event.sequence,
            "event_type": event.event_type,
            "payload": payload
        })
        await redis_client.publish(channel, msg)
        return event

    async def stream_run_events(
        self,
        db: AsyncSession,
        run_id: uuid.UUID,
        last_event_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        """
        Durable SSE Stream:
        1. Replays past events from PostgreSQL starting after last_event_id.
        2. If run is already completed/failed, cleanly closes stream.
        3. If run is still active, polls for new events until completed or timed out.
        """
        current_seq = last_event_id or 0

        # Phase 1: Replay past events
        stmt = (
            select(AnalysisRunEvent)
            .where(
                and_(
                    AnalysisRunEvent.run_id == run_id,
                    AnalysisRunEvent.sequence > current_seq
                )
            )
            .order_by(AnalysisRunEvent.sequence.asc())
        )
        res = await db.execute(stmt)
        past_events = res.scalars().all()

        is_terminal = False
        for ev in past_events:
            current_seq = max(current_seq, ev.sequence)
            data = json.dumps(ev.safe_payload)
            yield f"id: {ev.sequence}\nevent: {ev.event_type}\ndata: {data}\n\n"
            if ev.event_type in ("completed", "error"):
                is_terminal = True

        if is_terminal:
            return

        # Phase 2: Stream live events until completion
        max_wait_seconds = 30
        poll_interval = 0.5
        waited = 0.0

        while not is_terminal and waited < max_wait_seconds:
            await asyncio.sleep(poll_interval)
            waited += poll_interval

            # Check new events using a fresh session
            async with AsyncSessionLocal() as poll_db:
                new_stmt = (
                    select(AnalysisRunEvent)
                    .where(
                        and_(
                            AnalysisRunEvent.run_id == run_id,
                            AnalysisRunEvent.sequence > current_seq
                        )
                    )
                    .order_by(AnalysisRunEvent.sequence.asc())
                )
                new_res = await poll_db.execute(new_stmt)
                new_events = new_res.scalars().all()

                for ev in new_events:
                    current_seq = max(current_seq, ev.sequence)
                    data = json.dumps(ev.safe_payload)
                    yield f"id: {ev.sequence}\nevent: {ev.event_type}\ndata: {data}\n\n"
                    if ev.event_type in ("completed", "error"):
                        is_terminal = True
                        break


job_service = JobService()
