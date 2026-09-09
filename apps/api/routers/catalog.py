"""
Reframe V7 Films & Reveals Catalog Router
"""
import uuid
import html
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Request, Response, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import structlog

from src.reframe.catalog.service import catalog_service
from src.reframe.identity.auth import get_viewer_context, get_authenticated_user, get_authenticated_admin, enforce_csrf, ViewerContext
from src.reframe.shared.database import get_db
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.community.models import Post, PostVersion, Comment, Reaction
from src.reframe.community.service import community_service
from src.reframe.identity.models import PUBLIC_AUTHOR_USER_ID


logger = structlog.get_logger(__name__)
def private_analysis_response(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Cookie, Authorization'


router = APIRouter(tags=["Catalog"], dependencies=[Depends(private_analysis_response)])


@router.get('/films/{movie_id}/selected-portion-analysis')
async def get_selected_portion_analysis(
    movie_id: str, response: Response,
    edition_id: str = Query(min_length=1, max_length=128),
    selected_ms: Optional[int] = Query(default=None, ge=0, le=2**63-1),
    viewer: ViewerContext = Depends(get_viewer_context),
):
    from src.reframe.catalog.selected_portion import selected_portion
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Cookie, Authorization'
    norm_id = catalog_service.normalize_movie_id(movie_id)
    try:
        data = selected_portion(norm_id, edition_id, viewer, selected_ms)
    except (ValueError, KeyError, OSError):
        raise HTTPException(503, 'Selected-portion observations are unavailable')
    if data is None:
        raise HTTPException(404, 'Selected-portion analysis is unavailable for this edition')
    return {'data':data, 'meta':{'paid_model_calls':0, 'source':'INDEPENDENT_SEGMENT_OBSERVATIONS'}}


class CreateProofCommentRequest(BaseModel):
    body_markdown: str = Field(min_length=1, max_length=2000)
    parent_comment_id: Optional[uuid.UUID] = None
    contains_spoilers: bool = False


class PutProofReactionRequest(BaseModel):
    reaction_type: str = "LIKE"
    liked: bool = True


async def _get_or_create_proof_anchor_post(db: AsyncSession, proof_id: str, proof_title: str, work_id: str, edition_id: str) -> uuid.UUID:
    target_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"reframe:proof:{proof_id}")
    stmt = select(Post).where(Post.id == target_uuid)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if not existing:
        post = Post(
            id=target_uuid,
            author_id=PUBLIC_AUTHOR_USER_ID,
            work_id=work_id,
            edition_id=edition_id,
            content_type="PROOF_ANALYSIS",
            status="PUBLISHED"
        )
        db.add(post)
        ver = PostVersion(
            id=uuid.uuid4(),
            post_id=target_uuid,
            version_no=1,
            title=proof_title or f"Proof {proof_id}",
            body_markdown=f"Forensic proof analysis for {proof_id}",
            body_sanitized_html=f"<p>Forensic proof analysis for {html.escape(proof_id)}</p>",
            created_by=PUBLIC_AUTHOR_USER_ID
        )
        db.add(ver)
        post.current_version_id = ver.id
        await db.commit()
    return target_uuid


@router.api_route("/films/{movie_id}/media", methods=["GET", "HEAD"])
async def get_film_media(movie_id: str, edition_id: Optional[str] = None):
    """Retired playback endpoint. Source files remain available only to analysis jobs."""
    raise HTTPException(status_code=410, detail="Video playback is not provided on this site.",
                        headers={"Cache-Control": "no-store"})


