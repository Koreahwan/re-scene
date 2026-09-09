"""
Reframe V7 Unified Modular Monolith & Truthful API
"""
from __future__ import annotations
import sys
import os
import json
import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Query, Response, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import structlog

# Add src to sys.path
SRC_DIR = Path(__file__).resolve().parent.parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from src.reframe.shared.config import settings
from src.reframe.shared.database import async_engine, Base
import src.reframe.community.moderation_models  # Register the additive outbox before create_all.
from src.reframe.shared.redis_client import redis_client
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes

# V7 Routers
from apps.api.routers.health import router as health_router
from apps.api.routers.auth import router as auth_router
from apps.api.routers.catalog import router as catalog_router
from apps.api.routers.runs import router as runs_router
from apps.api.routers.fan_experience import router as fan_experience_router
from apps.api.routers.community import router as community_router
from apps.api.routers.theory_lab import router as theory_lab_router
from apps.api.routers.audience_lab import router as audience_lab_router
from apps.api.routers.magazine import router as magazine_router
from apps.api.routers.media import router as media_router
from apps.api.routers.account import router as account_router


# Domain Models
from reframe.domain.models import (
    Film,
    Reveal,
    Scene,
    ReframeResult,
    ReframedMomentCard,
    FanInsight,
    ExecutionTrace,
)
from reframe.domain.enums import ReframeRunStatus, AbstainReason
from reframe.application.orchestrator import ReframeOrchestrator
from reframe.mcp.gateway import (
    OfficialMcpNarrativeMemoryGateway,
    MockNarrativeMemoryGateway,
    ACTIVE_DATASET_VERSION,
)
from reframe.verification.verifier import EvidenceVerifier
from reframe.evals.evaluator import GoldenDatasetEvaluator

logger = structlog.get_logger(__name__)

# Production directories
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PROD_DIR = DATA_DIR / "production"
FIXTURES_DIR = DATA_DIR / "fixtures"
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
WEB_DIST_DIR = WEB_DIR / "dist"

from apps.api.web_delivery import WebDeliveryHandler, is_html_requested

web_delivery = WebDeliveryHandler(
    dist_dir=WEB_DIST_DIR,
    web_dir=WEB_DIR,
    public_dir=WEB_DIR / "public" if (WEB_DIR / "public").exists() else None,
)

RUNS_STORE: Dict[str, ReframeResult] = {}
TRACES_STORE: Dict[str, ExecutionTrace] = {}
INSIGHTS_STORE: Dict[str, List[FanInsight]] = {}
ANALYSIS_CACHE: Dict[str, Tuple[ReframeResult, Optional[ExecutionTrace]]] = {}
ORCHESTRATOR: Optional[ReframeOrchestrator] = None
FILMS_STORE: Dict[str, Film] = {}
REVEALS_STORE: Dict[str, Reveal] = {}
SCENES_STORE: Dict[str, Scene] = {}

PRODUCTION_DATASET_VERSION = ACTIVE_DATASET_VERSION


