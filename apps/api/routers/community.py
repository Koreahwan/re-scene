"""
Reframe V7 Community API Router
Implements evidence-native community posts, counterclaims, comments, reactions, and moderation reports (R3-14 / R3-15).
Centralized CSRF and XSS protection.
Zero Paid Model Calls.
"""
import uuid
import html
import hashlib
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import structlog

from src.reframe.shared.database import get_db
from src.reframe.identity.auth import get_authenticated_user, get_viewer_context, enforce_csrf, ViewerContext
from src.reframe.community.service import community_service
from src.reframe.community.models import Post, PostVersion, Comment
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, SpoilerVisibility
from src.reframe.community.schemas import (
    CreatePostRequest,
    CreateCounterclaimRequest,
    AddReactionRequest
)

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/community", tags=["Evidence-Native Community"])


async def validate_content_scope(db, work_id, edition_id, cutoff):
    from src.reframe.catalog.service import catalog_service
    from src.reframe.catalog.top_box import release_by_work
    external = await release_by_work(db, work_id) if work_id.startswith('topbox-') else None
    registered = catalog_service.get_film_entry(work_id, edition_id)
    if external:
        runtime = external['runtime_ms']
        expected_edition = external['edition_id']
    elif registered:
        runtime = registered['runtime_ms']
        expected_edition = registered['edition_id']
    elif catalog_service.get_film_entry(work_id):
        raise HTTPException(422, 'Edition does not belong to this film')
    else:
        from src.reframe.catalog.repository import FilmCatalogRepository
        film = await FilmCatalogRepository.get_film_by_id(db, work_id)
        if not film:
            raise HTTPException(422, 'Unknown film')
        runtime = film.runtime_minutes * 60000 if film.runtime_minutes else 0
        expected_edition = f'{film.movie_id}-catalog'
    if edition_id != expected_edition:
        raise HTTPException(422, 'Edition does not belong to this film')
    if cutoff is not None and cutoff > runtime:
        raise HTTPException(422, 'Spoiler cutoff exceeds film runtime')


class PutReactionRequest(BaseModel):
    reaction_type: str = "LIKE"
    liked: bool = True


@router.get('/top-box/{page_id}/review-target')
async def top_box_review_target(page_id: int, response: Response, db: AsyncSession = Depends(get_db), viewer: ViewerContext = Depends(get_viewer_context)):
    from src.reframe.catalog.top_box import release_by_page
    release = await release_by_page(db, page_id)
    if not release:
        raise HTTPException(404, 'This exact release is not verified for reviews yet')
    response.headers['Cache-Control'] = 'private, no-store'
    own = await db.scalar(select(Post.id).join(PostVersion, Post.current_version_id == PostVersion.id).where(
        Post.work_id == release['work_id'], Post.author_id == viewer.user_id,
        Post.status == 'PUBLISHED', PostVersion.rating.is_not(None)).limit(1)) if viewer.is_authenticated else None
    release['own_post_id'] = str(own) if own else None
    return {'data': release}


class UpdatePostRequest(BaseModel):
    expected_version: int = 1
    title: Optional[str] = Field(default=None, max_length=255)
    body_markdown: Optional[str] = Field(default=None, max_length=10000)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    author_cutoff_ms: Optional[int] = Field(default=None, ge=0)
    contains_spoilers: Optional[bool] = None


class UpdateCommentRequest(BaseModel):
    expected_version: int = 1
    body_markdown: str = Field(min_length=1, max_length=2000)
    author_cutoff_ms: Optional[int] = Field(default=None, ge=0)
    contains_spoilers: Optional[bool] = None


class CreateCommentRequest(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=2000)
    comment_type: str = "COMMENT"
    parent_comment_id: Optional[uuid.UUID] = None
    author_cutoff_ms: Optional[int] = Field(default=None, ge=0)
    contains_spoilers: bool = False


