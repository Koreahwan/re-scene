"""
Deep Snapshot V1.1 Validator Tool
Validates schema, integrity, clean-room constraints, and epistemic consistency for Deep Snapshot V1.1.
Zero Paid Model Calls.
"""
import os
import sys
sys.path.insert(0, ".")
import json
import hashlib
from typing import Dict, Any, List

from src.reframe.evidence.adapter import v3_adapter

SNAPSHOT_DIR = os.path.join("data", "analysis", "the_bat_whispers", "deep_snapshot_v1_1")

REQUIRED_FILES = [
    "manifest.json",
    "clean_room_manifest.json",
    "phase_a_lock.json",
    "media_review.json",
    "evidence_index.json",
    "characters.json",
    "knowledge_propositions.json",
    "character_epistemic_states.json",
    "claims.json",
    "actions.json",
    "claim_action_relations.json",
    "access_opportunities.json",
    "goals.json",
    "plan_steps.json",
    "causal_edges.json",
    "motifs.json",
    "negative_evidence.json",
    "proof_candidates.json",
    "counterfactual_evaluation.json",
    "why_missed.json",
    "legacy_comparison.json",
    "human_review_queue.json",
    "analysis_report.md",
    os.path.join("reveal_analysis", "reveal-anderson-identity.json"),
    os.path.join("reveal_analysis", "reveal-secret-room-location.json")
]


