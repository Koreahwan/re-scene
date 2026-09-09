"""
Reframe V7 Authentication & User Me Router
Implements production-shaped signup, login, logout, session management, CSRF hydration,
Argon2id password verification, Redis-backed rate limiting, and watch progress.
Zero Paid Model Calls.
"""
import uuid
import re
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import get_db
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from pydantic import BaseModel
from src.reframe.identity.models import (
    User, Profile, WatchProgress, SpoilerPreferences, UserCredential, AuthOperation,
    BrowserWatchProgress, BrowserContentUnlock
)
from src.reframe.identity.crypto import hash_password, verify_password, validate_password_strength
from src.reframe.identity.validators import validate_handle, validate_email, validate_password
from src.reframe.identity.rate_limit import check_auth_rate_limit
from src.reframe.catalog.service import catalog_service
from src.reframe.identity.auth import (
    get_viewer_context,
    get_authenticated_user,
    ViewerContext,
    create_session_token,
    generate_csrf_token,
    enforce_csrf
)
from src.reframe.identity.outbox import challenge_store, outbox_service
from src.reframe.identity.schemas import (
    UserMeResponse,
    ProfileDTO,
    SpoilerPreferencesDTO,
    WatchProgressDTO,
    UpdateWatchProgressRequest,
    UpdateSpoilerPreferencesRequest,
    DevLoginRequest,
    SignupRequest,
    LoginRequest,
    AuthUserDTO,
    CsrfResponseDTO,
    EmailVerificationRequest,
    EmailVerificationConfirmRequest,
    PasswordResetRequest,
    PasswordResetVerifyRequest,
    PasswordResetCompleteRequest,
    HandleAvailabilityResponseDTO
)

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Auth & Identity"])


@router.get("/auth/demo-account", response_model=Dict[str, Any])
async def get_demo_account(response: Response):
    """Public preview configuration, never credentials for a private identity."""
    from src.reframe.identity.demo_account import public_demo_configuration
    response.headers["Cache-Control"] = "no-store"
    return {"data": public_demo_configuration(settings.AUTH_DEMO_ACCOUNT_ENABLED)}


def require_regular_account_mode() -> None:
    if settings.AUTH_DEMO_ACCOUNT_ENABLED:
        raise ReframeException(status_code=409, code="DEMO_ACCOUNT_ONLY",
                               message="This preview uses one shared demo account. Use the prefilled login details.")


def _set_auth_cookies(response: Response, token: str) -> None:
    """Sets secure HttpOnly session cookie on the response."""
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/"
    )


def _clear_auth_cookies(response: Response) -> None:
    """Deletes session cookie with matching attributes."""
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/"
    )


@router.get("/auth/csrf", response_model=Dict[str, Any])
async def get_csrf_token(
    request: Request,
    viewer: ViewerContext = Depends(get_viewer_context)
):
    """
    Returns a fresh CSRF token for the current session or a secure guest session.
    """
    session_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not session_token:
        # Check authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            session_token = auth_header[7:]

    if not session_token:
        # Generate guest token
        session_token = f"guest-{uuid.uuid4().hex}"

    csrf = generate_csrf_token(session_token)
    return {
        "data": {"csrf_token": csrf},
        "meta": {"is_authenticated": viewer.is_authenticated}
    }


