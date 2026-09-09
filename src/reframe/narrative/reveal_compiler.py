"""
Reframe V6/V7 Reveal Compiler Engine
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import structlog

from src.reframe.evidence.schemas import RevealDTO
from src.reframe.narrative.anomalies import NarrativeAnomalyType

logger = structlog.get_logger(__name__)


class CompiledRevealProgram(BaseModel):
    reveal_id: str
    reveal_type: str  # IDENTITY, LOCATION, MOTIVATION, EVENT
    spoiler_cutoff_ms: int
    target_entities: List[str]
    expected_anomaly_types: List[str]
    retrieval_channels: List[str]
    required_graph_edges: List[str]
    proof_obligations: List[str]
    counterfactual_controls: List[str]


class RevealCompiler:
    @staticmethod
    def compile(reveal: RevealDTO) -> CompiledRevealProgram:
        if reveal.reveal_type == "IDENTITY":
            return CompiledRevealProgram(
                reveal_id=reveal.reveal_id,
                reveal_type="IDENTITY",
                spoiler_cutoff_ms=reveal.timestamp_ms,
                target_entities=reveal.affected_entities or ["Detective Anderson", "The Bat"],
                expected_anomaly_types=[
                    NarrativeAnomalyType.KNOWLEDGE_LEAK,
                    NarrativeAnomalyType.CLAIM_ACTION_CONFLICT,
                    NarrativeAnomalyType.DUAL_PURPOSE_ACTION
                ],
                retrieval_channels=["Entity", "Knowledge Conflict", "Claim–Action", "Plan Step", "Dialogue"],
                required_graph_edges=["REQUIRES_KNOWLEDGE_OF", "CONTRADICTS", "SATISFIES_PLAN_STEP", "EXPLAINS"],
                proof_obligations=["KNOWLEDGE_LEAK", "CLAIM_ACTION_CONFLICT", "HIDDEN_PLAN_CHAIN"],
                counterfactual_controls=["Reveal Swap", "Wrong Identity", "Evidence Ablation"]
            )
        elif reveal.reveal_type == "LOCATION":
            return CompiledRevealProgram(
                reveal_id=reveal.reveal_id,
                reveal_type="LOCATION",
                spoiler_cutoff_ms=reveal.timestamp_ms,
                target_entities=reveal.affected_entities or ["Grand Fireplace", "Dale Ogden"],
                expected_anomaly_types=[
                    NarrativeAnomalyType.ACCESS_ANOMALY,
                    NarrativeAnomalyType.KNOWLEDGE_LEAK,
                    NarrativeAnomalyType.UNEXPLAINED_ACTION
                ],
                retrieval_channels=["Entity", "Semantic Event", "Plan Step", "Access/Opportunity", "Discourse"],
                required_graph_edges=["ENABLES", "REQUIRES_ACCESS_TO", "SATISFIES_PLAN_STEP", "EXPLAINS"],
                proof_obligations=["KNOWLEDGE_LEAK", "CLAIM_ACTION_CONFLICT", "HIDDEN_PLAN_CHAIN"],
                counterfactual_controls=["Reveal Swap", "Wrong Mechanism", "Evidence Ablation"]
            )
        else:
            return CompiledRevealProgram(
                reveal_id=reveal.reveal_id,
                reveal_type=reveal.reveal_type,
                spoiler_cutoff_ms=reveal.timestamp_ms,
                target_entities=reveal.affected_entities,
                expected_anomaly_types=[NarrativeAnomalyType.KNOWLEDGE_LEAK, NarrativeAnomalyType.CLAIM_ACTION_CONFLICT],
                retrieval_channels=["Entity", "Semantic Event", "Dialogue"],
                required_graph_edges=["EXPLAINS", "MOTIVATES"],
                proof_obligations=["KNOWLEDGE_LEAK", "CLAIM_ACTION_CONFLICT"],
                counterfactual_controls=["Reveal Swap", "Evidence Ablation"]
            )


reveal_compiler = RevealCompiler()
