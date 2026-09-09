"""
Reframe V7 Health & Operations Endpoints (/live, /ready, /health, /admin/health)
Implements truthful health observability without hardcoded flags (R4.1-25 & R4.1-26).
Zero Paid Model Calls.
"""
from enum import Enum
from pathlib import Path
from typing import Dict, Any
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import httpx
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import get_db
from src.reframe.shared.redis_client import redis_client
from src.reframe.identity.auth import get_viewer_context, ViewerContext
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.evidence.adapter import v3_adapter

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["Health"])


class GeminiHealthStatus(str, Enum):
    DISABLED = "DISABLED"
    NOT_TESTED = "NOT_TESTED"
    CONFIGURED_NOT_VERIFIED = "CONFIGURED_NOT_VERIFIED"
    LAST_LIVE_CHECK_OK = "LAST_LIVE_CHECK_OK"
    LAST_LIVE_CHECK_FAILED = "LAST_LIVE_CHECK_FAILED"


@router.get("/live", status_code=status.HTTP_200_OK)
async def live_probe() -> Dict[str, str]:
    """Fast process liveness check; makes zero external calls."""
    return {"status": "ALIVE", "version": "v7.0.0"}


def _is_live_agent_runtime_configured() -> bool:
    """Return true only when all live flags and required Vertex config are present."""
    return bool(
        settings.EXECUTION_MODE == "LIVE_GOOGLE" and
        settings.LIVE_AGENT_ENABLED and
        settings.PAID_CALLS_ENABLED and
        not settings.SPEND_KILL_SWITCH_ACTIVE and
        settings.GOOGLE_CLOUD_PROJECT and
        settings.GOOGLE_CLOUD_LOCATION and
        settings.GEMINI_MODEL_ID
    )


def _is_agent_runtime_configured() -> bool:
    """Determine overall agent runtime configured status."""
    if settings.EXECUTION_MODE == "OFFLINE_FIXTURE":
        return True
    elif settings.EXECUTION_MODE == "LIVE_GOOGLE":
        return _is_live_agent_runtime_configured()
    return False


