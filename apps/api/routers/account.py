"""Authenticated My Reviews, Wishlist and nickname/photo editing. No external calls."""
import base64
import binascii
import hashlib
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from PIL import Image, ImageOps, UnidentifiedImageError

from src.reframe.shared.database import get_db
from src.reframe.identity.auth import ViewerContext, get_authenticated_user, enforce_csrf
from src.reframe.identity.models import User, Profile, ProfilePhoto, WishlistEntry
from src.reframe.community.models import Post, PostVersion
from src.reframe.catalog.repository import FilmCatalogRepository
from src.reframe.catalog.service import catalog_service

router = APIRouter(tags=["My Page"])


async def film_summary(db, work_id):
    if work_id.startswith('topbox-'):
        from src.reframe.catalog.top_box import release_by_work
        release = await release_by_work(db, work_id)
        if release:
            return {'movie_id': work_id, 'title': release['title'], 'poster_path': None, 'destination': release['destination']}
    normalized = catalog_service.normalize_movie_id(work_id)
    film = await FilmCatalogRepository.get_film_by_id(db, normalized)
    if film:
        return {"movie_id": film.movie_id, "title": film.title_en, "poster_path": film.poster_local_path}
    entry = catalog_service.get_film_entry(normalized)
    if entry:
        return {"movie_id": normalized, "title": entry.get("title", normalized), "poster_path": entry.get("poster_path")}
    raise HTTPException(404, "Film not found")


@router.get("/me/reviews")
async def my_reviews(response: Response, offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=100),
                     viewer: ViewerContext = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    condition = (Post.author_id == viewer.user_id, Post.status == "PUBLISHED", PostVersion.rating.is_not(None))
    base = select(Post, PostVersion).join(PostVersion, Post.current_version_id == PostVersion.id).where(*condition)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(Post.updated_at.desc(), Post.id).offset(offset).limit(limit))).all()
    data = []
    for post, version in rows:
        try:
            film = await film_summary(db, post.work_id)
        except HTTPException:
            film = {"movie_id": post.work_id, "title": "Unavailable film", "poster_path": None}
        data.append({**film, "post_id": str(post.id), "rating": version.rating,
                     "body_markdown": version.body_markdown[:400], "created_at": post.created_at.isoformat(),
                     "version_no": version.version_no, "contains_spoilers": version.contains_spoilers})
    return {"data": data, "meta": {"total": total, "offset": offset, "limit": limit}}


@router.get("/me/wishlist")
async def my_wishlist(response: Response, offset: int = Query(0, ge=0), limit: int = Query(12, ge=1, le=100),
                      viewer: ViewerContext = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    base = select(WishlistEntry).where(WishlistEntry.user_id == viewer.user_id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(WishlistEntry.created_at.desc(), WishlistEntry.work_id).offset(offset).limit(limit))).scalars().all()
    data = []
    for item in rows:
        try:
            film = await film_summary(db, item.work_id)
        except HTTPException:
            film = {"movie_id": item.work_id, "title": "Unavailable film", "poster_path": None}
        data.append({**film, "saved": True, "created_at": item.created_at.isoformat()})
    return {"data": data, "meta": {"total": total, "offset": offset, "limit": limit}}


class WishlistUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    saved: bool


@router.get("/me/wishlist/{work_id}")
async def wishlist_state(work_id: str, response: Response,
                         viewer: ViewerContext = Depends(get_authenticated_user), db: AsyncSession = Depends(get_db)):
    response.headers["Cache-Control"] = "private, no-store"
    normalized = catalog_service.normalize_movie_id(work_id)
    row = await db.get(WishlistEntry, (viewer.user_id, normalized))
    return {"data": {"movie_id": normalized, "saved": row is not None}}


@router.put("/me/wishlist/{work_id}")
async def update_wishlist(work_id: str, req: WishlistUpdate,
                          viewer: ViewerContext = Depends(get_authenticated_user),
                          _csrf: None = Depends(enforce_csrf), db: AsyncSession = Depends(get_db)):
    normalized = catalog_service.normalize_movie_id(work_id)
    if req.saved:
        normalized = (await film_summary(db, normalized))["movie_id"]
        # Idempotent even when two tabs add the film simultaneously.
        if db.get_bind().dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        await db.execute(insert(WishlistEntry).values(user_id=viewer.user_id, work_id=normalized,
            created_at=datetime.now(timezone.utc)).on_conflict_do_nothing(index_elements=["user_id", "work_id"]))
    else:
        await db.execute(delete(WishlistEntry).where(WishlistEntry.user_id == viewer.user_id, WishlistEntry.work_id == normalized))
    await db.commit()
    return {"data": {"movie_id": normalized, "saved": req.saved}}


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str = Field(min_length=1, max_length=100)
    photo_data: str | None = Field(default=None, max_length=1_400_000)


def sanitized_photo(data: str) -> bytes:
    try:
        if len(data) > 1_400_000:
            raise ValueError("Image is too large")
        header, encoded = data.split(",", 1)
        formats = {"data:image/png;base64": "PNG", "data:image/jpeg;base64": "JPEG",
                   "data:image/webp;base64": "WEBP"}
        if header not in formats:
            raise ValueError("Unsupported image")
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 1_000_000:
            raise ValueError("Image is too large")
        with Image.open(io.BytesIO(raw)) as image:
            if image.width * image.height > 4_000_000 or image.format != formats[header]:
                raise ValueError("Image is too large or unsupported")
            image.load()
            photo = ImageOps.exif_transpose(image).convert("RGB")
            photo.info.clear()
            photo.thumbnail((256, 256))
            output = io.BytesIO()
            photo.save(output, format="PNG")
            return output.getvalue()
    except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise HTTPException(422, "Choose a PNG, JPEG or WebP photo under 1 MB and 4 megapixels")


@router.patch("/profiles/me")
async def update_profile(req: ProfileUpdate, viewer: ViewerContext = Depends(get_authenticated_user),
                         _csrf: None = Depends(enforce_csrf), db: AsyncSession = Depends(get_db)):
    name = req.display_name.strip()
    if not name:
        raise HTTPException(422, "Nickname cannot be blank")
    png = sanitized_photo(req.photo_data) if req.photo_data else None
    await db.execute(select(User.id).where(User.id == viewer.user_id).with_for_update())
    profile = await db.get(Profile, viewer.user_id)
    if profile is None:
        profile = Profile(user_id=viewer.user_id, display_name=name)
        db.add(profile)
    profile.display_name = name
    if "photo_data" in req.model_fields_set:
        photo = await db.get(ProfilePhoto, viewer.user_id)
        if png is None:
            if photo: await db.delete(photo)
            profile.avatar_url = None
        else:
            if photo: photo.png = png
            else: db.add(ProfilePhoto(user_id=viewer.user_id, png=png))
            profile.avatar_url = f"/api/v1/profiles/{viewer.user_id}/avatar?v={hashlib.sha256(png).hexdigest()[:16]}"
    await db.commit()
    return {"data": {"display_name": profile.display_name, "avatar_url": profile.avatar_url}}


@router.get("/profiles/{user_id}/avatar")
async def profile_avatar(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    user = await db.get(User, user_id)
    photo = await db.get(ProfilePhoto, user_id)
    if not user or user.status != "ACTIVE" or not photo:
        raise HTTPException(404, "Profile photo not found")
    return Response(photo.png, media_type="image/png", headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"})
