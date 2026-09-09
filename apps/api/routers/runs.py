"""
Reframe V7 Reframe Runs & SSE Streaming Router
"""
import uuid
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Header, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from src.reframe.shared.database import get_db
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.identity.auth import get_authenticated_user, get_viewer_context, enforce_csrf, ViewerContext
from src.reframe.jobs.models import AnalysisRun
from src.reframe.jobs.service import job_service

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Reframe Runs"])


class CreateReframeRunRequest(BaseModel):
    movie_id: str = "the-bat-whispers-1930"
    edition_id: str = "tbw-fullscreen-archive"
    reveal_id: str
    mode: str = "STRICT_CANON"  # STRICT_CANON, DEEP_READING
    top_k: int = Field(default=5, ge=1, le=10)


@router.post("/reframe-runs", status_code=status.HTTP_202_ACCEPTED)
async def create_reframe_run(
    payload: CreateReframeRunRequest,
    request: Request,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Submits a durable reframe narrative analysis run.
    Strictly forbids client spoiler_cutoff_ms or SQL tampering.
    """
    if viewer.is_public_author or not viewer.is_admin:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Analysis execution is restricted to administrative operators"
        )

    if not idempotency_key:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Idempotency-Key header is mandatory for creating reframe analysis runs"
        )

    principal_id = str(viewer.user_id) if viewer.user_id else (request.client.host if request.client else "anonymous")
    route_key = "POST:/api/v1/reframe-runs"

    run = await job_service.create_or_get_idempotent_run(
        db=db,
        principal_id=principal_id,
        route_key=route_key,
        idempotency_key=idempotency_key,
        work_id=payload.movie_id,
        edition_id=payload.edition_id,
        reveal_id=payload.reveal_id,
        run_type="REFRAME",
        owner_user_id=viewer.user_id,
        config={"mode": payload.mode, "top_k": payload.top_k}
    )
    await db.commit()

    return {
        "data": {
            "run_id": str(run.id),
            "status": run.status,
            "events_url": f"/api/v1/reframe-runs/{run.id}/events"
        },
        "meta": {"idempotency_key": idempotency_key}
    }


@router.get("/reframe-runs/{run_id}", response_model=Dict[str, Any])
async def get_reframe_run(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()

    if not run:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Analysis run '{run_id}' not found"
        )

    # Check authorization if run has owner
    if run.owner_user_id and not viewer.is_admin and viewer.user_id != run.owner_user_id:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="You do not have permission to inspect this private analysis run"
        )

    return {
        "data": {
            "run_id": str(run.id),
            "run_type": run.run_type,
            "status": run.status,
            "work_id": run.work_id,
            "edition_id": run.edition_id,
            "reveal_id": run.reveal_id,
            "proof_ids": run.proof_ids or [],
            "error_code": run.failure_code,
            "created_at": run.created_at,
            "completed_at": run.completed_at
        },
        "meta": {}
    }



@router.get("/reframe-runs/{run_id}/events")
async def stream_reframe_run_events(
    run_id: uuid.UUID,
    last_event_id: Optional[int] = Header(None, alias="Last-Event-ID"),
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res = await db.execute(stmt)
    run = res.scalar_one_or_none()

    if not run:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Analysis run '{run_id}' not found"
        )

    if run.owner_user_id and not viewer.is_admin and viewer.user_id != run.owner_user_id:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="You do not have permission to stream this private analysis run"
        )

    return StreamingResponse(
        job_service.stream_run_events(db, run_id, last_event_id),
        media_type="text/event-stream"
    )

