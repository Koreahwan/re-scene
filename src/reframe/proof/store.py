"""
Reframe V7 Canonical Proof Store & Cache-First Lookup Engine
Enforces 0 model calls for normal fan access via version-pinned durable persistence.
Explicit trust namespaces (ENGINE_INFERENCE, human_review_status, presentation_status) (R4-09).
Canonical content hash verification and deep obligation alignment.
Zero Paid Model Calls.
"""
import uuid
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from src.reframe.shared.config import settings
from src.reframe.proof.models import ProofRecord
from src.reframe.proof.ai_publication import is_public_ai_analysis, label_ai_analysis
from src.reframe.catalog.runtime_state import synchronized
from src.reframe.identity.auth import ViewerContext
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility
from src.reframe.spoiler.analysis_boundary import analysis_visibility
from src.reframe.evidence.adapter import v3_adapter, compute_content_hash
from src.reframe.proof.validator import DeterministicProofValidator, ProofValidationVerdict

logger = structlog.get_logger(__name__)


def generate_proof_cache_key(
    work_id: str,
    edition_id: str,
    reveal_id: str,
    dataset_version: str = "v3",
    overlay_sha: str = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
    evidence_bundle_hash: str = "default_evidence_bundle",
    model_id: str = "gemini-2.5-flash",
    prompt_hash: str = "prompt_v7_canonical",
    reasoning_config_hash: str = "reasoning_p0_standard",
    retrieval_config_hash: str = "5channel_retrieval_v7",
    proof_schema_version: str = "1.0.0"
) -> str:
    """
    Computes the normative canonical proof cache key matching ADR-001 and Freeze Spec 03.
    """
    elements = [
        f"work:{work_id}",
        f"edition:{edition_id}",
        f"reveal:{reveal_id}",
        f"dataset:{dataset_version}",
        f"overlay_sha:{overlay_sha}",
        f"evidence_bundle_hash:{evidence_bundle_hash}",
        f"model_id:{model_id}",
        f"prompt_hash:{prompt_hash}",
        f"reasoning_config_hash:{reasoning_config_hash}",
        f"retrieval_config_hash:{retrieval_config_hash}",
        f"proof_schema_version:{proof_schema_version}"
    ]
    raw_str = "|".join(elements)
    return hashlib.sha256(raw_str.encode("utf-8")).hexdigest()


from src.reframe.proof.hasher import (
    canonical_event_hash,
    canonical_fact_hash,
    canonical_frame_hash,
    compute_canonical_proof_hash
)



def _build_premise(event_id: str, scene_id: str, timestamp_ms: int, actor: str, action: str, fact: str) -> Dict[str, Any]:
    ev = v3_adapter.get_event(event_id)
    frame_ids = ev.evidence_frame_ids if ev and ev.evidence_frame_ids else []
    frame_url = f"/api/v1/media/the-bat-whispers-1930/tbw-fullscreen-archive/frames/{frame_ids[0]}" if frame_ids else None
    raw_data = {
        "event_id": event_id,
        "scene_id": scene_id,
        "timestamp_ms": timestamp_ms,
        "actor": actor,
        "action": action,
        "fact": fact,
        "display_fact": fact,
        "display_paraphrase": fact,
        "evidence_frame_ids": frame_ids,
        "frame_url": frame_url,
        "canonical_content_hash": canonical_event_hash(event_id)
    }
    return raw_data


