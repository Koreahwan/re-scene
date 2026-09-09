"""
Reframe V7 Durable Worker Process
Enforces fine-grained step persistence, lease heartbeats, crash recovery,
5-channel MCP retrieval execution, and canonical proof persistence.
Zero Paid Model Calls.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, or_, func
import structlog

from src.reframe.shared.config import settings
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.shared.redis_client import redis_client
from src.reframe.jobs.models import AnalysisRun, AnalysisRunStep
from src.reframe.jobs.service import job_service
from src.reframe.cost.service import cost_service
from src.reframe.audit.service import audit_service
from src.reframe.proof.store import canonical_proof_store
from src.reframe.domain.enums import ExecutionMode
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.mcp.program import narrative_mcp_program
from src.reframe.agents.runtime import agent_runtime

logger = structlog.get_logger(__name__)


class DurableWorker:
    def __init__(self, worker_id: Optional[str] = None):
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._running = False

    async def update_redis_heartbeat(self):
        """Publishes worker heartbeat to Redis with lease expiration."""
        try:
            await redis_client.set(
                "worker:heartbeat",
                self.worker_id,
                ex=max(settings.WORKER_LEASE_SECONDS * 2, 60)
            )
        except Exception as e:
            logger.debug("worker_heartbeat_redis_failed", error=str(e))

    async def claim_next_job(self, db: AsyncSession) -> Optional[AnalysisRun]:
        now = datetime.now(timezone.utc)
        lease_cutoff = now - timedelta(seconds=settings.WORKER_LEASE_SECONDS)

        stmt = (
            select(AnalysisRun)
            .where(
                or_(
                    AnalysisRun.status == "QUEUED",
                    and_(
                        AnalysisRun.status == "RUNNING",
                        AnalysisRun.heartbeat_at < lease_cutoff
                    )
                )
            )
            .order_by(AnalysisRun.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        res = await db.execute(stmt)
        run = res.scalar_one_or_none()

        if run:
            run.status = "RUNNING"
            run.claimed_at = now
            run.heartbeat_at = now
            await db.flush()
            logger.info("Claimed analysis run", run_id=str(run.id), worker_id=self.worker_id)
            return run
        return None

    async def update_heartbeat(self, db: AsyncSession, run_id: uuid.UUID):
        now = datetime.now(timezone.utc)
        stmt = (
            update(AnalysisRun)
            .where(AnalysisRun.id == run_id)
            .values(heartbeat_at=now)
        )
        await db.execute(stmt)
        await db.flush()
        await self.update_redis_heartbeat()

    async def execute_run(self, db: AsyncSession, run: AnalysisRun):
        run_id = run.id
        logger.info("Executing durable analysis run", run_id=str(run_id), type=run.run_type)

        try:
            # Query already completed steps for crash recovery
            steps_stmt = select(AnalysisRunStep).where(AnalysisRunStep.run_id == run_id)
            steps_res = await db.execute(steps_stmt)
            existing_steps = {s.step_type: s for s in steps_res.scalars().all()}

            # Execute reasoning workflow
            if run.run_type == "AUDIENCE_SIMULATION":
                await self.update_heartbeat(db, run_id)
                from src.reframe.simulation.service import audience_lab_service
                from src.reframe.simulation.schemas import SimulationRunConfig, SimulationMode, ScenarioVariant

                config_dict = run.config_json or {}
                mode_str = config_dict.get("mode", "CI")
                try:
                    sim_mode = SimulationMode(mode_str)
                except ValueError:
                    sim_mode = SimulationMode.CI
                personas_count = config_dict.get("unique_source_personas", 10000)
                replications = config_dict.get("replications", 1)
                seed = config_dict.get("seed", 42)
                seed_content = config_dict.get("seed_content", False)

                raw_variants = config_dict.get("variants")
                if raw_variants:
                    parsed_variants = [ScenarioVariant(v) for v in raw_variants]
                else:
                    parsed_variants = [
                        ScenarioVariant.QUICK_VALUE,
                        ScenarioVariant.CURRENT_BASELINE,
                        ScenarioVariant.EARLY_AUTH,
                        ScenarioVariant.DEEP_ANALYSIS,
                        ScenarioVariant.COMMUNITY_FIRST,
                    ]

                async def _checkpoint_step(step_type: str, input_hash: str, output_json: Any, percent: int):
                    await self.update_heartbeat(db, run_id)
                    await job_service.emit_run_event(db, run_id, "step", {"step": step_type, "percent": percent})
                    existing = existing_steps.get(step_type)
                    if existing:
                        existing.status = "COMPLETED"
                        existing.output_json = output_json
                        existing.completed_at = datetime.now(timezone.utc)
                    else:
                        new_step = AnalysisRunStep(
                            id=uuid.uuid4(),
                            run_id=run_id,
                            step_type=step_type,
                            input_hash=input_hash,
                            status="COMPLETED",
                            output_json=output_json,
                            completed_at=datetime.now(timezone.utc),
                        )
                        db.add(new_step)
                        existing_steps[step_type] = new_step
                    await db.flush()

                # Step 1: LOADING_PERSONAS
                personas = audience_lab_service.load_personas(count=personas_count)
                await _checkpoint_step("LOADING_PERSONAS", "hash_load_personas", {"personas_loaded": len(personas)}, 10)

                # Step 2: ASSIGNING_FAN_TRAITS
                await _checkpoint_step("ASSIGNING_FAN_TRAITS", "hash_traits", {"traits_assigned": len(personas)}, 20)

                # Step 3: SIMULATING_SESSIONS
                sim_config = SimulationRunConfig(
                    mode=sim_mode,
                    unique_source_personas=personas_count,
                    variants=parsed_variants,
                    replications=replications,
                    seed=seed,
                )
                sim_result = await audience_lab_service.execute_simulation_run(sim_config, personas=personas)
                await _checkpoint_step("SIMULATING_SESSIONS", "hash_sim_sessions", {"sessions_simulated": sim_result.synthetic_sessions}, 40)

                # Step 4: AGGREGATING_METRICS
                await _checkpoint_step("AGGREGATING_METRICS", "hash_metrics", {"gp_rate": sim_result.aggregate_funnel.golden_path_completion_rate}, 55)

                # Step 5: CALCULATING_INTERVALS
                await _checkpoint_step("CALCULATING_INTERVALS", "hash_intervals", {"intervals_count": len(sim_result.aggregate_funnel.simulation_intervals)}, 65)

                # Step 6: RANKING_BOTTLENECKS
                await _checkpoint_step("RANKING_BOTTLENECKS", "hash_bottlenecks", {"bottlenecks_ranked": len(sim_result.bottlenecks.bottlenecks)}, 75)

                # Step 7: RUNNING_SENSITIVITY
                await _checkpoint_step("RUNNING_SENSITIVITY", "hash_sensitivity", {"factors_tested": len(sim_result.sensitivity.results)}, 85)

                # Step 8: EXPORTING_LOAD_PROFILE
                await _checkpoint_step("EXPORTING_LOAD_PROFILE", "hash_load_profile", {"path": sim_result.load_profile_location}, 90)

                # Step 9: OPTIONAL_CONTENT_SEED
                if seed_content:
                    seed_sum = await audience_lab_service.seed_synthetic_demo_content(
                        db=db,
                        simulation_run_id=run_id,
                        enable_magazine=True,
                    )
                    await _checkpoint_step("OPTIONAL_CONTENT_SEED", "hash_seed_content", seed_sum, 95)

                run.result_json = sim_result.model_dump()
                run.status = "COMPLETED"
                run.completed_at = datetime.now(timezone.utc)
                await job_service.emit_run_event(db, run_id, "completed", {"status": "COMPLETED", "result_summary": "Audience simulation completed."})
                await db.commit()
                return


            elif run.run_type == "THEORY_VALIDATION":
                await self.update_heartbeat(db, run_id)
                await job_service.emit_run_event(db, run_id, "step", {"step": "ANALYZING_THEORY", "percent": 50})
                from src.reframe.narrative.theory_engine import theory_engine
                theory_res = theory_engine.validate_theory(run.config_json or {})
                run.result_json = theory_res.model_dump()
                run.status = "COMPLETED"
                run.completed_at = datetime.now(timezone.utc)
                persisted_proof_ids = []


            else:
                from src.reframe.evidence.catalog_registry import catalog_registry

                try:
                    catalog_registry.require_work(run.work_id)
                    catalog_registry.require_edition(run.work_id, run.edition_id)
                except Exception as e:
                    logger.error("invalid_scope_for_analysis_run", run_id=str(run_id), error=str(e))
                    run.status = "FAILED"
                    run.failure_code = "INVALID_SCOPE"
                    run.failure_detail_redacted = str(e)
                    run.completed_at = datetime.now(timezone.utc)
                    await cost_service.settle_reservation(db, run_id)
                    await job_service.emit_run_event(db, run_id, "error", {"status": "FAILED", "code": "INVALID_SCOPE"})
                    await db.commit()
                    return

                approved_dataset_versions = {"v3", "the_bat_whispers_v3_gemini36"}
                if run.dataset_version not in approved_dataset_versions:
                    logger.error("invalid_dataset_version_for_analysis_run", run_id=str(run_id), dataset_version=run.dataset_version)
                    run.status = "FAILED"
                    run.failure_code = "INVALID_SCOPE"
                    run.failure_detail_redacted = f"Dataset version '{run.dataset_version}' is not approved."
                    run.completed_at = datetime.now(timezone.utc)
                    await cost_service.settle_reservation(db, run_id)
                    await job_service.emit_run_event(db, run_id, "error", {"status": "FAILED", "code": "INVALID_SCOPE"})
                    await db.commit()
                    return

                reveal_id = run.reveal_id
                if not reveal_id:
                    logger.error("missing_reveal_id_for_analysis_run", run_id=str(run_id))
                    run.status = "FAILED"
                    run.failure_code = "UNKNOWN_REVEAL"
                    run.failure_detail_redacted = "Analysis run is missing reveal_id."
                    run.completed_at = datetime.now(timezone.utc)
                    await cost_service.settle_reservation(db, run_id)
                    await job_service.emit_run_event(db, run_id, "error", {"status": "FAILED", "code": "UNKNOWN_REVEAL"})
                    await db.commit()
                    return

                reveal_obj = v3_adapter.get_reveal(reveal_id)
                if not reveal_obj:
                    logger.error("unknown_reveal_id_not_found_in_registry", run_id=str(run_id), reveal_id=reveal_id)
                    run.status = "FAILED"
                    run.failure_code = "UNKNOWN_REVEAL"
                    run.failure_detail_redacted = f"Reveal '{reveal_id}' not found in server registry."
                    run.completed_at = datetime.now(timezone.utc)
                    await cost_service.settle_reservation(db, run_id)
                    await job_service.emit_run_event(db, run_id, "error", {"status": "FAILED", "code": "UNKNOWN_REVEAL"})
                    await db.commit()
                    return

                cutoff_ms = reveal_obj.timestamp_ms

                # Step 1: RETRIEVAL via NarrativeMcpRetrievalProgram with Durable Checkpoints
                seeds = None
                retrieval_step = existing_steps.get("RETRIEVING")

                if retrieval_step and retrieval_step.status == "COMPLETED":
                    # Load checkpoint from durable output_json
                    out_json = retrieval_step.output_json or {}
                    seeds = out_json.get("seeds")
                    if seeds is not None:
                        logger.info("recovered_retrieval_seeds_from_checkpoint", run_id=str(run_id), count=len(seeds))
                    else:
                        logger.warning("retrieval_step_missing_seeds_checkpoint_reexecuting", run_id=str(run_id))

                        mcp_results, seeds = await narrative_mcp_program.execute_program(
                            work_id=run.work_id,
                            edition_id=run.edition_id,
                            reveal_id=reveal_id,
                            cutoff_ms=cutoff_ms,
                            analysis_run_id=str(run_id)
                        )
                        retrieval_step.output_json = {"seeds": [s.model_dump() if hasattr(s, "model_dump") else s for s in seeds]}
                        await db.flush()
                else:
                    await self.update_heartbeat(db, run_id)
                    await job_service.emit_run_event(db, run_id, "step", {"step": "RETRIEVING", "percent": 20})

                    mcp_results, seeds = await narrative_mcp_program.execute_program(
                        work_id=run.work_id,
                        edition_id=run.edition_id,
                        reveal_id=reveal_id,
                        cutoff_ms=cutoff_ms,
                        analysis_run_id=str(run_id)
                    )

                    step_rec = AnalysisRunStep(
                        id=uuid.uuid4(),
                        run_id=run_id,
                        step_type="RETRIEVING",
                        input_hash=run.input_hash,
                        status="COMPLETED",
                        attempt=1,
                        worker_id=self.worker_id,
                        output_json={"seeds": [s.model_dump() if hasattr(s, "model_dump") else s for s in seeds]},
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc)
                    )
                    db.add(step_rec)
                    await db.flush()

                # Step 2: ADK Multi-Role Reasoning with Durable Checkpoint
                await self.update_heartbeat(db, run_id)
                await job_service.emit_run_event(db, run_id, "step", {"step": "ADK_REASONING", "percent": 40})

                adk_step = existing_steps.get("ADK_REASONING") or existing_steps.get("GENERATING_HYPOTHESIS")
                adk_result = None

                if adk_step and adk_step.status == "COMPLETED" and adk_step.output_json and "adk_result" in adk_step.output_json:
                    adk_result = adk_step.output_json["adk_result"]
                    logger.info("recovered_adk_result_from_checkpoint", run_id=str(run_id))
                else:
                    # Check for prior live model claims without completed checkpoint (Task 5)
                    from src.reframe.cost.models import ModelCallClaim
                    claim_stmt = select(func.count(ModelCallClaim.id)).where(
                        ModelCallClaim.analysis_run_id == run_id
                    )
                    claim_res = await db.execute(claim_stmt)
                    if (claim_res.scalar() or 0) > 0:
                        logger.error("unreconciled_live_model_claim_detected_failing_closed", run_id=str(run_id))
                        run.status = "ABSTAINED"
                        run.failure_code = "MANUAL_RECONCILIATION_REQUIRED"
                        run.failure_detail_redacted = "Prior live ModelCallClaim exists without completed ADK_REASONING checkpoint. Manual reconciliation required."
                        run.completed_at = datetime.now(timezone.utc)
                        await cost_service.settle_reservation(db, run_id)
                        await job_service.emit_run_event(db, run_id, "error", {"status": "ABSTAINED", "code": "MANUAL_RECONCILIATION_REQUIRED"})
                        await db.commit()
                        return

                    # Record or update ADK_REASONING step in RUNNING state
                    if not adk_step:
                        adk_step = AnalysisRunStep(
                            id=uuid.uuid4(),
                            run_id=run_id,
                            step_type="ADK_REASONING",
                            input_hash=run.input_hash,
                            status="RUNNING",
                            attempt=1,
                            worker_id=self.worker_id,
                            started_at=datetime.now(timezone.utc)
                        )
                        db.add(adk_step)
                    else:
                        adk_step.status = "RUNNING"
                        adk_step.worker_id = self.worker_id
                    await db.flush()

                    adk_result = await agent_runtime.execute_adk_analysis(
                        work_id=run.work_id,
                        edition_id=run.edition_id,
                        reveal_id=reveal_id,
                        cutoff_ms=cutoff_ms,
                        analysis_run_id=str(run_id),
                        provided_seeds=seeds
                    )

                    # Persist completed ADK checkpoint with normalized result
                    exec_mode_val = adk_result.get("execution_mode")
                    if hasattr(exec_mode_val, "value"):
                        exec_mode_val = exec_mode_val.value
                    elif exec_mode_val is not None:
                        exec_mode_val = str(exec_mode_val)
                    else:
                        exec_mode_val = "OFFLINE_FIXTURE"

                    adk_step.status = "COMPLETED"
                    adk_step.completed_at = datetime.now(timezone.utc)
                    adk_step.output_json = {
                        "adk_result": {
                            "status": adk_result.get("status", "COMPLETED"),
                            "execution_mode": exec_mode_val,
                            "validated_proofs": adk_result.get("validated_proofs", []),
                            "hypotheses": [h.model_dump() if hasattr(h, "model_dump") else h for h in adk_result.get("hypotheses", [])],
                            "critiques": [c.model_dump() if hasattr(c, "model_dump") else c for c in adk_result.get("critiques", [])],
                            "judgments": [j.model_dump() if hasattr(j, "model_dump") else j for j in adk_result.get("judgments", [])],
                            "telemetries": [t.model_dump() if hasattr(t, "model_dump") else t for t in adk_result.get("telemetries", [])],
                            "proofs": adk_result.get("proofs", []),
                            "model_call_ids": adk_result.get("model_call_ids", [])
                        }
                    }
                    await db.flush()

                # GuardedGeminiInvoker is the sole billing/UsageLedger writer.
                # Worker does not create duplicate UsageLedger rows for live calls (Task 3).

                # Step 3: Persist Verified Proofs into Canonical Proof Store
                persisted_proof_ids = []
                for proof_dict in adk_result.get("proofs", []):
                    saved_record = await canonical_proof_store.save_canonical_proof(
                        db=db,
                        proof_data=proof_dict,
                        work_id=run.work_id,
                        edition_id=run.edition_id,
                        reveal_id=reveal_id
                    )
                    persisted_proof_ids.append(saved_record.proof_id)

                # Record PERSISTING step idempotently
                if "PERSISTING" not in existing_steps or existing_steps["PERSISTING"].status != "COMPLETED":
                    db.add(AnalysisRunStep(
                        id=uuid.uuid4(),
                        run_id=run_id,
                        step_type="PERSISTING",
                        input_hash=run.input_hash,
                        status="COMPLETED",
                        attempt=1,
                        worker_id=self.worker_id,
                        started_at=datetime.now(timezone.utc),
                        completed_at=datetime.now(timezone.utc)
                    ))
                    await db.flush()

                run.status = "COMPLETED" if (adk_result.get("status") == "COMPLETED" and persisted_proof_ids) else "ABSTAINED"
                run.proof_ids = persisted_proof_ids
                run.completed_at = datetime.now(timezone.utc)

            await cost_service.settle_reservation(db, run_id)

            await job_service.emit_run_event(db, run_id, "completed", {
                "status": run.status,
                "proof_ids": persisted_proof_ids
            })

            # Transactional Outbox Event
            await audit_service.emit_outbox_event(
                db=db,
                aggregate_type="analysis_run",
                aggregate_id=str(run_id),
                event_type="PROOF_COMPLETED",
                payload={"run_id": str(run_id), "status": run.status, "proof_ids": persisted_proof_ids}
            )
            await db.commit()
            logger.info("Successfully completed durable analysis run", run_id=str(run_id), proof_ids=persisted_proof_ids)

        except Exception as e:
            import traceback
            traceback.print_exc()
            logger.error("Analysis run failed", run_id=str(run_id), error=str(e))
            run.status = "FAILED"
            run.failure_code = "EXECUTION_ERROR"
            run.failure_detail_redacted = str(e)[:256]
            run.completed_at = datetime.now(timezone.utc)
            await cost_service.settle_reservation(db, run_id)
            await job_service.emit_run_event(db, run_id, "error", {"status": "FAILED", "code": "EXECUTION_ERROR"})
            await db.commit()

    async def run_once(self) -> bool:
        await self.update_redis_heartbeat()
        async with AsyncSessionLocal() as db:
            try:
                run = await self.claim_next_job(db)
                if run:
                    await self.execute_run(db, run)
                    return True
                await audit_service.process_pending_outbox_events(db)
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error("Worker error during loop cycle", error=str(e))
        return False

    async def run_loop(self):
        self._running = True
        logger.info("Durable Worker loop started", worker_id=self.worker_id)
        while self._running:
            had_work = await self.run_once()
            if not had_work:
                await asyncio.sleep(settings.WORKER_POLL_INTERVAL_SECONDS)

    def stop(self):
        self._running = False
        logger.info("Stopping durable worker", worker_id=self.worker_id)


worker = DurableWorker()