@router.get("/auth/handles/availability", response_model=Dict[str, Any])
async def check_handle_availability(
    handle: str,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Checks if a user handle is available for registration using SSOT handle validator.
    """
    await check_auth_rate_limit(request, action="handle_check", max_requests=30, window_seconds=60)

    try:
        clean_handle, handle_norm = validate_handle(handle)
    except ReframeException:
        return {"data": {"handle": handle.strip() if handle else "", "available": False}}

    stmt = select(User).where(User.handle_normalized == handle_norm)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()

    return {
        "data": {
            "handle": clean_handle,
            "available": existing is None
        }
    }


@router.post("/auth/signup", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
async def signup(
    payload: SignupRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Production user registration endpoint:
    - Pre-validates syntax (email, password, handle) via SSOT validators
    - Idempotency-Key handling via PostgreSQL AuthOperation table
    - Pre-checks duplicate email and handle
    - Atomically reserves verification ticket (AVAILABLE -> RESERVED with operation_id)
    - Persists User, Profile, SpoilerPreferences, and UserCredential in DB transaction
    - Handles uniqueness race conflicts safely and releases reservation on error
    - Atomically burns ticket on commit (RESERVED -> CONSUMED)
    """
    require_regular_account_mode()
    await check_auth_rate_limit(request, action="signup", max_requests=10, window_seconds=60)

    # 1. Pre-validate syntax via SSOT
    clean_email, email_norm = validate_email(payload.email)
    validate_password(payload.password)
    clean_handle, handle_norm = validate_handle(payload.handle)

    # 2. Idempotency Check via AuthOperation
    idempotency_key = (
        request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
        or f"signup_{hashlib.sha256((email_norm + payload.email_verification_ticket).encode()).hexdigest()[:32]}"
    )
    email_hash = hashlib.sha256(email_norm.encode()).hexdigest()
    ticket_hash = hashlib.sha256(payload.email_verification_ticket.encode()).hexdigest()

    existing_op_stmt = select(AuthOperation).where(AuthOperation.idempotency_key == idempotency_key)
    existing_op_res = await db.execute(existing_op_stmt)
    existing_op = existing_op_res.scalar_one_or_none()

    if existing_op:
        if existing_op.email_hash == email_hash and existing_op.ticket_hash == ticket_hash:
            if existing_op.status in ("COMPLETED", "DB_COMMITTED") and existing_op.result_json:
                return existing_op.result_json
        else:
            raise ReframeException(
                status_code=status.HTTP_409_CONFLICT,
                code="AUTH_IDEMPOTENCY_CONFLICT",
                message="Idempotency key already used with different parameters."
            )

    # 3. Pre-check duplicate email
    stmt = select(User).where(User.email_normalized == email_norm)
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise ReframeException(
            status_code=status.HTTP_409_CONFLICT,
            code="AUTH_EMAIL_UNAVAILABLE",
            message="An account with this email address already exists."
        )

    # 4. Pre-check duplicate handle if provided
    if handle_norm:
        h_stmt = select(User).where(User.handle_normalized == handle_norm)
        h_res = await db.execute(h_stmt)
        if h_res.scalars().first():
            raise ReframeException(
                status_code=status.HTTP_409_CONFLICT,
                code="AUTH_HANDLE_UNAVAILABLE",
                message="This handle is already taken. Please choose another."
            )

    # 5. Create AuthOperation record
    auth_op_id = uuid.uuid4()
    auth_op = AuthOperation(
        id=auth_op_id,
        idempotency_key=idempotency_key,
        operation_type="SIGNUP",
        email_hash=email_hash,
        ticket_hash=ticket_hash,
        status="STARTED"
    )
    db.add(auth_op)
    await db.flush()

    # 6. Atomically reserve verification ticket
    is_reserved = challenge_store.reserve_verification_ticket(
        ticket=payload.email_verification_ticket,
        email=email_norm,
        operation_id=auth_op_id.hex
    )
    if not is_reserved:
        auth_op.status = "FAILED"
        auth_op.failure_code = "AUTH_EMAIL_NOT_VERIFIED"
        await db.commit()
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_EMAIL_NOT_VERIFIED",
            message="Invalid, expired, or already used email verification ticket. Please verify your email again."
        )

    auth_op.status = "TICKET_RESERVED"

    # 7. Persist DB entities in atomic transaction
    user_id = uuid.uuid4()
    try:
        user = User(
            id=user_id,
            email_normalized=email_norm,
            handle=clean_handle,
            handle_normalized=handle_norm,
            status="ACTIVE",
            role="USER",
            auth_version=1
        )
        db.add(user)

        display_name = (
            payload.display_name.strip()
            if payload.display_name and payload.display_name.strip()
            else (clean_handle or email_norm.split("@")[0].capitalize())
        )
        profile = Profile(
            user_id=user_id,
            display_name=display_name,
            locale=payload.locale or "en-US",
            fan_depth="REGULAR"
        )
        db.add(profile)

        spoiler_prefs = SpoilerPreferences(
            user_id=user_id,
            default_mode="STRICT",
            mask_titles=True,
            mask_thumbnails=True,
            mask_comments=True
        )
        db.add(spoiler_prefs)

        pwd_hash = hash_password(payload.password)
        cred = UserCredential(
            user_id=user_id,
            password_hash=pwd_hash,
            password_algorithm="argon2id",
            password_updated_at=datetime.now(timezone.utc),
            failed_attempt_count=0
        )
        db.add(cred)

        auth_op.user_id = user_id
        auth_op.status = "DB_COMMITTED"

        session_token = create_session_token(user_id=user_id, role="USER", auth_version=1)
        _set_auth_cookies(response, session_token)
        csrf_token = generate_csrf_token(session_token)

        result_payload = {
            "data": {
                "user_id": str(user_id),
                "email": email_norm,
                "display_name": profile.display_name,
                "handle": user.handle,
                "role": "USER",
                "csrf_token": csrf_token
            },
            "meta": {"message": "Account created successfully"}
        }
        auth_op.result_json = result_payload

        await db.commit()

        # 8. Consume ticket in Redis
        try:
            challenge_store.confirm_consumed_verification_ticket(
                ticket=payload.email_verification_ticket,
                email=email_norm,
                operation_id=auth_op_id.hex
            )
            auth_op.status = "COMPLETED"
            await db.commit()
        except Exception as e:
            logger.warning("auth_ticket_consumption_redis_reconciliation_needed", error=str(e))
            auth_op.status = "RECONCILIATION_REQUIRED"
            await db.commit()

        logger.info("user_registered_successfully", user_id=str(user_id))
        return result_payload

    except IntegrityError as e:
        await db.rollback()
        challenge_store.release_verification_ticket(
            ticket=payload.email_verification_ticket,
            email=email_norm,
            operation_id=auth_op_id.hex
        )
        err_msg = str(e.orig).lower() if hasattr(e, "orig") else str(e).lower()
        if "handle" in err_msg:
            raise ReframeException(
                status_code=status.HTTP_409_CONFLICT,
                code="AUTH_HANDLE_UNAVAILABLE",
                message="This handle is already taken. Please choose another."
            )
        else:
            raise ReframeException(
                status_code=status.HTTP_409_CONFLICT,
                code="AUTH_EMAIL_UNAVAILABLE",
                message="An account with this email address already exists."
            )
    except Exception:
        await db.rollback()
        challenge_store.release_verification_ticket(
            ticket=payload.email_verification_ticket,
            email=email_norm,
            operation_id=auth_op_id.hex
        )
        raise
    except Exception:
        await db.rollback()
        challenge_store.release_verification_ticket(
            ticket=payload.email_verification_ticket,
            email=email_norm,
            operation_id=auth_op_id.hex
        )
        raise