# -------------------------------------------------------------
# Narrative Pattern & Rewatch Observation Repository (D3 Non-Normative)
# -------------------------------------------------------------
CANONICAL_PATTERNS_MAP: Dict[str, List[Dict[str, Any]]] = {
    "reveal-anderson-identity": [
        {
            "pattern_id": "pattern-anderson-01",
            "proof_id": "proof-anderson-01",
            "reveal_id": "reveal-anderson-identity",
            "pattern_type": "MULTI_SCENE_PATTERN",
            "proof_type": "MULTI_SCENE_PATTERN",
            "title": "Detective Anderson Performs Unbriefed Search Operations",
            "human_review_status": "NOT_REVIEWED",
            "presentation_status": "HIDDEN_FROM_PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Rewatch Observation)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
                {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000}
            ],
            "observed_premises": [
                _build_premise("ev-c017-05", "scene-tbw-c017", 2010000, "Detective Anderson", "observe", "Detective Anderson stands alone in the dark hall inspecting his surroundings."),
                _build_premise("ev-c021-03", "scene-tbw-c021", 2490000, "Detective Anderson", "displays", "Detective Anderson carries rolled papers across the room and unrolls blueprints before Dale and the group.")
            ],
            "blind_explanation": "A zealous detective conducting a thorough inspection and reviewing blueprints with witnesses.",
            "reveal_explanation": "Anderson was actively searching for the concealed safe because he is secretly The Bat.",
            "alternative_explanations": ["Standard police investigation sweep", "Routine examination of architectural plans"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.85,
                "display_heuristic_impact": 0.85,
                "authoritative": False
            }
        },
        {
            "pattern_id": "pattern-anderson-02",
            "proof_id": "proof-anderson-02",
            "reveal_id": "reveal-anderson-identity",
            "pattern_type": "GOAL_ALIGNED_PATTERN",
            "proof_type": "GOAL_ALIGNED_PATTERN",
            "title": "Phased Architectural Blueprint Review and Structural Fixture Search Pattern",
            "human_review_status": "NOT_REVIEWED",
            "presentation_status": "HIDDEN_FROM_PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Goal-Aligned Pattern)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000},
                {"scene_id": "scene-tbw-c023", "timestamp_ms": 2759000},
                {"scene_id": "scene-tbw-c028", "timestamp_ms": 3270000}
            ],
            "observed_premises": [
                _build_premise("ev-c021-03", "scene-tbw-c021", 2490000, "Detective Anderson", "displays", "Detective Anderson carries rolled papers across the room and unrolls blueprints before Dale and the group."),
                _build_premise("ev-c023-05", "scene-tbw-c023", 2759000, "Detective", "examines painting frame", "Detective stands on a stepladder to examine the painting above the fireplace."),
                _build_premise("ev-c028-03", "scene-tbw-c028", 3270000, "Detective Anderson", "moves", "Detective Anderson moves large framed portrait near stairs.")
            ],
            "blind_explanation": "Tactical perimeter defense to protect the household.",
            "reveal_explanation": "Anderson offered verbal reassurance while manipulating wall fixtures to locate the secret passage.",
            "alternative_explanations": ["Routine defensive repositioning", "Searching for signs of forced entry"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.85,
                "display_heuristic_impact": 0.85,
                "authoritative": False
            }
        },
        {
            "pattern_id": "pattern-anderson-03",
            "proof_id": "proof-anderson-03",
            "reveal_id": "reveal-anderson-identity",
            "pattern_type": "MULTI_SCENE_PATTERN",
            "proof_type": "MULTI_SCENE_PATTERN",
            "title": "Detective Anderson Multi-Stage Infiltration and Safe Search Sequence",
            "human_review_status": "NOT_REVIEWED",
            "presentation_status": "HIDDEN_FROM_PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Narrative Pattern)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c017", "timestamp_ms": 2010000},
                {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000},
                {"scene_id": "scene-tbw-c028", "timestamp_ms": 3270000}
            ],
            "observed_premises": [
                _build_premise("ev-c017-05", "scene-tbw-c017", 2010000, "Detective Anderson", "observe", "Detective Anderson stands alone in the dark hall inspecting his surroundings."),
                _build_premise("ev-c021-03", "scene-tbw-c021", 2490000, "Detective Anderson", "displays", "Detective Anderson carries rolled papers across the room and unrolls blueprints before Dale and the group."),
                _build_premise("ev-c028-03", "scene-tbw-c028", 3270000, "Detective Anderson", "moves", "Detective Anderson moves large framed portrait near stairs.")
            ],
            "blind_explanation": "Sequential routine investigative steps by the lead detective across the manor.",
            "reveal_explanation": "A coordinated multi-stage plan to locate the hidden room and safe while maintaining detective cover.",
            "alternative_explanations": ["Standard protocol progression", "Escalating security response to intruder alarms"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.85,
                "display_heuristic_impact": 0.85,
                "authoritative": False
            }
        }
    ],
    "reveal-secret-room-location": [
        {
            "pattern_id": "pattern-secret-room-01",
            "proof_id": "proof-secret-room-01",
            "reveal_id": "reveal-secret-room-location",
            "pattern_type": "MECHANISM_DISCOVERY",
            "proof_type": "MECHANISM_DISCOVERY",
            "title": "Direct Examination and Operation of Fireplace Mantel Mechanism",
            "human_review_status": "NOT_REVIEWED",
            "presentation_status": "HIDDEN_FROM_PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Rewatch Observation)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c023", "timestamp_ms": 2759000},
                {"scene_id": "scene-tbw-c031", "timestamp_ms": 3645000}
            ],
            "observed_premises": [
                _build_premise("ev-c023-05", "scene-tbw-c023", 2759000, "Detective", "examines painting frame", "Detective stands on a stepladder to examine the painting above the fireplace."),
                _build_premise("ev-c031-02", "scene-tbw-c031", 3645000, "Dale Ogden", "touches_mechanism", "Dale Ogden reaches up to touch and operate the mechanism located on the side of the fireplace mantel.")
            ],
            "blind_explanation": "Inspecting decorative art and furnishings above the mantelpiece.",
            "reveal_explanation": "Characters were examining and operating the concealed trigger that unlocks the rotating fireplace wall.",
            "alternative_explanations": ["Art historical examination", "Accidental discovery during frantic search"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.85,
                "display_heuristic_impact": 0.85,
                "authoritative": False
            }
        },
        {
            "pattern_id": "pattern-secret-room-02",
            "proof_id": "proof-secret-room-02",
            "reveal_id": "reveal-secret-room-location",
            "pattern_type": "MULTI_SCENE_PATTERN",
            "proof_type": "MULTI_SCENE_PATTERN",
            "title": "Multi-Phase Architecture Blueprint Analysis and Secret Portal Entry",
            "human_review_status": "NOT_REVIEWED",
            "presentation_status": "HIDDEN_FROM_PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Narrative Pattern)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c021", "timestamp_ms": 2490000},
                {"scene_id": "scene-tbw-c023", "timestamp_ms": 2759000},
                {"scene_id": "scene-tbw-c031", "timestamp_ms": 3645000}
            ],
            "observed_premises": [
                _build_premise("ev-c021-03", "scene-tbw-c021", 2490000, "Detective Anderson", "displays", "Detective Anderson carries rolled papers across the room and unrolls blueprints before Dale and the group."),
                _build_premise("ev-c023-05", "scene-tbw-c023", 2759000, "Detective", "examines painting frame", "Detective stands on a stepladder to examine the painting above the fireplace."),
                _build_premise("ev-c031-02", "scene-tbw-c031", 3645000, "Dale Ogden", "touches_mechanism", "Dale Ogden reaches up to touch and operate the mechanism located on the side of the fireplace mantel.")
            ],
            "blind_explanation": "Investigating floor plans and looking for structural clues across the manor.",
            "reveal_explanation": "A phased architectural recovery effort leading directly from blueprint analysis to mechanism activation.",
            "alternative_explanations": ["Independent unrelated discoveries", "Routine search after mysterious sounds"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.85,
                "display_heuristic_impact": 0.85,
                "authoritative": False
            }
        },
        {
            "pattern_id": "pattern-secret-room-03",
            "proof_id": "proof-secret-room-03",
            "reveal_id": "reveal-secret-room-location",
            "pattern_type": "MULTI_SCENE_PATTERN",
            "proof_type": "MULTI_SCENE_PATTERN",
            "title": "Contradiction Between Casual Art Appreciation and Mechanical Leverage",
            "human_review_status": "NEEDS_CORRECTION",
            "presentation_status": "HIDDEN_FROM_PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Review Pending)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c023", "timestamp_ms": 2759000},
                {"scene_id": "scene-tbw-c031", "timestamp_ms": 3645000}
            ],
            "observed_premises": [
                _build_premise("ev-c023-05", "scene-tbw-c023", 2759000, "Detective", "examines painting frame", "Detective stands on a stepladder to examine the painting above the fireplace."),
                _build_premise("ev-c031-02", "scene-tbw-c031", 3645000, "Dale Ogden", "touches_mechanism", "Dale Ogden reaches up to touch and operate the mechanism located on the side of the fireplace mantel.")
            ],
            "blind_explanation": "Casual examination of historic mantel architecture and portraits.",
            "reveal_explanation": "The seemingly decorative frame examination was a targeted probe for the hidden pivot mechanism.",
            "alternative_explanations": ["Routine inspection of household valuables", "Looking for hidden wires"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.75,
                "display_heuristic_impact": 0.75,
                "authoritative": False
            }
        }
    ],
    "reveal-brooks-innocence": [
        {
            "pattern_id": "pattern-brooks-01",
            "proof_id": "proof-brooks-01",
            "reveal_id": "reveal-brooks-innocence",
            "pattern_type": "MOTIVATION_REVERSAL",
            "proof_type": "MOTIVATION_REVERSAL",
            "title": "Brooks Disguised Gardener Movements and Dale Ogden Alliance",
            "human_review_status": "APPROVED",
            "presentation_status": "PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Rewatch Observation)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c010", "timestamp_ms": 1150000},
                {"scene_id": "scene-tbw-c017", "timestamp_ms": 1980000},
                {"scene_id": "scene-tbw-c024", "timestamp_ms": 2890000}
            ],
            "observed_premises": [
                _build_premise("ev-c010-02", "scene-tbw-c010", 1150000, "Brooks", "signals quietly", "Brooks appears in gardener attire outside the terrace window signaling Dale Ogden."),
                _build_premise("ev-c017-03", "scene-tbw-c017", 1980000, "Brooks", "recovers paper scrap", "Brooks retrieves a torn piece of ledger paper from the study wastebasket.")
            ],
            "blind_explanation": "A suspicious gardener lurking around the manor windows and searching for waste.",
            "reveal_explanation": "Brooks was framed by Anderson and disguised himself as a gardener solely to prove his innocence and protect Dale Ogden.",
            "alternative_explanations": ["Suspicious prowler activity", "Accomplice looking for bank loot"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.85,
                "display_heuristic_impact": 0.85,
                "authoritative": False
            }
        },
        {
            "pattern_id": "pattern-brooks-02",
            "proof_id": "proof-brooks-02",
            "reveal_id": "reveal-brooks-innocence",
            "pattern_type": "CONTRADICTION",
            "proof_type": "CONTRADICTION",
            "title": "Alibi Inconsistency Between Cashier Schedule and Murder Timing",
            "human_review_status": "APPROVED",
            "presentation_status": "PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Rewatch Observation)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c008", "timestamp_ms": 920000},
                {"scene_id": "scene-tbw-c020", "timestamp_ms": 2340000}
            ],
            "observed_premises": [
                _build_premise("ev-c008-01", "scene-tbw-c008", 920000, "Bank Ledger", "records exit", "Cashier log records Brooks departing Oakdale Bank thirty minutes before the vault breach."),
                _build_premise("ev-c020-04", "scene-tbw-c020", 2340000, "Miss Van Gorder", "confirms presence", "Cornelia Van Gorder confirms Brooks was unarmed when seen near the carriage house.")
            ],
            "blind_explanation": "Brooks appears to have fled the town with stolen funds.",
            "reveal_explanation": "Physical distance and witness testimony demonstrate Brooks could not have been present during the vault breach.",
            "alternative_explanations": ["Brooks had an unknown accomplice inside the vault", "Clock discrepancy"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.80,
                "display_heuristic_impact": 0.80,
                "authoritative": False
            }
        }
    ],
    "reveal-masked-robbery-vault": [
        {
            "pattern_id": "pattern-vault-01",
            "proof_id": "proof-vault-01",
            "reveal_id": "reveal-masked-robbery-vault",
            "pattern_type": "EVENT_REVERSAL",
            "proof_type": "EVENT_REVERSAL",
            "title": "Oakdale Bank Vault Combination Transfer Prior to Robbery",
            "human_review_status": "APPROVED",
            "presentation_status": "PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Rewatch Observation)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c002", "timestamp_ms": 240000},
                {"scene_id": "scene-tbw-c005", "timestamp_ms": 580000},
                {"scene_id": "scene-tbw-c011", "timestamp_ms": 1320000}
            ],
            "observed_premises": [
                _build_premise("ev-c002-01", "scene-tbw-c002", 240000, "Fleming", "transfers papers", "Fleming hands an unsealed envelope to Anderson before leaving the bank premises."),
                _build_premise("ev-c005-04", "scene-tbw-c005", 580000, "Anderson", "inspects combination dial", "Anderson memorizes the combination dial markings without consulting official records.")
            ],
            "blind_explanation": "Standard police briefing regarding bank vault security procedures.",
            "reveal_explanation": "The vault combination was leaked by Fleming to Anderson before the estate was rented, proving the vault was opened from the inside.",
            "alternative_explanations": ["Routine bank security review", "Investigating prior burglary threats"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.80,
                "display_heuristic_impact": 0.80,
                "authoritative": False
            }
        },
        {
            "pattern_id": "pattern-vault-02",
            "proof_id": "proof-vault-02",
            "reveal_id": "reveal-masked-robbery-vault",
            "pattern_type": "PHYSICAL_IMPOSSIBILITY",
            "proof_type": "PHYSICAL_IMPOSSIBILITY",
            "title": "Dual-Key Lock Failure Analysis and Internal Access Sequence",
            "human_review_status": "APPROVED",
            "presentation_status": "PUBLIC",
            "trust_namespace": "ENGINE_INFERENCE",
            "trust_label": "Engine-supported interpretation (Rewatch Observation)",
            "evidence_chain": [
                {"scene_id": "scene-tbw-c004", "timestamp_ms": 480000},
                {"scene_id": "scene-tbw-c015", "timestamp_ms": 1780000}
            ],
            "observed_premises": [
                _build_premise("ev-c004-03", "scene-tbw-c004", 480000, "Police Report", "identifies lock intact", "The bank vault heavy steel door shows zero signs of external explosive force or forced entry."),
                _build_premise("ev-c015-01", "scene-tbw-c015", 1780000, "Detective Anderson", "withholds master key", "Detective Anderson keeps his hand in his coat pocket where the duplicate vault key was concealed.")
            ],
            "blind_explanation": "A master criminal cracked the uncrackable time-lock from outside.",
            "reveal_explanation": "The robbery was committed using pre-arranged insider keys rather than mechanical safecracking.",
            "alternative_explanations": ["Time lock mechanism failed spontaneously", "A locksmith was coerced"],
            "heuristic_display_metadata": {
                "display_salience_estimate": 0.82,
                "display_heuristic_impact": 0.82,
                "authoritative": False
            }
        }
    ]
}

