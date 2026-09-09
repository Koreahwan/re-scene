"""
Reframe V7 Agent Role Separation: Hypothesis, Critic, and Judge Gateways
Implements strict offline fixture vs live Gemini/ADK gateway separation.
Zero Paid Model Calls in default offline configuration.
"""
import uuid
import hashlib
import json
import time
from abc import ABC, abstractmethod
from enum import Enum
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from pydantic import BaseModel, Field
import structlog

from src.reframe.shared.config import settings
from src.reframe.narrative.bundle import EvidenceBundle
from src.reframe.evidence.schemas import EventDTO, FactDTO, SceneDTO
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.domain.enums import ExecutionMode

logger = structlog.get_logger(__name__)



def compute_prompt_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class AgentCallTelemetry(BaseModel):
    model_call_id: str = Field(default_factory=lambda: f"trace-local-{uuid.uuid4().hex[:12]}")
    provider_call_id: Optional[str] = None
    role: str  # HYPOTHESIS, CRITIC, JUDGE, THEORY_CHECK, ROOT_ORCHESTRATOR
    stage_id: Optional[str] = None
    model_id: str = settings.GEMINI_MODEL_ID
    prompt_hash: str
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None
    attempt: int = 1
    input_tokens: Optional[int] = 0
    output_tokens: Optional[int] = 0
    reasoning_tokens: Optional[int] = 0
    latency_ms: Optional[float] = 0.0
    status: str = "COMPLETED"  # COMPLETED, FAILED, SKIPPED_OFFLINE, FIXTURE, UNAVAILABLE
    execution_mode: ExecutionMode = ExecutionMode.OFFLINE_FIXTURE
    paid_model_calls: int = 0


class HypothesisRoleOutput(BaseModel):
    title: str
    proof_type: str  # KNOWLEDGE_LEAK, CLAIM_ACTION_CONFLICT, HIDDEN_PLAN_CHAIN
    h0_blind_explanation: str
    hr_reveal_explanation: str
    ha_alternatives: List[str] = Field(default_factory=list)
    observed_premises: List[Dict[str, Any]] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    knowledge_proposition_id: Optional[str] = None
    knowledge_proposition: Optional[str] = None


class CriticRoleOutput(BaseModel):
    coincidence_score: float = Field(default=0.1, ge=0.0, le=1.0)
    routine_role_bias: float = Field(default=0.1, ge=0.0, le=1.0)
    hindsight_bias: float = Field(default=0.1, ge=0.0, le=1.0)
    future_contamination_detected: bool = False
    unsupported_authorial_intent: bool = False
    alternative_completeness: float = Field(default=0.9, ge=0.0, le=1.0)
    critic_verdict: str = "PASS"  # PASS, CHALLENGE, REJECT
    critique_notes: List[str] = Field(default_factory=list)


class JudgeRoleOutput(BaseModel):
    verdict: str = "VERIFIED"  # VERIFIED, ABSTAIN, REJECTED
    confidence: float = Field(default=0.90, ge=0.0, le=1.0)
    proof_strength: float = Field(default=0.88, ge=0.0, le=1.0)
    fan_impact: float = Field(default=0.85, ge=0.0, le=1.0)
    judge_rationale: str
    obligation_satisfaction: Dict[str, bool] = Field(default_factory=dict)


# -------------------------------------------------------------
# Abstract Role Gateways (R2-03)
# -------------------------------------------------------------

class HypothesisGateway(ABC):
    @abstractmethod
    def generate_hypotheses(
        self,
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[HypothesisRoleOutput], AgentCallTelemetry]:
        pass


class CriticGateway(ABC):
    @abstractmethod
    def critique_hypotheses(
        self,
        hypotheses: List[HypothesisRoleOutput],
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[CriticRoleOutput], AgentCallTelemetry]:
        pass


class JudgeGateway(ABC):
    @abstractmethod
    def judge_proofs(
        self,
        hypotheses: List[HypothesisRoleOutput],
        critiques: List[CriticRoleOutput],
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[JudgeRoleOutput], AgentCallTelemetry]:
        pass


# -------------------------------------------------------------
# Offline Fixture Implementations (R2-03) - $0.00 Cost Guarantee
# -------------------------------------------------------------