@router.post("/auth/login", status_code=status.HTTP_200_OK)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Production user login endpoint:
    - Verifies password using Argon2id against UserCredential
    - Checks user status == ACTIVE
    - Issues fresh HttpOnly session cookie
    - Returns safe user data + CSRF token (no raw passwords or session tokens in JSON)
    """
    await check_auth_rate_limit(request, action="login", max_requests=10, window_seconds=60)

    email_norm = payload.email.strip().lower()

    # Load User with UserCredential and Profile
    stmt = select(User).where(User.email_normalized == email_norm)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if (not user or user.status != "ACTIVE"
            or (user.account_origin == "PUBLIC_DEMO" and (not settings.AUTH_DEMO_ACCOUNT_ENABLED or user.role != "USER"))):
        logger.warning("login_failed_user_not_found_or_inactive", email=email_norm)
        raise ReframeException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID_CREDENTIALS",
            message="Invalid email or password."
        )

    # Load credentials
    cred_stmt = select(UserCredential).where(UserCredential.user_id == user.id)
    cred_res = await db.execute(cred_stmt)
    credentials = cred_res.scalar_one_or_none()

    now_utc = datetime.now(timezone.utc)
    if credentials and credentials.locked_until:
        locked_dt = credentials.locked_until
        if locked_dt.tzinfo is None:
            locked_dt = locked_dt.replace(tzinfo=timezone.utc)
        if locked_dt > now_utc:
            logger.warning("login_blocked_account_locked", user_id=str(user.id))
            raise ReframeException(
                status_code=status.HTTP_403_FORBIDDEN,
                code="AUTH_ACCOUNT_LOCKED",
                message="Account is temporarily locked due to multiple failed login attempts. Please try again later."
            )

    if not credentials or not verify_password(payload.password, credentials.password_hash):
        if credentials:
            credentials.failed_attempt_count += 1
            if credentials.failed_attempt_count >= 5:
                credentials.locked_until = now_utc + timedelta(minutes=15)
            await db.commit()
        logger.warning("login_failed_invalid_password", user_id=str(user.id))
        raise ReframeException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="AUTH_INVALID_CREDENTIALS",
            message="Invalid email or password."
        )


    # Reset failed attempts on success
    if credentials.failed_attempt_count > 0 or credentials.locked_until is not None:
        credentials.failed_attempt_count = 0
        credentials.locked_until = None
        await db.commit()

    # Fetch profile
    prof_stmt = select(Profile).where(Profile.user_id == user.id)
    prof_res = await db.execute(prof_stmt)
    profile = prof_res.scalar_one_or_none()

    # Issue session with user.auth_version
    token = create_session_token(user.id, user.role, auth_version=getattr(user, "auth_version", 1))
    csrf_token = generate_csrf_token(token)

    _set_auth_cookies(response, token)

    logger.info("user_logged_in_successfully", user_id=str(user.id), email=email_norm)

    return {
        "data": {
            "user_id": str(user.id),
            "email": user.email_normalized,
            "display_name": profile.display_name if profile else email_norm.split("@")[0].capitalize(),
            "handle": user.handle,
            "role": user.role,
            "fan_depth": profile.fan_depth if profile else "REGULAR",
            "csrf_token": csrf_token
        },
        "meta": {"message": "Authenticated successfully"}
    }


@router.post("/auth/logout", status_code=status.HTTP_200_OK)
async def logout(
    response: Response,
    _csrf: None = Depends(enforce_csrf)
):
    """
    State-changing logout requiring valid CSRF token.
    Clears session cookie.
    """
    _clear_auth_cookies(response)
    return {"data": {"logged_out": True}, "meta": {"message": "Logged out successfully"}}


@router.get("/auth/me", response_model=Dict[str, Any])
@router.get("/me", response_model=Dict[str, Any])
@router.get("/profiles/me", response_model=Dict[str, Any])
async def get_my_profile(
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    """
    Returns profile and spoiler preferences for current viewer context.
    """
    if not viewer.is_authenticated:
        return {
            "data": {
                "id": None,
                "display_name": "Guest Viewer",
                "role": "GUEST",
                "fan_depth": "CASUAL",
                "spoiler_preferences": viewer.spoiler_preferences
            },
            "meta": {"is_authenticated": False}
        }

    # Fetch profile
    prof_stmt = select(Profile).where(Profile.user_id == viewer.user_id)
    prof_res = await db.execute(prof_stmt)
    profile = prof_res.scalar_one_or_none()

    # Fetch user for email
    user_stmt = select(User).where(User.id == viewer.user_id)
    user_res = await db.execute(user_stmt)
    user = user_res.scalar_one_or_none()

    return {
        "data": {
            "id": str(viewer.user_id),
            "email": user.email_normalized if user else None,
            "display_name": profile.display_name if profile else "Viewer",
            "bio": profile.bio if profile else None,
            "avatar_url": profile.avatar_url if profile else None,
            "role": viewer.roles[0] if viewer.roles else "USER",
            "fan_depth": profile.fan_depth if profile else "REGULAR",
            "spoiler_preferences": viewer.spoiler_preferences
        },
        "meta": {"is_authenticated": True}
    }


@router.post("/auth/dev-login", status_code=status.HTTP_200_OK)
async def dev_login(
    payload: DevLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Local development login provider. Strictly disabled in production (requires AUTH_DEV_MODE=true).
    Always assigns USER role; never allows privilege escalation to ADMIN / MODERATOR.
    """
    if not settings.AUTH_DEV_MODE:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Development login is disabled in this environment."
        )

    email_norm = payload.email.strip().lower()
    stmt = select(User).where(User.email_normalized == email_norm)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if user:
        if user.status != "ACTIVE" or user.account_origin == "SYNTHETIC_DEMO":
            raise ReframeException(
                status_code=status.HTTP_403_FORBIDDEN,
                code=ReframeErrorCodes.FORBIDDEN,
                message="Account is disabled or is a synthetic demo user."
            )
    else:
        if email_norm.endswith("@example.invalid") or "demo_synthetic_" in email_norm:
            raise ReframeException(
                status_code=status.HTTP_403_FORBIDDEN,
                code=ReframeErrorCodes.FORBIDDEN,
                message="Cannot create live user with synthetic demo email domain."
            )

        user = User(
            id=uuid.uuid4(),
            email_normalized=email_norm,
            status="ACTIVE",
            role="USER"
        )
        db.add(user)
        await db.flush()

        profile = Profile(
            user_id=user.id,
            display_name=payload.display_name or email_norm.split("@")[0].capitalize(),
            locale="en",
            fan_depth="REGULAR"
        )
        db.add(profile)

        spoiler_prefs = SpoilerPreferences(
            user_id=user.id,
            default_mode="STRICT",
            mask_titles=True,
            mask_thumbnails=True,
            mask_comments=True
        )
        db.add(spoiler_prefs)
        await db.commit()

    token = create_session_token(user.id, user.role)
    csrf_token = generate_csrf_token(token)

    _set_auth_cookies(response, token)

    return {
        "data": {
            "user_id": str(user.id),
            "email": user.email_normalized,
            "role": user.role,
            "csrf_token": csrf_token
        },
        "meta": {"message": "Authenticated successfully"}
    }