@router.get("/ready", status_code=status.HTTP_200_OK)
async def ready_probe(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Readiness probe checking datastores and dependencies without triggering paid AI calls."""
    checks = {
        "postgres": False,
        "redis": False,
        "clickhouse": False,
        "dataset_ready": False,
        "runtime_db_readonly": not settings.CLICKHOUSE_ALLOW_WRITE_ACCESS,
        "migration_head": False,
        "media_available": False,
        "worker_heartbeat": False,
        "agent_runtime_configured": False,
        "overall_ready": False
    }

    # 1. Check PostgreSQL & Migration Head
    migration_version = None
    expected_head = None
    try:
        from src.reframe.shared.database import get_expected_alembic_head
        expected_head = get_expected_alembic_head()
        await db.execute(text("SELECT 1"))
        checks["postgres"] = True
        try:
            res = await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
            row = res.fetchone()
            if row and row[0] == expected_head:
                migration_version = row[0]
                checks["migration_head"] = True
            else:
                migration_version = row[0] if row else None
                checks["migration_head"] = False
        except Exception:
            checks["migration_head"] = False
    except Exception as e:
        logger.warning("Postgres readiness check failed", error=str(e))

    # 2. Check Redis (Distinguish real Redis from in-memory fallback)
    try:
        if settings.ENVIRONMENT == "production":
            checks["redis"] = bool(redis_client.is_real_redis)
        else:
            await redis_client.set("health_check_probe", "ok", ex=10)
            probe = await redis_client.get("health_check_probe")
            checks["redis"] = bool(probe == "ok")
    except Exception as e:
        logger.warning("Redis readiness check failed", error=str(e))
        checks["redis"] = False

    # 3. Check ClickHouse (HTTP ping / SELECT 1)
    try:
        ch_url = f"http://{settings.CLICKHOUSE_HOST}:{settings.CLICKHOUSE_PORT}/ping"
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.get(ch_url)
            if resp.status_code == 200 and resp.text.strip() == "Ok.":
                checks["clickhouse"] = True
            else:
                checks["clickhouse"] = False
    except Exception as e:
        logger.warning("ClickHouse readiness check failed", error=str(e))
        checks["clickhouse"] = False

    # 4. Check V3 Dataset Readiness
    dataset_counts = {"scenes": 0, "events": 0, "facts": 0, "frames": 0}
    try:
        scenes = v3_adapter.get_scenes()
        events = v3_adapter.get_events()
        facts = v3_adapter.get_facts()
        frames = v3_adapter.get_evidence_frames()
        reveals = v3_adapter.get_reveals()
        dataset_counts = {
            "scenes": len(scenes),
            "events": len(events),
            "facts": len(facts),
            "frames": len(frames)
        }
        checks["dataset_ready"] = len(scenes) >= 43 and len(reveals) >= 2
    except Exception as e:
        logger.warning("Dataset readiness check failed", error=str(e))
        checks["dataset_ready"] = False

    # 5. Check Media Availability (Strictly require proxy media on disk)
    media_path = Path("data/external/raw/the_bat_whispers/the_bat_whispers_1930_proxy.mp4")
    checks["media_available"] = media_path.exists()

    # 6. Check Worker Heartbeat
    try:
        worker_hb = await redis_client.get("worker:heartbeat")
        checks["worker_heartbeat"] = bool(worker_hb)
    except Exception:
        checks["worker_heartbeat"] = False

    # 7. Check Agent Runtime Configuration
    checks["agent_runtime_configured"] = _is_agent_runtime_configured()

    checks["overall_ready"] = (
        checks["postgres"] and
        checks["redis"] and
        checks["clickhouse"] and
        checks["dataset_ready"] and
        checks["runtime_db_readonly"] and
        checks["migration_head"] and
        checks["media_available"] and
        checks["worker_heartbeat"] and
        checks["agent_runtime_configured"]
    )

    return {
        "status": "ready" if checks["overall_ready"] else "degraded",
        "data": checks,
        "active_dataset_version": "the_bat_whispers_v3_gemini36",
        "mcp_backend": "ClickHouse/mcp-clickhouse",
        "dataset_counts": dataset_counts,
        "migration_version": migration_version,
        "meta": {"environment": settings.ENVIRONMENT}
    }


@router.get("/health", status_code=status.HTTP_200_OK)
async def health_probe(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Standard /health endpoint delegating directly to /ready."""
    return await ready_probe(db=db)


@router.get("/admin/health", status_code=status.HTTP_200_OK)
async def admin_health(
    viewer: ViewerContext = Depends(get_viewer_context),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """Admin-only detailed diagnostics without exposing raw credentials or secrets."""
    if not viewer.is_admin:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Admin role required to view detailed system diagnostics"
        )

    gemini_status = GeminiHealthStatus.DISABLED
    if settings.PAID_CALLS_ENABLED and not settings.SPEND_KILL_SWITCH_ACTIVE:
        if _is_live_agent_runtime_configured():
            gemini_status = GeminiHealthStatus.CONFIGURED_NOT_VERIFIED
        else:
            gemini_status = GeminiHealthStatus.NOT_TESTED

    return {
        "data": {
            "environment": settings.ENVIRONMENT,
            "database_url_scheme": settings.DATABASE_URL.split("://")[0],
            "redis_url_scheme": settings.REDIS_URL.split("://")[0],
            "clickhouse_host": settings.CLICKHOUSE_HOST,
            "clickhouse_port": settings.CLICKHOUSE_PORT,
            "clickhouse_readonly": not settings.CLICKHOUSE_ALLOW_WRITE_ACCESS,
            "canonical_asset_sha256": settings.CANONICAL_ASSET_SHA256,
            "gemini_model_id": settings.GEMINI_MODEL_ID,
            "gemini_status": gemini_status.value,
            "spend_kill_switch": settings.SPEND_KILL_SWITCH_ACTIVE,
            "paid_calls_enabled": settings.PAID_CALLS_ENABLED,
            "max_budget_micros": settings.MAX_BUDGET_MICROS_PER_RUN,
            "daily_budget_micros": settings.DAILY_BUDGET_MICROS,
            "hard_budget_public_calls": settings.PUBLIC_REFRAME_MODEL_CALLS
        },
        "meta": {"request_viewer": viewer.to_dict()}
    }