@router.get("/films/{movie_id}/scene-index")
async def get_film_scene_index(
    movie_id: str,
    edition_id: Optional[str] = None,
    viewer: ViewerContext = Depends(get_viewer_context)
):
    """Scene positions only, up to this viewer's saved progress. No plot text."""
    norm_id = catalog_service.normalize_movie_id(movie_id)
    if not catalog_service.is_film_registered(norm_id, edition_id):
        raise HTTPException(status_code=404, detail=f"Film '{movie_id}' not found in catalog")

    film_data = catalog_service.get_film_entry(norm_id, edition_id)
    actual_edition = film_data.get("edition_id") if film_data else edition_id
    progress = viewer.work_progress_by_edition.get(f"{norm_id}:{actual_edition}", 0)

    if norm_id == "the-bat-whispers-1930" and actual_edition == "tbw-fullscreen-archive":
        from src.reframe.evidence.adapter import v3_adapter
        scenes = v3_adapter.get_scenes(cutoff_ms=progress)
        return {"data": [{"scene_id": s.scene_id, "start_ms": s.start_ms, "end_ms": s.end_ms} for s in scenes]}
    else:
        return {"data": [{"scene_id": s["scene_id"], "start_ms": s["start_ms"], "end_ms": s["end_ms"]}
                         for s in film_data.get("scenes", []) if s["end_ms"] <= progress]}


from fastapi import Query
from src.reframe.catalog.repository import FilmCatalogRepository
from src.reframe.catalog.models import FilmCatalog
from src.reframe.catalog.views import ViewRequest, record_view, view_counts


@router.get("/films", response_model=Dict[str, Any])
async def list_films(
    q: Optional[str] = None,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=50),
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
):
    imported = catalog_service.get_imported_entries()
    excluded_ids = [entry["movie_id"] for entry in imported]
    query = (q or "").strip().casefold()
    matching = [entry for entry in imported if not query or query in entry["title"].casefold()]
    local_page = matching[offset:offset + limit]
    remaining = limit - len(local_page)
    try:
        db_films, total = await FilmCatalogRepository.list_films(
            db, q=q, offset=max(0, offset - len(matching)), limit=max(1, remaining),
            exclude_movie_ids=excluded_ids,
        )
    except Exception as e:
        logger.error("Database query failed in list_films", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable",
        )
    results = []
    for entry in local_page:
        item = catalog_service.get_film_detail(entry["movie_id"], viewer, entry["edition_id"]).model_dump()
        item.update(poster_path=entry.get("poster_path"), directors=entry.get("directors", []),
                    cast=entry.get("cast", []), genres=entry.get("genres", []),
                    destination=f"/films/{entry['movie_id']}", core_demo_supported=entry["analysis_status"] == "READY")
        results.append(item)
    for f in db_films[:remaining]:
        if f.movie_id == "the-bat-whispers-1930":
            item = catalog_service.get_film_summary().model_dump()
            item["poster_path"] = f.poster_local_path or item.get("poster_path") or "/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I8-28118-73-6268.png"
            item["destination"] = "/films/the-bat-whispers-1930"
            item["core_demo_supported"] = True
            item["title_ko"] = f.title_ko
            item["directors"] = f.directors
            item["cast"] = f.cast_members
            item["genres"] = f.genres
        else:
            item = {
                "movie_id": f.movie_id,
                "edition_id": f"{f.movie_id}-edition",
                "title": f.title_en,
                "title_ko": f.title_ko,
                "year": f.year,
                "synopsis_safe": f.description_en or "Public catalog metadata record.",
                "runtime_ms": (f.runtime_minutes * 60 * 1000) if f.runtime_minutes else 0,
                "rights_status": "CATALOG_METADATA_ONLY",
                "analysis_status": "NOT_SUPPORTED",
                "available_modes": [],
                "poster_path": f.poster_local_path,
                "destination": f"/films/{f.movie_id}",
                "core_demo_supported": False,
                "directors": f.directors,
                "cast": f.cast_members,
                "genres": f.genres,
            }
        results.append(item)

    ids = [item["movie_id"] for item in results]
    counts = await view_counts(db, "film", ids)
    registered = dict((await db.execute(select(FilmCatalog.movie_id, FilmCatalog.created_at)
        .where(FilmCatalog.movie_id.in_(ids)))).all()) if ids else {}
    for item in results:
        item.update(counts.get(item["movie_id"], {"view_count": 0, "views_7d": 0}))
        created = registered.get(item["movie_id"])
        item["registered_at"] = created.isoformat() if created else None
    return {
        "data": results,
        "meta": {"total": total + len(matching), "offset": offset, "limit": limit}
    }


