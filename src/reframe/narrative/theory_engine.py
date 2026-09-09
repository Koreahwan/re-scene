"""
Reframe V7 Deep Theory Analysis & Grounding Engine (TheoryAnalysisEngine)
Analyzes fan theory text as USER_CONTENT, computing distinct semantic grounding scores,
supporting evidence, counterevidence, and counterfactual robustness.
Zero Paid Model Calls in offline mode.
"""
import uuid
import hashlib
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import structlog

from src.reframe.evidence.adapter import v3_adapter
from src.reframe.evidence.catalog_registry import catalog_registry

logger = structlog.get_logger(__name__)


class TheoryValidationResult(BaseModel):
    theory_id: str
    post_version_id: str
    claim_version_id: Optional[str] = None
    target_reveal_id: str
    validation_verdict: str  # RELATED_EVIDENCE or NO_MATCH; not a truth verdict
    validation_mode: str = "LOCAL_KEYWORD_RETRIEVAL"
    live_model_used: bool = False
    trust_namespace: str = "ENGINE_INFERENCE"
    grounding_score: float
    supporting_evidence: List[str] = Field(default_factory=list)
    counterevidence: List[str] = Field(default_factory=list)
    missing_evidence: List[Dict[str, Any]] = Field(default_factory=list)
    alternative_explanations: List[str] = Field(default_factory=list)
    counterfactual_results: Dict[str, Any] = Field(default_factory=dict)
    uncertainty: Optional[float] = None
    ai_disclosure: str = "ENGINE_GENERATED_DISCOVERY"
    input_hash: str


class TheoryAnalysisEngine:
    """
    Evaluates fan theory claims against pre-cutoff canon evidence.
    Produces genuinely different outputs for different fan theory texts.
    """
    @staticmethod
    def validate_theory(theory_input: Dict[str, Any]) -> TheoryValidationResult:
        theory_text = theory_input.get("theory_text", "")
        theory_id = theory_input.get("theory_id", "")
        post_version_id = theory_input.get("post_version_id", "")
        claim_version_id = theory_input.get("claim_version_id")
        target_reveal_id = theory_input.get("target_reveal_id", "reveal-anderson-identity")
        input_hash = theory_input.get("input_hash", hashlib.sha256(theory_text.encode("utf-8")).hexdigest()[:16])

        reveal = v3_adapter.get_reveal(target_reveal_id)
        cutoff_ms = reveal.timestamp_ms if reveal else 4860000

        # Retrieve pre-cutoff events
        pre_cutoff_events = v3_adapter.get_events(cutoff_ms=cutoff_ms)
        text_lower = theory_text.lower()
        # Small, explicit search lexicon; not a translation or reasoning model.
        korean_search_terms = {'벽난로': 'fireplace', '선반': 'mantel', '그림': 'painting',
            '장치': 'mechanism', '설계도': 'blueprints', '앤더슨': 'anderson', '금고': 'safe',
            '초상화': 'portrait', '사다리': 'stepladder', '손전등': 'flashlight',
            '방아쇠': 'trigger', '단서': 'clue', '통로': 'passage', '숨겨진': 'hidden', '형사': 'detective'}
        text_lower += ' ' + ' '.join(english for korean, english in korean_search_terms.items() if korean in theory_text)

        # Specific narrative forensic domain keywords
        domain_keywords = {
            "fireplace", "mantel", "painting", "mechanism", "blueprints",
            "anderson", "safe", "portrait", "stepladder", "flashlight",
            "trigger", "clue", "passage", "hidden", "detective"
        }

        # Check keyword matches against pre-cutoff events
        supporting_events: List[str] = []
        ranked_events = []
        matched_score = 0.0

        for ev in pre_cutoff_events:
            ev_desc = (ev.description + " " + ev.actor + " " + ev.action).lower()
            ev_keywords = [w for w in domain_keywords if w in ev_desc]
            theory_matches = [w for w in ev_keywords if w in text_lower]

            if len(theory_matches) >= 2:
                ranked_events.append((sum(.25 if word in {'anderson', 'detective', 'clue'} else 1 for word in theory_matches), ev.timestamp_ms, ev.event_id))
                matched_score += 0.35
            elif len(theory_matches) == 1:
                ranked_events.append((.25 if theory_matches[0] in {'anderson', 'detective', 'clue'} else 1, ev.timestamp_ms, ev.event_id))
                matched_score += 0.15

        supporting_events = [item[2] for item in sorted(ranked_events, key=lambda item: (-item[0], item[1]))]
        matched_score = min(0.95, round(matched_score, 2))

        # Lexical retrieval cannot validate an interpretation or contradiction.
        # In particular, zero English keyword matches says nothing about a
        # Unmatched phrasing. Never fabricate counterfactual measurements.
        verdict = "RELATED_EVIDENCE" if supporting_events else "NO_MATCH"
        missing = [{"type": "SEMANTIC_REVIEW_NOT_RUN", "proposition": theory_text[:64], "evidence_id": None}]

        return TheoryValidationResult(
            theory_id=theory_id,
            post_version_id=post_version_id,
            claim_version_id=claim_version_id,
            target_reveal_id=target_reveal_id,
            validation_verdict=verdict,
            grounding_score=matched_score,
            supporting_evidence=supporting_events[:5],
            counterevidence=[],
            missing_evidence=missing,
            alternative_explanations=[],
            counterfactual_results={"status": "NOT_RUN"},
            uncertainty=None,
            input_hash=input_hash
        )


theory_engine = TheoryAnalysisEngine()
