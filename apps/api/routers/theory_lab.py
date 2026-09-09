"""
Reframe V7 Theory Lab API Router
Implements user theory drafting, immutable versioning, structured hypothesis validation runs, SSE events, and evidence-grounded publishing (R3-07 / R3-08).
Zero Paid Model Calls in offline mode.
"""
import uuid
import html
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import get_db
from src.reframe.identity.auth import get_authenticated_user, get_viewer_context, enforce_csrf, ViewerContext
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.jobs.models import AnalysisRun
from src.reframe.jobs.service import job_service
from src.reframe.cost.service import cost_service
from src.reframe.community.models import Post, PostVersion, Claim, ClaimVersion
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.evidence.adapter import v3_adapter

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Theory Lab"])


def sanitize_markdown_text(raw_text: str) -> str:
    """Escapes raw HTML and ensures safe markdown formatting (R2-12)."""
    return html.escape(raw_text.strip())


class CreateTheoryRequest(BaseModel):
    work_id: str = "the-bat-whispers-1930"
    edition_id: str = "tbw-fullscreen-archive"
    target_reveal_id: str
    title: str = Field(min_length=3, max_length=255)
    hypothesis_explanation: str = Field(min_length=10)
    cited_premise_scenes: List[str] = Field(default_factory=list)
    cited_event_ids: List[str] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)