# -------------------------------------------------------------
# -------------------------------------------------------------
# Canonical Frozen Proof Map (Normative Reframed Proofs Only: D4=0, D5=0 -> Empty)
# -------------------------------------------------------------
CANONICAL_PROOFS_MAP: Dict[str, List[Dict[str, Any]]] = {}

# Legacy moment ID aliases mapping to D3 RewatchPattern IDs for route/contract compatibility
LEGACY_MOMENT_ALIASES: Dict[str, str] = {
    "moment-anderson-knowledge-leak": "pattern-anderson-01",
    "moment-anderson-claim-action-conflict": "pattern-anderson-02",
    "moment-secret-room-fireplace": "pattern-secret-room-01",
}

# Known legacy fixture proof IDs for durable store reconciliation
LEGACY_FIXTURE_PROOF_IDS = {
    "proof-anderson-01",
    "proof-anderson-02",
    "proof-anderson-03",
    "proof-secret-room-01",
    "proof-secret-room-02",
    "proof-secret-room-03",
}


class RewatchPatternRepository:
    """
    Repository for D3 narrative patterns and rewatch observations.
    Non-normative: distinct from canonical Reframed Proofs.
    """
    @staticmethod
    def get_patterns_for_reveal(reveal_id: str) -> List[Dict[str, Any]]:
        return CANONICAL_PATTERNS_MAP.get(reveal_id, [])

    @staticmethod
    def get_pattern_by_id(pattern_id: str) -> Optional[Dict[str, Any]]:
        target_id = LEGACY_MOMENT_ALIASES.get(pattern_id, pattern_id)
        for rev_id, patterns in CANONICAL_PATTERNS_MAP.items():
            for p in patterns:
                pid = p.get("pattern_id") or p.get("proof_id", "")
                p_aliases = {pid, f"proof-{pid}", f"pattern-{pid}", pid.replace("pattern-", "proof-"), pid.replace("proof-", "pattern-"), pid.replace("pattern-", "moment-"), pid.replace("proof-", "moment-")}
                if target_id in p_aliases or pattern_id in p_aliases:
                    return p
        return None



