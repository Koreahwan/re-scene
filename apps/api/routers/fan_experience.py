"""
Reframe V7 Fan Experience API Router (Quick Wow, Rewatch Sync, Trust Label, Deep Dive)
Projects dynamically over canonical proof store (CANONICAL_PROOFS_MAP, ProofRecord, and Rewatch Patterns).
Zero Paid Model Calls.
"""
from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import structlog

from src.reframe.shared.database import get_db
from src.reframe.identity.auth import get_current_viewer, ViewerContext
from src.reframe.evidence.adapter import v3_adapter
from src.reframe.proof.store import CANONICAL_PROOFS_MAP, CANONICAL_PATTERNS_MAP, LEGACY_MOMENT_ALIASES, LEGACY_FIXTURE_PROOF_IDS, is_verified_canonical_proof
from src.reframe.proof.models import ProofRecord
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.spoiler.policy import evaluate_spoiler_visibility, sanitize_payload_for_viewer, SpoilerVisibility
from src.reframe.spoiler.analysis_boundary import analysis_visibility, retrospective_cutoff

logger = structlog.get_logger(__name__)

def private_moment_response(response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    response.headers['Vary'] = 'Cookie, Authorization'


router = APIRouter(prefix="/moments", tags=["Fan Experience"], dependencies=[Depends(private_moment_response)])


def moment_visibility(scope, viewer):
    from src.reframe.catalog.service import catalog_service
    entry = catalog_service.get_film_entry(scope.work_id, scope.edition_id) or {}
    scope.minimum_progress_ms = retrospective_cutoff(scope.work_id,scope.edition_id,
        scope.minimum_progress_ms,entry.get('runtime_ms'))
    return analysis_visibility(scope,viewer)


async def _resolve_moment(
    moment_id: str,
    viewer: Optional[ViewerContext] = None,
    db: Optional[AsyncSession] = None
) -> Dict[str, Any]:
    """
    Dynamically projects a moment from CANONICAL_PROOFS_MAP, CANONICAL_PATTERNS_MAP, or durable ProofRecord in DB.
    Enforces strict access control for HIDDEN_FROM_PUBLIC patterns (non-admins receive 404).
    Legacy moment aliases are mapped directly to corresponding RewatchPattern entries.
    """
    is_admin = bool(viewer and (getattr(viewer, "is_admin", False) or getattr(viewer, "is_moderator", False)))

    # 1. Check CANONICAL_PROOFS_MAP (Verified Proofs only)
    for rev_id, proofs in CANONICAL_PROOFS_MAP.items():
        for p in proofs:
            p_ids = {p.get("proof_id", ""), p.get("pattern_id", "")} - {""}
            match = False
            for pid in list(p_ids):
                if moment_id in (pid, f"moment-{pid}", pid.replace("proof-", "moment-").replace("pattern-", "moment-")):
                    match = True
                    break
            if match:
                pres_status = p.get("presentation_status", "PUBLIC")
                if viewer is not None and not is_admin and pres_status == "HIDDEN_FROM_PUBLIC":
                    raise HTTPException(status_code=404, detail=f"Reframed moment '{moment_id}' not found")
                sc_id = p["evidence_chain"][0]["scene_id"] if p.get("evidence_chain") else "scene-tbw-c017"
                ref_ts = p["evidence_chain"][0]["timestamp_ms"] if p.get("evidence_chain") else 2010000
                reveal = v3_adapter.get_reveal(rev_id)
                rev_ts = reveal.timestamp_ms if reveal else 4860000
                return {
                    "moment_id": moment_id,
                    "content_kind": "VERIFIED_PROOF",
                    "presentation_status": pres_status,
                    "verification_status": "VERIFIED_CANON",
                    "proof_badge": f"Verified Canon ({p.get('proof_type', 'VERIFIED_PROOF')})",
                    "work_id": "the-bat-whispers-1930",
                    "edition_id": "tbw-fullscreen-archive",
                    "reveal_id": rev_id,
                    "proof_type": p.get("proof_type", "VERIFIED_PROOF"),
                    "title": p["title"],
                    "scene_id": sc_id,
                    "reframed_timestamp_ms": ref_ts,
                    "reveal_timestamp_ms": rev_ts,
                    "before_understanding": p["blind_explanation"],
                    "after_understanding": p["reveal_explanation"],
                    "clue_description": p["observed_premises"][0].get("fact", "") if p.get("observed_premises") else "",
                    "evidence_frame_ids": ["tbw_v3_frame_0012"],
                    "graph_path": [sc_id, "EXPLAINS", rev_id],
                    "counterfactual_delta": p.get("counterfactual_results", {}).get("wrong_reveal_delta", -0.85),
                    "counterfactual_robustness": {
                        "reveal_swap_delta": p.get("counterfactual_results", {}).get("wrong_reveal_delta", -0.85),
                        "verdict": "COUNTERFACTUALLY_ROBUST"
                    },
                    "proof_strength": p.get("proof_strength", 0.90),
                    "fan_impact": p.get("fan_impact", 0.88),
                    "human_review_status": p.get("human_review_status", "APPROVED"),
                    "trust_namespace": p.get("trust_namespace", "CANONICAL_VERIFIED"),
                    "trust_label": p.get("trust_label", "Verified Canon")
                }

    # 2. Check CANONICAL_PATTERNS_MAP (D3 Non-Normative Engine Inference) & Legacy Moment Aliases
    target_pattern_id = LEGACY_MOMENT_ALIASES.get(moment_id, moment_id)
    for rev_id, patterns in CANONICAL_PATTERNS_MAP.items():
        for p in patterns:
            p_ids = {p.get("pattern_id", ""), p.get("proof_id", "")} - {""}
            match = False
            for pid in list(p_ids):
                p_aliases = {
                    pid,
                    f"moment-{pid}",
                    f"proof-{pid}",
                    f"pattern-{pid}",
                    pid.replace("pattern-", "moment-").replace("proof-", "moment-"),
                    pid.replace("moment-", "pattern-").replace("proof-", "pattern-")
                }
                if target_pattern_id in p_aliases or moment_id in p_aliases:
                    match = True
                    break
            if match:
                pres_status = p.get("presentation_status", "HIDDEN_FROM_PUBLIC")
                hr_status = p.get("human_review_status", "NOT_REVIEWED")
                if viewer is not None and not is_admin and (pres_status == "HIDDEN_FROM_PUBLIC" or hr_status not in ("APPROVED", "VERIFIED_CANONICAL")):
                    raise HTTPException(status_code=404, detail=f"Reframed moment '{moment_id}' not found")

                sc_id = p["evidence_chain"][0]["scene_id"] if p.get("evidence_chain") else "scene-tbw-c017"
                ref_ts = p["evidence_chain"][0]["timestamp_ms"] if p.get("evidence_chain") else 2010000
                reveal = v3_adapter.get_reveal(rev_id)
                rev_ts = reveal.timestamp_ms if reveal else 4860000
                disp_meta = p.get("heuristic_display_metadata", {})
                frame_ids = []
                for prem in p.get("observed_premises", []):
                    f_list = prem.get("evidence_frame_ids")
                    if f_list:
                        frame_ids.extend(f_list)
                    else:
                        ev = v3_adapter.get_event(prem.get("event_id"))
                        if ev and ev.evidence_frame_ids:
                            frame_ids.extend(ev.evidence_frame_ids)
                if not frame_ids:
                    frame_ids = ["tbw_v3_frame_0012"]

                return {
                    "moment_id": moment_id,
                    "content_kind": "REWATCH_PATTERN",
                    "presentation_status": pres_status,
                    "verification_status": "ENGINE_INFERENCE",
                    "proof_badge": "Verified Clue" if p.get("human_review_status") == "APPROVED" else "Rewatch Pattern",
                    "work_id": "the-bat-whispers-1930",
                    "edition_id": "tbw-fullscreen-archive",
                    "reveal_id": rev_id,
                    "proof_type": p.get("pattern_type") or p.get("proof_type", "MULTI_SCENE_PATTERN"),
                    "title": p["title"],
                    "scene_id": sc_id,
                    "reframed_timestamp_ms": ref_ts,
                    "reveal_timestamp_ms": rev_ts,
                    "before_understanding": p["blind_explanation"],
                    "after_understanding": p["reveal_explanation"],
                    "clue_description": p["observed_premises"][0].get("fact", "") if p.get("observed_premises") else "",
                    "evidence_frame_ids": frame_ids,
                    "frame_url": f"/api/v1/media/the-bat-whispers-1930/tbw-fullscreen-archive/frames/{frame_ids[0]}",
                    "graph_path": [sc_id, "EXPLAINS", rev_id],
                    "counterfactual_delta": None,
                    "counterfactual_robustness": {
                        "verdict": "NOT_VALIDATED"
                    },
                    "display_salience_estimate": disp_meta.get("display_salience_estimate", 0.85),
                    "display_heuristic_impact": disp_meta.get("display_heuristic_impact", 0.85),
                    "human_review_status": p.get("human_review_status", "NOT_REVIEWED"),
                    "trust_namespace": p.get("trust_namespace", "ENGINE_INFERENCE"),
                    "trust_label": p.get("trust_label", "Engine-supported interpretation")
                }

    # 3. Check DB ProofRecord
    if db:
        stmt = select(ProofRecord).where(
            (ProofRecord.proof_id == moment_id) |
            (ProofRecord.proof_id == moment_id.replace("moment-", "proof-"))
        )
        res = await db.execute(stmt)
        rec = res.scalar_one_or_none()
        if rec:
            pres_status = rec.presentation_status
            if viewer is not None and not is_admin and pres_status == "HIDDEN_FROM_PUBLIC":
                raise HTTPException(status_code=404, detail=f"Reframed moment '{moment_id}' not found")
            sc_id = rec.evidence_chain[0]["scene_id"] if rec.evidence_chain else "scene-tbw-c017"
            ref_ts = rec.evidence_chain[0]["timestamp_ms"] if rec.evidence_chain else 2010000
            reveal = v3_adapter.get_reveal(rec.reveal_id)
            rev_ts = reveal.timestamp_ms if reveal else 4860000

            # Check verification eligibility for ProofRecord using authoritative predicate
            is_verified_canon = is_verified_canonical_proof(rec)

            if is_verified_canon:
                cf_delta = rec.counterfactual_results.get("wrong_reveal_delta", -0.85)
                return {
                    "moment_id": moment_id,
                    "content_kind": "VERIFIED_PROOF",
                    "presentation_status": pres_status,
                    "verification_status": "VERIFIED_CANON",
                    "proof_badge": f"Verified Canon ({rec.proof_type})",
                    "work_id": rec.work_id,
                    "edition_id": rec.edition_id,
                    "reveal_id": rec.reveal_id,
                    "proof_type": rec.proof_type,
                    "title": rec.title,
                    "scene_id": sc_id,
                    "reframed_timestamp_ms": ref_ts,
                    "reveal_timestamp_ms": rev_ts,
                    "before_understanding": rec.blind_explanation,
                    "after_understanding": rec.reveal_explanation,
                    "clue_description": rec.observed_premises[0].get("fact", "") if rec.observed_premises else "",
                    "evidence_frame_ids": ["tbw_v3_frame_0012"],
                    "graph_path": [sc_id, "EXPLAINS", rec.reveal_id],
                    "counterfactual_delta": cf_delta,
                    "counterfactual_robustness": {
                        "reveal_swap_delta": cf_delta,
                        "verdict": "COUNTERFACTUALLY_ROBUST"
                    },
                    "proof_strength": rec.proof_strength,
                    "fan_impact": rec.fan_impact,
                    "human_review_status": rec.human_review_status,
                    "trust_namespace": rec.trust_namespace,
                    "trust_label": rec.trust_label
                }
            else:
                return {
                    "moment_id": moment_id,
                    "content_kind": "REWATCH_PATTERN",
                    "presentation_status": pres_status,
                    "verification_status": "ENGINE_INFERENCE",
                    "proof_badge": "Rewatch Pattern",
                    "work_id": rec.work_id,
                    "edition_id": rec.edition_id,
                    "reveal_id": rec.reveal_id,
                    "proof_type": rec.proof_type,
                    "title": rec.title,
                    "scene_id": sc_id,
                    "reframed_timestamp_ms": ref_ts,
                    "reveal_timestamp_ms": rev_ts,
                    "before_understanding": rec.blind_explanation,
                    "after_understanding": rec.reveal_explanation,
                    "clue_description": rec.observed_premises[0].get("fact", "") if rec.observed_premises else "",
                    "evidence_frame_ids": ["tbw_v3_frame_0012"],
                    "graph_path": [sc_id, "EXPLAINS", rec.reveal_id],
                    "counterfactual_delta": None,
                    "counterfactual_robustness": {
                        "verdict": "NOT_VALIDATED"
                    },
                    "display_salience_estimate": rec.proof_strength,
                    "display_heuristic_impact": rec.fan_impact,
                    "human_review_status": rec.human_review_status,
                    "trust_namespace": "ENGINE_INFERENCE",
                    "trust_label": rec.trust_label if "superseded" in (rec.trust_label or "").lower() else "Engine-supported interpretation"
                }

    raise HTTPException(status_code=404, detail=f"Reframed moment '{moment_id}' not found")


@router.get("/{moment_id}/quick-wow")
async def get_quick_wow(
    moment_id: str,
    viewer: ViewerContext = Depends(get_current_viewer),
    db: AsyncSession = Depends(get_db)
):
    """
    1. Quick Wow: Mobile-first visual contrast card.
    """
    moment = await _resolve_moment(moment_id, viewer, db)

    scope = SpoilerScope(
        work_id=moment["work_id"],
        edition_id=moment["edition_id"],
        minimum_progress_ms=moment["reveal_timestamp_ms"],
        required_reveal_ids=[moment["reveal_id"]],
        severity="ENDING",
        safe_title="Crucial Reframed Moment",
        safe_preview="A key past scene that completely shifts meaning after the ending reveal."
    )
    visibility = moment_visibility(scope, viewer)

    is_pattern = moment.get("content_kind") == "REWATCH_PATTERN"
    raw_payload = {
        "moment_id": moment["moment_id"],
        "title": moment["title"],
        "proof_type": moment["proof_type"],
        "before_understanding": moment["before_understanding"],
        "after_understanding": moment["after_understanding"],
        "reframed_timestamp_ms": moment["reframed_timestamp_ms"],
        "evidence_frame_url": f"/media/frames/{moment['evidence_frame_ids'][0]}.jpg" if moment.get("evidence_frame_ids") else None,
        "proof_badge": moment.get("proof_badge", "Rewatch Pattern" if is_pattern else f"Verified Canon ({moment['proof_type']})"),
        "trust_namespace": moment.get("trust_namespace", "ENGINE_INFERENCE"),
        "trust_label": moment.get("trust_label", "Engine-supported interpretation"),
        "display_heuristic_impact": moment.get("display_heuristic_impact", 0.85) if is_pattern else moment.get("fan_impact", 0.85),
    }
    if not is_pattern:
        raw_payload["fan_impact"] = moment.get("fan_impact", 0.85)

    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=visibility,
        safe_title="Classified Reframed Clue",
        safe_preview="Unlock by completing the movie reveal."
    )
    return {"status": "SUCCESS", "data": sanitized}


