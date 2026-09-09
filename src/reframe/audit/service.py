"""
Reframe V7 Transactional Outbox & Audit Logging Service
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
import structlog

from src.reframe.audit.models import AuditLog, OutboxEvent
from src.reframe.shared.redis_client import redis_client

logger = structlog.get_logger(__name__)


class AuditService:
    @staticmethod
    async def log_action(
        db: AsyncSession,
        actor_type: str,
        actor_id: str,
        action: str,
        subject_type: str,
        subject_id: str,
        before_hash: Optional[str] = None,
        after_hash: Optional[str] = None,
        safe_metadata: Optional[Dict[str, Any]] = None
    ) -> AuditLog:
        entry = AuditLog(
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            subject_type=subject_type,
            subject_id=subject_id,
            before_hash=before_hash,
            after_hash=after_hash,
            safe_metadata=safe_metadata or {},
            created_at=datetime.now(timezone.utc)
        )
        db.add(entry)
        await db.flush()
        return entry

    record_audit_log = log_action

    @staticmethod
    async def emit_outbox_event(
        db: AsyncSession,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: Dict[str, Any]
    ) -> OutboxEvent:
        event = OutboxEvent(
            id=uuid.uuid4(),
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            status="PENDING",
            attempts=0,
            available_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc)
        )
        db.add(event)
        await db.flush()
        return event

    @staticmethod
    async def process_pending_outbox_events(db: AsyncSession, batch_size: int = 50) -> int:
        stmt = (
            select(OutboxEvent)
            .where(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.created_at.asc())
            .limit(batch_size)
        )
        res = await db.execute(stmt)
        events = res.scalars().all()

        processed_count = 0
        for event in events:
            try:
                # Fan out to Redis pub/sub for SSE / websocket
                channel = f"outbox:{event.aggregate_type}:{event.aggregate_id}"
                msg = json.dumps({
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "payload": event.payload
                })
                await redis_client.publish(channel, msg)

                event.status = "DELIVERED"
                event.delivered_at = datetime.now(timezone.utc)
                processed_count += 1
            except Exception as e:
                logger.error("Failed processing outbox event", event_id=str(event.id), error=str(e))
                event.attempts += 1
                if event.attempts >= 5:
                    event.status = "FAILED"

        await db.flush()
        return processed_count


audit_service = AuditService()