@router.post("/films/{movie_id}/views")
async def record_film_view(movie_id: str, body: ViewRequest, request: Request,
    viewer: ViewerContext = Depends(get_viewer_context), db: AsyncSession = Depends(get_db)):
    detail = await get_film_detail(movie_id, viewer, db)
    return await record_view(db, "film", detail["data"]["movie_id"], body.event_id, request)


@router.get("/films/{movie_id}", response_model=Dict[str, Any])
@router.get("/catalog/works/{movie_id}", response_model=Dict[str, Any])
@router.get("/catalog/films/{movie_id}", response_model=Dict[str, Any])
async def get_film_detail(
    movie_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
    edition_id: Optional[str] = None,
):
    try:
        film = await FilmCatalogRepository.get_film_by_id(db, movie_id)
    except Exception as e:
        logger.error("Database query failed in get_film_detail", error=str(e), movie_id=movie_id)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service temporarily unavailable",
        )

    norm_id = catalog_service.normalize_movie_id(movie_id)
    if not film:
        service_detail = catalog_service.get_film_detail(norm_id, viewer, edition_id)
        if not service_detail:
            raise ReframeException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ReframeErrorCodes.NOT_FOUND,
                message=f"Film '{movie_id}' not found in catalog"
            )
        data = service_detail.model_dump()
        from src.reframe.catalog.featured_credits import featured_cast
        data['cast'] = featured_cast(norm_id, data.get('cast', []))
        data["core_demo_supported"] = (service_detail.analysis_status == "READY")
        if service_detail.analysis_status == "PREPARING":
            data["analysis_notice"] = f"Core forensic analysis features for {service_detail.title} are currently preparing."
        return {"data": data, "meta": {}}

    # Aggregate real reviews rating from PostgreSQL PostVersion records
    avg_rating, ratings_count_val = None, 0
    try:
        rating_stmt = (
            select(
                func.coalesce(func.avg(PostVersion.rating), 0.0),
                func.count(PostVersion.rating)
            )
            .join(Post, Post.current_version_id == PostVersion.id)
            .where(
                Post.work_id == movie_id,
                Post.status == "PUBLISHED",
                PostVersion.rating.isnot(None)
            )
        )
        rating_res = await db.execute(rating_stmt)
        avg_rating_val, cnt_val = rating_res.first() or (0.0, 0)
        ratings_count_val = cnt_val
        avg_rating = round(float(avg_rating_val), 1) if ratings_count_val > 0 else None
    except Exception:
        avg_rating, ratings_count_val = None, 0

    norm_id = catalog_service.normalize_movie_id(film.movie_id)
    service_detail = catalog_service.get_film_detail(norm_id, viewer, edition_id)
    if edition_id and not service_detail:
        raise HTTPException(status_code=404, detail="Unknown film edition")
    if service_detail:
        data = service_detail.model_dump()
        data["poster_path"] = film.poster_local_path or data.get("poster_path")
        data["core_demo_supported"] = (service_detail.analysis_status == "READY")
        data["title_ko"] = film.title_ko
        data["directors"] = film.directors
        from src.reframe.catalog.featured_credits import featured_cast
        data["cast"] = featured_cast(norm_id, film.cast_members)
        data["genres"] = film.genres
        data["average_rating"] = avg_rating
        data["ratings_count"] = ratings_count_val
        if service_detail.analysis_status == "PREPARING":
            data["analysis_notice"] = f"Core forensic analysis features for {film.title_en} are currently preparing."
        return {"data": data, "meta": {}}

    return {
        "data": {
            "movie_id": film.movie_id,
            "qid": film.source_qid,
            "title": film.title_en,
            "title_ko": film.title_ko,
            "year": film.year,
            "synopsis_safe": film.description_en or "Public catalog metadata record.",
            "description_ko": film.description_ko,
            "runtime_minutes": film.runtime_minutes,
            "runtime_ms": (film.runtime_minutes * 60 * 1000) if film.runtime_minutes else 0,
            "directors": film.directors,
            "cast": film.cast_members,
            "genres": film.genres,
            "countries": film.countries,
            "languages": film.languages,
            "poster_path": film.poster_local_path,
            "poster_license": film.poster_license,
            "core_demo_supported": False,
            "analysis_status": "NOT_SUPPORTED",
            "analysis_notice": "Core forensic analysis features are currently demonstrated exclusively on The Bat Whispers (1930).",
            "source_url": film.source_url,
            "source_revision": film.source_revision,
            "fetched_at": film.fetched_at.isoformat() if film.fetched_at else None,
            "average_rating": avg_rating,
            "ratings_count": ratings_count_val,
        },
        "meta": {}
    }