class UpdateTheoryRequest(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    hypothesis_explanation: Optional[str] = Field(default=None, min_length=10)
    change_summary: Optional[str] = "Theory revision"
    target_reveal_id: Optional[str] = None


def theory_scope(work_id: str, edition_id: str, reveal_id: str) -> SpoilerScope:
    reveal = v3_adapter.get_reveal(reveal_id)
    if work_id != "the-bat-whispers-1930" or edition_id != "tbw-fullscreen-archive" or not reveal:
        raise HTTPException(status_code=400, detail="Unknown film edition or reveal")
    return SpoilerScope(
        id=uuid.uuid4(), work_id=work_id, edition_id=edition_id,
        minimum_progress_ms=reveal.timestamp_ms, required_reveal_ids=[reveal_id],
        severity="ENDING", safe_title="Fan theory (spoilers)",
        safe_preview="A fan theory analyzing narrative clues.",
    )


class CreateTheoryRunRequest(BaseModel):
    theory_id: uuid.UUID
    work_id: str = "the-bat-whispers-1930"
    edition_id: str = "tbw-fullscreen-archive"
    target_reveal_id: str


@router.post("/theories", status_code=status.HTTP_201_CREATED)
async def create_theory(
    req: CreateTheoryRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a structured Fan Theory draft with immutable PostVersion 1 (R3-07 / R3-08).
    """
    clean_title = sanitize_markdown_text(req.title)
    clean_body = sanitize_markdown_text(req.hypothesis_explanation)

    post_id = uuid.uuid4()
    scope = theory_scope(req.work_id, req.edition_id, req.target_reveal_id)
    db.add(scope)
    post = Post(
        id=post_id,
        author_id=viewer.user_id,
        work_id=req.work_id,
        edition_id=req.edition_id,
        content_type="FAN_THEORY",
        status="DRAFT",
        ai_disclosure="HUMAN",
        spoiler_scope_id=scope.id,
    )
    db.add(post)

    version_id = uuid.uuid4()
    version = PostVersion(
        id=version_id,
        post_id=post_id,
        version_no=1,
        title=clean_title,
        body_markdown=clean_body,
        body_sanitized_html=f"<p>{clean_body}</p>",
        change_summary="Initial Theory Draft",
        created_by=viewer.user_id
    )
    db.add(version)
    post.current_version_id = version_id

    claim_id = uuid.uuid4()
    claim = Claim(
        id=claim_id,
        post_id=post_id,
        status="ACTIVE"
    )
    db.add(claim)

    claim_ver_id = uuid.uuid4()
    claim_ver = ClaimVersion(
        id=claim_ver_id,
        claim_id=claim_id,
        text=clean_body,
        classification="STRONG_INTERPRETATION"
    )
    db.add(claim_ver)
    claim.current_version_id = claim_ver_id

    await db.commit()

    return {
        "data": {
            "theory_id": str(post_id),
            "status": post.status,
            "title": clean_title,
            "target_reveal_id": req.target_reveal_id,
            "version_no": 1
        },
        "meta": {}
    }


@router.get("/theories/{theory_id}")
async def get_theory(
    theory_id: uuid.UUID,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves theory draft with strict IDOR protection (R2-12).
    """
    stmt = select(Post).where(Post.id == theory_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()

    if not post:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Theory not found"
        )

    # IDOR Check: Unpublished drafts are visible only to author or admin
    if post.status != "PUBLISHED" and not viewer.is_admin and viewer.user_id != post.author_id:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="You do not have permission to view this private theory draft"
        )

    version = None
    scope = await db.get(SpoilerScope, post.spoiler_scope_id) if post.spoiler_scope_id else None
    if post.current_version_id:
        v_stmt = select(PostVersion).where(PostVersion.id == post.current_version_id)
        v_res = await db.execute(v_stmt)
        version = v_res.scalar_one_or_none()

    return {
        "data": {
            "theory_id": str(post.id),
            "target_reveal_id": scope.required_reveal_ids[0] if scope and scope.required_reveal_ids else None,
            "author_id": str(post.author_id),
            "work_id": post.work_id,
            "edition_id": post.edition_id,
            "status": post.status,
            "title": version.title if version else "",
            "body_markdown": version.body_markdown if version else "",
            "version_no": version.version_no if version else 1,
            "created_at": post.created_at.isoformat() if post.created_at else None
        },
        "meta": {}
    }


@router.patch("/theories/{theory_id}")
async def update_theory(
    theory_id: uuid.UUID,
    req: UpdateTheoryRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates an immutable new revision (PostVersion version_no + 1) for the theory (R3-08).
    Never mutates existing versions in place.
    """
    stmt = select(Post).where(and_(Post.id == theory_id, Post.author_id == viewer.user_id))
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Theory not found or unauthorized to edit"
        )

    if post.status == "PUBLISHED":
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Cannot mutate a published theory directly; submit a new revision."
        )

    current_version = None
    if post.current_version_id:
        v_stmt = select(PostVersion).where(PostVersion.id == post.current_version_id)
        v_res = await db.execute(v_stmt)
        current_version = v_res.scalar_one_or_none()

    next_version_no = (current_version.version_no + 1) if current_version else 2
    new_title = sanitize_markdown_text(req.title) if req.title else (current_version.title if current_version else "Untitled")
    new_body = sanitize_markdown_text(req.hypothesis_explanation) if req.hypothesis_explanation else (current_version.body_markdown if current_version else "")

    existing_scope = await db.get(SpoilerScope, post.spoiler_scope_id) if post.spoiler_scope_id else None
    same_target = not req.target_reveal_id or bool(existing_scope and req.target_reveal_id in existing_scope.required_reveal_ids)
    if current_version and new_title == current_version.title and new_body == current_version.body_markdown and same_target:
        return {"data": {"theory_id": str(post.id), "version_no": current_version.version_no, "status": post.status}, "meta": {}}

    new_version = PostVersion(
        id=uuid.uuid4(),
        post_id=post.id,
        version_no=next_version_no,
        title=new_title,
        body_markdown=new_body,
        body_sanitized_html=f"<p>{new_body}</p>",
        change_summary=req.change_summary or f"Revision v{next_version_no}",
        created_by=viewer.user_id
    )
    db.add(new_version)
    post.current_version_id = new_version.id

    if req.target_reveal_id:
        scope = theory_scope(post.work_id, post.edition_id, req.target_reveal_id)
        db.add(scope)
        post.spoiler_scope_id = scope.id

    # Counterclaims must target the same claim revision the author just saved.
    claims = (await db.execute(select(Claim).where(Claim.post_id == post.id))).scalars().all()
    for claim in claims:
        claim_version = ClaimVersion(id=uuid.uuid4(), claim_id=claim.id,
                                     text=new_body, classification="STRONG_INTERPRETATION")
        db.add(claim_version)
        claim.current_version_id = claim_version.id

    await db.commit()
    return {
        "data": {
            "theory_id": str(theory_id),
            "version_no": next_version_no,
            "status": post.status,
            "message": f"Theory revision v{next_version_no} created successfully"
        },
        "meta": {}
    }


@router.post("/theories/{theory_id}/publish")
async def publish_theory(
    theory_id: uuid.UUID,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Post).where(and_(Post.id == theory_id, Post.author_id == viewer.user_id))
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Theory not found or unauthorized to publish"
        )

    from src.reframe.community.models import SpoilerScope, PostEvidenceLink, EvidenceCatalog
    from src.reframe.evidence.adapter import v3_adapter
    from src.reframe.narrative.blindness import blind_alias

    if post.status == "PUBLISHED":
        return {"data": {"theory_id": str(post.id), "status": "PUBLISHED"}, "meta": {}}

    # Draft scope is authoritative, including drafts published without a run.
    target_reveal_id = None
    if post.spoiler_scope_id:
        draft_scope = await db.get(SpoilerScope, post.spoiler_scope_id)
        if draft_scope and draft_scope.required_reveal_ids:
            target_reveal_id = draft_scope.required_reveal_ids[0]
    run_stmt = select(AnalysisRun).where(
        AnalysisRun.owner_user_id == viewer.user_id
    ).order_by(AnalysisRun.created_at.desc())
    run_res = await db.execute(run_stmt)
    for r in run_res.scalars().all():
        if not target_reveal_id and r.config_json and r.config_json.get("theory_id") == str(theory_id):
            target_reveal_id = r.reveal_id
            break

    if not target_reveal_id:
        target_reveal_id = "reveal-anderson-identity"

    target_rev = v3_adapter.get_reveal(target_reveal_id)
    if not target_rev:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message=f"Cannot publish theory: target reveal '{target_reveal_id}' not found in canonical catalog"
        )

    # Derive max evidence screen timestamp
    max_evidence_screen_ms = target_rev.timestamp_ms
    required_reveals = [target_rev.reveal_id]

    # Fetch current version title for safe preview
    v_stmt = select(PostVersion).where(PostVersion.id == post.current_version_id)
    v_res = await db.execute(v_stmt)
    version = v_res.scalar_one_or_none()
    theory_title = version.title if version else "Theory"

    scope = SpoilerScope(
        id=uuid.uuid4(),
        work_id=post.work_id,
        edition_id=post.edition_id,
        minimum_progress_ms=max_evidence_screen_ms,
        required_reveal_ids=required_reveals,
        severity="ENDING" if max_evidence_screen_ms >= 4500000 else "MIDPOINT",
        safe_title=f"Fan Theory: {blind_alias.anonymize_text(theory_title)[:40]}...",
        safe_preview="A fan theory analyzing narrative clues."
    )
    db.add(scope)
    await db.flush()

    post.spoiler_scope_id = scope.id
    post.status = "PUBLISHED"
    post.published_at = datetime.now(timezone.utc)
    await db.commit()

    return {
        "data": {
            "theory_id": str(theory_id),
            "status": "PUBLISHED",
            "spoiler_scope_id": str(scope.id),
            "published_at": post.published_at.isoformat()
        },
        "meta": {}
    }


@router.post("/theory-runs", status_code=status.HTTP_202_ACCEPTED)
async def create_theory_validation_run(
    req: CreateTheoryRunRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db)
):
    if not idempotency_key:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Idempotency-Key header is mandatory for theory validation runs"
        )

    stmt = select(Post).where(Post.id == req.theory_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise ReframeException(status_code=404, code=ReframeErrorCodes.NOT_FOUND, message="Theory not found")

    # Enforce theory draft ownership / admin authorization (Task 8)
    if post.author_id != viewer.user_id and not viewer.is_admin:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Not authorized to submit validation runs for this private theory draft"
        )

    # Fetch current version
    v_stmt = select(PostVersion).where(PostVersion.id == post.current_version_id)
    v_res = await db.execute(v_stmt)
    version = v_res.scalar_one_or_none()

    theory_text = version.body_markdown if version else ""
    input_hash = hashlib.sha256(theory_text.encode("utf-8")).hexdigest()[:16]

    theory_config = {
        "theory_id": str(post.id),
        "post_version_id": str(version.id) if version else None,
        "theory_title": version.title if version else "",
        "theory_text": theory_text,
        "target_reveal_id": req.target_reveal_id,
        "input_hash": input_hash
    }

    if post.work_id != req.work_id or post.edition_id != req.edition_id:
        raise HTTPException(status_code=400, detail="Theory film edition does not match request")
    from src.reframe.spoiler.policy import evaluate_spoiler_visibility, SpoilerVisibility
    run_scope = theory_scope(req.work_id, req.edition_id, req.target_reveal_id)
    if evaluate_spoiler_visibility(run_scope, viewer) != SpoilerVisibility.VISIBLE:
        raise HTTPException(status_code=403, detail="Complete viewing this reveal before searching its scenes")

    # Budget Preflight
    if settings.PAID_CALLS_ENABLED and not settings.SPEND_KILL_SWITCH_ACTIVE:
        await cost_service.check_budget_preflight(db=db, user_id=viewer.user_id)

    run = await job_service.create_or_get_idempotent_run(
        db=db,
        principal_id=str(viewer.user_id),
        route_key="POST:/api/v1/theory-runs",
        idempotency_key=idempotency_key,
        work_id=req.work_id,
        edition_id=req.edition_id,
        reveal_id=req.target_reveal_id,
        run_type="THEORY_VALIDATION",
        owner_user_id=viewer.user_id,
        config=theory_config
    )
    await db.commit()

    return {
        "data": {
            "run_id": str(run.id),
            "status": run.status,
            "theory_id": str(req.theory_id),
            "events_url": f"/api/v1/theory-runs/{run.id}/events"
        },
        "meta": {"idempotency_key": idempotency_key}
    }


@router.get("/theory-runs/{run_id}")
async def get_theory_run_detail(
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
            message=f"Theory validation run '{run_id}' not found"
        )

    # IDOR Check (R2-12)
    if run.owner_user_id and not viewer.is_admin and viewer.user_id != run.owner_user_id:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="You do not have permission to inspect this private theory run"
        )

    # Read real persisted TheoryValidationResult from result_json
    result_data = run.result_json or {}
    validation_verdict = result_data.get("validation_verdict", "PENDING" if run.status in ("QUEUED", "RUNNING") else "ABSTAINED")
    grounding_score = result_data.get("grounding_score", 0.0)
    # Old persisted local runs predate explicit provenance. Do not relabel them
    # as semantic validation just because their old status says VALIDATED.
    mode = result_data.get("validation_mode", "LOCAL_KEYWORD_RETRIEVAL")
    if mode == "LOCAL_KEYWORD_RETRIEVAL" and run.status == "COMPLETED":
        validation_verdict = "RELATED_EVIDENCE" if result_data.get("supporting_evidence") else "NO_MATCH"
    evidence_details = []
    for evidence_id in result_data.get("supporting_evidence", []):
        event = v3_adapter.get_event(evidence_id) if isinstance(evidence_id, str) else None
        if event:
            evidence_details.append({"event_id": event.event_id, "scene_id": event.scene_id,
                                     "description": event.description, "timestamp_ms": event.timestamp_ms})

    return {
        "data": {
            "run_id": str(run.id),
            "status": run.status,
            "work_id": run.work_id,
            "target_reveal_id": run.reveal_id,
            "validation_verdict": validation_verdict,
            "grounding_score": grounding_score,
            "validation_mode": mode,
            "trust_namespace": result_data.get("trust_namespace", "ENGINE_INFERENCE"),
            "live_model_used": result_data.get("live_model_used", False),
            "supporting_evidence": result_data.get("supporting_evidence", []),
            "evidence_details": evidence_details,
            "uncertainty": result_data.get("uncertainty") if mode != "LOCAL_KEYWORD_RETRIEVAL" else None,
            "counterevidence": result_data.get("counterevidence", []),
            "missing_evidence": result_data.get("missing_evidence", []),
            "alternative_explanations": result_data.get("alternative_explanations", []),
            "counterfactual_results": {"status": "NOT_RUN"} if mode == "LOCAL_KEYWORD_RETRIEVAL" else result_data.get("counterfactual_results", {}),
            "created_at": run.created_at,
            "completed_at": run.completed_at
        },
        "meta": {}
    }


@router.get("/theory-runs/{run_id}/events")
async def stream_theory_run_events(
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
            message=f"Theory validation run '{run_id}' not found"
        )

    # IDOR Check (R2-12)
    if run.owner_user_id and not viewer.is_admin and viewer.user_id != run.owner_user_id:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="You do not have permission to stream this private theory run"
        )

    return StreamingResponse(
        job_service.stream_run_events(db, run_id, last_event_id),
        media_type="text/event-stream"
    )
