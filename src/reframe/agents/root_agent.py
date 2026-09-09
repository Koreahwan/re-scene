"""
Reframe V7 Google ADK Root Agent (reframe_root_agent)
"""
from typing import List, Dict, Any, Optional
import google.adk as adk
import structlog

from src.reframe.shared.config import settings
from src.reframe.agents.tools.mcp_tools import (
    retrieve_narrative_evidence,
    retrieve_entity_evidence,
    retrieve_character_states
)
from src.reframe.cost.invoker import GuardedGeminiAdkLlm

logger = structlog.get_logger(__name__)

REFRAME_ROOT_INSTRUCTION = """
You are the Reframe Deep Narrative Forensics Root Agent (`reframe_root_agent`).
Your purpose is to identify retrospective narrative clues that change meaning in light of a verified Reveal.

Core Operating Rules:
1. You must compile the selected Reveal into an evidence query program.
2. Search and verify clues strictly using official MCP ClickHouse tools (`retrieve_narrative_evidence`, `retrieve_entity_evidence`, `retrieve_character_states`).
3. You must never invent or hallucinate scene timestamps, events, or facts.
4. Maintain strict separation between OBSERVED facts, CANONICAL truths, and INFERRED hypotheses.
5. All final proofs must contain at least two distinct scenes and satisfy proof obligations (KNOWLEDGE_LEAK, CLAIM_ACTION_CONFLICT, HIDDEN_PLAN_CHAIN).
6. If evidence is insufficient or contradicted, you must ABSTAIN.
"""


def create_reframe_root_agent() -> adk.Agent:
    """
    Constructs the offline Google ADK root agent instance.
    """
    agent = adk.Agent(
        name="reframe_root_agent",
        model=settings.GEMINI_MODEL_ID,
        instruction=REFRAME_ROOT_INSTRUCTION,
        tools=[retrieve_narrative_evidence, retrieve_entity_evidence, retrieve_character_states]
    )
    return agent


def create_live_reframe_root_agent() -> adk.Agent:
    """
    Constructs the real Google ADK live root agent explicitly bound to GuardedGeminiAdkLlm
    under the 'reframe-live-guarded' model alias.
    """
    agent = adk.Agent(
        name="reframe_live_root_agent",
        model="reframe-live-guarded",
        instruction=REFRAME_ROOT_INSTRUCTION,
        tools=[retrieve_narrative_evidence, retrieve_entity_evidence, retrieve_character_states]
    )
    return agent


reframe_root_agent = create_reframe_root_agent()
reframe_live_root_agent = create_live_reframe_root_agent()