@router.get("/films/{movie_id}/reveals", response_model=Dict[str, Any])
@router.get("/catalog/works/{movie_id}/reveals", response_model=Dict[str, Any])
@router.get("/catalog/films/{movie_id}/reveals", response_model=Dict[str, Any])
async def list_film_reveals(
    movie_id: str,
    edition_id: Optional[str] = None,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
    watched_only: bool = False,
):
    norm_id = catalog_service.normalize_movie_id(movie_id)
    if not catalog_service.is_film_registered(norm_id, edition_id):
        try:
            film = await FilmCatalogRepository.get_film_by_id(db, norm_id)
        except Exception as e:
            logger.error("Database query failed in list_film_reveals", error=str(e), movie_id=movie_id)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database service temporarily unavailable",
            )

        if not film:
            raise ReframeException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ReframeErrorCodes.NOT_FOUND,
                message=f"Film '{movie_id}' not found in catalog"
            )

    reveals = catalog_service.get_reveals(norm_id, viewer, edition_id=edition_id)
    from src.reframe.spoiler.analysis_boundary import SEPARATED_ANALYSIS_EDITIONS
    reveals = [r for r in reveals if not r.is_locked or
               (r.work_id, r.edition_id) not in SEPARATED_ANALYSIS_EDITIONS]
    if watched_only:
        reveals = [r for r in reveals if not r.is_locked and
            viewer.work_progress_by_edition.get(f"{r.work_id}:{r.edition_id}", 0) > 0 and
            max(r.timestamp_ms, r.spoiler_cutoff_ms) <= viewer.work_progress_by_edition.get(f"{r.work_id}:{r.edition_id}", 0)]
    return {
        "data": [r.model_dump() for r in reveals],
        "meta": {"total": len(reveals)}
    }


@router.get("/scenes/{scene_id}", response_model=Dict[str, Any])
@router.get("/fan/scenes/{scene_id}", response_model=Dict[str, Any])
async def get_scene_detail(scene_id: str, viewer: ViewerContext = Depends(get_viewer_context)):
    from src.reframe.evidence.adapter import v3_adapter
    scene = v3_adapter.get_scene(scene_id)
    if not scene:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Scene '{scene_id}' not found in canonical dataset"
        )
    from src.reframe.spoiler.analysis_boundary import SEPARATED_ANALYSIS_EDITIONS, current_position
    if (scene.work_id,scene.edition_id) in SEPARATED_ANALYSIS_EDITIONS:
        entry = catalog_service.get_film_entry(scene.work_id,scene.edition_id) or {}
        # This legacy scene DTO is assembled from a whole-film dataset, not the
        # independent segment publication used by selected-portion analysis.
        if current_position(viewer,scene.work_id,scene.edition_id) < entry.get('runtime_ms',2**63-1):
            raise HTTPException(403, 'Full-context scene details remain protected',
                                headers={'Cache-Control':'private, no-store','Vary':'Cookie, Authorization'})
    return {
        "data": scene.model_dump(),
        "meta": {}
    }




@router.get("/reveals/{reveal_id}", response_model=Dict[str, Any])
async def get_reveal_detail(reveal_id: str, viewer: ViewerContext = Depends(get_viewer_context)):
    reveal = catalog_service.get_reveal_by_id(reveal_id, viewer)
    from src.reframe.spoiler.analysis_boundary import SEPARATED_ANALYSIS_EDITIONS
    if reveal and reveal.is_locked and (reveal.work_id,reveal.edition_id) in SEPARATED_ANALYSIS_EDITIONS:
        reveal = None
    if not reveal:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Reveal '{reveal_id}' not found in P0 registry"
        )

    return {
        "data": reveal.model_dump(),
        "meta": {}
    }