class CreateReportRequest(BaseModel):
    subject_type: str  # post, comment, counterclaim
    subject_id: uuid.UUID
    category: str  # SPOILER, HARASSMENT, FALSE_EVIDENCE, OFF_TOPIC
    description: Optional[str] = None


@router.post("/posts", status_code=status.HTTP_201_CREATED)
async def create_post(
    req: CreatePostRequest,
    idempotency_key: Optional[str] = Header(default=None, alias='Idempotency-Key', max_length=128),
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new evidence-native community post.
    """
    if req.content_type == "MAGAZINE_ARTICLE" and not viewer.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can create or publish magazine articles"
        )
    if not viewer.is_admin and req.content_type not in ('FAN_THEORY', 'REVIEW'):
        raise HTTPException(403, 'Only administrators can publish analysis or editorial content')
    await validate_content_scope(db, req.work_id, req.edition_id, req.author_cutoff_ms)
    marker = None
    if idempotency_key:
        from src.reframe.jobs.models import IdempotencyRecord
        digest = hashlib.sha256(req.model_dump_json().encode()).hexdigest()
        marker = (await db.execute(select(IdempotencyRecord).where(
            IdempotencyRecord.principal_id == str(viewer.user_id),
            IdempotencyRecord.route_key == 'POST:/community/posts',
            IdempotencyRecord.idempotency_key == idempotency_key))).scalar_one_or_none()
        if marker:
            if marker.request_hash != digest:
                raise HTTPException(409, 'Idempotency key already used for different content')
            return json.loads(marker.response_body_ref)
        marker = IdempotencyRecord(principal_id=str(viewer.user_id),route_key='POST:/community/posts',
            idempotency_key=idempotency_key,request_hash=digest,response_status=201,response_body_ref='{}',
            expires_at=datetime.now(timezone.utc)+timedelta(days=1))
        db.add(marker)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(409, 'Concurrent request with this idempotency key; retry to read its result')
    post = await community_service.create_post(db=db, user_id=viewer.user_id, req=req, commit=False)
    response = {
        "status": "SUCCESS",
        "data": {
            "post_id": str(post.id),
            "status": post.status,
            "published_at": post.published_at.isoformat() if post.published_at else None
        }
    }
    if marker:
        marker.response_body_ref = json.dumps(response)
    await db.commit()
    return response


@router.patch("/posts/{post_id}", status_code=status.HTTP_200_OK)
async def update_post(
    post_id: uuid.UUID,
    req: UpdatePostRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Post).where(Post.id == post_id).with_for_update()
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.content_type not in ("FAN_THEORY", "REVIEW") and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit magazine articles")
    if post.author_id != viewer.user_id and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own or public community posts")
    if post.status != "PUBLISHED" and not viewer.is_admin:
        raise HTTPException(404, "Post not found")
    await validate_content_scope(db, post.work_id, post.edition_id, req.author_cutoff_ms)

    ver_stmt = select(PostVersion).where(PostVersion.post_id == post.id).order_by(PostVersion.version_no.desc()).limit(1)
    ver_res = await db.execute(ver_stmt)
    latest_ver = ver_res.scalar_one_or_none()
    latest_ver_no = latest_ver.version_no if latest_ver else 1
    if req.expected_version != latest_ver_no:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: current version is {latest_ver_no}, expected {req.expected_version}"
        )

    new_title = req.title.strip() if req.title is not None else (latest_ver.title if latest_ver else "Untitled")
    new_body = req.body_markdown if req.body_markdown is not None else (latest_ver.body_markdown if latest_ver else "")
    if not new_title or not new_body.strip():
        raise HTTPException(422, "A title and nonblank review are required")
    if req.rating is not None and (latest_ver is None or latest_ver.rating is None):
        await community_service.claim_review_slot(db, post.author_id, post.work_id, post.id)
    new_version_no = latest_ver_no + 1
    now = datetime.now(timezone.utc)
    new_ver = PostVersion(
        id=uuid.uuid4(),
        post_id=post.id,
        version_no=new_version_no,
        title=html.escape(new_title),
        body_markdown=new_body,
        body_sanitized_html=f"<p>{html.escape(new_body)}</p>",
        created_by=viewer.user_id,
        rating=req.rating if req.rating is not None else (latest_ver.rating if latest_ver else None),
        author_cutoff_ms=req.author_cutoff_ms if req.author_cutoff_ms is not None else (latest_ver.author_cutoff_ms if latest_ver else None),
        contains_spoilers=req.contains_spoilers if req.contains_spoilers is not None else bool(latest_ver and latest_ver.contains_spoilers),
        inspection_status="UNVERIFIED_CALLS_DISABLED",
        created_at=now
    )
    db.add(new_ver)
    post.current_version_id = new_ver.id
    post.updated_at = now
    await db.flush()

    # Determine previous user cutoff
    prev_cutoff = 0
    if post.spoiler_scope_id:
        prev_scope = (await db.execute(select(SpoilerScope).where(SpoilerScope.id == post.spoiler_scope_id))).scalar_one_or_none()
        if prev_scope:
            prev_cutoff = prev_scope.minimum_progress_ms or 0
    if req.author_cutoff_ms is not None:
        prev_cutoff = max(prev_cutoff, req.author_cutoff_ms)

    from src.reframe.ai.inspection import spoiler_inspection_service
    insp_res = await spoiler_inspection_service.inspect_content(
        db=db,
        subject_id=post.id,
        version_no=new_version_no,
        raw_text=f"{new_title}\n{new_body}",
        user_cutoff_ms=prev_cutoff,
        work_id=post.work_id or "the-bat-whispers-1930",
        edition_id=post.edition_id or "tbw-fullscreen-archive"
    )
    await spoiler_inspection_service.apply_post_inspection_result(
        db=db,
        post_id=post.id,
        version_no=new_version_no,
        result=insp_res,
        user_cutoff_ms=prev_cutoff
    )
    await db.commit()
    return {"status": "SUCCESS", "data": {"post_id": str(post.id), "version_no": new_version_no, "inspection_status": insp_res.status}}


@router.delete("/posts/{post_id}", status_code=status.HTTP_200_OK)
async def delete_post(
    post_id: uuid.UUID,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Post).where(Post.id == post_id)
    res = await db.execute(stmt)
    post = res.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Post not found")
    if post.content_type not in ("FAN_THEORY", "REVIEW") and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete magazine articles")
    if post.author_id != viewer.user_id and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own or public community posts")

    post.status = "REMOVED"
    post.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "SUCCESS", "data": {"post_id": str(post.id), "status": "REMOVED"}}


@router.get("/posts")
async def list_posts(
    work_id: str = Query(default="the-bat-whispers-1930"),
    origin: Optional[str] = Query(default=None),
    sort: Optional[str] = Query(default="recent"),
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists community posts with server-side spoiler masking and stable sorting.
    """
    posts = await community_service.list_posts(db=db, viewer=viewer, work_id=work_id, origin=origin, sort=sort)
    return {"status": "SUCCESS", "data": posts}



@router.get("/posts/{post_id}")
async def get_post_detail(
    post_id: uuid.UUID,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves full post detail with claims, evidence links, and counterclaims.
    """
    detail = await community_service.get_post_detail(db=db, post_id=post_id, viewer=viewer)
    return {"status": "SUCCESS", "data": detail}


@router.post("/posts/{post_id}/counterclaims", status_code=status.HTTP_201_CREATED)
async def create_counterclaim(
    post_id: uuid.UUID,
    req: CreateCounterclaimRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a structured rebuttal/counterclaim against a specific claim on the post.
    """
    cc = await community_service.create_counterclaim(db=db, post_id=post_id, user_id=viewer.user_id, req=req)
    return {
        "status": "SUCCESS",
        "data": {
            "counterclaim_id": str(cc.id),
            "status": cc.status
        }
    }


@router.put("/posts/{post_id}/reactions", status_code=status.HTTP_200_OK)
async def put_reaction(
    post_id: uuid.UUID,
    req: PutReactionRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Sets desired state of reaction (liked=True/False), idempotent, returns latest state.
    """
    if req.liked:
        reaction = await community_service.add_reaction(
            db=db,
            subject_type="POST",
            subject_id=post_id,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type
        )
        return {"status": "SUCCESS", "data": {"reaction_type": req.reaction_type, "liked": True}}
    else:
        removed = await community_service.delete_reaction(
            db=db,
            subject_type="POST",
            subject_id=post_id,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type
        )
        return {"status": "SUCCESS", "data": {"reaction_type": req.reaction_type, "liked": False, "removed": removed}}


@router.post("/posts/{post_id}/reactions", status_code=status.HTTP_200_OK)
async def add_reaction(
    post_id: uuid.UUID,
    req: AddReactionRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Adds a structured reaction to the post (WELL_SUPPORTED, NEW_INSIGHT, etc.)
    """
    reaction = await community_service.add_reaction(
        db=db,
        subject_type="POST",
        subject_id=post_id,
        user_id=viewer.user_id,
        reaction_type=req.reaction_type
    )
    return {
        "status": "SUCCESS",
        "data": {
            "reaction_id": str(reaction.id),
            "reaction_type": reaction.reaction_type
        }
    }


@router.delete("/posts/{post_id}/reactions", status_code=status.HTTP_200_OK)
async def delete_reaction(
    post_id: uuid.UUID,
    reaction_type: str = Query(...),
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Removes a reaction from a post.
    """
    removed = await community_service.delete_reaction(
        db=db,
        subject_type="POST",
        subject_id=post_id,
        user_id=viewer.user_id,
        reaction_type=reaction_type
    )
    return {
        "status": "SUCCESS",
        "data": {"removed": removed}
    }


@router.post("/posts/{post_id}/comments", status_code=status.HTTP_201_CREATED)
async def create_comment(
    post_id: uuid.UUID,
    req: CreateCommentRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new comment on a community post.
    """
    from src.reframe.community.idempotency import reserve_comment_request, finish_comment_request
    marker, replay = await reserve_comment_request(db, viewer.user_id, f"POST:/posts/{post_id}/comments", idempotency_key, req.model_dump_json())
    if replay is not None:
        return replay
    comment = await community_service.create_comment(
        db=db,
        post_id=post_id,
        user_id=viewer.user_id,
        body_markdown=req.body_markdown,
        comment_type=req.comment_type,
        parent_comment_id=req.parent_comment_id,
        author_cutoff_ms=req.author_cutoff_ms,
        contains_spoilers=req.contains_spoilers,
        commit=False,
    )
    return await finish_comment_request(db, marker, {"status": "SUCCESS", "data": comment})


@router.get("/posts/{post_id}/comments", status_code=status.HTTP_200_OK)
async def list_comments(
    post_id: uuid.UUID,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists all comments for a community post.
    """
    comments = await community_service.list_comments(db=db, post_id=post_id, viewer=viewer)
    return {
        "status": "SUCCESS",
        "data": comments
    }


@router.get("/posts/{post_id}/comments/{comment_id}", status_code=status.HTTP_200_OK)
@router.get("/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def get_comment_detail(
    comment_id: uuid.UUID,
    post_id: Optional[uuid.UUID] = None,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Retrieves a single comment detail with publication verification and spoiler protection.
    """
    stmt = select(Comment).where(Comment.id == comment_id)
    if post_id:
        stmt = stmt.where(Comment.post_id == post_id)
    res = await db.execute(stmt)
    comment = res.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.status != "PUBLISHED" and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    parent_stmt = select(Post).where(Post.id == comment.post_id)
    parent_post = (await db.execute(parent_stmt)).scalar_one_or_none()
    if not parent_post or (parent_post.status != "PUBLISHED" and not viewer.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    curr_parent_id = comment.parent_comment_id
    while curr_parent_id:
        parent_comment = (await db.execute(select(Comment).where(Comment.id == curr_parent_id))).scalar_one_or_none()
        if not parent_comment or (parent_comment.status not in ("PUBLISHED", "DELETED") and not viewer.is_admin):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
        curr_parent_id = parent_comment.parent_comment_id

    c_version = getattr(comment, "version_no", 1)
    comment_ref = f"COMMENT:{comment.id}:{c_version}"
    comment_is_author = bool(viewer.user_id and comment.author_id == viewer.user_id and not viewer.is_public_author)
    comment_unlocked = comment_ref in viewer.explicit_unlocks

    scope = None
    if comment.spoiler_scope_id:
        scope = (await db.execute(select(SpoilerScope).where(SpoilerScope.id == comment.spoiler_scope_id))).scalar_one_or_none()
    elif parent_post.spoiler_scope_id:
        scope = (await db.execute(select(SpoilerScope).where(SpoilerScope.id == parent_post.spoiler_scope_id))).scalar_one_or_none()

    progress_satisfied = False
    if scope:
        progress_visibility = evaluate_spoiler_visibility(scope, viewer, content_ref=None)
        progress_satisfied = (progress_visibility == SpoilerVisibility.VISIBLE)
        is_locked = (progress_visibility in (SpoilerVisibility.LOCKED, SpoilerVisibility.MASKED)) and not comment_is_author and not viewer.is_admin
    else:
        is_locked = False

    insp_status = getattr(comment, "inspection_status", "UNVERIFIED_CALLS_DISABLED")
    from src.reframe.community.comment_visibility import comment_masked
    if comment_masked(comment, viewer, is_locked, parent_post.work_id, parent_post.edition_id):
        body = "🔒 [Spoiler Comment Masked] Complete the reveal or confirm warning to view."
        masked = True
    else:
        body = comment.body_markdown
        masked = False

    return {
        "status": "SUCCESS",
        "data": {
            "comment_id": str(comment.id),
            "post_id": str(comment.post_id),
            "parent_comment_id": str(comment.parent_comment_id) if comment.parent_comment_id else None,
            "author_id": str(comment.author_id),
            "comment_type": comment.comment_type,
            "body_markdown": body,
            "version_no": c_version,
            "author_cutoff_ms": getattr(comment, "author_cutoff_ms", None),
            "contains_spoilers": comment.contains_spoilers,
            "inspection_status": insp_status,
            "can_reveal": comment.status == "PUBLISHED",
            "status": comment.status,
            "is_spoiler_masked": masked,
            "created_at": comment.created_at.isoformat()
        }
    }


@router.patch("/posts/{post_id}/comments/{comment_id}", status_code=status.HTTP_200_OK)
@router.patch("/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def update_comment(
    comment_id: uuid.UUID,
    req: UpdateCommentRequest,
    post_id: Optional[uuid.UUID] = None,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Comment).where(Comment.id == comment_id).with_for_update()
    if post_id:
        stmt = stmt.where(Comment.post_id == post_id)
    res = await db.execute(stmt)
    comment = res.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.status != "PUBLISHED" and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.author_id != viewer.user_id and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own or public comments")

    current_ver = getattr(comment, "version_no", 1)
    if req.expected_version != current_ver:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Version conflict: current version is {current_ver}, expected {req.expected_version}"
        )

    clean_body = req.body_markdown
    if not clean_body.strip():
        raise HTTPException(422, "A comment cannot be blank")
    new_version_no = current_ver + 1
    comment.version_no = new_version_no
    comment.body_markdown = clean_body
    comment.body_sanitized_html = f"<p>{html.escape(clean_body)}</p>"
    if req.contains_spoilers is not None:
        comment.contains_spoilers = req.contains_spoilers
    comment.inspection_status = "UNVERIFIED_CALLS_DISABLED"
    comment.updated_at = datetime.now(timezone.utc)
    await db.flush()

    # Determine parent post cutoff
    parent_post = (await db.execute(select(Post).where(Post.id == comment.post_id))).scalar_one_or_none()
    post_cutoff = 0
    if parent_post and parent_post.spoiler_scope_id:
        parent_scope = (await db.execute(select(SpoilerScope).where(SpoilerScope.id == parent_post.spoiler_scope_id))).scalar_one_or_none()
        if parent_scope:
            post_cutoff = parent_scope.minimum_progress_ms or 0

    if req.author_cutoff_ms is not None:
        comment.author_cutoff_ms = req.author_cutoff_ms
        post_cutoff = max(post_cutoff, req.author_cutoff_ms)

    from src.reframe.community.comment_moderation import enqueue_comment
    # Reset inherited scope after editing: a stale AI cutoff cannot govern the new version.
    comment.spoiler_scope_id = parent_post.spoiler_scope_id if parent_post else None
    enqueue_comment(db, comment)
    await db.commit()
    return {"status": "SUCCESS", "data": {"comment_id": str(comment.id), "version_no": new_version_no, "inspection_status": comment.inspection_status}}


@router.put("/comments/{comment_id}/reactions", status_code=status.HTTP_200_OK)
async def put_comment_reaction(
    comment_id: uuid.UUID,
    req: PutReactionRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Comment).where(Comment.id == comment_id)
    comment = (await db.execute(stmt)).scalar_one_or_none()
    if not comment or (comment.status != "PUBLISHED" and not viewer.is_admin):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")

    if req.liked:
        await community_service.add_reaction(
            db=db,
            subject_type="COMMENT",
            subject_id=comment_id,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type
        )
        return {"status": "SUCCESS", "data": {"reaction_type": req.reaction_type, "liked": True}}
    else:
        removed = await community_service.delete_reaction(
            db=db,
            subject_type="COMMENT",
            subject_id=comment_id,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type
        )
        return {"status": "SUCCESS", "data": {"reaction_type": req.reaction_type, "liked": False, "removed": removed}}


@router.delete("/posts/{post_id}/comments/{comment_id}", status_code=status.HTTP_200_OK)
@router.delete("/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_comment(
    comment_id: uuid.UUID,
    post_id: Optional[uuid.UUID] = None,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Author deletion leaves a tombstone; moderator removal hides the branch.
    """
    stmt = select(Comment).where(Comment.id == comment_id).with_for_update()
    if post_id:
        stmt = stmt.where(Comment.post_id == post_id)
    res = await db.execute(stmt)
    comment = res.scalar_one_or_none()
    if not comment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Comment not found")
    if comment.author_id != viewer.user_id and not viewer.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only delete your own or public comments")

    # Author deletion preserves public replies; moderator removal still hides the branch.
    comment.status = "DELETED" if comment.author_id == viewer.user_id else "REMOVED"
    comment.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"status": "SUCCESS", "data": {"comment_id": str(comment.id), "status": comment.status}}


@router.post("/moderation/reports", status_code=status.HTTP_201_CREATED)
async def create_moderation_report(
    req: CreateReportRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    """
    Submits a moderation report for a post, comment, or counterclaim.
    """
    report = await community_service.create_moderation_report(
        db=db,
        reporter_id=viewer.user_id,
        subject_type=req.subject_type,
        subject_id=req.subject_id,
        category=req.category,
        description=req.description
    )
    return {
        "status": "SUCCESS",
        "data": report
    }


@router.get("/moderation/reports", status_code=status.HTTP_200_OK)
async def list_moderation_reports(
    viewer: ViewerContext = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Lists moderation reports (Admin or Moderator only).
    """
    reports = await community_service.list_moderation_reports(db=db, viewer=viewer)
    return {
        "status": "SUCCESS",
        "data": reports
    }