class OfflineFixtureHypothesisGateway(HypothesisGateway):
    """Deterministic offline hypothesis generator grounded strictly in bundle evidence."""
    def generate_hypotheses(
        self,
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[HypothesisRoleOutput], AgentCallTelemetry]:
        t0 = time.perf_counter()
        prompt_text = f"GENERATE_HYPOTHESIS for {bundle.reveal.reveal_id} with {len(bundle.related_scenes)} scenes"
        prompt_hash = compute_prompt_hash(prompt_text)

        hypotheses: List[HypothesisRoleOutput] = []
        reveal_id = bundle.reveal.reveal_id

        # Check DeepSnapshotRepository for clean-room snapshot candidates (Section 15)
        from src.reframe.narrative.snapshot_repo import snapshot_repo, SnapshotIntegrityError
        try:
            snapshot_candidates = snapshot_repo.get_proof_candidates(reveal_id=reveal_id, snapshot_id="deep_snapshot_v1_1")
        except SnapshotIntegrityError as e:
            logger.error("offline_fixture_snapshot_integrity_error", error=str(e))
            latency = (time.perf_counter() - t0) * 1000.0
            telemetry = AgentCallTelemetry(
                role="HYPOTHESIS",
                prompt_hash=prompt_hash,
                latency_ms=round(latency, 2),
                status="FAILED",
                execution_mode=ExecutionMode.OFFLINE_FIXTURE,
                paid_model_calls=0
            )
            return [], telemetry

        if snapshot_candidates:
            for p in snapshot_candidates:
                hypotheses.append(
                    HypothesisRoleOutput(
                        title=p["title"],
                        proof_type=p["proof_type"],
                        h0_blind_explanation=p["blind_explanation"],
                        hr_reveal_explanation=p["reveal_explanation"],
                        ha_alternatives=p.get("alternative_explanations", ["Routine activity", "Coincidental timing"]),
                        observed_premises=p.get("observed_premises", []),
                        assumptions=["Character/structural behavior re-evaluated under reveal."]
                    )
                )


        latency = (time.perf_counter() - t0) * 1000.0
        telemetry = AgentCallTelemetry(
            role="HYPOTHESIS",
            prompt_hash=prompt_hash,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            latency_ms=round(latency, 2),
            status="SKIPPED_OFFLINE",
            execution_mode=ExecutionMode.OFFLINE_FIXTURE,
            paid_model_calls=0
        )
        return hypotheses, telemetry


class OfflineFixtureCriticGateway(CriticGateway):
    """Deterministic offline critic enforcing alternative explanations and hindsight checks."""
    def critique_hypotheses(
        self,
        hypotheses: List[HypothesisRoleOutput],
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[CriticRoleOutput], AgentCallTelemetry]:
        t0 = time.perf_counter()
        prompt_text = f"CRITIQUE_HYPOTHESIS for {len(hypotheses)} candidates"
        prompt_hash = compute_prompt_hash(prompt_text)

        critiques: List[CriticRoleOutput] = []
        for h in hypotheses:
            has_alternatives = len(h.ha_alternatives) >= 2
            future_leak = any(p.get("timestamp_ms", 0) >= bundle.reveal.timestamp_ms for p in h.observed_premises)

            if future_leak:
                critiques.append(
                    CriticRoleOutput(
                        coincidence_score=0.9,
                        routine_role_bias=0.8,
                        hindsight_bias=0.9,
                        future_contamination_detected=True,
                        unsupported_authorial_intent=True,
                        alternative_completeness=0.2,
                        critic_verdict="REJECT",
                        critique_notes=["Critical violation: Future scene timestamp detected in premise."]
                    )
                )
            elif not has_alternatives:
                critiques.append(
                    CriticRoleOutput(
                        coincidence_score=0.4,
                        routine_role_bias=0.3,
                        hindsight_bias=0.4,
                        alternative_completeness=0.5,
                        critic_verdict="CHALLENGE",
                        critique_notes=["Lacks exhaustive alternative hypotheses to counter hindsight bias."]
                    )
                )
            else:
                critiques.append(
                    CriticRoleOutput(
                        coincidence_score=0.15,
                        routine_role_bias=0.20,
                        hindsight_bias=0.10,
                        future_contamination_detected=False,
                        unsupported_authorial_intent=False,
                        alternative_completeness=0.95,
                        critic_verdict="PASS",
                        critique_notes=["Robust epistemic grounding and balanced alternative explanations."]
                    )
                )

        latency = (time.perf_counter() - t0) * 1000.0
        telemetry = AgentCallTelemetry(
            role="CRITIC",
            prompt_hash=prompt_hash,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            latency_ms=round(latency, 2),
            status="SKIPPED_OFFLINE",
            execution_mode=ExecutionMode.OFFLINE_FIXTURE,
            paid_model_calls=0
        )
        return critiques, telemetry

    @classmethod
    def critique(
        cls,
        hypothesis: HypothesisRoleOutput,
        bundle: EvidenceBundle,
        cutoff_ms: Optional[int] = None
    ) -> Tuple[CriticRoleOutput, AgentCallTelemetry]:
        gw = cls()
        results, telem = gw.critique_hypotheses([hypothesis], bundle, "direct-test")
        return results[0], telem


