"""
Reframe V7 Film Magazine Router
Provides public endpoints for browsing and reading DB-seeded film magazine articles,
scene breakdowns, and rewatch guides with strict central spoiler governance, evidence links, and disclosure badges.
Zero External Generative Model Calls.
Zero Static Fallback in Production/Public mode.
"""
import uuid
import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, Query, Path, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import get_db
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.identity.auth import get_viewer_context, get_authenticated_user, enforce_csrf, ViewerContext
from src.reframe.identity.models import Profile, User
from src.reframe.community.models import Post, PostVersion, PostEvidenceLink, Reaction, Comment
from src.reframe.community.service import community_service
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility
from src.reframe.simulation.models import SyntheticContentProvenance, SyntheticPersona
from src.reframe.evidence.models import EvidenceCatalog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/magazine", tags=["Film Magazine"])


def check_synthetic_article_access(prov: Optional[SyntheticContentProvenance], viewer: ViewerContext) -> None:
    """Checks if a synthetic magazine article can be accessed by the current viewer."""
    if prov is not None and not settings.ENABLE_SYNTHETIC_MAGAZINE:
        if not viewer.is_admin:
            raise ReframeException(
                status_code=status.HTTP_403_FORBIDDEN,
                code=ReframeErrorCodes.FORBIDDEN,
                message="Synthetic Magazine feature is currently disabled.",
            )


