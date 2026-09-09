"""
Reframe V7 Canonical Evidence & Proof Content Hash Utilities
Provides deterministic 64-char SHA256 hashes for events, facts, frames, and proof packages.
Zero Paid Model Calls.
"""
import hashlib
from src.reframe.evidence.adapter import v3_adapter


def canonical_event_hash(event_id: str) -> str:
    ev = v3_adapter.get_event(event_id)
    if not ev:
        return hashlib.sha256(event_id.encode("utf-8")).hexdigest()
    normalized = f"{ev.event_id}|{ev.scene_id}|{ev.timestamp_ms}|{ev.actor}|{ev.action}|{ev.description}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_fact_hash(fact_id: str) -> str:
    f = v3_adapter.get_fact(fact_id)
    if not f:
        return hashlib.sha256(fact_id.encode("utf-8")).hexdigest()
    normalized = f"{f.fact_id}|{f.scene_id}|{f.timestamp_ms}|{f.subject}|{f.predicate}|{f.object}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_frame_hash(frame_id: str) -> str:
    fr = v3_adapter.get_frame(frame_id)
    if not fr:
        return hashlib.sha256(frame_id.encode("utf-8")).hexdigest()
    normalized = f"{fr.frame_id}|{fr.scene_id}|{fr.timestamp_ms}|{fr.frame_path}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def compute_canonical_proof_hash(
    work_id: str,
    edition_id: str,
    reveal_id: str,
    dataset_version: str = "v3",
    overlay_sha: str = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948",
    evidence_bundle_hash: str = "default_evidence_bundle",
    model_id: str = "gemini-3.6-flash",
    prompt_hash: str = "prompt_v7_canonical",
    reasoning_config_hash: str = "reasoning_p0_standard",
    retrieval_config_hash: str = "5channel_retrieval_v7",
    proof_schema_version: str = "1.0.0"
) -> str:
    elements = [
        f"work_id:{work_id}",
        f"edition_id:{edition_id}",
        f"reveal_id:{reveal_id}",
        f"dataset_version:{dataset_version}",
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