def is_verified_canonical_proof(record: Any) -> bool:
    """
    Authoritative domain predicate for verified canonical proof eligibility (Sections 59 & 60).
    Requires:
    - Not a legacy fixture (checked by ID and legacy generation mode/provenance)
    - Normative proof type (KNOWLEDGE_LEAK, CLAIM_ACTION_CONFLICT, HIDDEN_PLAN_CHAIN)
    - Approved human review status (APPROVED or VERIFIED_CANONICAL)
    - Valid counterfactual validation results (with wrong_reveal_delta)
    - Trust namespace CANONICAL_VERIFIED
    """
    if record is None:
        return False

    proof_id = getattr(record, "proof_id", "") if not isinstance(record, dict) else record.get("proof_id", "")
    gen_mode = getattr(record, "generation_mode", "") if not isinstance(record, dict) else record.get("generation_mode", "")
    # Test data cannot become canon, even if an older bootstrap stamped approval.
    if any(marker in (gen_mode or "").upper() for marker in ("TEST_DOUBLE", "FIXTURE", "PREVIEW")):
        return False
    trust_label = getattr(record, "trust_label", "") if not isinstance(record, dict) else record.get("trust_label", "")
    trust_ns = getattr(record, "trust_namespace", "") if not isinstance(record, dict) else record.get("trust_namespace", "")
    hr_status = getattr(record, "human_review_status", "") if not isinstance(record, dict) else record.get("human_review_status", "")
    ptype = getattr(record, "proof_type", "") if not isinstance(record, dict) else record.get("proof_type", "")
    cf_results = getattr(record, "counterfactual_results", None) if not isinstance(record, dict) else record.get("counterfactual_results", None)

    is_legacy_fixture = (
        proof_id in LEGACY_FIXTURE_PROOF_IDS and
        (gen_mode in ("OFFLINE_CANONICAL_FIXTURE", "SEED_FIXTURE", "SUPERSEDED_FIXTURE", "DEVELOPMENT_PREVIEW", "") or
         "superseded" in (trust_label or "").lower())
    ) or gen_mode in ("OFFLINE_CANONICAL_FIXTURE", "SEED_FIXTURE", "SUPERSEDED_FIXTURE", "DEVELOPMENT_PREVIEW") or "superseded" in (trust_label or "").lower()

    has_valid_human_review = hr_status in ("APPROVED", "VERIFIED_CANONICAL")
    has_normative_proof_type = ptype in ("KNOWLEDGE_LEAK", "CLAIM_ACTION_CONFLICT", "HIDDEN_PLAN_CHAIN")
    has_cf_results = bool(cf_results and isinstance(cf_results, dict) and "wrong_reveal_delta" in cf_results)

    return bool(
        not is_legacy_fixture and
        has_valid_human_review and
        has_normative_proof_type and
        has_cf_results and
        trust_ns == "CANONICAL_VERIFIED"
    )


_DYNAMIC_PROOFS_BY_ID: Dict[str, Dict[str, Any]] = {}
_DYNAMIC_PROOFS_BY_REVEAL: Dict[str, List[Dict[str, Any]]] = {}


@synchronized
def register_dynamic_proof(proof_data: Dict[str, Any]) -> None:
    pid = proof_data["proof_id"]
    rev_id = proof_data["reveal_id"]
    existing = _DYNAMIC_PROOFS_BY_ID.get(pid)
    if existing is not None:
        if existing != proof_data:
            raise ValueError(f"Conflicting proof ID: {pid}")
        return
    if RewatchPatternRepository.get_pattern_by_id(pid):
        raise ValueError(f"Reserved proof ID: {pid}")
    _DYNAMIC_PROOFS_BY_ID[pid] = deepcopy(proof_data)
    _DYNAMIC_PROOFS_BY_REVEAL.setdefault(rev_id, []).append(deepcopy(proof_data))


@synchronized
def _dynamic_proof_payload(proof: Dict[str, Any], viewer: ViewerContext) -> Optional[Dict[str, Any]]:
    """Use the imported edition's own publication and spoiler contract for every read."""
    from src.reframe.catalog.service import catalog_service

    is_admin = bool(viewer.is_admin or viewer.is_moderator)
    approved = proof.get("human_review_status") in ("APPROVED", "VERIFIED_CANONICAL")
    if not is_admin and (not approved or proof.get("presentation_status") != "PUBLIC"):
        return None
    work_id = proof.get("work_id") or proof.get("movie_id")
    edition_id = proof.get("edition_id")
    entry = catalog_service.get_film_entry(work_id, edition_id)
    reveal = catalog_service.get_reveal_by_id(
        proof["reveal_id"], viewer, movie_id=work_id, edition_id=edition_id
    )
    cutoff = proof.get("spoiler_cutoff_ms")
    if (not entry or not reveal or type(cutoff) is not int
            or not 0 <= cutoff <= entry["runtime_ms"]):
        return None
    cutoff = max(cutoff, reveal.spoiler_cutoff_ms)
    scope = SpoilerScope(
        work_id=work_id, edition_id=edition_id, minimum_progress_ms=cutoff,
        required_reveal_ids=[proof["reveal_id"]], severity=proof.get("severity", "MAJOR"),
        safe_title=proof.get("safe_preview_title", "Narrative clue"),
        safe_preview=proof.get("safe_preview_summary", "Unlocked after viewing the reveal."),
    )
    visibility = analysis_visibility(scope, viewer)
    payload = deepcopy(proof)
    payload.update(
        work_id=work_id, movie_id=work_id, edition_id=edition_id,
        spoiler_cutoff_ms=cutoff, cutoff_ms=cutoff,
        asset_sha256=entry.get("canonical_asset_sha256"),
        dataset_version=entry["dataset_version"],
        blind_explanation=proof.get("blind_explanation", ""),
        reveal_explanation=proof.get("reveal_explanation") or proof.get("summary", ""),
        evidence_chain=proof.get("evidence_chain", []),
        alternative_explanations=proof.get("alternative_explanations", []),
        is_locked=visibility != SpoilerVisibility.VISIBLE,
        # Imported analysis is not promoted to canonical verification by a label in the bundle.
        verification_status="ENGINE_INFERENCE", trust_namespace="ENGINE_INFERENCE",
        proof_badge="Reviewed interpretation" if approved else "Rewatch Pattern",
    )
    return sanitize_payload_for_viewer(
        payload, visibility, scope.safe_title, scope.safe_preview,
        unlock_metadata={"minimum_progress_ms": cutoff, "required_reveal_ids": [proof["reveal_id"]]},
    )