@router.get("/auth/google/callback", status_code=status.HTTP_200_OK)
async def google_oidc_callback():
    """
    Production Google OIDC Authentication Callback.
    Marked EXTERNAL_PENDING when live Google credentials are not configured in environment.
    """
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return {
            "status": "EXTERNAL_PENDING",
            "message": "Google OIDC credentials not configured in environment.",
            "provider": "google_oidc"
        }
    return {
        "status": "CONFIGURED",
        "redirect_uri": settings.GOOGLE_OIDC_REDIRECT_URI
    }


class ContentUnlockRequest(BaseModel):
    content_type: str = "POST"  # POST, COMMENT
    content_id: uuid.UUID
    version_no: int = 1


@router.get("/viewer/watch-progress", response_model=Dict[str, Any])
@router.get("/me/watch-progress", response_model=Dict[str, Any])
async def get_my_watch_progress(
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
):
    # Decoupled browser session progress (Phase 1)
    if viewer.is_public_author or viewer.is_shared_demo or (not viewer.is_authenticated and viewer.session_id):
        stmt = select(BrowserWatchProgress).where(BrowserWatchProgress.session_id == viewer.session_id)
        res = await db.execute(stmt)
        records = res.scalars().all()
        items = [
            WatchProgressDTO(
                work_id=r.work_id,
                edition_id=r.edition_id,
                state=r.state,
                progress_ms=r.progress_ms,
                completed_reveal_ids=r.completed_reveal_ids if isinstance(r.completed_reveal_ids, list) else [],
                updated_at=r.updated_at
            )
            for r in records
        ]
        return {"data": items, "meta": {"count": len(items), "session_id": viewer.session_id}}

    if not viewer.is_authenticated:
        raise ReframeException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ReframeErrorCodes.AUTH_REQUIRED,
            message="Authentication required for this operation"
        )

    stmt = select(WatchProgress).where(WatchProgress.user_id == viewer.user_id)
    res = await db.execute(stmt)
    records = res.scalars().all()

    items = [
        WatchProgressDTO(
            work_id=r.work_id,
            edition_id=r.edition_id,
            state=r.state,
            progress_ms=r.progress_ms,
            completed_reveal_ids=r.completed_reveal_ids if isinstance(r.completed_reveal_ids, list) else [],
            updated_at=r.updated_at
        )
        for r in records
    ]
    return {"data": items, "meta": {"count": len(items)}}


