"""
Reframe V7 Admin Audience Lab Router
Provides admin-only endpoints for managing synthetic audience simulations,
bottlenecks, cohort analysis, sensitivity reports, load exports, and synthetic content seeding/purging.
Zero External Generative Model Calls.
"""
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path

from fastapi import APIRouter, Depends, Request, Response, Header, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import get_db
from src.reframe.shared.exceptions import ReframeException, ReframeErrorCodes
from src.reframe.identity.auth import get_viewer_context, ViewerContext, enforce_csrf
from src.reframe.jobs.models import AnalysisRun, IdempotencyRecord
from src.reframe.jobs.service import job_service
from src.reframe.simulation.schemas import (
    SimulationMode,
    ScenarioVariant,
    SimulationRunConfig,
    SimulationRunResult,
    DirectionalDemandInput,
)
from src.reframe.simulation.service import audience_lab_service
from src.reframe.simulation.bottlenecks import rank_bottlenecks
from src.reframe.simulation.sensitivity import run_sensitivity_analysis
from src.reframe.simulation.demand_scenarios import evaluate_directional_demand

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/admin/audience-lab", tags=["Admin Audience Lab"])


def require_admin_or_moderator(viewer: ViewerContext = Depends(get_viewer_context)) -> ViewerContext:
    if not settings.ENABLE_AUDIENCE_LAB:
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Audience Lab feature is currently disabled.",
        )
    if not viewer.is_authenticated:
        raise ReframeException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code=ReframeErrorCodes.AUTH_REQUIRED,
            message="Authentication required for Audience Lab.",
        )
    if not (viewer.is_admin or viewer.is_moderator):
        raise ReframeException(
            status_code=status.HTTP_403_FORBIDDEN,
            code=ReframeErrorCodes.FORBIDDEN,
            message="Admin or Moderator privileges required to access Audience Lab.",
        )
    return viewer



class CreateAudienceRunRequest(BaseModel):
    mode: SimulationMode = SimulationMode.CI
    unique_source_personas: int = Field(default=10000, ge=100, le=1000000)
    variants: List[ScenarioVariant] = Field(default_factory=lambda: [
        ScenarioVariant.QUICK_VALUE,
        ScenarioVariant.CURRENT_BASELINE,
        ScenarioVariant.EARLY_AUTH,
        ScenarioVariant.DEEP_ANALYSIS,
        ScenarioVariant.COMMUNITY_FIRST,
    ])
    replications: int = Field(default=1, ge=1, le=20)
    seed: int = 42
    seed_content: bool = False


class SeedContentRequest(BaseModel):
    posts_count: int = Field(default=20, ge=1, le=150)
    comments_count: int = Field(default=40, ge=1, le=800)
    counterclaims_count: int = Field(default=20, ge=1, le=150)
    reactions_count: int = Field(default=60, ge=1, le=2000)
    enable_magazine: bool = True


class PurgeContentRequest(BaseModel):
    confirm_delete_synthetic_only: bool = False


@router.get("/personas/summary")
async def get_personas_summary(
    viewer: ViewerContext = Depends(require_admin_or_moderator),
):
    """Returns metadata and demographic summary of the Nemotron-Personas-USA sample."""
    sample = audience_lab_service.load_personas(count=1000)
    age_dist = {}
    region_dist = {}
    occ_dist = {}
    for p in sample:
        age_dist[p.age_band] = age_dist.get(p.age_band, 0) + 1
        region_dist[p.census_region] = region_dist.get(p.census_region, 0) + 1
        occ_dist[p.occupation_group] = occ_dist.get(p.occupation_group, 0) + 1

    return {
        "dataset_id": settings.NEMOTRON_DATASET_ID,
        "dataset_revision": settings.NEMOTRON_DATASET_REVISION,
        "license": "CC BY 4.0",
        "sample_size": len(sample),
        "available_lenses": ["GENERAL", "PROFESSIONAL", "ARTS", "SPORTS", "TRAVEL", "CULINARY"],
        "age_distribution": age_dist,
        "region_distribution": region_dist,
        "occupation_distribution": occ_dist,
        "fairness_firewall": "ACTIVE (Zero demographic behavioral assumptions)",
        "disclaimer": "Profiles are synthetic, pseudonymized, and non-ground-truth."
    }


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_audience_simulation_run(
    request: Request,
    body: CreateAudienceRunRequest,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db),
):
    """Enqueues a durable Audience Simulation analysis run."""
    if not idempotency_key:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Idempotency-Key header is required for creating simulation runs.",
        )

    # Check existing run by idempotency key
    idemp_stmt = select(AnalysisRun).where(AnalysisRun.idempotency_key == idempotency_key)
    idemp_res = await db.execute(idemp_stmt)
    existing_run = idemp_res.scalar_one_or_none()
    if existing_run:
        return {
            "run_id": str(existing_run.id),
            "status": existing_run.status,
            "message": "Analysis run already exists.",
        }


    config_dict = body.model_dump()
    run = AnalysisRun(
        id=uuid.uuid4(),
        run_type="AUDIENCE_SIMULATION",
        owner_user_id=viewer.user_id,
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        status="QUEUED",
        idempotency_key=idempotency_key,
        input_hash=f"aud_in_{body.seed}_{body.mode.value}",
        config_hash=f"aud_cfg_{body.unique_source_personas}_{body.replications}",
        dataset_version="v7-simulation",
        model_id="zero-model-deterministic-engine",
        prompt_hash="deterministic_behavior_policy_v1",
        proof_schema_version="1.0.0",
        cost_reserved_micros=0,
        config_json=config_dict,
        result_json={},
    )
    db.add(run)
    await db.commit()

    return {
        "run_id": str(run.id),
        "status": "QUEUED",
        "message": "Simulation run queued for background worker execution.",
    }


