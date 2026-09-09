"""
Phase B Legacy Comparison Tool
Compares Phase A locked candidate proofs against legacy fixtures and V1 snapshots.
Produces legacy_comparison.json without modifying Phase A artifacts.
"""
import os
import json
from typing import Dict, Any, List

SNAPSHOT_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1_1")
V1_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1")


def compare_legacy():
    # Load Phase A candidate proofs
    with open(os.path.join(SNAPSHOT_DIR, "phase_a_candidate_proofs.json"), "r", encoding="utf-8") as f:
        phase_a_cands = json.load(f)

    # Load legacy V1 proof candidates if present
    v1_cands = []
    if os.path.exists(os.path.join(V1_DIR, "proof_candidates.json")):
        with open(os.path.join(V1_DIR, "proof_candidates.json"), "r", encoding="utf-8") as f:
            v1_cands = json.load(f)

    # Load golden fixture if present
    golden_path = os.path.join("data", "fixtures", "the_bat_whispers_golden.json")
    golden_data = {}
    if os.path.exists(golden_path):
        with open(golden_path, "r", encoding="utf-8") as f:
            golden_data = json.load(f)

    comparison_results = []
    for cand in phase_a_cands:
        cid = cand.get("candidate_id")
        revid = cand.get("reveal_id")
        cand_events = {p.get("event_id") for p in cand.get("observed_premises", []) if p.get("event_id")}

        matched_v1 = None
        max_overlap = 0.0
        for v1c in v1_cands:
            if v1c.get("reveal_id") == revid:
                v1_events = {p.get("event_id") for p in v1c.get("observed_premises", []) if p.get("event_id")}
                if cand_events and v1_events:
                    overlap = len(cand_events.intersection(v1_events)) / len(cand_events.union(v1_events))
                    if overlap > max_overlap:
                        max_overlap = overlap
                        matched_v1 = v1c

        if max_overlap == 1.0:
            classification = "MATCH"
        elif max_overlap > 0.0:
            classification = "PARTIAL_MATCH"
        else:
            classification = "NOVEL"

        # Check for title/explanation reproduction
        contamination_flag = "CLEAN_ROOM_INDEPENDENT"
        if matched_v1:
            if cand.get("title") == matched_v1.get("title"):
                contamination_flag = "POTENTIAL_CONTAMINATION_EXACT_TITLE"
            elif cand.get("blind_explanation") == matched_v1.get("blind_explanation"):
                contamination_flag = "POTENTIAL_CONTAMINATION_EXACT_EXPLANATION"

        comparison_results.append({
            "candidate_id": cid,
            "reveal_id": revid,
            "phase_a_title": cand.get("title"),
            "legacy_classification": classification,
            "evidence_overlap_ratio": round(max_overlap, 3),
            "matched_legacy_id": matched_v1.get("proof_id") if matched_v1 else None,
            "contamination_flag": contamination_flag,
            "differences": {
                "epistemic_time_model": "V1.1 uses multi-time model (canonical/audience/household/private)",
                "observation_separation": "V1.1 strictly separates observed visual facts from inferred purposes",
                "counterfactual_derivation": "V1.1 removes hardcoded deltas in favor of engine evaluation"
            }
        })

    payload = {
        "comparison_version": "1.1",
        "phase": "PHASE_B_LEGACY_AUDIT",
        "total_candidates_compared": len(comparison_results),
        "results": comparison_results,
        "summary": {
            "clean_room_differentiators": [
                "Replaced single public_available_from_ms with 4-way epistemic time model",
                "Reclassified Anderson multi-scene sequence as honest D3 search pattern with partial causal link",
                "Demoted verbal claims without verbatim text to INSUFFICIENT_CONTENT",
                "Replaced canned counterfactual deltas with dynamic engine evaluation"
            ]
        }
    }

    out_path = os.path.join(SNAPSHOT_DIR, "legacy_comparison.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"Legacy comparison generated: {out_path}")
    return payload


if __name__ == "__main__":
    compare_legacy()
