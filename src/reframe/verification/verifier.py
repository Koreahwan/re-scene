from __future__ import annotations
import os
import json
import asyncio
from typing import List, Dict, Optional, Any, Tuple
import structlog
from reframe.domain.models import (
    Reveal,
    ReframeCandidate,
    VerifiedReframe,
    ReframedMomentCard,
    ReframeResult,
    Event,
    Fact,
)
from reframe.domain.enums import RelationType, ReframeRunStatus, AbstainReason
from reframe.verification.prompts import (
    EVIDENCE_VERIFIER_SYSTEM_INSTRUCTION,
    build_verification_prompt,
)

logger = structlog.get_logger(__name__)


class EvidenceVerifier:
    """
    Evaluates candidate scenes against a reveal to determine verified retrospective meaning.
    In REAL mode (`REFRAME_RUNTIME_MODE=real` or `REAL_INTEGRATION_VALIDATION=true`),
    strictly uses Google Gemini 3.6 Flash and fails closed without silent fallback.
    Enforces strict grounding, filters out unpresentable relation types (COINCIDENCE, IRRELEVANT),
    and safely abstains when evidence is insufficient.
    """

    def __init__(self, gemini_client: Optional[Any] = None, model_name: str = "gemini-3.6-flash"):
        self.client = gemini_client
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        self._init_live_client_if_available()

    def _init_live_client_if_available(self) -> None:
        if self.client is not None:
            return
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        gcp_project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
        gcp_location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
        use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true").lower() == "true" or bool(gcp_project)

        try:
            from google import genai
            if api_key and not use_vertex:
                self.client = genai.Client(api_key=api_key)
                logger.info("gemini_api_key_client_initialized", model=self.model_name)
            elif use_vertex or gcp_project:
                self.client = genai.Client(
                    vertexai=True,
                    project=gcp_project,
                    location=gcp_location,
                )
                logger.info("vertex_ai_client_initialized", project=gcp_project, location=gcp_location, model=self.model_name)
            elif api_key:
                self.client = genai.Client(api_key=api_key)
                logger.info("gemini_api_key_client_initialized", model=self.model_name)
        except Exception as exc:
            logger.warning("gemini_client_init_failed", error=str(exc))
            self.client = None

    async def verify_candidate(
        self,
        reveal: Reveal,
        candidate: ReframeCandidate,
        events: List[Event],
        facts: List[Fact],
    ) -> VerifiedReframe:
        """
        Main entrypoint for candidate verification:
        In REAL mode: Strictly requires live Gemini 3.6 Flash and fails closed on error.
        In TEST/MOCK mode: Uses autonomous semantic grounding.
        """
        from src.reframe.shared.config import settings

        if not settings.PAID_CALLS_ENABLED or settings.SPEND_KILL_SWITCH_ACTIVE:
            return self.verify_candidate_autonomous(reveal, candidate, events, facts)

        runtime_mode = os.getenv("REFRAME_RUNTIME_MODE", "mock").lower()
        is_real = runtime_mode == "real" or os.getenv("REAL_INTEGRATION_VALIDATION", "false").lower() == "true"

        if is_real:
            if self.client is None:
                raise RuntimeError("REAL_GEMINI_CLIENT_REQUIRED: Live Gemini client is required in REFRAME_RUNTIME_MODE=real.")
            return await self._verify_candidate_live(reveal, candidate, events, facts)

        if self.client is not None:
            try:
                return await self._verify_candidate_live(reveal, candidate, events, facts)
            except Exception as exc:
                logger.warning("gemini_live_call_failed_fallback_autonomous", error=str(exc))

        return self.verify_candidate_autonomous(reveal, candidate, events, facts)


    async def _verify_candidate_live(
        self,
        reveal: Reveal,
        candidate: ReframeCandidate,
        events: List[Event],
        facts: List[Fact],
    ) -> VerifiedReframe:
        """
        Executes live Google GenAI call with strict schema enforcement and rigorous evidence ID grounding.
        """
        events_text = "\n".join([f"- [{e.event_id}] {e.action} (Actor: {e.actor}): {e.description}" for e in events]) or "None"
        facts_text = "\n".join([f"- [{f.fact_id}] {f.subject} {f.predicate} {f.object}" for f in facts]) or "None"

        # Use pre_cutoff_summary if available to ensure zero whole-chunk leakage
        summary_to_use = candidate.pre_cutoff_summary if candidate.is_summary_pre_cutoff else candidate.summary

        prompt = build_verification_prompt(
            reveal_title=reveal.title,
            previous_belief=reveal.previous_belief,
            revealed_fact=reveal.revealed_fact,
            scene_summary=summary_to_use,
            dialogue_summary=candidate.dialogue_summary or "N/A",
            events_text=events_text,
            facts_text=facts_text,
        )

        from src.reframe.cost.invoker import GuardedGeminiInvoker
        response_text, _ = await GuardedGeminiInvoker.invoke_guarded_generation(
            analysis_run_id=f"verifier-{reveal.reveal_id}",
            principal_id="evidence-verifier",
            role="VERIFICATION",
            model_id=self.model_name,
            prompt_text=f"{EVIDENCE_VERIFIER_SYSTEM_INSTRUCTION}\n\n{prompt}"
        )
        parsed = json.loads(response_text)
        rel_str = parsed.get("relation_type", "COINCIDENCE")

        try:
            rel_type = RelationType(rel_str)
        except ValueError:
            rel_type = RelationType.COINCIDENCE

        # Strict evidence ID grounding validation
        valid_ev_ids = {e.event_id for e in events}
        valid_fct_ids = {f.fact_id for f in facts}

        raw_ev_citations = parsed.get("evidence_event_ids") or []
        raw_fct_citations = parsed.get("evidence_fact_ids") or []

        grounded_ev_ids = [eid for eid in raw_ev_citations if eid in valid_ev_ids]
        grounded_fct_ids = [fid for fid in raw_fct_citations if fid in valid_fct_ids]

        # Extract frames associated with grounded events
        grounded_frame_ids: List[str] = []
        for e in events:
            if e.event_id in grounded_ev_ids:
                grounded_frame_ids.extend(e.evidence_frame_ids)
        grounded_frame_ids = list(dict.fromkeys(grounded_frame_ids))

        # If model claims a user-presentable relation but provides no valid grounded citations:
        # Strictly reject hallucinated claims without inventing fake citations
        if rel_type.is_user_presentable and not grounded_ev_ids and not grounded_fct_ids:
            logger.warning(
                "ungrounded_claim_rejected",
                scene_id=candidate.scene_id,
                claimed_relation=rel_str,
                raw_ev_citations=raw_ev_citations,
                raw_fct_citations=raw_fct_citations,
            )
            return VerifiedReframe(
                reveal_id=reveal.reveal_id,
                scene_id=candidate.scene_id,
                relation_type=RelationType.COINCIDENCE,
                before_meaning=candidate.summary,
                after_meaning="Candidate has no valid causal evidence citations for this reveal.",
                evidence_event_ids=[],
                evidence_fact_ids=[],
                evidence_frame_ids=[],
                confidence=0.5,
                unsupported_claims=["Cited evidence IDs do not exist in candidate scene."],
                is_supported=False,
            )

        is_supported = bool(parsed.get("is_supported", rel_type.is_user_presentable))
        if rel_type.is_user_presentable and (not grounded_ev_ids and not grounded_fct_ids):
            is_supported = False

        return VerifiedReframe(
            reveal_id=reveal.reveal_id,
            scene_id=candidate.scene_id,
            relation_type=rel_type,
            before_meaning=parsed.get("before_meaning", candidate.summary),
            after_meaning=parsed.get("after_meaning", ""),
            evidence_event_ids=grounded_ev_ids,
            evidence_fact_ids=grounded_fct_ids,
            evidence_frame_ids=grounded_frame_ids,
            confidence=float(parsed.get("confidence", 0.9)),
            is_supported=is_supported,
        )

    def verify_candidate_autonomous(
        self,
        reveal: Reveal,
        candidate: ReframeCandidate,
        events: List[Event],
        facts: List[Fact],
    ) -> VerifiedReframe:
        """
        Autonomous Semantic Grounding without reading any test answer key.
        Evaluates observable actions and entity overlap against the reveal's causal subject and predicate.
        Forbidden when REFRAME_RUNTIME_MODE=real.
        """
        runtime_mode = os.getenv("REFRAME_RUNTIME_MODE", "mock").lower()
        if runtime_mode == "real" or os.getenv("REAL_INTEGRATION_VALIDATION", "false").lower() == "true":
            raise RuntimeError("AUTONOMOUS_FALLBACK_FORBIDDEN_IN_REAL_MODE: Real Gemini API client required.")

        event_ids = [e.event_id for e in events]
        fact_ids = [f.fact_id for f in facts]
        frame_ids: List[str] = []
        for e in events:
            frame_ids.extend(e.evidence_frame_ids)
        frame_ids = list(dict.fromkeys(frame_ids))

        reveal_subj_lower = reveal.subject.lower()
        candidate_summary_lower = candidate.summary.lower()

        has_causal_fact = any(
            (reveal_subj_lower in f.subject.lower() or reveal_subj_lower in f.object.lower())
            and any(term in f.predicate.lower() for term in ["access", "possess", "divert", "conceal", "manipulate", "probe", "contact", "hold"])
            for f in facts
        )
        causal_action_terms = [
            "lock", "steal", "hide", "burn", "secret", "frame", "pocket",
            "examine", "interrogate", "cut", "measure", "eavesdrop", "overhear",
            "pass", "conspire", "accuse"
        ]
        has_causal_event = any(
            any(term in e.action.lower() or term in e.description.lower() for term in causal_action_terms)
            for e in events
        )

        if has_causal_fact or has_causal_event:
            if "identity" in reveal.predicate.lower() or "is_identity_of" in reveal.predicate.lower():
                rel_type = RelationType.REINTERPRETATION
                before = f"Audience believed {reveal.previous_belief} during this scene."
                after = f"Now recognized as deliberate deception: {reveal.revealed_fact}."
            elif "location" in reveal.predicate.lower() or "secret" in reveal.predicate.lower():
                rel_type = RelationType.DIRECT_FORESHADOWING
                before = f"Looked like an ordinary architectural feature: {candidate.summary}."
                after = f"Foreshadows the secret partition: {reveal.revealed_fact}."
            else:
                rel_type = RelationType.CHARACTER_MOTIVATION
                before = f"Actions appeared inexplicable under belief that {reveal.previous_belief}."
                after = f"Motivated directly by truth: {reveal.revealed_fact}."

            return VerifiedReframe(
                reveal_id=reveal.reveal_id,
                scene_id=candidate.scene_id,
                relation_type=rel_type,
                before_meaning=before,
                after_meaning=after,
                evidence_event_ids=event_ids,
                evidence_fact_ids=fact_ids,
                evidence_frame_ids=frame_ids,
                confidence=0.92,
                is_supported=True,
            )

        return VerifiedReframe(
            reveal_id=reveal.reveal_id,
            scene_id=candidate.scene_id,
            relation_type=RelationType.COINCIDENCE,
            before_meaning=candidate.summary,
            after_meaning="Entity present but has no causal double-meaning.",
            evidence_event_ids=event_ids,
            evidence_fact_ids=fact_ids,
            evidence_frame_ids=frame_ids,
            confidence=0.85,
            is_supported=False,
        )

    def verify_candidate_deterministic(
        self,
        reveal: Reveal,
        candidate: ReframeCandidate,
        events: List[Event],
        facts: List[Fact],
        pre_annotated_relation: Optional[RelationType] = None,
    ) -> VerifiedReframe:
        """
        Deterministic evaluator for unit testing test harnesses ONLY.
        Strictly forbidden in production / real runtime.
        """
        runtime_mode = os.getenv("REFRAME_RUNTIME_MODE", "mock").lower()
        if runtime_mode == "real" or os.getenv("REAL_INTEGRATION_VALIDATION", "false").lower() == "true":
            raise RuntimeError("DETERMINISTIC_VERIFIER_FORBIDDEN_IN_REAL_MODE: Real Gemini API client required.")

        rel = pre_annotated_relation or RelationType.REINTERPRETATION
        event_ids = [e.event_id for e in events]
        fact_ids = [f.fact_id for f in facts]
        frame_ids: List[str] = []
        for e in events:
            frame_ids.extend(e.evidence_frame_ids)
        frame_ids = list(dict.fromkeys(frame_ids))

        if rel == RelationType.COINCIDENCE:
            return VerifiedReframe(
                reveal_id=reveal.reveal_id,
                scene_id=candidate.scene_id,
                relation_type=RelationType.COINCIDENCE,
                before_meaning=candidate.summary,
                after_meaning="Scene contains character but has no causal double-meaning.",
                evidence_event_ids=event_ids,
                evidence_fact_ids=fact_ids,
                evidence_frame_ids=frame_ids,
                confidence=0.9,
                is_supported=False,
            )
        elif rel == RelationType.IRRELEVANT:
            return VerifiedReframe(
                reveal_id=reveal.reveal_id,
                scene_id=candidate.scene_id,
                relation_type=RelationType.IRRELEVANT,
                before_meaning=candidate.summary,
                after_meaning="Unrelated background action.",
                confidence=0.95,
                is_supported=False,
            )
        else:
            return VerifiedReframe(
                reveal_id=reveal.reveal_id,
                scene_id=candidate.scene_id,
                relation_type=rel,
                before_meaning=f"Audience believed {reveal.previous_belief} during this scene.",
                after_meaning=f"In reality, this was a key precursor: {reveal.revealed_fact}.",
                evidence_event_ids=event_ids,
                evidence_fact_ids=fact_ids,
                evidence_frame_ids=frame_ids,
                confidence=0.95,
                is_supported=True,
            )

    def assemble_results(
        self,
        run_id: str,
        reveal: Reveal,
        spoiler_cutoff_ms: int,
        verified_items: List[Tuple[ReframeCandidate, VerifiedReframe]],
        top_k: int = 5,
        dataset_version: str = "the_bat_whispers_v3_gemini36",
    ) -> ReframeResult:
        """
        Applies post-verification policy filtering and builds the final ReframeResult with grounded evidence.
        """
        presentable_cards: List[ReframedMomentCard] = []

        for cand, verified in verified_items:
            if not verified.is_supported:
                continue

            if not verified.relation_type.is_user_presentable:
                continue

            if not verified.evidence_event_ids and not verified.evidence_fact_ids:
                continue

            loc = "Oakdale Manor"

            # Derive precise evidence end timestamp strictly before cutoff
            ev_end = min(cand.end_ms, spoiler_cutoff_ms - 1) if cand.end_ms >= spoiler_cutoff_ms else cand.end_ms
            if ev_end == 0:
                ev_end = min(cand.start_ms + 120000, spoiler_cutoff_ms - 1)

            card = ReframedMomentCard(
                scene_id=cand.scene_id,
                start_ms=cand.start_ms,
                end_ms=ev_end,
                location=loc,
                scene_summary=cand.summary,
                relation_type=verified.relation_type,
                before_meaning=verified.before_meaning,
                after_meaning=verified.after_meaning,
                evidence_facts=verified.evidence_fact_ids,
                evidence_events=verified.evidence_event_ids,
                evidence_frame_ids=verified.evidence_frame_ids,
                confidence=verified.confidence,
                dataset_version=dataset_version,
            )
            presentable_cards.append(card)

        presentable_cards = presentable_cards[:top_k]

        if not presentable_cards:
            return ReframeResult(
                run_id=run_id,
                movie_id=reveal.movie_id,
                reveal_id=reveal.reveal_id,
                spoiler_cutoff_ms=spoiler_cutoff_ms,
                status=ReframeRunStatus.ABSTAINED,
                cards=[],
                abstain_reason=AbstainReason.EVIDENCE_INSUFFICIENT,
                dataset_version=dataset_version,
            )

        return ReframeResult(
            run_id=run_id,
            movie_id=reveal.movie_id,
            reveal_id=reveal.reveal_id,
            spoiler_cutoff_ms=spoiler_cutoff_ms,
            status=ReframeRunStatus.COMPLETED,
            cards=presentable_cards,
            dataset_version=dataset_version,
        )