@router.get("/reveals/{reveal_id}/proofs", response_model=Dict[str, Any])
async def get_reveal_proofs(
    reveal_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db),
    watched_only: bool = False,
):
    """
    Returns precomputed canonical proofs for the reveal.
    Guarantees exactly 0 paid Gemini model calls for normal public users.
    """
    from src.reframe.proof.store import canonical_proof_store
    proofs = await canonical_proof_store.get_proofs_for_reveal(db, reveal_id, viewer)
    if watched_only:
        def watched(proof):
            progress = viewer.work_progress_by_edition.get(f"{proof.get('work_id')}:{proof.get('edition_id')}", 0)
            cutoff = proof.get("spoiler_cutoff_ms")
            return (proof.get("visibility") == "VISIBLE" and not proof.get("is_locked") and
                isinstance(cutoff, (int, float)) and 0 <= cutoff <= progress and progress > 0)
        proofs = [proof for proof in proofs if watched(proof)]
    return {
        "data": proofs,
        "meta": {"total": len(proofs), "source": "CANONICAL_PRECOMPUTED_STORE", "paid_model_calls": 0}
    }


@router.get("/proofs/{proof_id}", response_model=Dict[str, Any])
async def get_proof_detail(
    proof_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns verified proof details with server-side spoiler protection.
    0 paid model calls.
    """
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )
    return {"data": proof, "meta": {"paid_model_calls": 0}}


@router.get("/proofs/{proof_id}/evidence", response_model=Dict[str, Any])
async def get_proof_evidence(
    proof_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns verified forensic evidence premises, canonical hashes, and frame IDs for a proof.
    """
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )

    evidence_data = {
        "proof_id": proof_id,
        "evidence_chain": proof.get("evidence_chain", []),
        "observed_premises": proof.get("observed_premises", []),
        "proof_strength": proof.get("proof_strength", 0.90),
        "counterfactual_results": proof.get("counterfactual_results", {})
    }
    return {"data": evidence_data, "meta": {"paid_model_calls": 0}}