class CanonicalProofStore:
    @staticmethod
    async def get_proof_by_id(
        db: AsyncSession,
        proof_id: str,
        viewer: ViewerContext
    ) -> Optional[Dict[str, Any]]:
        stmt = select(ProofRecord).where(ProofRecord.proof_id == proof_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()
        is_admin = bool(getattr(viewer, "is_admin", False) or getattr(viewer, "is_moderator", False))
        if not record:
            if proof_id in _DYNAMIC_PROOFS_BY_ID:
                return _dynamic_proof_payload(_DYNAMIC_PROOFS_BY_ID[proof_id], viewer)
            dev_pattern = RewatchPatternRepository.get_pattern_by_id(proof_id)
            if dev_pattern:
                hr_status = dev_pattern.get("human_review_status", "NOT_REVIEWED")
                pres_status = dev_pattern.get("presentation_status", "HIDDEN_FROM_PUBLIC")
                is_truly_approved = hr_status in ("APPROVED", "VERIFIED_CANONICAL")

                # Non-admin viewers must never access unapproved or hidden interpretations
                if not is_admin and (not is_truly_approved or pres_status == "HIDDEN_FROM_PUBLIC"):
                    return None

                from src.reframe.catalog.service import catalog_service
                reveal = catalog_service.get_reveal_by_id(dev_pattern["reveal_id"], viewer,
                    movie_id='the-bat-whispers-1930', edition_id='tbw-fullscreen-archive')
                if not reveal:
                    return None
                cutoff_ms = reveal.spoiler_cutoff_ms
                p_type = dev_pattern.get("pattern_type") or dev_pattern.get("proof_type", "MULTI_SCENE_PATTERN")
                gen_mode = dev_pattern.get("generation_mode", "DEVELOPMENT_PREVIEW")
                t_label = dev_pattern.get("trust_label", "Engine-supported interpretation")

                badge = f"Verified Clue ({p_type})" if is_truly_approved else "Rewatch Pattern"
                safe_title_text = f"Verified Narrative Clue ({p_type})" if is_truly_approved else f"Rewatch Observation ({p_type})"
                safe_preview_text = "Unlocked after viewing the reveal." if is_truly_approved else "Rewatch observation pending human review."

                scope = SpoilerScope(
                    work_id="the-bat-whispers-1930",
                    edition_id="tbw-fullscreen-archive",
                    minimum_progress_ms=cutoff_ms,
                    required_reveal_ids=[dev_pattern["reveal_id"]],
                    severity="ENDING",
                    safe_title=safe_title_text,
                    safe_preview=safe_preview_text
                )
                visibility = analysis_visibility(scope, viewer)
                disp_meta = dev_pattern.get("heuristic_display_metadata", {})
                raw_payload = {
                    "proof_id": proof_id,
                    "pattern_id": dev_pattern.get("pattern_id"),
                    "work_id": "the-bat-whispers-1930",
                    "movie_id": "the-bat-whispers-1930",
                    "edition_id": "tbw-fullscreen-archive",
                    "reveal_id": dev_pattern["reveal_id"],
                    "spoiler_cutoff_ms": cutoff_ms,
                    "cutoff_ms": cutoff_ms,
                    "proof_type": p_type,
                    "pattern_type": p_type,
                    "title": dev_pattern["title"],
                    "blind_explanation": dev_pattern["blind_explanation"],
                    "reveal_explanation": dev_pattern["reveal_explanation"],
                    "evidence_chain": dev_pattern["evidence_chain"],
                    "observed_premises": dev_pattern["observed_premises"],
                    "alternative_explanations": dev_pattern["alternative_explanations"],
                    "counterfactual_results": {},
                    "counterfactual_robustness": {"verdict": "NOT_VALIDATED"},
                    "proof_badge": badge,
                    "verification_status": "ENGINE_INFERENCE",
                    "proof_strength": disp_meta.get("display_salience_estimate", 0.85),
                    "fan_impact": disp_meta.get("display_heuristic_impact", 0.85),
                    "display_salience_estimate": disp_meta.get("display_salience_estimate", 0.85),
                    "display_heuristic_impact": disp_meta.get("display_heuristic_impact", 0.85),
                    "human_review_status": hr_status,
                    "presentation_status": pres_status,
                    "trust_namespace": dev_pattern.get("trust_namespace", "ENGINE_INFERENCE"),
                    "trust_label": t_label,
                    "generation_mode": gen_mode,
                    "live_analysis_pending_approval": not is_truly_approved,
                    "asset_sha256": "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
                    "correction_overlay_sha": "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
                    "evidence_bundle_hash": "default_evidence_bundle",
                    "model_id": "gemini-2.5-flash",
                    "prompt_hash": "prompt_v7_canonical",
                    "retrieval_config_hash": "5channel_retrieval_v7",
                    "proof_schema_version": "1.0.0",
                    "dataset_version": "v3",
                    "created_at": None
                }
                return sanitize_payload_for_viewer(
                    payload=raw_payload,
                    visibility=visibility,
                    safe_title=safe_title_text,
                    safe_preview=safe_preview_text,
                    unlock_metadata={
                        "minimum_progress_ms": cutoff_ms,
                        "required_reveal_ids": [dev_pattern["reveal_id"]],
                    }
                )
            return None

        is_admin = bool(getattr(viewer, "is_admin", False) or getattr(viewer, "is_moderator", False))
        # Filter out hidden proofs or unreviewed proofs for non-admin viewers
        is_verified_canon = is_verified_canonical_proof(record)
        if not is_admin and (record.presentation_status == "HIDDEN_FROM_PUBLIC"
                or not (is_verified_canon or is_public_ai_analysis(record))):
            return None

        from src.reframe.catalog.service import catalog_service
        reveal = catalog_service.get_reveal_by_id(
            record.reveal_id, viewer, movie_id=record.work_id, edition_id=record.edition_id
        )
        if not reveal:
            return None
        cutoff_ms = reveal.spoiler_cutoff_ms

        # Check verification eligibility for ProofRecord using authoritative predicate
        is_verified_canon = is_verified_canonical_proof(record)
        is_ai_analysis = is_public_ai_analysis(record)
        safe_title = (f"Verified Narrative Clue ({record.proof_type})" if is_verified_canon else
                      "AI Analysis · Spoiler protected" if is_ai_analysis else f"Development Pattern ({record.proof_type})")
        safe_preview = ("Unlock after viewing the reveal to read this interpretation." if is_ai_analysis else
                        "A key past clue unlocked after the reveal." if is_verified_canon else "Unlocked for administrative inspection.")

        scope = SpoilerScope(
            work_id=record.work_id,
            edition_id=record.edition_id,
            minimum_progress_ms=cutoff_ms,
            required_reveal_ids=[record.reveal_id],
            severity="ENDING",
            safe_title=safe_title,
            safe_preview=safe_preview,
        )
        visibility = analysis_visibility(scope, viewer)

        if is_verified_canon:
            cf_delta = record.counterfactual_results.get("wrong_reveal_delta", -0.85)
            raw_payload = {
                "proof_id": record.proof_id,
                "work_id": record.work_id,
                "movie_id": record.work_id,
                "edition_id": record.edition_id,
                "reveal_id": record.reveal_id,
                "spoiler_cutoff_ms": cutoff_ms,
                "cutoff_ms": cutoff_ms,
                "proof_type": record.proof_type,
                "title": record.title,
                "blind_explanation": record.blind_explanation,
                "reveal_explanation": record.reveal_explanation,
                "evidence_chain": record.evidence_chain,
                "observed_premises": record.observed_premises,
                "alternative_explanations": record.alternative_explanations,
                "counterfactual_results": record.counterfactual_results,
                "counterfactual_robustness": {
                    "reveal_swap_delta": cf_delta,
                    "verdict": "COUNTERFACTUALLY_ROBUST"
                },
                "proof_badge": f"Verified Canon ({record.proof_type})",
                "verification_status": "VERIFIED_CANON",
                "proof_strength": record.proof_strength,
                "fan_impact": record.fan_impact,
                "human_review_status": record.human_review_status,
                "presentation_status": record.presentation_status,
                "trust_namespace": record.trust_namespace,
                "trust_label": record.trust_label,
                "generation_mode": record.generation_mode,
                "asset_sha256": record.asset_sha256,
                "correction_overlay_sha": record.correction_overlay_sha,
                "evidence_bundle_hash": record.evidence_bundle_hash,
                "model_id": record.model_id,
                "prompt_hash": record.prompt_hash,
                "retrieval_config_hash": record.retrieval_config_hash,
                "proof_schema_version": record.proof_schema_version,
                "dataset_version": record.dataset_version,
                "created_at": record.created_at.isoformat() if record.created_at else None
            }
        else:
            raw_payload = {
                "proof_id": record.proof_id,
                "work_id": record.work_id,
                "movie_id": record.work_id,
                "edition_id": record.edition_id,
                "reveal_id": record.reveal_id,
                "spoiler_cutoff_ms": cutoff_ms,
                "cutoff_ms": cutoff_ms,
                "proof_type": record.proof_type,
                "title": record.title,
                "blind_explanation": record.blind_explanation,
                "reveal_explanation": record.reveal_explanation,
                "evidence_chain": record.evidence_chain,
                "observed_premises": record.observed_premises,
                "alternative_explanations": record.alternative_explanations,
                "counterfactual_results": {},
                "counterfactual_robustness": {
                    "verdict": "NOT_VALIDATED"
                },
                "proof_badge": "Rewatch Pattern",
                "verification_status": "ENGINE_INFERENCE",
                "display_salience_estimate": record.proof_strength,
                "display_heuristic_impact": record.fan_impact,
                "proof_strength": record.proof_strength,
                "fan_impact": record.fan_impact,
                "human_review_status": record.human_review_status,
                "presentation_status": record.presentation_status,
                "trust_namespace": "ENGINE_INFERENCE",
                "trust_label": record.trust_label if "superseded" in (record.trust_label or "").lower() else "Engine-supported interpretation",
                "generation_mode": record.generation_mode,
                "asset_sha256": record.asset_sha256,
                "correction_overlay_sha": record.correction_overlay_sha,
                "evidence_bundle_hash": record.evidence_bundle_hash,
                "model_id": record.model_id,
                "prompt_hash": record.prompt_hash,
                "retrieval_config_hash": record.retrieval_config_hash,
                "proof_schema_version": record.proof_schema_version,
                "dataset_version": record.dataset_version,
                "created_at": record.created_at.isoformat() if record.created_at else None
            }

        return sanitize_payload_for_viewer(
            payload=label_ai_analysis(raw_payload, record),
            visibility=visibility,
            safe_title=safe_title,
            safe_preview=safe_preview,
            unlock_metadata={
                "minimum_progress_ms": cutoff_ms,
                "required_reveal_ids": [record.reveal_id],
            }
        )

    @staticmethod
    async def get_proofs_for_reveal(
        db: AsyncSession,
        reveal_id: str,
        viewer: ViewerContext
    ) -> List[Dict[str, Any]]:
        stmt = (
            select(ProofRecord)
            .where(ProofRecord.reveal_id == reveal_id)
            .order_by(ProofRecord.fan_impact.desc())
        )
        res = await db.execute(stmt)
        records = res.scalars().all()

        from src.reframe.catalog.service import catalog_service
        reveal_obj = catalog_service.get_reveal_by_id(reveal_id, viewer)
        if not reveal_obj:
            return []
        cutoff_ms = reveal_obj.spoiler_cutoff_ms
        work_id = reveal_obj.work_id
        edition_id = reveal_obj.edition_id

        scope = SpoilerScope(
            work_id=work_id,
            edition_id=edition_id,
            minimum_progress_ms=cutoff_ms,
            required_reveal_ids=[reveal_id],
            severity="ENDING",
            safe_title="Verified Clue",
            safe_preview="Unlocked after viewing the reveal."
        )
        visibility = analysis_visibility(scope, viewer)

        out = []
        is_admin = bool(getattr(viewer, "is_admin", False) or getattr(viewer, "is_moderator", False))
        for r in records:
            if r.work_id != work_id or r.edition_id != edition_id:
                continue
            # Filter out hidden proofs for non-admin viewers
            if r.presentation_status == "HIDDEN_FROM_PUBLIC" and not is_admin:
                continue

            is_verified_canon = is_verified_canonical_proof(r)

            # Public viewers only receive verified canonical proofs
            if not is_admin and not is_verified_canon and not is_public_ai_analysis(r):
                continue

            if is_verified_canon:
                cf_delta = r.counterfactual_results.get("wrong_reveal_delta", -0.85)
                raw = {
                    "proof_id": r.proof_id,
                    "work_id": r.work_id,
                    "movie_id": r.work_id,
                    "edition_id": r.edition_id,
                    "reveal_id": r.reveal_id,
                    "spoiler_cutoff_ms": cutoff_ms,
                    "cutoff_ms": cutoff_ms,
                    "proof_type": r.proof_type,
                    "title": r.title,
                    "blind_explanation": r.blind_explanation,
                    "reveal_explanation": r.reveal_explanation,
                    "evidence_chain": r.evidence_chain,
                    "observed_premises": r.observed_premises,
                    "alternative_explanations": r.alternative_explanations,
                    "counterfactual_results": r.counterfactual_results,
                    "counterfactual_robustness": {
                        "reveal_swap_delta": cf_delta,
                        "verdict": "COUNTERFACTUALLY_ROBUST"
                    },
                    "proof_badge": f"Verified Canon ({r.proof_type})",
                    "verification_status": "VERIFIED_CANON",
                    "proof_strength": r.proof_strength,
                    "fan_impact": r.fan_impact,
                    "human_review_status": r.human_review_status,
                    "presentation_status": r.presentation_status,
                    "trust_namespace": r.trust_namespace,
                    "trust_label": r.trust_label,
                    "generation_mode": r.generation_mode,
                    "asset_sha256": r.asset_sha256,
                    "correction_overlay_sha": r.correction_overlay_sha,
                    "evidence_bundle_hash": r.evidence_bundle_hash,
                    "model_id": r.model_id,
                    "prompt_hash": r.prompt_hash,
                    "retrieval_config_hash": r.retrieval_config_hash,
                    "proof_schema_version": r.proof_schema_version,
                    "dataset_version": r.dataset_version,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }
            else:
                raw = {
                    "proof_id": r.proof_id,
                    "work_id": r.work_id,
                    "movie_id": r.work_id,
                    "edition_id": r.edition_id,
                    "reveal_id": r.reveal_id,
                    "spoiler_cutoff_ms": cutoff_ms,
                    "cutoff_ms": cutoff_ms,
                    "proof_type": r.proof_type,
                    "title": r.title,
                    "blind_explanation": r.blind_explanation,
                    "reveal_explanation": r.reveal_explanation,
                    "evidence_chain": r.evidence_chain,
                    "observed_premises": r.observed_premises,
                    "alternative_explanations": r.alternative_explanations,
                    "counterfactual_results": {},
                    "counterfactual_robustness": {
                        "verdict": "NOT_VALIDATED"
                    },
                    "proof_badge": "Rewatch Pattern",
                    "verification_status": "ENGINE_INFERENCE",
                    "display_salience_estimate": r.proof_strength,
                    "display_heuristic_impact": r.fan_impact,
                    "proof_strength": r.proof_strength,
                    "fan_impact": r.fan_impact,
                    "human_review_status": r.human_review_status,
                    "presentation_status": r.presentation_status,
                    "trust_namespace": "ENGINE_INFERENCE",
                    "trust_label": r.trust_label if "superseded" in (r.trust_label or "").lower() else "Engine-supported interpretation",
                    "generation_mode": r.generation_mode,
                    "live_analysis_pending_approval": r.human_review_status not in ("APPROVED", "VERIFIED_CANONICAL"),
                    "asset_sha256": r.asset_sha256,
                    "correction_overlay_sha": r.correction_overlay_sha,
                    "evidence_bundle_hash": r.evidence_bundle_hash,
                    "model_id": r.model_id,
                    "prompt_hash": r.prompt_hash,
                    "retrieval_config_hash": r.retrieval_config_hash,
                    "proof_schema_version": r.proof_schema_version,
                    "dataset_version": r.dataset_version,
                    "created_at": r.created_at.isoformat() if r.created_at else None
                }

            sanitized = sanitize_payload_for_viewer(
                payload=label_ai_analysis(raw, r),
                visibility=visibility,
                safe_title=f"Verified Clue ({r.proof_type})" if is_verified_canon else "AI Analysis · Spoiler protected",
                safe_preview="Unlock after viewing the reveal to read this interpretation.",
                unlock_metadata={
                    "minimum_progress_ms": cutoff_ms,
                    "required_reveal_ids": [reveal_id],
                }
            )
            out.append(sanitized)

        is_admin = bool(getattr(viewer, "is_admin", False) or getattr(viewer, "is_moderator", False))
        seen_ids = {item.get("proof_id") for item in out}
        if is_admin or settings.PHASE1_SUBMISSION_PROFILE_ENABLED:
            dev_patterns = RewatchPatternRepository.get_patterns_for_reveal(reveal_id)
            is_p1 = settings.PHASE1_SUBMISSION_PROFILE_ENABLED
            for p in dev_patterns:
                pid = p.get("proof_id") or p.get("pattern_id")
                if pid in seen_ids:
                    continue
                disp_meta = p.get("heuristic_display_metadata", {})
                p_type = p.get("proof_type") or p.get("pattern_type")
                hr_status = p.get("human_review_status", "NOT_REVIEWED")
                pres_status = p.get("presentation_status", "HIDDEN_FROM_PUBLIC")
                gen_mode = p.get("generation_mode", "DEVELOPMENT_PREVIEW")
                t_label = p.get("trust_label", "Engine-supported interpretation")
                is_truly_approved = hr_status in ("APPROVED", "VERIFIED_CANONICAL")

                # Epistemic separation: unreviewed/hidden dev patterns cannot be exposed to non-admins
                if not is_admin and (not is_truly_approved or pres_status == "HIDDEN_FROM_PUBLIC"):
                    continue

                badge = f"Verified Clue ({p_type})" if is_truly_approved else "Rewatch Pattern"
                safe_title_text = f"Verified Narrative Clue ({p_type})" if is_truly_approved else f"Rewatch Observation ({p_type})"
                safe_preview_text = "Unlocked after viewing the reveal." if is_truly_approved else "Rewatch observation pending human review."

                raw = {
                    "proof_id": pid,
                    "work_id": "the-bat-whispers-1930",
                    "movie_id": "the-bat-whispers-1930",
                    "edition_id": "tbw-fullscreen-archive",
                    "reveal_id": reveal_id,
                    "spoiler_cutoff_ms": cutoff_ms,
                    "cutoff_ms": cutoff_ms,
                    "proof_type": p_type,
                    "title": p["title"],
                    "blind_explanation": p["blind_explanation"],
                    "reveal_explanation": p["reveal_explanation"],
                    "evidence_chain": p["evidence_chain"],
                    "observed_premises": p["observed_premises"],
                    "alternative_explanations": p["alternative_explanations"],
                    "counterfactual_results": p.get("counterfactual_results", {}),
                    "proof_badge": badge,
                    "verification_status": "ENGINE_INFERENCE",
                    "proof_strength": disp_meta.get("display_salience_estimate", 0.85),
                    "fan_impact": disp_meta.get("display_heuristic_impact", 0.85),
                    "human_review_status": hr_status,
                    "presentation_status": pres_status,
                    "trust_namespace": p.get("trust_namespace", "ENGINE_INFERENCE"),
                    "trust_label": t_label,
                    "generation_mode": gen_mode,
                    "live_analysis_pending_approval": not is_truly_approved,
                    "asset_sha256": "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
                    "correction_overlay_sha": "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
                    "evidence_bundle_hash": "default_evidence_bundle",
                    "model_id": "gemini-2.5-flash",
                    "prompt_hash": "prompt_v7_canonical",
                    "retrieval_config_hash": "5channel_retrieval_v7",
                    "proof_schema_version": "1.0.0",
                    "dataset_version": "v3",
                    "created_at": None
                }
                sanitized = sanitize_payload_for_viewer(
                    payload=raw,
                    visibility=visibility,
                    safe_title=safe_title_text,
                    safe_preview=safe_preview_text,
                    unlock_metadata={
                        "minimum_progress_ms": cutoff_ms,
                        "required_reveal_ids": [reveal_id],
                    }
                )
                out.append(sanitized)
                seen_ids.add(pid)

        # Collect dynamic proofs registered for this reveal
        if reveal_id in _DYNAMIC_PROOFS_BY_REVEAL:
            for p_dict in _DYNAMIC_PROOFS_BY_REVEAL[reveal_id]:
                pid = p_dict["proof_id"]
                if pid not in seen_ids:
                    payload = _dynamic_proof_payload(p_dict, viewer)
                    if payload is not None:
                        out.append(payload)
                        seen_ids.add(pid)

        return out

    @staticmethod
    async def save_canonical_proof(
        db: AsyncSession,
        proof_data: Dict[str, Any],
        work_id: str,
        edition_id: str,
        reveal_id: str
    ) -> ProofRecord:
        proof_id = proof_data["proof_id"]
        computed_cache_key = generate_proof_cache_key(
            work_id=work_id,
            edition_id=edition_id,
            reveal_id=reveal_id,
            dataset_version=proof_data.get("dataset_version", "v3"),
            evidence_bundle_hash=compute_content_hash(proof_data.get("observed_premises", []))
        )

        stmt = select(ProofRecord).where(ProofRecord.proof_id == proof_id)
        res = await db.execute(stmt)
        record = res.scalar_one_or_none()

        hr_status = proof_data.get("human_review_status", "NOT_REVIEWED")
        raw_gen_mode = proof_data.get("generation_mode") or ""
        gen_mode = raw_gen_mode or "OFFLINE_CANONICAL_FIXTURE"

        # Invariant: Unreviewed material, offline fixtures, or test doubles MUST be HIDDEN_FROM_PUBLIC.
        # Explicit presentation_status="PUBLIC" is rejected/forced to HIDDEN_FROM_PUBLIC if not approved or if fixture.
        is_fixture = any(marker in raw_gen_mode.upper() for marker in ("TEST_DOUBLE", "FIXTURE", "PREVIEW"))
        if hr_status not in ("APPROVED", "VERIFIED_CANONICAL") or is_fixture:
            pres_status = "HIDDEN_FROM_PUBLIC"
        else:
            pres_status = proof_data.get("presentation_status") or "PUBLIC"

        if not record:
            record = ProofRecord(
                id=uuid.uuid4(),
                proof_id=proof_id,
                work_id=work_id,
                edition_id=edition_id,
                dataset_version=proof_data.get("dataset_version", "v3"),
                reveal_id=reveal_id,
                proof_type=proof_data["proof_type"],
                title=proof_data["title"],
                blind_explanation=proof_data["blind_explanation"],
                reveal_explanation=proof_data["reveal_explanation"],
                evidence_chain=proof_data["evidence_chain"],
                observed_premises=proof_data["observed_premises"],
                alternative_explanations=proof_data["alternative_explanations"],
                counterfactual_results=proof_data["counterfactual_results"],
                proof_strength=proof_data.get("proof_strength", 0.90),
                fan_impact=proof_data.get("fan_impact", 0.85),
                human_review_status=hr_status,
                presentation_status=pres_status,
                trust_namespace=proof_data.get("trust_namespace", "ENGINE_INFERENCE"),
                trust_label=proof_data.get("trust_label", "Engine-supported interpretation"),
                generation_mode=proof_data.get("generation_mode", "OFFLINE_CANONICAL_FIXTURE"),
                asset_sha256=proof_data.get("asset_sha256", "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"),
                correction_overlay_sha=proof_data.get("correction_overlay_sha", "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"),
                evidence_bundle_hash=proof_data.get("evidence_bundle_hash", "default_evidence_bundle"),
                model_id=proof_data.get("model_id", "gemini-2.5-flash"),
                prompt_hash=proof_data.get("prompt_hash", "prompt_v7_canonical"),
                retrieval_config_hash=proof_data.get("retrieval_config_hash", "5channel_retrieval_v7"),
                proof_schema_version=proof_data.get("proof_schema_version", "1.0.0"),
                cache_key=computed_cache_key,
                created_at=datetime.now(timezone.utc)
            )
            db.add(record)
        else:
            record.title = proof_data["title"]
            record.blind_explanation = proof_data["blind_explanation"]
            record.reveal_explanation = proof_data["reveal_explanation"]
            record.evidence_chain = proof_data["evidence_chain"]
            record.observed_premises = proof_data["observed_premises"]
            record.alternative_explanations = proof_data["alternative_explanations"]
            record.counterfactual_results = proof_data["counterfactual_results"]
            record.proof_strength = proof_data.get("proof_strength", 0.90)
            record.fan_impact = proof_data.get("fan_impact", 0.85)
            record.human_review_status = hr_status
            record.presentation_status = pres_status
            record.trust_namespace = proof_data.get("trust_namespace", record.trust_namespace)
            record.trust_label = proof_data.get("trust_label", record.trust_label)
            record.generation_mode = proof_data.get("generation_mode", record.generation_mode)
            record.asset_sha256 = proof_data.get("asset_sha256", record.asset_sha256)
            record.correction_overlay_sha = proof_data.get("correction_overlay_sha", record.correction_overlay_sha)
            record.evidence_bundle_hash = proof_data.get("evidence_bundle_hash", record.evidence_bundle_hash)
            record.model_id = proof_data.get("model_id", record.model_id)
            record.prompt_hash = proof_data.get("prompt_hash", record.prompt_hash)
            record.retrieval_config_hash = proof_data.get("retrieval_config_hash", record.retrieval_config_hash)
            record.proof_schema_version = proof_data.get("proof_schema_version", record.proof_schema_version)
            record.cache_key = computed_cache_key

        await db.flush()
        return record

    @staticmethod
    async def reconcile_superseded_fixture_proofs(db: AsyncSession) -> int:
        """
        Reconciles superseded legacy ProofRecord fixture rows in the database.
        Marks known legacy fixture records as HIDDEN_FROM_PUBLIC, NEEDS_CORRECTION,
        and ENGINE_INFERENCE so they are never returned as VERIFIED_CANON to normal viewers.
        Does NOT modify or delete arbitrary user or live-generated proofs.
        """
        stmt = select(ProofRecord).where(ProofRecord.proof_id.in_(LEGACY_FIXTURE_PROOF_IDS))
        res = await db.execute(stmt)
        legacy_records = res.scalars().all()
        reconciled_count = 0
        for rec in legacy_records:
            if (
                rec.proof_id in LEGACY_FIXTURE_PROOF_IDS
                and rec.generation_mode in ("OFFLINE_CANONICAL_FIXTURE", "SEED_FIXTURE", "DEVELOPMENT_PREVIEW", "SUPERSEDED_FIXTURE", "")
            ):
                rec.presentation_status = "HIDDEN_FROM_PUBLIC"
                rec.human_review_status = "NEEDS_CORRECTION"
                rec.trust_namespace = "ENGINE_INFERENCE"
                rec.trust_label = "Engine interpretation (Superseded legacy development fixture)"
                reconciled_count += 1
        if reconciled_count > 0:
            await db.flush()
        return reconciled_count

    @staticmethod
    async def seed_canonical_proofs_if_empty(db: AsyncSession, work_id: str = "the-bat-whispers-1930", edition_id: str = "tbw-fullscreen-archive"):
        """Reconciles legacy fixtures and seeds normative canonical proofs if any are defined."""
        reconciled_count = await CanonicalProofStore.reconcile_superseded_fixture_proofs(db)

        seeded_count = 0
        for reveal_id, proofs in CANONICAL_PROOFS_MAP.items():
            for p in proofs:
                await CanonicalProofStore.save_canonical_proof(
                    db=db,
                    proof_data=p,
                    work_id=work_id,
                    edition_id=edition_id,
                    reveal_id=reveal_id
                )
                seeded_count += 1
        await db.commit()
        logger.info(
            "canonical_proofs_reconciliation_completed",
            work_id=work_id,
            legacy_fixtures_reconciled=reconciled_count,
            total_proofs_seeded=seeded_count
        )

    # Alias for compatibility with tests
    seed_canonical_proofs = seed_canonical_proofs_if_empty


canonical_proof_store = CanonicalProofStore()