@router.put("/viewer/watch-progress/{work_id}", response_model=Dict[str, Any])
@router.put("/me/watch-progress/{work_id}", response_model=Dict[str, Any])
async def update_watch_progress(
    work_id: str,
    payload: UpdateWatchProgressRequest,
    viewer: ViewerContext = Depends(get_viewer_context),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    # Server-side validation of work_id, edition_id, progress bounds, and reveal IDs (Section 17)
    try:
        catalog_service.validate_watch_progress(
            work_id=work_id,
            edition_id=payload.edition_id,
            progress_ms=payload.progress_ms,
            completed_reveal_ids=payload.completed_reveal_ids
        )
    except ValueError as val_err:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message=str(val_err)
        )

    # Decoupled browser session progress (Phase 1)
    if viewer.is_public_author or viewer.is_shared_demo or (not viewer.is_authenticated and viewer.session_id):
        session_id = viewer.session_id
        stmt = select(BrowserWatchProgress).where(
            BrowserWatchProgress.session_id == session_id,
            BrowserWatchProgress.work_id == work_id,
            BrowserWatchProgress.edition_id == payload.edition_id
        )
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if not record:
            record = BrowserWatchProgress(
                id=uuid.uuid4(),
                session_id=session_id,
                work_id=work_id,
                edition_id=payload.edition_id,
                state=payload.state,
                progress_ms=payload.progress_ms,
                completed_reveal_ids=payload.completed_reveal_ids,
                updated_at=now
            )
            db.add(record)
        else:
            record.state = payload.state
            record.progress_ms = payload.progress_ms
            record.completed_reveal_ids = payload.completed_reveal_ids
            record.updated_at = now

        await db.commit()
        await db.refresh(record)

        return {
            "data": {
                "work_id": work_id,
                "edition_id": payload.edition_id,
                "state": record.state,
                "progress_ms": record.progress_ms,
                "completed_reveal_ids": record.completed_reveal_ids
            },
            "meta": {"message": "Browser watch progress updated", "session_id": session_id}
        }

    if not viewer.is_authenticated:
        raise ReframeException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ReframeErrorCodes.AUTH_REQUIRED,
            message="Authentication required for this operation"
        )

    stmt = select(WatchProgress).where(
        WatchProgress.user_id == viewer.user_id,
        WatchProgress.work_id == work_id,
        WatchProgress.edition_id == payload.edition_id
    )
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        record = WatchProgress(
            user_id=viewer.user_id,
            work_id=work_id,
            edition_id=payload.edition_id,
            state=payload.state,
            progress_ms=payload.progress_ms,
            completed_reveal_ids=payload.completed_reveal_ids
        )
        db.add(record)
    else:
        record.state = payload.state
        record.progress_ms = payload.progress_ms
        record.completed_reveal_ids = payload.completed_reveal_ids

    await db.commit()

    return {
        "data": {
            "work_id": work_id,
            "edition_id": payload.edition_id,
            "state": record.state,
            "progress_ms": record.progress_ms,
            "completed_reveal_ids": record.completed_reveal_ids
        },
        "meta": {"message": "Watch progress updated"}
    }


@router.post("/viewer/unlock", response_model=Dict[str, Any])
async def unlock_content(
    payload: ContentUnlockRequest,
    viewer: ViewerContext = Depends(get_viewer_context),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    session_id = viewer.session_id
    if not session_id:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.VALIDATION_ERROR,
            message="Browser session required for unlocking content"
        )

    if payload.content_type not in ("POST", "COMMENT"):
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.VALIDATION_ERROR,
            message=f"Invalid content_type '{payload.content_type}'. Only POST and COMMENT can be unlocked."
        )

    if payload.content_type == "POST":
        from src.reframe.community.models import Post, PostVersion
        post_stmt = select(Post).where(Post.id == payload.content_id)
        post = (await db.execute(post_stmt)).scalar_one_or_none()
        if not post:
            raise ReframeException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ReframeErrorCodes.NOT_FOUND,
                message=f"Post '{payload.content_id}' not found"
            )
        if post.status != "PUBLISHED":
            raise ReframeException(
                status_code=status.HTTP_410_GONE if post.status in ("REMOVED", "DELETED") else status.HTTP_400_BAD_REQUEST,
                code=ReframeErrorCodes.CONTENT_REMOVED if post.status in ("REMOVED", "DELETED") else ReframeErrorCodes.VALIDATION_ERROR,
                message=f"Cannot unlock post with status '{post.status}'. Only published posts can be unlocked."
            )
        if post.content_type == "MAGAZINE_ARTICLE":
            raise ReframeException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=ReframeErrorCodes.VALIDATION_ERROR,
                message="Magazine articles cannot be unlocked via individual warning unlock"
            )
        ver_stmt = select(PostVersion).where(PostVersion.post_id == post.id).order_by(PostVersion.version_no.desc()).limit(1)
        latest_ver = (await db.execute(ver_stmt)).scalar_one_or_none()
        latest_version_no = latest_ver.version_no if latest_ver else 1
        if payload.version_no != latest_version_no:
            raise ReframeException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=ReframeErrorCodes.VERSION_CONFLICT,
                message=f"Version mismatch: current post version is {latest_version_no}, cannot unlock version {payload.version_no}"
            )
    elif payload.content_type == "COMMENT":
        from src.reframe.community.models import Comment, Post
        comm_stmt = select(Comment).where(Comment.id == payload.content_id)
        comment = (await db.execute(comm_stmt)).scalar_one_or_none()
        if not comment:
            raise ReframeException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ReframeErrorCodes.NOT_FOUND,
                message=f"Comment '{payload.content_id}' not found"
            )
        if comment.status != "PUBLISHED":
            raise ReframeException(
                status_code=status.HTTP_410_GONE if comment.status in ("REMOVED", "DELETED") else status.HTTP_400_BAD_REQUEST,
                code=ReframeErrorCodes.CONTENT_REMOVED if comment.status in ("REMOVED", "DELETED") else ReframeErrorCodes.VALIDATION_ERROR,
                message=f"Cannot unlock comment with status '{comment.status}'."
            )
        parent_stmt = select(Post).where(Post.id == comment.post_id)
        parent_post = (await db.execute(parent_stmt)).scalar_one_or_none()
        if not parent_post or parent_post.status != "PUBLISHED":
            raise ReframeException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=ReframeErrorCodes.VALIDATION_ERROR,
                message="Cannot unlock comment under non-published or removed parent post"
            )
        comm_ver = comment.version_no if hasattr(comment, "version_no") and comment.version_no is not None else 1
        # Explicit spoiler consent does not certify an AI inspection. The body
        # stays masked for other sessions and for every later edited version.
        if payload.version_no != comm_ver:
            raise ReframeException(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=ReframeErrorCodes.VERSION_CONFLICT,
                message=f"Version mismatch: current comment version is {comm_ver}, cannot unlock version {payload.version_no}"
            )

    stmt = select(BrowserContentUnlock).where(
        BrowserContentUnlock.session_id == session_id,
        BrowserContentUnlock.content_type == payload.content_type,
        BrowserContentUnlock.content_id == payload.content_id,
        BrowserContentUnlock.version_no == payload.version_no
    )
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()
    if not existing:
        unlock = BrowserContentUnlock(
            id=uuid.uuid4(),
            session_id=session_id,
            content_type=payload.content_type,
            content_id=payload.content_id,
            version_no=payload.version_no,
            unlocked_at=datetime.now(timezone.utc)
        )
        db.add(unlock)
        await db.commit()

    return {
        "status": "SUCCESS",
        "data": {
            "session_id": session_id,
            "content_type": payload.content_type,
            "content_id": str(payload.content_id),
            "version_no": payload.version_no,
            "unlocked": True
        }
    }