@router.get("/runs/{run_id}")
async def get_audience_simulation_run(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    """Fetches status and results of an audience simulation run."""
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run or run.run_type != "AUDIENCE_SIMULATION":
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Audience simulation run not found.",
        )

    return {
        "run_id": str(run.id),
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "config": run.config_json,
        "result": run.result_json,
    }


@router.get("/runs/{run_id}/funnel")
async def get_run_funnel(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run:
        raise ReframeException(404, ReframeErrorCodes.NOT_FOUND, "Run not found.")
    res = run.result_json or {}
    return {
        "run_id": str(run.id),
        "aggregate_funnel": res.get("aggregate_funnel", {}),
        "scenario_funnels": res.get("scenario_funnels", {}),
    }


@router.get("/runs/{run_id}/bottlenecks")
async def get_run_bottlenecks(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run:
        raise ReframeException(404, ReframeErrorCodes.NOT_FOUND, "Run not found.")
    res = run.result_json or {}
    return res.get("bottlenecks", {"bottlenecks": []})


@router.get("/runs/{run_id}/cohorts")
async def get_run_cohorts(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run:
        raise ReframeException(404, ReframeErrorCodes.NOT_FOUND, "Run not found.")
    res = run.result_json or {}
    return {
        "balanced_eval_cohorts": res.get("balanced_eval_cohorts", []),
        "source_weighted_cohorts": res.get("source_weighted_cohorts", []),
    }


@router.get("/runs/{run_id}/sensitivity")
async def get_run_sensitivity(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run:
        raise ReframeException(404, ReframeErrorCodes.NOT_FOUND, "Run not found.")
    res = run.result_json or {}
    return res.get("sensitivity", {"results": [], "dominant_assumptions": []})


@router.get("/runs/{run_id}/load-profile")
async def get_run_load_profile(
    run_id: uuid.UUID,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run:
        raise ReframeException(404, ReframeErrorCodes.NOT_FOUND, "Run not found.")
    res = run.result_json or {}
    return {
        "run_id": str(run.id),
        "load_profile_location": res.get("load_profile_location", ""),
    }



@router.post("/runs/{run_id}/seed-content")
async def seed_content_for_run(
    run_id: uuid.UUID,
    body: SeedContentRequest,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db),
):
    if not idempotency_key:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Idempotency-Key header is required for seeding content.",
        )

    # 1. Compute request hash for conflict detection
    req_hash = hashlib.sha256(json.dumps(body.model_dump(), sort_keys=True).encode()).hexdigest()
    route_key = f"POST:/admin/audience-lab/runs/{run_id}/seed-content"

    # 2. Check existing IdempotencyRecord
    idemp_stmt = select(IdempotencyRecord).where(
        and_(
            IdempotencyRecord.route_key == route_key,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
    )
    idemp_res = await db.execute(idemp_stmt)
    existing_rec = idemp_res.scalars().first()

    if existing_rec:
        if existing_rec.request_hash == req_hash:
            return json.loads(existing_rec.response_body_ref)
        else:
            raise ReframeException(
                status_code=status.HTTP_409_CONFLICT,
                code=ReframeErrorCodes.CONFLICT,
                message="Idempotency key reused with different request payload.",
            )

    # 3. Verify that the simulation run exists and is COMPLETED
    stmt = select(AnalysisRun).where(AnalysisRun.id == run_id)
    res_run = await db.execute(stmt)
    run = res_run.scalar_one_or_none()
    if not run or run.run_type != "AUDIENCE_SIMULATION":
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="Audience simulation run not found.",
        )
    if run.status != "COMPLETED":
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message=f"Simulation run must be COMPLETED before seeding content. Current status: {run.status}",
        )

    summary = await audience_lab_service.seed_synthetic_demo_content(
        db=db,
        simulation_run_id=run_id,
        post_target_count=body.posts_count,
        comment_target_count=body.comments_count,
        counterclaim_target_count=body.counterclaims_count,
        reaction_target_count=body.reactions_count,
        enable_magazine=body.enable_magazine,
    )

    resp_data = {
        "status": "SUCCESS",
        "seeded_counts": summary,
        "message": "Synthetic demo content successfully seeded."
    }

    # 4. Persist IdempotencyRecord
    rec = IdempotencyRecord(
        id=uuid.uuid4(),
        principal_id=str(viewer.user_id),
        route_key=route_key,
        idempotency_key=idempotency_key,
        request_hash=req_hash,
        response_status=200,
        response_body_ref=json.dumps(resp_data),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(rec)
    await db.commit()

    return resp_data


@router.get("/runs/latest/summary")
async def get_latest_simulation_summary(
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    """Returns the latest completed simulation result or pre-generated DEMO_US run."""
    stmt = (
        select(AnalysisRun)
        .where(AnalysisRun.run_type == "AUDIENCE_SIMULATION", AnalysisRun.status == "COMPLETED")
        .order_by(AnalysisRun.created_at.desc())
        .limit(1)
    )
    res = await db.execute(stmt)
    latest_run = res.scalar_one_or_none()
    if latest_run and latest_run.result_json:
        return latest_run.result_json

    # Fallback to demo artifact on disk
    artifact_path = Path(settings.SIMULATION_DATA_DIR) / "runs" / "usa_audience_demo_v1_summary.json"
    if artifact_path.exists():
        with open(artifact_path, "r", encoding="utf-8") as f:
            return json.load(f)

    raise ReframeException(
        status_code=status.HTTP_404_NOT_FOUND,
        code=ReframeErrorCodes.NOT_FOUND,
        message="No completed simulation runs or summary artifacts found.",
    )


@router.post("/demand-scenario")
async def calculate_demand_scenario(
    body: DirectionalDemandInput,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    db: AsyncSession = Depends(get_db),
):
    """Calculates directional demand scenario projections strictly from a completed simulation run result."""
    from src.reframe.simulation.schemas import FunnelMetrics
    result_json = None
    run_id_str = None
    policy_ver = "reframe_us_audience_policy_v1"

    if body.simulation_run_id:
        stmt = select(AnalysisRun).where(AnalysisRun.id == body.simulation_run_id)
        res_run = await db.execute(stmt)
        run = res_run.scalar_one_or_none()
        if not run or run.run_type != "AUDIENCE_SIMULATION" or not run.result_json:
            raise ReframeException(
                status_code=status.HTTP_404_NOT_FOUND,
                code=ReframeErrorCodes.NOT_FOUND,
                message=f"Completed simulation run {body.simulation_run_id} not found.",
            )
        result_json = run.result_json
        run_id_str = str(run.id)
        policy_ver = result_json.get("policy_version", policy_ver)
    else:
        # Load latest completed run from DB or disk
        stmt = (
            select(AnalysisRun)
            .where(AnalysisRun.run_type == "AUDIENCE_SIMULATION", AnalysisRun.status == "COMPLETED")
            .order_by(AnalysisRun.created_at.desc())
            .limit(1)
        )
        latest_run = (await db.execute(stmt)).scalar_one_or_none()
        if latest_run and latest_run.result_json:
            result_json = latest_run.result_json
            run_id_str = str(latest_run.id)
            policy_ver = result_json.get("policy_version", policy_ver)
        else:
            artifact_path = Path(settings.SIMULATION_DATA_DIR) / "runs" / "usa_audience_demo_v1_summary.json"
            if artifact_path.exists():
                with open(artifact_path, "r", encoding="utf-8") as f:
                    result_json = json.load(f)
                    run_id_str = "artifact:usa_audience_demo_v1_summary.json"
                    policy_ver = result_json.get("policy_version", policy_ver)

    if not result_json or "aggregate_funnel" not in result_json:
        raise ReframeException(
            status_code=status.HTTP_404_NOT_FOUND,
            code=ReframeErrorCodes.NOT_FOUND,
            message="No valid simulation run results found to base demand scenario on.",
        )

    funnel_data = result_json["aggregate_funnel"]
    metrics = FunnelMetrics(**funnel_data)
    result = evaluate_directional_demand(
        demand_input=body,
        metrics=metrics,
        source_run_id=run_id_str,
        source_policy_version=policy_ver,
        source_scenario="CURRENT_BASELINE",
    )
    return result.model_dump()


@router.post("/seed-content", status_code=status.HTTP_410_GONE)
async def seed_synthetic_content():
    """Deprecated standalone seed endpoint."""
    raise ReframeException(
        status_code=status.HTTP_410_GONE,
        code=ReframeErrorCodes.INVALID_REQUEST,
        message="Standalone seed endpoint is deprecated. Use POST /admin/audience-lab/runs/{run_id}/seed-content with completed run_id.",
    )


@router.post("/purge-content")
async def purge_synthetic_content(
    body: PurgeContentRequest,
    viewer: ViewerContext = Depends(require_admin_or_moderator),
    _csrf: None = Depends(enforce_csrf),
    db: AsyncSession = Depends(get_db),
):
    """Safely purges synthetic demo content only, leaving human user content completely untouched."""
    if not body.confirm_delete_synthetic_only:
        raise ReframeException(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=ReframeErrorCodes.INVALID_REQUEST,
            message="Must set confirm_delete_synthetic_only=True to execute purge.",
        )

    summary = await audience_lab_service.purge_synthetic_demo_content(db=db)
    return {
        "status": "PURGED",
        "summary": summary,
        "message": "All synthetic demo content safely deleted."
    }

