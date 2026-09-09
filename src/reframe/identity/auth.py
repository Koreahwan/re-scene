"""
Reframe V7 Authentication, Session Management & ViewerContext Resolver
"""
import uuid
import hmac
import hashlib
import time
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import jwt
from fastapi import Request, Response, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import get_db
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.identity.models import (
    User, Profile, WatchProgress, SpoilerPreferences,
    BrowserWatchProgress, BrowserContentUnlock, PUBLIC_AUTHOR_USER_ID
)

logger = structlog.get_logger(__name__)


class ViewerContext:
    def __init__(
        self,
        user_id: Optional[uuid.UUID] = None,
        roles: Optional[List[str]] = None,
        work_progress_by_edition: Optional[Dict[str, int]] = None,
        completed_reveal_ids: Optional[List[str]] = None,
        spoiler_preferences: Optional[Dict[str, Any]] = None,
        explicit_unlocks: Optional[List[str]] = None,
        admin_override: bool = False,
        session_id: Optional[str] = None,
        is_shared_demo: bool = False
    ):
        self.user_id = user_id
        self.roles = roles or ["GUEST"]
        self.work_progress_by_edition = work_progress_by_edition or {}
        self.completed_reveal_ids = completed_reveal_ids or []
        self.spoiler_preferences = spoiler_preferences or {
            "default_mode": "STRICT",
            "mask_titles": True,
            "mask_thumbnails": True,
            "mask_comments": True
        }
        self.explicit_unlocks = explicit_unlocks or []
        self.admin_override = admin_override
        self.session_id = session_id
        self.is_shared_demo = is_shared_demo

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None and not self.is_public_author and "GUEST" not in self.roles

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles or self.admin_override

    @property
    def is_moderator(self) -> bool:
        return "MODERATOR" in self.roles or self.is_admin

    @property
    def is_public_author(self) -> bool:
        return "PUBLIC_AUTHOR" in self.roles

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id) if self.user_id else None,
            "roles": self.roles,
            "work_progress_by_edition": self.work_progress_by_edition,
            "completed_reveal_ids": self.completed_reveal_ids,
            "spoiler_preferences": self.spoiler_preferences,
            "explicit_unlocks": self.explicit_unlocks,
            "admin_override": self.admin_override,
            "session_id": self.session_id,
            "is_public_author": self.is_public_author
        }


def create_session_token(user_id: uuid.UUID, role: str, auth_version: int = 1) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "auth_version": auth_version,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.SESSION_MAX_AGE_SECONDS
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_session_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except Exception as e:
        logger.debug("Failed decoding session token", error=str(e))
        return None