@router.get("/{moment_id}/rewatch-sync")
async def get_rewatch_sync(
    moment_id: str,
    viewer: ViewerContext = Depends(get_current_viewer),
    db: AsyncSession = Depends(get_db)
):
    """
    2. Rewatch Sync: Dual-stream synchronized video player cuepoints and A/B loops.
    """
    moment = await _resolve_moment(moment_id, viewer, db)

    scope = SpoilerScope(
        work_id=moment["work_id"],
        edition_id=moment["edition_id"],
        minimum_progress_ms=moment["reveal_timestamp_ms"],
        required_reveal_ids=[moment["reveal_id"]],
        severity="ENDING"
    )
    visibility = moment_visibility(scope, viewer)

    raw_payload = {
        "moment_id": moment["moment_id"],
        "title": moment["title"],
        "work_id": moment["work_id"],
        "edition_id": moment["edition_id"],
        "reframed_scene": {
            "scene_id": moment["scene_id"],
            "start_ms": moment["reframed_timestamp_ms"],
            "end_ms": moment["reframed_timestamp_ms"] + 30000,
            "loop_segment_ms": [moment["reframed_timestamp_ms"], moment["reframed_timestamp_ms"] + 15000]
        },
        "reveal_scene": {
            "reveal_id": moment["reveal_id"],
            "timestamp_ms": moment["reveal_timestamp_ms"]
        },
        "suggested_playback_speed": 1.0,
        "companion_notes": moment["clue_description"],
        "trust_label": moment.get("trust_label", "Engine-supported interpretation")
    }

    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=visibility,
        safe_title="Synchronized Rewatch Cuepoint"
    )
    return {"status": "SUCCESS", "data": sanitized}