@router.get("/me/spoiler-preferences", response_model=Dict[str, Any])
async def get_spoiler_preferences(
    viewer: ViewerContext = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(SpoilerPreferences).where(SpoilerPreferences.user_id == viewer.user_id)
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()
    if not record:
        return {
            "data": {
                "default_mode": "STRICT_CUTOFF",
                "mask_titles": True,
                "mask_thumbnails": True,
                "mask_comments": True
            }
        }
    return {
        "data": {
            "default_mode": record.default_mode,
            "mask_titles": record.mask_titles,
            "mask_thumbnails": record.mask_thumbnails,
            "mask_comments": record.mask_comments
        }
    }


@router.put("/me/spoiler-preferences", response_model=Dict[str, Any])
async def update_spoiler_preferences(

    payload: UpdateSpoilerPreferencesRequest,
    viewer: ViewerContext = Depends(get_authenticated_user),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db)
):
    if viewer.is_shared_demo:
        raise ReframeException(status_code=409, code="DEMO_PREFERENCES_FIXED",
                               message="Shared demo preferences stay strict. Adjust your browser viewing position instead.")
    stmt = select(SpoilerPreferences).where(SpoilerPreferences.user_id == viewer.user_id)
    res = await db.execute(stmt)
    record = res.scalar_one_or_none()

    if not record:
        record = SpoilerPreferences(
            user_id=viewer.user_id,
            default_mode=payload.default_mode,
            mask_titles=payload.mask_titles,
            mask_thumbnails=payload.mask_thumbnails,
            mask_comments=payload.mask_comments
        )
        db.add(record)
    else:
        record.default_mode = payload.default_mode
        record.mask_titles = payload.mask_titles
        record.mask_thumbnails = payload.mask_thumbnails
        record.mask_comments = payload.mask_comments

    await db.commit()

    return {
        "data": {
            "default_mode": record.default_mode,
            "mask_titles": record.mask_titles,
            "mask_thumbnails": record.mask_thumbnails,
            "mask_comments": record.mask_comments
        },
        "meta": {"message": "Spoiler preferences updated"}
    }


# =========================================================================
# Email Verification Subsystem (Server Challenge + Opaque Ticket)
# =========================================================================