def generate_csrf_token(session_token: str) -> str:
    return hmac.new(
        settings.CSRF_SECRET.encode("utf-8"),
        session_token.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def verify_csrf_token(session_token: str, csrf_token: str) -> bool:
    expected = generate_csrf_token(session_token)
    return hmac.compare_digest(expected, csrf_token)


async def get_viewer_context(
    request: Request,
    response: Response = Response(),
    db: AsyncSession = Depends(get_db)
) -> ViewerContext:
    """Derives trusted ViewerContext entirely on the server side"""
    # 1. Resolve browser session for decoupled anonymous watch progress
    cookie_name = getattr(settings, "BROWSER_SESSION_COOKIE_NAME", "reframe_viewer_session")
    session_id = request.cookies.get(cookie_name) or getattr(request.state, "browser_session_id", None) or request.headers.get("X-Viewer-Session")
    if not session_id:
        session_id = uuid.uuid4().hex
        if response:
            try:
                response.set_cookie(
                    key=cookie_name,
                    value=session_id,
                    max_age=getattr(settings, "BROWSER_SESSION_MAX_AGE_SECONDS", 2592000),
                    httponly=True,
                    samesite="lax",
                    path="/"
                )
            except Exception:
                pass

    # 2. Check for explicit authenticated session token (e.g. admin or registered user)
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    # Determine whether server profile enables Phase 1 public authoring
    # NON-NEGOTIABLE INVARIANT: If server profile is False, client headers/queries/cookies MUST NOT activate it!
    server_profile_enabled = bool(
        getattr(settings, "PHASE1_SUBMISSION_PROFILE_ENABLED", False)
    )

    async def _create_anonymous_context() -> ViewerContext:
        if not server_profile_enabled:
            # Viewing consent does not grant public-author or account privileges.
            unlock_rows = await db.execute(select(BrowserContentUnlock).where(BrowserContentUnlock.session_id == session_id))
            unlocks = [f"{u.content_type}:{u.content_id}:{u.version_no}" for u in unlock_rows.scalars().all()]
            return ViewerContext(
                user_id=None,
                roles=["GUEST"],
                work_progress_by_edition={},
                completed_reveal_ids=[],
                explicit_unlocks=unlocks,
                admin_override=False,
                session_id=session_id
            )

        work_progress_by_edition: Dict[str, int] = {}
        completed_reveals: List[str] = []
        explicit_unlocks: List[str] = []

        try:
            # Load decoupled watch progress for this browser session
            bwp_stmt = select(BrowserWatchProgress).where(BrowserWatchProgress.session_id == session_id)
            bwp_res = await db.execute(bwp_stmt)
            for r in bwp_res.scalars().all():
                key = f"{r.work_id}:{r.edition_id}"
                work_progress_by_edition[key] = r.progress_ms
                if r.state in ("COMPLETED", "ALL_SPOILERS_ALLOWED"):
                    work_progress_by_edition[key] = 999999999
                if isinstance(r.completed_reveal_ids, list):
                    completed_reveals.extend(r.completed_reveal_ids)

            # Load decoupled explicit warning unlocks for this browser session (strictly typed & versioned)
            bcu_stmt = select(BrowserContentUnlock).where(BrowserContentUnlock.session_id == session_id)
            bcu_res = await db.execute(bcu_stmt)
            for u in bcu_res.scalars().all():
                explicit_unlocks.append(f"{u.content_type}:{u.content_id}:{u.version_no}")
        except Exception as e:
            logger.warning("browser_journey_tables_lookup_failed", error=str(e), session_id=session_id)

        return ViewerContext(
            user_id=PUBLIC_AUTHOR_USER_ID,
            roles=["PUBLIC_AUTHOR"],
            work_progress_by_edition=work_progress_by_edition,
            completed_reveal_ids=list(set(completed_reveals)),
            explicit_unlocks=list(set(explicit_unlocks)),
            admin_override=False,
            session_id=session_id
        )

    if not session_token:
        return await _create_anonymous_context()

    payload = decode_session_token(session_token)
    if not payload or "sub" not in payload:
        return await _create_anonymous_context()

    try:
        user_uuid = uuid.UUID(payload["sub"])
    except ValueError:
        return await _create_anonymous_context()

    # Load User, Profile, WatchProgress, SpoilerPreferences
    user_stmt = select(User).where(User.id == user_uuid, User.status == "ACTIVE")
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    if not user:
        return await _create_anonymous_context()

    is_shared_demo = user.account_origin == "PUBLIC_DEMO"
    if is_shared_demo and (not settings.AUTH_DEMO_ACCOUNT_ENABLED or user.role != "USER"):
        return ViewerContext(user_id=None, roles=["GUEST"], session_id=session_id)

    # Validate auth_version for session revocation
    token_auth_version = payload.get("auth_version", 1)
    current_auth_version = getattr(user, "auth_version", 1)
    if token_auth_version != current_auth_version:
        logger.info("session_revoked_by_auth_version", user_id=str(user.id), token_version=token_auth_version, current_version=current_auth_version)
        return ViewerContext(user_id=None, roles=["GUEST"], session_id=session_id)

    # Load Watch progress
    wp_stmt = (select(BrowserWatchProgress).where(BrowserWatchProgress.session_id == session_id)
               if is_shared_demo else select(WatchProgress).where(WatchProgress.user_id == user_uuid))
    wp_res = await db.execute(wp_stmt)
    progress_records = wp_res.scalars().all()

    work_progress_by_edition = {}
    completed_reveals = []
    for r in progress_records:
        key = f"{r.work_id}:{r.edition_id}"
        work_progress_by_edition[key] = r.progress_ms
        if r.state == "COMPLETED" or r.state == "ALL_SPOILERS_ALLOWED":
            work_progress_by_edition[key] = 999999999
        if isinstance(r.completed_reveal_ids, list):
            completed_reveals.extend(r.completed_reveal_ids)

    # Load Spoiler preferences
    sp_stmt = select(SpoilerPreferences).where(SpoilerPreferences.user_id == user_uuid)
    sp_res = await db.execute(sp_stmt)
    sp = sp_res.scalar_one_or_none()
    sp_dict = {
        "default_mode": sp.default_mode if sp else "STRICT",
        "mask_titles": sp.mask_titles if sp else True,
        "mask_thumbnails": sp.mask_thumbnails if sp else True,
        "mask_comments": sp.mask_comments if sp else True
    }

    # Warning reveals belong to this browser for regular accounts as well as demo viewers.
    unlock_rows = await db.execute(select(BrowserContentUnlock).where(BrowserContentUnlock.session_id == session_id))
    unlocks = [f"{u.content_type}:{u.content_id}:{u.version_no}" for u in unlock_rows.scalars().all()]

    return ViewerContext(
        user_id=user.id,
        roles=[user.role],
        work_progress_by_edition=work_progress_by_edition,
        completed_reveal_ids=list(set(completed_reveals)),
        spoiler_preferences=sp_dict,
        admin_override=(user.role == "ADMIN"),
        session_id=session_id,
        is_shared_demo=is_shared_demo,
        explicit_unlocks=unlocks
    )


async def get_authenticated_user(
    viewer: ViewerContext = Depends(get_viewer_context)
) -> ViewerContext:
    if not viewer.is_authenticated:
        raise ReframeException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ReframeErrorCodes.AUTH_REQUIRED,
            message="Authentication required for this operation"
        )
    return viewer


async def get_authenticated_admin(
    viewer: ViewerContext = Depends(get_authenticated_user)
) -> ViewerContext:
    if not viewer.is_admin:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Administrator privileges required for this operation"
        )
    return viewer


async def enforce_csrf(request: Request) -> None:
    """
    Enforces CSRF token presence and validity for state-changing methods
    when browser session cookies or bearer tokens are used.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if not session_token:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                session_token = auth_header[7:]

        if session_token:
            csrf_token = request.headers.get("X-CSRF-Token") or request.headers.get("X-CSRFToken")
            if not csrf_token or not verify_csrf_token(session_token, csrf_token):
                raise ReframeException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    code="CSRF_REJECTED",
                    message="Missing or invalid CSRF token"
                )



get_current_viewer = get_viewer_context

