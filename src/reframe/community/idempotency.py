"""Transaction-scoped idempotency for comment creation. Never commits partial work."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from src.reframe.jobs.models import IdempotencyRecord


async def reserve_comment_request(db, principal, route, key, payload):
    if not key:
        return None, None
    digest = hashlib.sha256(payload.encode()).hexdigest()
    existing = (await db.execute(select(IdempotencyRecord).where(
        IdempotencyRecord.principal_id == str(principal),
        IdempotencyRecord.route_key == route,
        IdempotencyRecord.idempotency_key == key,
    ))).scalar_one_or_none()
    if existing:
        if existing.request_hash != digest:
            raise HTTPException(409, "This request key was already used for different content")
        return None, json.loads(existing.response_body_ref)
    marker = IdempotencyRecord(
        principal_id=str(principal), route_key=route, idempotency_key=key,
        request_hash=digest, response_status=201, response_body_ref="{}",
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(marker)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "This comment is already being posted. Retry to read the result.")
    return marker, None


async def finish_comment_request(db, marker, response):
    if marker:
        marker.response_body_ref = json.dumps(response)
    await db.commit()
    return response