@router.get("/{moment_id}/trust-label")
async def get_trust_label(
    moment_id: str,
    viewer: ViewerContext = Depends(get_current_viewer),
    db: AsyncSession = Depends(get_db)
):
    """
    3. Trust Label: Scientific transparency breakdown of narrative evidence grounding.
    Enforces ViewerContext spoiler protection.
    """
    moment = await _resolve_moment(moment_id, viewer, db)

    scope = SpoilerScope(
        work_id=moment["work_id"],
        edition_id=moment["edition_id"],
        minimum_progress_ms=moment["reveal_timestamp_ms"],
        required_reveal_ids=[moment["reveal_id"]],
        severity="ENDING",
        safe_title="Verified Narrative Trust Label" if moment.get("content_kind") == "VERIFIED_PROOF" else "Narrative Pattern Trust Label",
        safe_preview="Evidence grounding breakdown unlocked with reveal."
    )
    visibility = moment_visibility(scope, viewer)

    is_pattern = moment.get("content_kind") == "REWATCH_PATTERN"
    grounding_metrics = {
        "multi_scene_chain_length": len(moment.get("graph_path", [])) // 2 + 1,
        "observable_events_cited": len(moment.get("evidence_frame_ids", []))
    }
    if is_pattern:
        grounding_metrics["display_salience_estimate"] = moment.get("display_salience_estimate", 0.85)
    else:
        grounding_metrics["proof_strength"] = moment.get("proof_strength", 0.85)

    raw_payload = {
        "moment_id": moment["moment_id"],
        "verification_status": moment.get("verification_status", "ENGINE_INFERENCE"),
        "human_review_status": moment.get("human_review_status", "NOT_REVIEWED"),
        "trust_namespace": moment.get("trust_namespace", "ENGINE_INFERENCE"),
        "trust_label": moment.get("trust_label", "Engine-supported interpretation"),
        "dataset_version": "v3",
        "proof_type": moment["proof_type"],
        "canonical_asset_sha256": "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
        "counterfactual_robustness": moment.get("counterfactual_robustness", {"verdict": "NOT_VALIDATED"}),
        "grounding_metrics": grounding_metrics
    }

    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=visibility,
        safe_title="Narrative Evidence Trust Label",
        safe_preview="Forensic verification metadata for this moment."
    )
    return {"status": "SUCCESS", "data": sanitized}