@router.post("/auth/email-verification/request", status_code=status.HTTP_200_OK)
async def request_email_verification(
    payload: EmailVerificationRequest,
    request: Request
):
    """
    Dispatches a 6-digit verification code to the requested email address.
    Enforces resend cooldown and rate limits.
    """
    require_regular_account_mode()
    await check_auth_rate_limit(
        request,
        action="email_verification_request",
        max_requests=settings.AUTH_EMAIL_VERIFICATION_MAX_REQUESTS,
        window_seconds=settings.AUTH_EMAIL_VERIFICATION_WINDOW_SECONDS
    )

    email_norm = payload.email.strip().lower()
    email_pattern = r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$"
    if not re.match(email_pattern, email_norm):
        raise ReframeException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Invalid email address format."
        )

    cooldown = challenge_store.check_resend_cooldown(email_norm, purpose="verification")
    if cooldown is not None:
        raise ReframeException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="AUTH_RATE_LIMITED",
            message=f"Please wait {cooldown} seconds before requesting another verification code."
        )

    challenge_store.create_code_challenge(email_norm, purpose="verification")
    email_hash = hashlib.sha256(email_norm.encode()).hexdigest()[:12]
    logger.info("email_verification_code_dispatched", email_hash=email_hash)

    return {
        "data": {"sent": True, "expires_in_seconds": settings.AUTH_CODE_TTL_SECONDS},
        "meta": {"message": "Verification code has been dispatched."}
    }


@router.post("/auth/email-verification/confirm", status_code=status.HTTP_200_OK)
async def confirm_email_verification(
    payload: EmailVerificationConfirmRequest,
    request: Request
):
    """
    Validates and consumes a verification code, issuing a short-lived one-time ticket for signup.
    """
    require_regular_account_mode()
    await check_auth_rate_limit(request, action="email_verification_confirm", max_requests=10, window_seconds=60)

    email_norm = payload.email.strip().lower()
    is_valid = challenge_store.verify_and_consume_code(email_norm, payload.code, purpose="verification")

    if not is_valid:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_CODE_INVALID",
            message="Invalid or expired verification code."
        )

    ticket = challenge_store.issue_verification_ticket(email_norm)

    return {
        "data": {
            "verified": True,
            "email_verification_ticket": ticket
        },
        "meta": {"message": "Email address successfully verified."}
    }


# =========================================================================
# Password Reset Subsystem (Anti-Enumeration, Opaque Reset Ticket, Session Revocation)
# =========================================================================