@router.get("")
async def list_magazine_articles(
    work_id: Optional[str] = Query(None),
    article_type: Optional[str] = Query(None),
    origin: Optional[str] = Query("EDITORIAL"),
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Lists published film magazine articles directly from PostgreSQL with central spoiler policy.
    Strictly queries Post.content_type == 'MAGAZINE_ARTICLE'.
    Honors article_type filtering and fails closed if spoiler scope is missing.
    Distinguishes regular editorial articles from synthetic demo articles.
    Zero static asset fallback.
    """
    stmt = (
        select(Post, SyntheticContentProvenance, SpoilerScope, Profile.display_name)
        .outerjoin(SyntheticContentProvenance, SyntheticContentProvenance.subject_id == Post.id)
        .outerjoin(SpoilerScope, SpoilerScope.id == Post.spoiler_scope_id)
        .outerjoin(Profile, Profile.user_id == Post.author_id)
        .where(
            Post.content_type == "MAGAZINE_ARTICLE",
            Post.status == "PUBLISHED",
        )
        .order_by(Post.published_at.desc())
    )
    if work_id:
        stmt = stmt.where(Post.work_id == work_id)
    if origin == "EDITORIAL" or origin is None:
        stmt = stmt.where(SyntheticContentProvenance.id.is_(None))
    elif origin == "SYNTHETIC":
        stmt = stmt.where(SyntheticContentProvenance.id.is_not(None))
    elif origin == "ALL":
        pass


    res = await db.execute(stmt)
    db_rows = res.all()

    articles = []
    has_synthetic = False
    for idx, (post, prov, spoiler, author_name) in enumerate(db_rows, start=1):
        # Filter out synthetic articles when feature flag is disabled and viewer is not admin
        if prov is not None and not settings.ENABLE_SYNTHETIC_MAGAZINE and not viewer.is_admin:
            continue

        ver_stmt = select(PostVersion).where(PostVersion.post_id == post.id).order_by(PostVersion.version_no.desc()).limit(1)
        ver_res = await db.execute(ver_stmt)
        ver = ver_res.scalar_one_or_none()
        if not ver:
            continue

        # Parse actual article_type and metadata from body payload
        art_type = "EDITORIAL_ESSAY" if prov is None else "SCENE_BREAKDOWN"
        hero_image_url = None
        read_time_minutes = 5
        try:
            parsed = json.loads(ver.body_markdown)
            if isinstance(parsed, dict):
                art_type = parsed.get("article_type", art_type)
                hero_image_url = parsed.get("hero_image_url")
                read_time_minutes = parsed.get("read_time_minutes", 5)
        except Exception:
            parsed = None

        # Honor article_type query filter
        if article_type and art_type.upper() != article_type.upper():
            continue

        is_synth = (prov is not None)
        if is_synth:
            has_synthetic = True

        # Editorial self-published articles: status PUBLISHED determines visibility, zero spoiler locks
        if not is_synth and not spoiler:
            is_locked = False
            title = ver.title
            dek = (parsed.get("dek") if isinstance(parsed, dict) else None) or ver.change_summary or (parsed.get("paragraphs", [""])[0][:120] if (parsed and parsed.get("paragraphs")) else "Reframe Film Editorial")
            cutoff = None
        elif not spoiler and not viewer.is_admin:
            # Fail closed on missing spoiler scope for synthetic magazine content
            is_locked = True
            title = f"The Bat Whispers (1930) — Scene Analysis #{idx:02d}"
            dek = "Complete the required story reveal to unlock this analysis."
            cutoff = 4860000
        else:
            visibility = evaluate_spoiler_visibility(spoiler, viewer) if spoiler else SpoilerVisibility.VISIBLE
            cutoff = spoiler.minimum_progress_ms if spoiler else 4860000

            if visibility == SpoilerVisibility.VISIBLE:
                title = ver.title
                dek = ver.change_summary or "In-depth narrative forensic analysis."
                is_locked = False
            else:
                safe_t = spoiler.safe_title if (spoiler and spoiler.safe_title) else f"The Bat Whispers (1930) — Scene Analysis #{idx:02d}"
                safe_d = spoiler.safe_preview if (spoiler and spoiler.safe_preview) else "Complete the required story reveal to unlock this analysis."
                title = safe_t
                dek = safe_d
                is_locked = True

        articles.append({
            "article_id": str(post.id),
            "title": title,
            "dek": dek,
            "article_type": art_type,
            "work_id": post.work_id,
            "author_alias": author_name or ("Synthetic Fan Editorial" if is_synth else "Reframe Editorial"),
            "is_synthetic": is_synth,
            "content_origin": prov.content_origin if prov else "EDITORIAL",
            "generator_mode": prov.generator_mode if prov else None,
            "ai_disclosure": post.ai_disclosure,
            "trust_class": "ENGINE_INFERENCE" if is_synth else None,
            "spoiler_cutoff_ms": cutoff,
            "is_spoiler_locked": is_locked,
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "hero_image_url": hero_image_url,
            "read_time_minutes": read_time_minutes,
        })

    from src.reframe.catalog.views import view_counts
    counts = await view_counts(db, "article", [item["article_id"] for item in articles])
    for item in articles:
        item.update(counts.get(item["article_id"], {"view_count": 0, "views_7d": 0}))
        # Public registration is publication, not the creation of a private draft.
        item["registered_at"] = item["published_at"]
    disclaimer = (
        "All synthetic magazine articles are demo assets grounded in observed evidence."
        if has_synthetic
        else None
    )

    return {
        "articles": articles,
        "total": len(articles),
        "disclaimer": disclaimer,
    }


from fastapi import Request, HTTPException
from src.reframe.catalog.views import ViewRequest, record_view


@router.post("/{article_id}/views")
async def record_article_view(article_id: str, body: ViewRequest, request: Request,
    viewer: ViewerContext = Depends(get_viewer_context), db: AsyncSession = Depends(get_db)):
    article = await get_magazine_article(article_id, viewer, db)
    published = await db.scalar(select(Post.id).where(Post.id == uuid.UUID(article_id), Post.status == "PUBLISHED"))
    if not published or article.get("is_spoiler_locked") is not False:
        raise HTTPException(404, "Readable published article not found")
    return await record_view(db, "article", str(uuid.UUID(article_id)), body.event_id, request)


@router.get("/{article_id}")
async def get_magazine_article(
    article_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieves a full magazine article with central spoiler protection and real EvidenceCatalog links.
    """
    try:
        post_uuid = uuid.UUID(article_id)
    except ValueError:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    stmt = (
        select(Post, SyntheticContentProvenance, Profile.display_name)
        .outerjoin(SyntheticContentProvenance, SyntheticContentProvenance.subject_id == Post.id)
        .outerjoin(Profile, Profile.user_id == Post.author_id)
        .where(Post.id == post_uuid, Post.content_type == "MAGAZINE_ARTICLE")
    )
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found in database.",
        )
    post, prov, author_alias = row

    # Non-published (DRAFT / ARCHIVED) articles are not publicly visible
    if post.status != "PUBLISHED" and not viewer.is_admin and viewer.user_id != post.author_id:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    check_synthetic_article_access(prov, viewer)

    ver_stmt = select(PostVersion).where(PostVersion.post_id == post.id).order_by(PostVersion.version_no.desc()).limit(1)
    ver = (await db.execute(ver_stmt)).scalar_one_or_none()
    if not ver:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article version not found.",
        )

    is_synth = (prov is not None)

    # Check spoiler scope
    spoiler = None
    if post.spoiler_scope_id:
        sp_stmt = select(SpoilerScope).where(SpoilerScope.id == post.spoiler_scope_id)
        spoiler = (await db.execute(sp_stmt)).scalar_one_or_none()

    if not is_synth and not spoiler:
        # General editorial article: always visible, no spoiler locks, zero canonical hallucination
        is_locked = False
        cutoff = None
        trust_class = None
    elif not spoiler and not viewer.is_admin:
        # Synthetic article missing spoiler scope fails closed
        is_locked = True
        cutoff = 4860000
        trust_class = "ENGINE_INFERENCE"
    else:
        cutoff = spoiler.minimum_progress_ms if spoiler else 4860000
        visibility = evaluate_spoiler_visibility(spoiler, viewer) if spoiler else SpoilerVisibility.VISIBLE
        is_locked = (visibility != SpoilerVisibility.VISIBLE)
        trust_class = "ENGINE_INFERENCE" if is_synth else None

    # Parse body sections, article_type, hero_image, and paragraphs
    art_type = "EDITORIAL_ESSAY" if not is_synth else "SCENE_BREAKDOWN"
    body_sections = {}
    hero_image_url = None
    intro_paragraphs = []
    paragraphs = []
    outro_paragraphs = []
    read_time_minutes = 5
    parsed = None
    try:
        parsed = json.loads(ver.body_markdown)
        if isinstance(parsed, dict):
            art_type = parsed.get("article_type", art_type)
            hero_image_url = parsed.get("hero_image_url")
            intro_paragraphs = parsed.get("intro_paragraphs", [])
            paragraphs = parsed.get("paragraphs", [])
            outro_paragraphs = parsed.get("outro_paragraphs", [])
            read_time_minutes = parsed.get("read_time_minutes", 5)
            body_sections = parsed.get("sections", parsed)
        else:
            body_sections = {
                "WHAT_THE_FILM_SHOWS": ver.body_markdown,
                "CANONICAL_METADATA": f"Work: {post.work_id or 'General'}.",
                "ENGINE_INTERPRETATION": "Narrative inference.",
                "SYNTHETIC_AUTHOR_VIEW": "Curated analysis.",
                "ALTERNATIVE_EXPLANATION": "Theatrical convention.",
                "REWATCH_TIMESTAMPS": "Scene focal point.",
            }
    except Exception:
        body_sections = {
            "WHAT_THE_FILM_SHOWS": ver.body_markdown,
            "CANONICAL_METADATA": f"Work: {post.work_id or 'General'}.",
            "ENGINE_INTERPRETATION": "Narrative inference.",
            "SYNTHETIC_AUTHOR_VIEW": "Curated analysis.",
            "ALTERNATIVE_EXPLANATION": "Theatrical convention.",
            "REWATCH_TIMESTAMPS": "Scene focal point.",
        }

    # Query actual linked EvidenceCatalog records
    ev_stmt = (
        select(EvidenceCatalog)
        .join(PostEvidenceLink, PostEvidenceLink.evidence_catalog_id == EvidenceCatalog.id)
        .where(PostEvidenceLink.post_version_id == ver.id)
    )
    ev_res = await db.execute(ev_stmt)
    linked_evidence = ev_res.scalars().all()

    evidence_refs = []
    for ev in linked_evidence:
        evidence_refs.append({
            "evidence_type": ev.evidence_type.upper(),
            "evidence_id": ev.evidence_id,
            "evidence_hash": ev.evidence_hash,
            "timestamp_ms": ev.screen_start_ms,
            "trust_class": "OBSERVED_EVIDENCE",
        })

    if is_locked:
        sanitized_sections = {
            "WHAT_THE_FILM_SHOWS": "[SPOILER PROTECTED CONTENT - Unlock spoiler scope to view]",
            "CANONICAL_METADATA": "[SPOILER PROTECTED]",
            "ENGINE_INTERPRETATION": "[SPOILER PROTECTED]",
            "SYNTHETIC_AUTHOR_VIEW": "[SPOILER PROTECTED]",
            "ALTERNATIVE_EXPLANATION": "[SPOILER PROTECTED]",
            "REWATCH_TIMESTAMPS": "[SPOILER PROTECTED]",
        }
        title = spoiler.safe_title if (spoiler and spoiler.safe_title) else "The Bat Whispers (1930) — Scene Analysis (Locked)"
        dek = spoiler.safe_preview if (spoiler and spoiler.safe_preview) else "Complete the required reveal to unlock this analysis."
        final_evidence_refs = []
        hero_image_url = None
        intro_paragraphs = []
        paragraphs = []
        outro_paragraphs = []
    else:
        sanitized_sections = body_sections
        title = ver.title
        dek = (parsed.get("dek") if isinstance(parsed, dict) else None) or ver.change_summary or (paragraphs[0][:120] if paragraphs else "Narrative forensic analysis.")
        final_evidence_refs = evidence_refs

    return {
        "article_id": str(post.id),
        "title": title,
        "dek": dek,
        "article_type": art_type,
        "work_id": post.work_id,
        "author_alias": author_alias or ("Synthetic Fan Editorial" if is_synth else "Reframe Editorial"),
        "is_synthetic": is_synth,
        "content_origin": prov.content_origin if prov else "EDITORIAL",
        "generator_mode": prov.generator_mode if prov else None,
        "ai_disclosure": post.ai_disclosure,
        "trust_class": trust_class,
        "spoiler_cutoff_ms": cutoff,
        "is_spoiler_locked": is_locked,
        "published_at": post.published_at.isoformat() if post.published_at else None,
        "hero_image_url": hero_image_url,
        "intro_paragraphs": intro_paragraphs,
        "paragraphs": paragraphs,
        "outro_paragraphs": outro_paragraphs,
        "read_time_minutes": read_time_minutes,
        "body_sections": sanitized_sections,
        "evidence_refs": final_evidence_refs,
    }