@router.get("/proofs/{proof_id}/rewatch", response_model=Dict[str, Any])
async def get_proof_rewatch_journey(
    proof_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns the chronological rewatch journey sequence for a verified proof.
    """
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )

    rewatch_moments = []
    for idx, prem in enumerate(proof.get("observed_premises", [])):
        rewatch_moments.append({
            "step_no": idx + 1,
            "scene_id": prem.get("scene_id"),
            "timestamp_ms": prem.get("timestamp_ms"),
            "event_id": prem.get("event_id"),
            "observation": prem.get("fact"),
            "blind_perspective": proof.get("blind_explanation"),
            "reframed_perspective": proof.get("reveal_explanation")
        })

    return {
        "data": {
            "proof_id": proof_id,
            "title": proof.get("title"),
            "rewatch_moments": rewatch_moments
        },
        "meta": {"total_moments": len(rewatch_moments)}
    }




@router.get("/proofs/{proof_id}/comments", response_model=Dict[str, Any])
async def list_proof_comments(
    proof_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )
    target_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"reframe:proof:{proof_id}")
    post = (await db.execute(select(Post).where(Post.id == target_uuid))).scalar_one_or_none()
    if not post:
        return {"status": "SUCCESS", "data": []}
    comments = await community_service.list_comments(db=db, post_id=target_uuid, viewer=viewer)
    return {"status": "SUCCESS", "data": comments}


@router.post("/proofs/{proof_id}/comments", status_code=status.HTTP_201_CREATED)
async def create_proof_comment(
    proof_id: str,
    req: CreateProofCommentRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )
    post_id = await _get_or_create_proof_anchor_post(db, proof_id, proof.get("title", ""), proof.get("work_id") or proof.get("movie_id") or "the-bat-whispers-1930", proof.get("edition_id") or "tbw-fullscreen-archive")
    from src.reframe.community.idempotency import reserve_comment_request, finish_comment_request
    marker, replay = await reserve_comment_request(db, viewer.user_id, f"POST:/proofs/{proof_id}/comments", idempotency_key, req.model_dump_json())
    if replay is not None:
        return replay
    comment_dict = await community_service.create_comment(
        db=db,
        post_id=post_id,
        user_id=viewer.user_id,
        body_markdown=req.body_markdown,
        parent_comment_id=req.parent_comment_id,
        contains_spoilers=req.contains_spoilers,
        commit=False,
    )
    return await finish_comment_request(db, marker, {"status": "SUCCESS", "data": comment_dict})


@router.get("/proofs/{proof_id}/reactions", response_model=Dict[str, Any])
async def get_proof_reactions(
    proof_id: str,
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )
    post_id = uuid.uuid5(uuid.NAMESPACE_DNS, f"reframe:proof:{proof_id}")
    cnt_stmt = select(func.count(Reaction.id)).where(
        Reaction.subject_type == "POST",
        Reaction.subject_id == post_id,
        Reaction.reaction_type == "LIKE"
    )
    cnt = (await db.execute(cnt_stmt)).scalar() or 0
    viewer_liked = False
    if viewer.user_id:
        v_stmt = select(Reaction).where(
            Reaction.subject_type == "POST",
            Reaction.subject_id == post_id,
            Reaction.user_id == viewer.user_id,
            Reaction.reaction_type == "LIKE"
        )
        viewer_liked = (await db.execute(v_stmt)).scalar_one_or_none() is not None

    return {
        "status": "SUCCESS",
        "data": {
            "proof_id": proof_id,
            "like_count": cnt,
            "viewer_liked": viewer_liked
        }
    }


@router.put("/proofs/{proof_id}/reactions", status_code=status.HTTP_200_OK)
async def put_proof_reaction(
    proof_id: str,
    req: PutProofReactionRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    from src.reframe.proof.store import canonical_proof_store
    proof = await canonical_proof_store.get_proof_by_id(db, proof_id, viewer)
    if not proof:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message=f"Proof '{proof_id}' not found"
        )
    post_id = await _get_or_create_proof_anchor_post(db, proof_id, proof.get("title", ""), proof.get("work_id") or proof.get("movie_id") or "the-bat-whispers-1930", proof.get("edition_id") or "tbw-fullscreen-archive")
    if req.liked:
        await community_service.add_reaction(
            db=db,
            subject_type="POST",
            subject_id=post_id,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type
        )
    else:
        await community_service.delete_reaction(
            db=db,
            subject_type="POST",
            subject_id=post_id,
            user_id=viewer.user_id,
            reaction_type=req.reaction_type
        )

    cnt_stmt = select(func.count(Reaction.id)).where(
        Reaction.subject_type == "POST",
        Reaction.subject_id == post_id,
        Reaction.reaction_type == req.reaction_type
    )
    cnt = (await db.execute(cnt_stmt)).scalar() or 0

    return {
        "status": "SUCCESS",
        "data": {
            "proof_id": proof_id,
            "liked": req.liked,
            "like_count": cnt
        }
    }


@router.post("/admin/reveals/{reveal_id}/refresh-proof", status_code=status.HTTP_202_ACCEPTED)
async def admin_refresh_proof(
    reveal_id: str,
    viewer: ViewerContext = Depends(get_authenticated_admin),
    _csrf: None = Depends(enforce_csrf),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin-only live proof regeneration route.
    Strictly requires ADMIN role, valid CSRF token, Idempotency-Key, and budget preflight.
    """
    from src.reframe.cost.service import cost_service
    from src.reframe.jobs.service import job_service

    # Budget preflight
    await cost_service.check_budget_preflight(db=db, user_id=viewer.user_id)

    run = await job_service.create_or_get_idempotent_run(
        db=db,
        principal_id=str(viewer.user_id),
        route_key=f"POST:/api/v1/admin/reveals/{reveal_id}/refresh-proof",
        idempotency_key=idempotency_key,
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id=reveal_id,
        run_type="CANONICAL_REFRESH",
        owner_user_id=viewer.user_id,
        config={"mode": "ADMIN_REFRESH", "max_paid_calls": 3}
    )
    await db.commit()

    return {
        "data": {
            "run_id": str(run.id),
            "status": run.status,
            "message": "Canonical proof refresh queued for worker execution."
        },
        "meta": {"idempotency_key": idempotency_key}
    }