def load_initial_data() -> None:
    global FILMS_STORE, REVEALS_STORE, SCENES_STORE

    v3_export_path = PROD_DIR / "v3_dataset_export.json"
    if v3_export_path.exists():
        try:
            with open(v3_export_path, "r", encoding="utf-8") as f:
                v3_data = json.load(f)
            film_d = v3_data.get("movie", {})
            if film_d:
                FILMS_STORE[film_d["movie_id"]] = Film(**film_d)
            for rev in v3_data.get("reveals", []):
                REVEALS_STORE[rev["reveal_id"]] = Reveal(**rev)
            for sc in v3_data.get("scenes", []):
                SCENES_STORE[sc["scene_id"]] = Scene(**sc)
        except Exception as e:
            logger.warning("Failed loading v3 production export", error=str(e))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 0. Enforce fail-fast production settings validation (Section 16)
    settings.validate_production_settings()

    # 1. Database Schema Initialization (R4-14)
    if settings.ENVIRONMENT != "production" and settings.SCHEMA_INIT_MODE != "MIGRATIONS_ONLY":
        from sqlalchemy import text
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            try:
                await conn.execute(text("ALTER TABLE post_versions ADD COLUMN inspection_status VARCHAR(64) DEFAULT 'UNVERIFIED_CALLS_DISABLED'"))
            except Exception:
                pass
            try:
                await conn.execute(text("ALTER TABLE comments ADD COLUMN inspection_status VARCHAR(64) DEFAULT 'UNVERIFIED_CALLS_DISABLED'"))
            except Exception:
                pass

    # 2. Seed canonical precomputed proofs in PostgreSQL
    from src.reframe.shared.database import AsyncSessionLocal
    from src.reframe.proof.store import canonical_proof_store
    async with AsyncSessionLocal() as db_session:
        await canonical_proof_store.seed_canonical_proofs(db_session)

    if settings.AUTH_DEMO_ACCOUNT_ENABLED:
        from src.reframe.identity.demo_account import ensure_demo_account
        async with AsyncSessionLocal() as db_session:
            await ensure_demo_account(db_session)

    # 3. Connect Redis
    await redis_client.connect()

    # 4. Load dataset
    load_initial_data()
    from src.reframe.catalog.dataset_import import load_imported_datasets_from_disk
    load_imported_datasets_from_disk(PROD_DIR / "imported_datasets")

    # 5. Start background worker loop ONLY when EMBEDDED_WORKER_ENABLED is explicitly enabled
    worker_task = None
    if settings.EMBEDDED_WORKER_ENABLED:
        import asyncio
        from src.reframe.jobs.worker import worker
        worker_task = asyncio.create_task(worker.run_loop())

    moderation_task = None
    if settings.COMMENT_MODERATION_ENABLED:
        import asyncio
        from src.reframe.community.comment_moderation import run_loop
        moderation_task = asyncio.create_task(run_loop())

    yield

    # Cleanup
    if moderation_task is not None:
        import asyncio
        moderation_task.cancel()
        try:
            await moderation_task
        except asyncio.CancelledError:
            pass
    if worker_task is not None:
        import asyncio
        from src.reframe.jobs.worker import worker
        worker.stop()
        worker_task.cancel()
        try:
            await worker_task
        except (asyncio.CancelledError, Exception):
            pass
    await redis_client.close()
    await async_engine.dispose()



app = FastAPI(
    title="Reframe V7 API",
    description="Dual-Run Retrospective Deep Narrative Forensics API with ClickHouse & Google ADK",
    version="7.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
from apps.api.request_limits import RequestBodyLimitMiddleware

app.add_middleware(RequestBodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Correlation & Logging Middleware
@app.middleware("http")
async def correlation_and_logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    start_time = time.time()
    response: Response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000

    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
    return response


# Server-Issued Browser Session Cookie Middleware
@app.middleware("http")
async def ensure_browser_session_cookie(request: Request, call_next):
    cookie_name = getattr(settings, "BROWSER_SESSION_COOKIE_NAME", "reframe_viewer_session")
    session_id = request.cookies.get(cookie_name)
    is_new = False
    if not session_id:
        session_id = uuid.uuid4().hex
        request.state.browser_session_id = session_id
        is_new = True

    response: Response = await call_next(request)
    if is_new:
        response.set_cookie(
            key=cookie_name,
            value=session_id,
            max_age=getattr(settings, "BROWSER_SESSION_MAX_AGE_SECONDS", 2592000),
            httponly=True,
            samesite="lax",
            path="/"
        )
    return response


# Reframe Exception Handler
@app.exception_handler(ReframeException)
async def reframe_exception_handler(request: Request, exc: ReframeException):
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id
            }
        },
        headers=exc.headers
    )


# Retired playback URL; do not expose source footage through legacy links.
@app.api_route("/media/{filename}", methods=["GET", "HEAD"])
async def serve_media(filename: str):
    raise HTTPException(status_code=410, detail="Video playback is not provided on this site.",
                        headers={"Cache-Control": "no-store"})


# -------------------------------------------------------------
# Legacy Compatibility Endpoints (410 GONE - R4-20)
# -------------------------------------------------------------


@app.api_route("/films/{movie_id}", methods=["GET", "HEAD"])
async def get_film(movie_id: str, request: Request):
    if is_html_requested(request):
        resp = web_delivery.serve_index_html(request)
        v = resp.headers.get("vary")
        if v:
            parts = [p.strip() for p in v.split(",")]
            if "Accept" not in parts:
                parts.append("Accept")
            resp.headers["vary"] = ", ".join(parts)
        else:
            resp.headers["vary"] = "Accept"
        return resp
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=f"ENDPOINT_GONE: Legacy /films/{movie_id} is deprecated. Use GET /api/v1/catalog/works/{movie_id}.",
        headers={"Vary": "Accept"}
    )