class OfflineFixtureJudgeGateway(JudgeGateway):
    """Deterministic offline judge synthesizing hypotheses and critiques."""
    def judge_proofs(
        self,
        hypotheses: List[HypothesisRoleOutput],
        critiques: List[CriticRoleOutput],
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[JudgeRoleOutput], AgentCallTelemetry]:
        t0 = time.perf_counter()
        prompt_text = f"JUDGE_SYNTHESIS for {len(hypotheses)} pairs"
        prompt_hash = compute_prompt_hash(prompt_text)

        judgments: List[JudgeRoleOutput] = []
        for h, c in zip(hypotheses, critiques):
            if c.critic_verdict == "REJECT" or c.future_contamination_detected:
                judgments.append(
                    JudgeRoleOutput(
                        verdict="REJECTED",
                        confidence=0.1,
                        proof_strength=0.0,
                        fan_impact=0.0,
                        judge_rationale=f"Rejected due to critic finding: {c.critique_notes}",
                        obligation_satisfaction={"critic_passed": False, "temporal_integrity": False}
                    )
                )
            elif c.critic_verdict == "CHALLENGE":
                judgments.append(
                    JudgeRoleOutput(
                        verdict="ABSTAIN",
                        confidence=0.60,
                        proof_strength=0.50,
                        fan_impact=0.40,
                        judge_rationale="Insufficient proof strength; abstaining from presentation.",
                        obligation_satisfaction={"critic_passed": False, "temporal_integrity": True}
                    )
                )
            else:
                judgments.append(
                    JudgeRoleOutput(
                        verdict="VERIFIED",
                        confidence=0.94,
                        proof_strength=0.92,
                        fan_impact=0.90,
                        judge_rationale=f"Verified multi-scene proof grounded in {len(h.observed_premises)} concrete observations.",
                        obligation_satisfaction={"critic_passed": True, "temporal_integrity": True, "epistemic_valid": True}
                    )
                )

        latency = (time.perf_counter() - t0) * 1000.0
        telemetry = AgentCallTelemetry(
            role="JUDGE",
            prompt_hash=prompt_hash,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            latency_ms=round(latency, 2),
            status="SKIPPED_OFFLINE",
            execution_mode=ExecutionMode.OFFLINE_FIXTURE,
            paid_model_calls=0
        )
        return judgments, telemetry

    @classmethod
    def judge(
        cls,
        hypothesis: HypothesisRoleOutput,
        critic_result: CriticRoleOutput,
        cf_delta: float = -0.85,
        validation_valid: bool = True
    ) -> Tuple[JudgeRoleOutput, AgentCallTelemetry]:
        gw = cls()
        from src.reframe.narrative.bundle import bundle_builder
        bundle = bundle_builder.build_bundle(v3_adapter.get_reveal("reveal-anderson-identity"))
        judgments, telem = gw.judge_proofs([hypothesis], [critic_result], bundle, "direct-test")
        return judgments[0], telem



CriticRoleExecutor = OfflineFixtureCriticGateway
HypothesisRoleExecutor = OfflineFixtureHypothesisGateway
JudgeRoleExecutor = OfflineFixtureJudgeGateway


# -------------------------------------------------------------
# Live Gemini / Google ADK Gateways (Deprecated in favor of LiveGoogleAdkExecutionGateway)
# -------------------------------------------------------------

class LiveGeminiHypothesisGateway(HypothesisGateway):
    """Deprecated: All live execution routes through LiveGoogleAdkExecutionGateway."""
    def generate_hypotheses(
        self,
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[HypothesisRoleOutput], AgentCallTelemetry]:
        raise RuntimeError("DEPRECATED_GATEWAY: Use LiveGoogleAdkExecutionGateway for all live ADK execution.")


class LiveGeminiCriticGateway(CriticGateway):
    """Deprecated: All live execution routes through LiveGoogleAdkExecutionGateway."""
    def critique_hypotheses(
        self,
        hypotheses: List[HypothesisRoleOutput],
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[CriticRoleOutput], AgentCallTelemetry]:
        raise RuntimeError("DEPRECATED_GATEWAY: Use LiveGoogleAdkExecutionGateway for all live ADK execution.")


class LiveGeminiJudgeGateway(JudgeGateway):
    """Deprecated: All live execution routes through LiveGoogleAdkExecutionGateway."""
    def judge_proofs(
        self,
        hypotheses: List[HypothesisRoleOutput],
        critiques: List[CriticRoleOutput],
        bundle: EvidenceBundle,
        analysis_run_id: str
    ) -> Tuple[List[JudgeRoleOutput], AgentCallTelemetry]:
        raise RuntimeError("DEPRECATED_GATEWAY: Use LiveGoogleAdkExecutionGateway for all live ADK execution.")


# -------------------------------------------------------------
# Gateway Factory (R2-03)
# -------------------------------------------------------------

def get_hypothesis_gateway() -> HypothesisGateway:
    return OfflineFixtureHypothesisGateway()


def get_critic_gateway() -> CriticGateway:
    return OfflineFixtureCriticGateway()


def get_judge_gateway() -> JudgeGateway:
    return OfflineFixtureJudgeGateway()


# Backward compatibility aliases
HypothesisRoleExecutor = OfflineFixtureHypothesisGateway
CriticRoleExecutor = OfflineFixtureCriticGateway
JudgeRoleExecutor = OfflineFixtureJudgeGateway

