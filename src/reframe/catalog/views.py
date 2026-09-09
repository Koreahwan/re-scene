"""Anonymous, retry-safe page views; no account, IP or user-agent is stored."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, Index, String, Uuid, case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.reframe.shared.database import Base
from src.reframe.shared.redis_client import redis_client


class ContentView(Base):
    __tablename__ = "content_views"
    kind = Column(String(16), primary_key=True)
    content_id = Column(String(64), primary_key=True)
    event_id = Column(Uuid, primary_key=True)
    viewed_at = Column(DateTime(timezone=True), nullable=False)
    __table_args__ = (Index("ix_content_views_lookup", "kind", "content_id", "viewed_at"),)


class ViewRequest(BaseModel):
    event_id: UUID


async def record_view(db, kind: str, content_id: str, event_id: UUID, request: Request):
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Cross-site view submissions are not accepted")
    # Content-scoped cap avoids collecting a visitor identifier or IP address.
    try:
        count = await redis_client.incr(f"page-views:{kind}:{content_id}", ex=60)
    except Exception:
        raise HTTPException(503, "View recording temporarily unavailable")
    if count > 120:
        raise HTTPException(429, "View recording rate limit reached")
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    statement = insert(ContentView).values(kind=kind, content_id=content_id,
        event_id=event_id, viewed_at=datetime.now(timezone.utc)).on_conflict_do_nothing()
    await db.execute(statement)
    await db.commit()
    return {"data": {"recorded": True}}


async def view_counts(db, kind: str, ids: list[str], now=None):
    if not ids:
        return {}
    now = now or datetime.now(timezone.utc)
    rows = (await db.execute(select(ContentView.content_id, func.count(),
        func.sum(case((ContentView.viewed_at >= now - timedelta(days=7), 1), else_=0)))
        .where(ContentView.kind == kind, ContentView.content_id.in_(ids), ContentView.viewed_at <= now)
        .group_by(ContentView.content_id))).all()
    return {content_id: {"view_count": total, "views_7d": recent} for content_id, total, recent in rows}