def sha256_file(filepath: str) -> str:
    with open(filepath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def validate_snapshot(snapshot_dir: str = SNAPSHOT_DIR) -> Dict[str, Any]:
    errors = []
    warnings = []

    # 1. Check all required files exist
    for rel_path in REQUIRED_FILES:
        full_path = os.path.join(snapshot_dir, rel_path)
        if not os.path.exists(full_path):
            errors.append(f"Missing required snapshot file: {rel_path}")
        elif os.path.getsize(full_path) == 0:
            errors.append(f"Empty required snapshot file: {rel_path}")

    if errors:
        return {"is_valid": False, "errors": errors, "warnings": warnings}

    # 2. Check Phase A Lock Integrity
    lock_path = os.path.join(snapshot_dir, "phase_a_lock.json")
    with open(lock_path, "r", encoding="utf-8") as f:
        lock_data = json.load(f)

    for locked_file, meta in lock_data.get("files_locked", {}).items():
        file_path = os.path.join(snapshot_dir, locked_file)
        if not os.path.exists(file_path):
            errors.append(f"Locked file missing: {locked_file}")
            continue
        current_sha = sha256_file(file_path)
        if current_sha != meta["sha256"]:
            errors.append(f"Phase A lock hash mismatch on {locked_file}: expected {meta['sha256']}, got {current_sha}")

    # 3. Check Canonical Referential Integrity
    valid_scenes = {s.scene_id for s in v3_adapter.get_scenes()}
    valid_events = {e.event_id for e in v3_adapter.get_events()}
    valid_facts = {f.fact_id for f in v3_adapter.get_facts()}

    # Check proof candidates
    with open(os.path.join(snapshot_dir, "proof_candidates.json"), "r", encoding="utf-8") as f:
        candidates = json.load(f)

    for cand in candidates:
        if cand.get("human_review_status") != "NOT_REVIEWED":
            errors.append(f"Candidate {cand.get('proof_id')} must have human_review_status == 'NOT_REVIEWED'")

        if "counterfactual_results" in cand:
            errors.append(f"Candidate {cand.get('proof_id')} must not embed counterfactual_results; counterfactual_evaluation.json is SSOT (Instruction 8)")

        if not cand.get("counterfactual_evaluation_id"):
            errors.append(f"Candidate {cand.get('proof_id')} missing counterfactual_evaluation_id")

        if cand.get("proof_type") not in {"KNOWLEDGE_LEAK", "CLAIM_ACTION_CONFLICT", "HIDDEN_PLAN_CHAIN", "MECHANISM_DISCOVERY", "MULTI_SCENE_PATTERN", "GOAL_ALIGNED_PATTERN", "DISCOVERY_SETUP_PAYOFF"}:
            errors.append(f"Invalid proof_type {cand.get('proof_type')} in {cand.get('proof_id')}")

        if cand.get("presentation_status") not in {"PUBLIC", "HIDDEN_FROM_PUBLIC"}:
            errors.append(f"Invalid presentation_status {cand.get('presentation_status')} in {cand.get('proof_id')}")

        for ec in cand.get("evidence_chain", []):
            if ec.get("scene_id") not in valid_scenes:
                errors.append(f"Invalid scene_id in evidence_chain: {ec.get('scene_id')}")

        for prem in cand.get("observed_premises", []):
            if prem.get("scene_id") and prem.get("scene_id") not in valid_scenes:
                errors.append(f"Invalid scene_id in premise: {prem.get('scene_id')}")
            if prem.get("event_id") and prem.get("event_id") not in valid_events:
                errors.append(f"Invalid event_id in premise: {prem.get('event_id')}")
            if prem.get("fact_id") and prem.get("fact_id") not in valid_facts:
                errors.append(f"Invalid fact_id in premise: {prem.get('fact_id')}")

            # Check for contamination in observed action text
            action_text = (prem.get("action") or prem.get("observed_action") or "").lower()
            forbidden_words = ["unbriefed", "to find the safe", "to deflect suspicion", "covertly searches"]
            for fw in forbidden_words:
                if fw in action_text:
                    errors.append(f"Contaminated observed action text in {prem.get('evidence_ref')}: contains '{fw}'")

    # 4. Check Epistemic Propositions
    with open(os.path.join(snapshot_dir, "knowledge_propositions.json"), "r", encoding="utf-8") as f:
        kps = json.load(f)

    for kp in kps:
        for req_field in ["proposition_id", "normalized_proposition", "canonical_truth_valid_from_ms", "audience_available_from_ms", "household_available_from_ms", "character_access"]:
            if req_field not in kp:
                errors.append(f"Proposition {kp.get('proposition_id')} missing field {req_field}")

        for ca in kp.get("character_access", []):
            valid_access_types = {"OBSERVED", "INFERRED", "INFERRED_REVEAL_DEPENDENT", "DISCOVERS_BY_OPERATION", "UNKNOWN"}
            if ca.get("access_type") not in valid_access_types:
                errors.append(f"Invalid access_type {ca.get('access_type')} in {kp.get('proposition_id')}")

    # 5. Check Claims
    with open(os.path.join(snapshot_dir, "claims.json"), "r", encoding="utf-8") as f:
        claims = json.load(f)

    for clm in claims:
        if clm.get("grounding_status") not in {"VERBATIM_SUPPORTED", "PARAPHRASE_SUPPORTED", "INSUFFICIENT_CONTENT"}:
            errors.append(f"Invalid grounding_status {clm.get('grounding_status')} in {clm.get('claim_id')}")

    # 6. Check Causal Edges
    with open(os.path.join(snapshot_dir, "causal_edges.json"), "r", encoding="utf-8") as f:
        edges = json.load(f)

    for edge in edges:
        if edge.get("relation_type") not in {"ENABLES", "PREPARES", "CAUSES", "TEMPORAL_PRECEDENCE_ONLY"}:
            errors.append(f"Invalid causal relation_type {edge.get('relation_type')} in {edge.get('edge_id')}")

    is_valid = len(errors) == 0
    return {
        "is_valid": is_valid,
        "total_files_checked": len(REQUIRED_FILES),
        "total_candidates": len(candidates),
        "total_propositions": len(kps),
        "errors": errors,
        "warnings": warnings
    }


if __name__ == "__main__":
    res = validate_snapshot()
    print(f"Validation result: {'PASSED' if res['is_valid'] else 'FAILED'}")
    if not res["is_valid"]:
        for err in res["errors"]:
            print(f"  ERROR: {err}")
    else:
        print(f"  All {res['total_files_checked']} snapshot files validated successfully.")
