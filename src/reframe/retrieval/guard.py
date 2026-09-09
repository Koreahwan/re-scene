from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Sequence, Union, Any, Dict, List, Optional, Tuple
from reframe.domain.models import Reveal, Scene, ReframeCandidate, Event, Fact
from reframe.domain.enums import AbstainReason

_FRAME_MANIFEST_CACHE: Optional[Dict[str, int]] = None
_MANIFEST_PATH = Path("data/manifests/v3_frame_manifest.json")


def get_frame_timestamp_ms(frame_id: str) -> Optional[int]:
    """
    Looks up the exact persisted absolute timestamp for a frame ID from v3_frame_manifest.json.
    Caches the manifest in memory for high-performance deterministic checks.
    """
    global _FRAME_MANIFEST_CACHE
    if _FRAME_MANIFEST_CACHE is None:
        cache: Dict[str, int] = {}
        if _MANIFEST_PATH.exists():
            try:
                with open(_MANIFEST_PATH, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                    for item in manifest:
                        fid = item.get("frame_id")
                        ts = item.get("absolute_timestamp_ms")
                        if fid and ts is not None:
                            cache[fid] = int(ts)
            except Exception:
                pass
        _FRAME_MANIFEST_CACHE = cache
    return _FRAME_MANIFEST_CACHE.get(frame_id)


class SpoilerGuardViolation(Exception):
    """Raised when a query or result violates the spoiler cutoff invariant."""
    def __init__(self, message: str, reason: AbstainReason = AbstainReason.SPOILER_GUARD_BLOCKED):
        super().__init__(message)
        self.reason = reason


def derive_spoiler_cutoff(reveal: Reveal) -> int:
    """
    Derives the non-negotiable server-side spoiler cutoff timestamp in milliseconds.
    No future scene (timestamp >= cutoff_ms) may ever enter retrieval or model context.
    """
    if reveal.timestamp_ms <= 0:
        raise SpoilerGuardViolation(
            f"Invalid reveal timestamp_ms ({reveal.timestamp_ms}) for reveal {reveal.reveal_id}"
        )
    return reveal.timestamp_ms


def validate_client_request_parameters(request_params: Dict[str, Any]) -> None:
    """
    Guards against client-side cutoff tampering.
    Rejects any request that attempts to supply a spoiler_cutoff_ms or arbitrary SQL.
    """
    forbidden_keys = {"spoiler_cutoff_ms", "cutoff_ms", "sql", "query", "raw_query"}
    for key in forbidden_keys:
        if key in request_params:
            raise SpoilerGuardViolation(
                f"Client parameter '{key}' is forbidden. Server strictly controls spoiler boundaries."
            )


def filter_pre_cutoff_evidence(
    events: List[Event],
    facts: List[Fact],
    cutoff_ms: int,
) -> Tuple[List[Event], List[Fact]]:
    """
    Filters events and facts to ensure strict pre-cutoff conformance:
    - timestamp_ms < cutoff_ms
    - evidence_start_ms < cutoff_ms
    - evidence_end_ms < cutoff_ms
    - all referenced frame timestamps strictly < cutoff_ms
    """
    valid_events: List[Event] = []
    for ev in events:
        if ev.timestamp_ms >= cutoff_ms:
            continue
        if ev.evidence_end_ms >= cutoff_ms:
            continue
        # Verify frame timestamps
        frame_violation = False
        for fid in ev.evidence_frame_ids:
            ft = get_frame_timestamp_ms(fid)
            if ft is not None and ft >= cutoff_ms:
                frame_violation = True
                break
        if frame_violation:
            continue
        valid_events.append(ev)

    valid_facts: List[Fact] = []
    for fct in facts:
        if fct.timestamp_ms >= cutoff_ms:
            continue
        if fct.evidence_end_ms >= cutoff_ms:
            continue
        frame_violation = False
        for fid in fct.evidence_frame_ids:
            ft = get_frame_timestamp_ms(fid)
            if ft is not None and ft >= cutoff_ms:
                frame_violation = True
                break
        if frame_violation:
            continue
        valid_facts.append(fct)

    return valid_events, valid_facts


def sanitize_candidate_for_cutoff(
    candidate: ReframeCandidate,
    events: List[Event],
    facts: List[Fact],
    cutoff_ms: int,
) -> ReframeCandidate:
    """
    For an overlapping SceneGroup where end_ms >= cutoff_ms:
    Constructs a pre-cutoff candidate summary exclusively from pre-cutoff Events/Facts/evidence
    so the original whole-chunk summary containing post-cutoff information never enters Gemini.
    """
    if candidate.start_ms >= cutoff_ms:
        raise SpoilerGuardViolation(
            f"Candidate scene {candidate.scene_id} start_ms {candidate.start_ms} >= cutoff {cutoff_ms}"
        )

    # If the scene entirely precedes cutoff (end_ms < cutoff_ms), return as-is
    if candidate.end_ms > 0 and candidate.end_ms < cutoff_ms:
        return candidate

    # Overlapping scene: build pre-cutoff summary from verified pre-cutoff evidence
    pre_cutoff_descriptions = [f"- Event ({ev.timestamp_ms}ms, {ev.actor}): {ev.description}" for ev in events]
    pre_cutoff_facts = [f"- Fact ({f.timestamp_ms}ms): {f.subject} {f.predicate} {f.object}" for f in facts]
    
    combined_body = "\n".join(pre_cutoff_descriptions + pre_cutoff_facts)
    pre_cutoff_summary = (
        f"[Pre-Cutoff Narrative Excerpt for {candidate.scene_id} (< {cutoff_ms}ms)]:\n"
        f"{combined_body if combined_body else 'Observable actions before cutoff.'}"
    )

    max_ev_ms = max([ev.evidence_end_ms for ev in events] + [f.evidence_end_ms for f in facts], default=candidate.start_ms)

    return candidate.model_copy(
        update={
            "end_ms": min(candidate.end_ms, cutoff_ms - 1) if candidate.end_ms > 0 else cutoff_ms - 1,
            "evidence_end_ms": min(max_ev_ms, cutoff_ms - 1),
            "summary": pre_cutoff_summary,
            "pre_cutoff_summary": pre_cutoff_summary,
            "is_summary_pre_cutoff": True,
        }
    )


def assert_zero_future_leakage(
    candidates: Sequence[Union[Scene, ReframeCandidate, dict]],
    cutoff_ms: int,
    events: Optional[List[Event]] = None,
    facts: Optional[List[Fact]] = None,
) -> None:
    """
    Post-retrieval in-memory verification.
    Asserts that 100% of retrieved records strictly precede the spoiler cutoff.
    Enforces:
    1. Candidate start_ms < cutoff_ms
    2. Overlapping scene evidence_end_ms < cutoff_ms
    3. Events timestamp_ms, evidence_end_ms, and frame timestamps < cutoff_ms
    4. Facts timestamp_ms, evidence_end_ms, and frame timestamps < cutoff_ms
    """
    for item in candidates:
        if isinstance(item, (Scene, ReframeCandidate)):
            ts = int(item.start_ms)
            item_id = item.scene_id
            ev_end = getattr(item, "evidence_end_ms", 0)
        elif isinstance(item, dict):
            raw_ts = item.get("start_ms", item.get("timestamp_ms", 0))
            ts = int(raw_ts) if raw_ts is not None else 0
            item_id = item.get("scene_id", item.get("id", "unknown"))
            ev_end = int(item.get("evidence_end_ms", 0))
        else:
            raise TypeError(f"Unsupported item type for spoiler assertion: {type(item)}")

        if ts >= int(cutoff_ms):
            raise SpoilerGuardViolation(
                f"CRITICAL SPOILER LEAKAGE: Scene {item_id} (timestamp: {ts}ms) >= cutoff {cutoff_ms}ms"
            )
        if ev_end >= int(cutoff_ms):
            raise SpoilerGuardViolation(
                f"CRITICAL SPOILER LEAKAGE: Scene {item_id} evidence_end_ms ({ev_end}ms) >= cutoff {cutoff_ms}ms"
            )

    if events:
        for ev in events:
            if ev.timestamp_ms >= cutoff_ms:
                raise SpoilerGuardViolation(
                    f"CRITICAL SPOILER LEAKAGE: Event {ev.event_id} (timestamp: {ev.timestamp_ms}ms) >= cutoff {cutoff_ms}ms"
                )
            if ev.evidence_end_ms >= cutoff_ms:
                raise SpoilerGuardViolation(
                    f"CRITICAL SPOILER LEAKAGE: Event {ev.event_id} evidence_end_ms ({ev.evidence_end_ms}ms) >= cutoff {cutoff_ms}ms"
                )
            for fid in ev.evidence_frame_ids:
                ft = get_frame_timestamp_ms(fid)
                if ft is not None and ft >= cutoff_ms:
                    raise SpoilerGuardViolation(
                        f"CRITICAL SPOILER LEAKAGE: Event {ev.event_id} references frame {fid} at {ft}ms >= cutoff {cutoff_ms}ms"
                    )

    if facts:
        for fct in facts:
            if fct.timestamp_ms >= cutoff_ms:
                raise SpoilerGuardViolation(
                    f"CRITICAL SPOILER LEAKAGE: Fact {fct.fact_id} (timestamp: {fct.timestamp_ms}ms) >= cutoff {cutoff_ms}ms"
                )
            if fct.evidence_end_ms >= cutoff_ms:
                raise SpoilerGuardViolation(
                    f"CRITICAL SPOILER LEAKAGE: Fact {fct.fact_id} evidence_end_ms ({fct.evidence_end_ms}ms) >= cutoff {cutoff_ms}ms"
                )
            for fid in fct.evidence_frame_ids:
                ft = get_frame_timestamp_ms(fid)
                if ft is not None and ft >= cutoff_ms:
                    raise SpoilerGuardViolation(
                        f"CRITICAL SPOILER LEAKAGE: Fact {fct.fact_id} references frame {fid} at {ft}ms >= cutoff {cutoff_ms}ms"
                    )

