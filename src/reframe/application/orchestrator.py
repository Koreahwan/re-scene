from __future__ import annotations
import os
import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
import structlog

from reframe.domain.models import (
    Reveal,
    Scene,
    Event,
    Fact,
    ReframeCandidate,
    VerifiedReframe,
    ReframedMomentCard,
    ReframeResult,
    RetrievalPlan,
    ExecutionTrace,
)
from reframe.domain.enums import RelationType, ReframeRunStatus, AbstainReason
from reframe.retrieval.guard import (
    derive_spoiler_cutoff,
    validate_client_request_parameters,
    assert_zero_future_leakage,
    filter_pre_cutoff_evidence,
    sanitize_candidate_for_cutoff,
    SpoilerGuardViolation,
)
from reframe.retrieval.fusion import reciprocal_rank_fusion
from reframe.mcp.gateway import NarrativeMemoryGateway, ACTIVE_DATASET_VERSION
from reframe.verification.verifier import EvidenceVerifier

logger = structlog.get_logger(__name__)


class ReframeOrchestrator:
    """
    Core Runtime Orchestrator for Reframe.
    Executes the non-negotiable Golden Path:
    User Request (movie_id + reveal_id)
    -> Server Derived Spoiler Cutoff
    -> Narrative Memory Retrieval via official mcp-clickhouse
    -> Candidate Fusion & Ranking (RRF)
    -> Gemini Evidence Verifier (Blind evaluation without answer key)
    -> Presentation Filter
    -> Top 3-5 Reframed Moments or ABSTAIN.
    """

    def __init__(
        self,
        gateway: NarrativeMemoryGateway,
        verifier: Optional[EvidenceVerifier] = None,
        reveals_registry: Optional[Dict[str, Reveal]] = None,
        dataset_version: Optional[str] = None,
    ):
        self.gateway = gateway
        self.verifier = verifier or EvidenceVerifier()
        self.reveals_registry = reveals_registry or {}
        self.dataset_version = dataset_version or ACTIVE_DATASET_VERSION

    def register_reveal(self, reveal: Reveal) -> None:
        self.reveals_registry[reveal.reveal_id] = reveal

    async def execute_reframe_analysis(
        self,
        movie_id: str,
        reveal_id: str,
        top_k: int = 5,
        client_request_params: Optional[Dict[str, Any]] = None,
        dataset_version: Optional[str] = None,
    ) -> Tuple[ReframeResult, Optional[ExecutionTrace]]:
        run_id = f"run_{uuid.uuid4().hex[:12]}"
        start_time = time.perf_counter()
        active_version = dataset_version or self.dataset_version

        logger.info("reframe_analysis_started", run_id=run_id, movie_id=movie_id, reveal_id=reveal_id, dataset_version=active_version)

        # 1. Parameter Validation (Guards against client-side cutoff tampering)
        if client_request_params:
            try:
                validate_client_request_parameters(client_request_params)
            except SpoilerGuardViolation as e:
                logger.error("client_cutoff_tampering_rejected", run_id=run_id, error=str(e))
                result = ReframeResult(
                    run_id=run_id,
                    movie_id=movie_id,
                    reveal_id=reveal_id,
                    spoiler_cutoff_ms=0,
                    status=ReframeRunStatus.ABSTAINED,
                    cards=[],
                    abstain_reason=AbstainReason.SPOILER_GUARD_BLOCKED,
                    dataset_version=active_version,
                )
                return result, None

        # 2. Lookup Reveal from Server Registry
        reveal = self.reveals_registry.get(reveal_id)
        if not reveal or reveal.movie_id != movie_id:
            logger.warning("reveal_not_found", run_id=run_id, reveal_id=reveal_id)
            result = ReframeResult(
                run_id=run_id,
                movie_id=movie_id,
                reveal_id=reveal_id,
                spoiler_cutoff_ms=0,
                status=ReframeRunStatus.ABSTAINED,
                cards=[],
                abstain_reason=AbstainReason.REVEAL_NOT_FOUND,
                dataset_version=active_version,
            )
            return result, None

        # 3. Server Derives Spoiler Cutoff (Client CANNOT override)
        try:
            spoiler_cutoff_ms = derive_spoiler_cutoff(reveal)
        except SpoilerGuardViolation:
            result = ReframeResult(
                run_id=run_id,
                movie_id=movie_id,
                reveal_id=reveal_id,
                spoiler_cutoff_ms=0,
                status=ReframeRunStatus.ABSTAINED,
                cards=[],
                abstain_reason=AbstainReason.SPOILER_GUARD_BLOCKED,
                dataset_version=active_version,
            )
            return result, None

        logger.info("spoiler_cutoff_derived", run_id=run_id, cutoff_ms=spoiler_cutoff_ms)

        # 4. Retrieval via Official mcp-clickhouse
        mcp_start = time.perf_counter()
        try:
            entity_candidates = await self.gateway.search_entity_candidates(
                movie_id=movie_id,
                reveal_id=reveal_id,
                cutoff_ms=spoiler_cutoff_ms,
                entities=reveal.affected_entities,
                limit=30,
                dataset_version=active_version,
            )
        except Exception as exc:
            logger.error("mcp_retrieval_failed", run_id=run_id, error=str(exc))
            result = ReframeResult(
                run_id=run_id,
                movie_id=movie_id,
                reveal_id=reveal_id,
                spoiler_cutoff_ms=spoiler_cutoff_ms,
                status=ReframeRunStatus.ABSTAINED,
                cards=[],
                abstain_reason=AbstainReason.MCP_UNAVAILABLE,
                dataset_version=active_version,
            )
            return result, None
        mcp_latency_ms = (time.perf_counter() - mcp_start) * 1000.0

        # 5. In-Memory Post-Retrieval Leakage Verification
        try:
            assert_zero_future_leakage(entity_candidates, cutoff_ms=spoiler_cutoff_ms)
        except SpoilerGuardViolation as leak_err:
            logger.critical("future_leakage_detected", run_id=run_id, error=str(leak_err))
            result = ReframeResult(
                run_id=run_id,
                movie_id=movie_id,
                reveal_id=reveal_id,
                spoiler_cutoff_ms=spoiler_cutoff_ms,
                status=ReframeRunStatus.ABSTAINED,
                cards=[],
                abstain_reason=AbstainReason.SPOILER_GUARD_BLOCKED,
                dataset_version=active_version,
            )
            return result, None

        if not entity_candidates:
            logger.info("no_candidates_found", run_id=run_id)
            result = ReframeResult(
                run_id=run_id,
                movie_id=movie_id,
                reveal_id=reveal_id,
                spoiler_cutoff_ms=spoiler_cutoff_ms,
                status=ReframeRunStatus.ABSTAINED,
                cards=[],
                abstain_reason=AbstainReason.NO_CANDIDATES,
                dataset_version=active_version,
            )
            return result, None

        # 6. Reciprocal Rank Fusion (RRF)
        fused_candidates = reciprocal_rank_fusion(
            ranked_lists={"entity": entity_candidates},
            k=60,
            max_candidates=20,
        )

        # 7. Fetch Supporting Evidence (Events & Facts strictly < cutoff)
        candidate_scene_ids = [c.scene_id for c in fused_candidates]
        events_by_scene, facts_by_scene = await self.gateway.get_supporting_evidence(
            movie_id=movie_id,
            cutoff_ms=spoiler_cutoff_ms,
            scene_ids=candidate_scene_ids,
            dataset_version=active_version,
        )

        # 8. Evidence Verification (Blind execution against Gemini 3.6 Flash)
        import asyncio

        gemini_start = time.perf_counter()

        async def _verify_single(cand: ReframeCandidate) -> Tuple[ReframeCandidate, VerifiedReframe]:
            raw_events = events_by_scene.get(cand.scene_id, [])
            raw_facts = facts_by_scene.get(cand.scene_id, [])
            valid_events, valid_facts = filter_pre_cutoff_evidence(raw_events, raw_facts, cutoff_ms=spoiler_cutoff_ms)
            sanitized_cand = sanitize_candidate_for_cutoff(cand, valid_events, valid_facts, cutoff_ms=spoiler_cutoff_ms)

            # Strict post-filtering assertion on candidate and evidence
            assert_zero_future_leakage([sanitized_cand], cutoff_ms=spoiler_cutoff_ms, events=valid_events, facts=valid_facts)

            verified_item = await self.verifier.verify_candidate(
                reveal=reveal,
                candidate=sanitized_cand,
                events=valid_events,
                facts=valid_facts,
            )
            return (sanitized_cand, verified_item)

        verification_tasks = [_verify_single(cand) for cand in fused_candidates]
        verified_pairs = list(await asyncio.gather(*verification_tasks))
        gemini_latency_ms = (time.perf_counter() - gemini_start) * 1000.0

        # 9. Assembly & Presentation Filtering (COINCIDENCE / IRRELEVANT pruned, ABSTAIN if 0 cards)
        final_result = self.verifier.assemble_results(
            run_id=run_id,
            reveal=reveal,
            spoiler_cutoff_ms=spoiler_cutoff_ms,
            verified_items=verified_pairs,
            top_k=top_k,
            dataset_version=active_version,
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        # 10. Generate Real Execution Trace from Gateway Telemetry
        last_telem = self.gateway.get_last_telemetry() if hasattr(self.gateway, "get_last_telemetry") else None
        actual_sql = last_telem.get("query") if (last_telem and last_telem.get("query")) else f"SELECT scene_id FROM reframe.scenes WHERE movie_id = '{movie_id}' AND dataset_version = '{active_version}' AND start_ms < {spoiler_cutoff_ms}"
        actual_tool = last_telem.get("tool_name", "run_query") if last_telem else "run_query"
        actual_transport = last_telem.get("transport", "fastmcp:in-process") if last_telem else "fastmcp:in-process"

        trace = ExecutionTrace(
            run_id=run_id,
            movie_id=movie_id,
            reveal_id=reveal_id,
            spoiler_cutoff_ms=spoiler_cutoff_ms,
            mcp_provider=f"ClickHouse/mcp-clickhouse ({actual_transport})",
            tool_called=actual_tool,
            template_id="entity_candidates_sql",
            sql_query=actual_sql.strip(),
            parameters={
                "movie_id": movie_id,
                "dataset_version": active_version,
                "cutoff_ms": spoiler_cutoff_ms,
                "spoiler_cutoff_ms": spoiler_cutoff_ms,
                "entities": reveal.affected_entities,
                "limit": 30,
            },
            candidates_count=len(entity_candidates),
            verified_count=len(final_result.cards),
            latency_ms=round(elapsed_ms, 2),
            model_id=self.verifier.model_name,
            dataset_version=active_version,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )

        logger.info(
            "reframe_analysis_completed",
            run_id=run_id,
            status=final_result.status,
            cards_count=len(final_result.cards),
            elapsed_ms=round(elapsed_ms, 2),
            mcp_latency_ms=round(mcp_latency_ms, 2),
            gemini_latency_ms=round(gemini_latency_ms, 2),
        )

        return final_result, trace