@router.post("/auth/password-reset/request", status_code=status.HTTP_200_OK)
async def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Initiates password recovery. Returns generic response to prevent account enumeration.
    """
    require_regular_account_mode()
    await check_auth_rate_limit(request, action="password_reset_request", max_requests=5, window_seconds=60)

    email_norm = payload.email.strip().lower()
    email_hash = hashlib.sha256(email_norm.encode()).hexdigest()[:12]

    stmt = select(User).where(User.email_normalized == email_norm)
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if user and user.status == "ACTIVE":
        cooldown = challenge_store.check_resend_cooldown(email_norm, purpose="password_reset")
        if cooldown is None:
            challenge_store.create_code_challenge(email_norm, purpose="password_reset")
            logger.info("password_reset_code_dispatched", email_hash=email_hash)

    # Generic anti-enumeration response
    return {
        "data": {"sent": True, "expires_in_seconds": settings.AUTH_CODE_TTL_SECONDS},
        "meta": {"message": "If an account exists with this email, a password recovery code has been sent."}
    }


@router.post("/auth/password-reset/verify", status_code=status.HTTP_200_OK)
async def verify_password_reset_code(
    payload: PasswordResetVerifyRequest,
    request: Request
):
    """
    Verifies and consumes the 6-digit recovery code, issuing an opaque password_reset_ticket.
    """
    require_regular_account_mode()
    await check_auth_rate_limit(request, action="password_reset_verify", max_requests=10, window_seconds=60)

    email_norm = payload.email.strip().lower()
    is_valid = challenge_store.verify_and_consume_code(email_norm, payload.code, purpose="password_reset")

    if not is_valid:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_CODE_INVALID",
            message="Invalid or expired recovery code."
        )

    ticket = challenge_store.issue_password_reset_ticket(email_norm)

    return {
        "data": {
            "valid": True,
            "password_reset_ticket": ticket
        },
        "meta": {"message": "Recovery code verified. Proceed to set new password."}
    }


@router.post("/auth/password-reset/complete", status_code=status.HTTP_200_OK)
async def complete_password_reset(
    payload: PasswordResetCompleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """
    Idempotent Password Reset Saga:
    - Validates new password complexity via SSOT
    - Checks Idempotency-Key via AuthOperation
    - Atomically reserves password reset ticket (AVAILABLE -> RESERVED with operation_id)
    - Row-locks User and UserCredential with with_for_update()
    - Updates Argon2id password hash and increments user.auth_version
    - Commits DB transaction (DB_COMMITTED)
    - Burns reset ticket in Redis (TICKET_CONSUMED -> COMPLETED)
    - Releases reservation on DB error
    """
    require_regular_account_mode()
    await check_auth_rate_limit(request, action="password_reset_complete", max_requests=5, window_seconds=60)

    # 1. Validate password strength via SSOT
    validate_password(payload.new_password)
    email_norm = payload.email.strip().lower()

    # 2. Idempotency Check via AuthOperation
    idempotency_key = (
        request.headers.get("Idempotency-Key")
        or request.headers.get("X-Idempotency-Key")
        or f"reset_{hashlib.sha256((email_norm + payload.password_reset_ticket).encode()).hexdigest()[:32]}"
    )
    email_hash = hashlib.sha256(email_norm.encode()).hexdigest()
    ticket_hash = hashlib.sha256(payload.password_reset_ticket.encode()).hexdigest()

    existing_op_stmt = select(AuthOperation).where(AuthOperation.idempotency_key == idempotency_key)
    existing_op_res = await db.execute(existing_op_stmt)
    existing_op = existing_op_res.scalar_one_or_none()

    if existing_op:
        if existing_op.email_hash == email_hash and existing_op.ticket_hash == ticket_hash:
            if existing_op.status in ("COMPLETED", "DB_COMMITTED") and existing_op.result_json:
                return existing_op.result_json
        else:
            raise ReframeException(
                status_code=status.HTTP_409_CONFLICT,
                code="AUTH_IDEMPOTENCY_CONFLICT",
                message="Idempotency key already used with different parameters."
            )

    # 3. Create AuthOperation record
    auth_op_id = uuid.uuid4()
    auth_op = AuthOperation(
        id=auth_op_id,
        idempotency_key=idempotency_key,
        operation_type="PASSWORD_RESET",
        email_hash=email_hash,
        ticket_hash=ticket_hash,
        status="STARTED"
    )
    db.add(auth_op)
    await db.flush()

    # 4. Atomically reserve reset ticket (AVAILABLE -> RESERVED)
    is_reserved = challenge_store.reserve_password_reset_ticket(
        ticket=payload.password_reset_ticket,
        email=email_norm,
        operation_id=auth_op_id.hex
    )
    if not is_reserved:
        auth_op.status = "FAILED"
        auth_op.failure_code = "AUTH_CODE_INVALID"
        await db.commit()
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="AUTH_CODE_INVALID",
            message="Invalid, expired, or already used password reset ticket. Please restart password recovery."
        )

    auth_op.status = "TICKET_RESERVED"

    # 5. Fetch User and Credential with row lock and commit password update
    try:
        stmt = select(User).where(User.email_normalized == email_norm).with_for_update()
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if not user:
            raise ReframeException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ReframeErrorCodes.NOT_FOUND,
                message="Account not found."
            )

        cred_stmt = select(UserCredential).where(UserCredential.user_id == user.id).with_for_update()
        cred_res = await db.execute(cred_stmt)
        credential = cred_res.scalar_one_or_none()

        now_utc = datetime.now(timezone.utc)
        new_hash = hash_password(payload.new_password)

        if not credential:
            credential = UserCredential(
                user_id=user.id,
                password_hash=new_hash,
                password_algorithm="argon2id",
                password_updated_at=now_utc,
                failed_attempt_count=0
            )
            db.add(credential)
        else:
            credential.password_hash = new_hash
            credential.password_updated_at = now_utc
            credential.failed_attempt_count = 0
            credential.locked_until = None

        # Increment auth_version to revoke previous sessions
        user.auth_version = (getattr(user, "auth_version", None) or 1) + 1
        auth_op.user_id = user.id
        auth_op.status = "DB_COMMITTED"

        result_payload = {
            "data": {"updated": True},
            "meta": {"message": "Password updated successfully. All previous sessions have been revoked. Please log in."}
        }
        auth_op.result_json = result_payload

        await db.commit()

        # 6. Consume reset ticket in Redis
        try:
            challenge_store.confirm_consumed_password_reset_ticket(
                ticket=payload.password_reset_ticket,
                email=email_norm,
                operation_id=auth_op_id.hex
            )
            auth_op.status = "COMPLETED"
            await db.commit()
        except Exception as e:
            logger.warning("auth_reset_ticket_consumption_redis_reconciliation_needed", error=str(e))
            auth_op.status = "RECONCILIATION_REQUIRED"
            await db.commit()

        logger.info("password_reset_completed_and_sessions_revoked", user_id=str(user.id), new_auth_version=user.auth_version)
        return result_payload

    except Exception as e:
        await db.rollback()
        challenge_store.release_password_reset_ticket(
            ticket=payload.password_reset_ticket,
            email=email_norm,
            operation_id=auth_op_id.hex
        )
        raise e


# =========================================================================
# Development Outbox Viewer (Dev/Test Loopback Only)
# =========================================================================

@router.get("/dev/auth/outbox", response_model=Dict[str, Any])
async def get_dev_outbox(request: Request):
    """
    Returns active dev outbox messages for browser testing and local development.
    Strictly blocked in production (returns 404).
    In non-production, requires loopback or local-dev token.
    """
    if (
        settings.ENVIRONMENT == "production"
        or not settings.AUTH_DEV_OUTBOX_VIEWER_ENABLED
        or settings.AUTH_EMAIL_DELIVERY_MODE != "DEV_OUTBOX"
    ):
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Not found"
        )

    client_host = request.client.host if request.client else ""
    dev_token = request.headers.get("X-Dev-Outbox-Token") or request.query_params.get("dev_token")
    is_loopback = (
        client_host in ("127.0.0.1", "localhost", "::1", "testclient", "")
        or client_host.startswith("172.")
        or client_host.startswith("10.")
    )
    secret = getattr(settings, "AUTH_CODE_HMAC_SECRET", None) or settings.SECRET_KEY
    is_valid_token = dev_token == hashlib.sha256(secret.encode()).hexdigest()[:16]



    if not is_loopback and not is_valid_token:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Dev outbox access restricted to loopback clients"
        )

    messages = challenge_store.get_dev_outbox_messages()
    return {
        "data": messages,
        "meta": {"total": len(messages)}
    }