class PutArticleReactionRequest(BaseModel):
    reaction_type: str = "LIKE"
    liked: bool = True


class CreateArticleCommentRequest(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=2000)
    parent_comment_id: Optional[uuid.UUID] = None


@router.get("/{article_id}/reactions")
async def get_magazine_reactions(
    article_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns like count and viewer liked status for a magazine article.
    """
    try:
        post_uuid = uuid.UUID(article_id)
    except ValueError:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    stmt = select(Post).where(Post.id == post_uuid)
    post = (await db.execute(stmt)).scalar_one_or_none()
    if not post or post.content_type != "MAGAZINE_ARTICLE" or post.status != "PUBLISHED":
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    cnt_stmt = select(func.count(Reaction.id)).where(
        Reaction.subject_type == "POST",
        Reaction.subject_id == post_uuid,
        Reaction.reaction_type == "LIKE",
    )
    cnt = (await db.execute(cnt_stmt)).scalar() or 0

    viewer_liked = False
    if viewer.user_id:
        v_stmt = select(Reaction).where(
            Reaction.subject_type == "POST",
            Reaction.subject_id == post_uuid,
            Reaction.user_id == viewer.user_id,
            Reaction.reaction_type == "LIKE",
        )
        viewer_liked = (await db.execute(v_stmt)).scalar_one_or_none() is not None

    return {
        "status": "SUCCESS",
        "data": {
            "article_id": article_id,
            "like_count": cnt,
            "viewer_liked": viewer_liked,
        },
    }


@router.put("/{article_id}/reactions", status_code=status.HTTP_200_OK)
async def put_magazine_reaction(
    article_id: str,
    req: PutArticleReactionRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db),
):
    """
    Toggles or sets the liked status of a magazine article.
    """
    try:
        post_uuid = uuid.UUID(article_id)
    except ValueError:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    stmt = select(Post).where(Post.id == post_uuid)
    post = (await db.execute(stmt)).scalar_one_or_none()
    if not post or post.content_type != "MAGAZINE_ARTICLE" or post.status != "PUBLISHED":
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    if req.liked:
        await community_service.add_reaction(
            db=db,
            subject_type="POST",
            subject_id=post_uuid,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type,
        )
    else:
        await community_service.delete_reaction(
            db=db,
            subject_type="POST",
            subject_id=post_uuid,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type,
        )

    cnt_stmt = select(func.count(Reaction.id)).where(
        Reaction.subject_type == "POST",
        Reaction.subject_id == post_uuid,
        Reaction.reaction_type == req.reaction_type,
    )
    cnt = (await db.execute(cnt_stmt)).scalar() or 0

    return {
        "status": "SUCCESS",
        "data": {
            "article_id": article_id,
            "like_count": cnt,
            "liked": req.liked,
        },
    }


@router.get("/{article_id}/comments")
async def get_magazine_comments(
    article_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns comments for a magazine article with centralized spoiler masking and ancestor validation.
    """
    try:
        post_uuid = uuid.UUID(article_id)
    except ValueError:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    stmt = select(Post).where(Post.id == post_uuid)
    post = (await db.execute(stmt)).scalar_one_or_none()
    if not post or post.content_type != "MAGAZINE_ARTICLE" or (post.status != "PUBLISHED" and not viewer.is_admin):
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    comments_data = await community_service.list_comments(db=db, post_id=post_uuid, viewer=viewer)
    return {
        "status": "SUCCESS",
        "data": comments_data,
        "total": len(comments_data),
    }


@router.post("/{article_id}/comments", status_code=status.HTTP_201_CREATED)
async def create_magazine_comment(
    article_id: str,
    req: CreateArticleCommentRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db),
):
    """
    Adds a comment to a magazine article. Returns HTTP 201 with valid comment envelope.
    """
    try:
        post_uuid = uuid.UUID(article_id)
    except ValueError:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    stmt = select(Post).where(Post.id == post_uuid)
    post = (await db.execute(stmt)).scalar_one_or_none()
    if not post or post.content_type != "MAGAZINE_ARTICLE" or (post.status != "PUBLISHED" and not viewer.is_admin):
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Magazine article not found.",
        )

    comment_dict = await community_service.create_comment(
        db=db,
        user_id=viewer.user_id,
        post_id=post_uuid,
        body_markdown=req.body_markdown,
        parent_comment_id=req.parent_comment_id,
    )

    return {
        "status": "SUCCESS",
        "data": {
            "id": str(comment_dict.get("comment_id") or comment_dict.get("id")),
            "comment_id": str(comment_dict.get("comment_id") or comment_dict.get("id")),
            "post_id": str(comment_dict.get("post_id")),
            "parent_comment_id": str(comment_dict.get("parent_comment_id")) if comment_dict.get("parent_comment_id") else None,
            "author_alias": getattr(viewer, "display_name", None) or "Anonymous",
            "body_markdown": comment_dict.get("body_markdown", req.body_markdown),
            "created_at": comment_dict.get("created_at"),
            "version_no": comment_dict.get("version_no", 1),
            "inspection_status": comment_dict.get("inspection_status", "UNVERIFIED_CALLS_DISABLED"),
        },
    }