@router.get("/{moment_id}/deep-dive")
async def get_deep_dive(
    moment_id: str,
    viewer: ViewerContext = Depends(get_current_viewer),
    db: AsyncSession = Depends(get_db)
):
    """
    4. Deep Dive: Forensic workbench with complete graph path and counterfactual data.
    """
    moment = await _resolve_moment(moment_id, viewer, db)

    scope = SpoilerScope(
        work_id=moment["work_id"],
        edition_id=moment["edition_id"],
        minimum_progress_ms=moment["reveal_timestamp_ms"],
        required_reveal_ids=[moment["reveal_id"]],
        severity="ENDING"
    )
    visibility = moment_visibility(scope, viewer)

    is_pattern = moment.get("content_kind") == "REWATCH_PATTERN"
    raw_payload = {
        "moment_id": moment["moment_id"],
        "title": moment["title"],
        "proof_type": moment["proof_type"],
        "clue_description": moment["clue_description"],
        "before_understanding": moment["before_understanding"],
        "after_understanding": moment["after_understanding"],
        "reframed_timestamp_ms": moment["reframed_timestamp_ms"],
        "reveal_timestamp_ms": moment["reveal_timestamp_ms"],
        "graph_path": moment["graph_path"],
        "evidence_frame_ids": moment["evidence_frame_ids"],
        "counterfactual_delta": moment.get("counterfactual_delta"),
        "trust_namespace": moment.get("trust_namespace", "ENGINE_INFERENCE"),
        "trust_label": moment.get("trust_label", "Engine-supported interpretation")
    }
    if is_pattern:
        raw_payload["display_salience_estimate"] = moment.get("display_salience_estimate", 0.85)
        raw_payload["display_heuristic_impact"] = moment.get("display_heuristic_impact", 0.85)
    else:
        raw_payload["proof_strength"] = moment.get("proof_strength", 0.85)
        raw_payload["fan_impact"] = moment.get("fan_impact", 0.85)

    sanitized = sanitize_payload_for_viewer(
        payload=raw_payload,
        visibility=visibility,
        safe_title="Full Forensic Deep Dive"
    )
    return {"status": "SUCCESS", "data": sanitized}
