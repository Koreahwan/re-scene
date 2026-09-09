"""
Reframe V7 Agent Runtime & ADK Execution Orchestrator
Executes the full Hypothesis -> Critic -> Counterfactual -> Judge reasoning pipeline
grounded in multi-channel retrieved evidence via Google ADK Execution Gateway.
Zero Paid Model Calls in default offline configuration.
"""
import uuid
import structlog
from typing import Dict, Any, List, Optional

from src.reframe.shared.config import settings
from src.reframe.agents.root_agent import reframe_root_agent
from src.reframe.agents.tools.mcp_tools import retrieve_entity_evidence, retrieve_character_states
from src.reframe.agents.adk_gateway import get_adk_execution_gateway, AdkExecutionResult
from src.reframe.agents.roles import AgentCallTelemetry

logger = structlog.get_logger(__name__)


def get_google_genai_client():
    """Returns official Google GenAI client if live calls are enabled."""
    if not settings.PAID_CALLS_ENABLED or settings.SPEND_KILL_SWITCH_ACTIVE:
        raise RuntimeError("PAID_CALLS_DISABLED: Live Google model calls are disabled.")
    from google import genai
    return genai.Client()


class AgentRuntime:
    def __init__(self):
        self.root_agent = reframe_root_agent

    async def execute_adk_analysis(
        self,
        work_id: str,
        edition_id: str,
        reveal_id: str,
        cutoff_ms: int,
        analysis_run_id: str,
        provided_seeds: Optional[List[Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes genuine Google ADK analysis pipeline across Hypothesis, Critic, and Judge roles.
        Builds all proof candidates from retrieved evidence and multi-channel observations.
        """
        logger.info(
            "Executing ADK agent analysis workflow",
            agent_name=self.root_agent.name,
            run_id=analysis_run_id,
            reveal_id=reveal_id,
            cutoff_ms=cutoff_ms
        )

        gateway = get_adk_execution_gateway()
        result: AdkExecutionResult = await gateway.run_analysis(
            work_id=work_id,
            edition_id=edition_id,
            reveal_id=reveal_id,
            cutoff_ms=cutoff_ms,
            analysis_run_id=analysis_run_id,
            provided_seeds=provided_seeds
        )

        return {
            "status": result.status,
            "reveal_id": result.reveal_id,
            "cutoff_ms": result.cutoff_ms,
            "session_id": result.session_id,
            "runner_name": result.runner_name,
            "execution_mode": result.execution_mode,
            "proofs": result.validated_proofs,
            "validated_proofs": result.validated_proofs,
            "hypotheses": [h.model_dump() for h in result.hypotheses],
            "critiques": [c.model_dump() for c in result.critiques],
            "judgments": [j.model_dump() for j in result.judgments],
            "telemetries": [t.model_dump() for t in result.telemetries]
        }



agent_runtime = AgentRuntime()