@app.api_route("/films/{movie_id}/reveals", methods=["GET", "HEAD"])
async def get_film_reveals(movie_id: str, request: Request):
    if is_html_requested(request):
        resp = web_delivery.serve_index_html(request)
        v = resp.headers.get("vary")
        if v:
            parts = [p.strip() for p in v.split(",")]
            if "Accept" not in parts:
                parts.append("Accept")
            resp.headers["vary"] = ", ".join(parts)
        else:
            resp.headers["vary"] = "Accept"
        return resp
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=f"ENDPOINT_GONE: Legacy /films/{movie_id}/reveals is deprecated. Use GET /api/v1/catalog/works/{movie_id}/reveals.",
        headers={"Vary": "Accept"}
    )


@app.get("/films/{movie_id}/insights")
async def get_film_insights(movie_id: str):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="ENDPOINT_GONE: Legacy /films/{id}/insights is deprecated."
    )


@app.get("/scenes/{scene_id}")
async def get_scene(scene_id: str):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=f"ENDPOINT_GONE: Legacy /scenes/{scene_id} is deprecated. Use GET /api/v1/fan/scenes/{scene_id}."
    )


@app.post("/reframe")
async def reframe_endpoint():
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="ENDPOINT_GONE: Legacy synchronous /reframe endpoint is deprecated. Use asynchronous POST /api/v1/reframe-runs."
    )


@app.get("/traces/{run_id}")
async def get_trace(run_id: str):
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=f"ENDPOINT_GONE: Legacy /traces/{run_id} is deprecated. Use GET /api/v1/reframe-runs/{run_id}/events."
    )


@app.get("/eval/summary")
async def get_evaluation_summary() -> Dict[str, Any]:
    """Evaluation summary without canned 1.0 metrics (R4-21)."""
    return {
        "dataset_version": PRODUCTION_DATASET_VERSION,
        "evaluation_type": "OFFLINE_EVALUATION",
        "status": "EVALUATION_ON_DEMAND",
        "detail": "Execute offline golden eval suite via pytest or dedicated eval worker to compute metrics."
    }


# -------------------------------------------------------------
# Mount V7 Modular Routers
# -------------------------------------------------------------
app.include_router(health_router, prefix="")
app.include_router(health_router, prefix=settings.API_V1_PREFIX)
app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(catalog_router, prefix=settings.API_V1_PREFIX)
app.include_router(runs_router, prefix=settings.API_V1_PREFIX)
app.include_router(fan_experience_router, prefix=settings.API_V1_PREFIX)
app.include_router(community_router, prefix=settings.API_V1_PREFIX)
app.include_router(theory_lab_router, prefix=settings.API_V1_PREFIX)
app.include_router(audience_lab_router, prefix=settings.API_V1_PREFIX)
app.include_router(magazine_router, prefix=settings.API_V1_PREFIX)
app.include_router(media_router, prefix=settings.API_V1_PREFIX)
app.include_router(account_router, prefix=settings.API_V1_PREFIX)



# -------------------------------------------------------------
# Static Web Application & React Build Serving (R4-15)
# -------------------------------------------------------------
@app.api_route("/styles.css", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_styles(request: Request):
    return web_delivery.serve_styles(request)


@app.api_route("/assets/{asset_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_asset(asset_path: str, request: Request):
    return web_delivery.serve_asset(asset_path, request)


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_index(request: Request):
    return web_delivery.serve_index_html(request)


@app.api_route("/community", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/community/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def redirect_community_route(request: Request, path: str = ""):
    if is_html_requested(request):
        return RedirectResponse(url="/films/the-bat-whispers-1930", status_code=status.HTTP_302_FOUND)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"status": "REDIRECTED", "redirect_url": "/films/the-bat-whispers-1930", "message": "Community page has been integrated into film exploration."}
    )


@app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_spa_or_asset(full_path: str, request: Request):
    return web_delivery.handle_spa_or_asset(full_path, request)
