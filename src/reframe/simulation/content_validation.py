"""
Reframe V7 Synthetic Content Grounding & Evidence Validation
Ensures all synthetic demo content strictly cites valid V3 facts, events, scenes, reveals, frames, and adheres to spoiler scopes.
Zero External Generative Model Calls.
"""
from __future__ import annotations
import json
import os
from typing import Dict, List, Any, Optional, Tuple
from src.reframe.evidence.adapter import v3_adapter

ALLOWED_TRUST_CLASSES = {
    "OBSERVED_EVIDENCE",
    "CANONICAL_FACT",
    "ENGINE_INFERENCE",
    "COMMUNITY_INTERPRETATION",
    "SPECULATIVE_THEORY",
    "NOT_VALIDATED",
}

FORBIDDEN_CANON_CLAIMS = [
    "VERIFIED_CANON",
    "D4 VERIFIED",
    "D5 VERIFIED",
    "COUNTERFACTUALLY_ROBUST",
    "100% PROVEN",
    "deliberate staging",
    "completely confirms",
]


class ContentValidator:
    def __init__(self):
        self.adapter = v3_adapter

    def validate_trust_class(self, trust_class: str) -> bool:
        if trust_class not in ALLOWED_TRUST_CLASSES:
            return False
        for forbidden in FORBIDDEN_CANON_CLAIMS:
            if forbidden in trust_class:
                return False
        return True

    def validate_content_grounding(
        self,
        trust_class: str = "OBSERVED_EVIDENCE",
        timestamp_ms: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        if not self.validate_trust_class(trust_class):
            return False, f"Invalid trust class: {trust_class}"
        if timestamp_ms is not None and (timestamp_ms < 0 or timestamp_ms > 5100000):
            return False, f"Timestamp out of bounds: {timestamp_ms}ms"
        return True, None

    def validate_evidence_ref(self, ref: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        ev_type = ref.get("evidence_type")
        ev_id = ref.get("evidence_id")
        scene_id = ref.get("scene_id")
        ts = ref.get("timestamp_ms")
        trust_class = ref.get("trust_class", "COMMUNITY_INTERPRETATION")

        if not self.validate_trust_class(trust_class):
            return False, f"Forbidden trust class: {trust_class}"

        if ts is not None and (ts < 0 or ts > 5100000):
            return False, f"Timestamp out of movie bounds: {ts}ms"

        if ev_type == "FACT":
            fact = self.adapter.get_fact(ev_id)
            if not fact:
                return False, f"Unknown fact_id: {ev_id}"
            if scene_id and fact.scene_id != scene_id:
                return False, f"Fact {ev_id} belongs to scene {fact.scene_id}, not {scene_id}"
            if ts is not None and fact.timestamp_ms != ts:
                return False, f"Fact {ev_id} timestamp {ts} does not match canonical {fact.timestamp_ms}"

        elif ev_type == "EVENT":
            event = self.adapter.get_event(ev_id)
            if not event:
                return False, f"Unknown event_id: {ev_id}"
            if scene_id and event.scene_id != scene_id:
                return False, f"Event {ev_id} belongs to scene {event.scene_id}, not {scene_id}"
            if ts is not None and event.timestamp_ms != ts:
                return False, f"Event {ev_id} timestamp {ts} does not match canonical {event.timestamp_ms}"

        elif ev_type == "SCENE":
            scene = self.adapter.get_scene(ev_id)
            if not scene:
                return False, f"Unknown scene_id: {ev_id}"
            if scene_id and scene.scene_id != scene_id:
                return False, f"Scene ID mismatch: {ev_id} vs {scene_id}"
            if ts is not None and not (scene.start_ms <= ts <= scene.end_ms):
                return False, f"Scene {ev_id} timestamp {ts} out of bounds [{scene.start_ms}, {scene.end_ms}]"

        elif ev_type == "FRAME":
            frame = self.adapter.get_frame(ev_id)
            if not frame:
                return False, f"Unknown frame_id: {ev_id}"
            if scene_id and frame.scene_id != scene_id:
                return False, f"Frame {ev_id} belongs to scene {frame.scene_id}, not {scene_id}"
            if ts is not None and frame.timestamp_ms != ts:
                return False, f"Frame {ev_id} timestamp {ts} does not match canonical {frame.timestamp_ms}"

        elif ev_type == "REVEAL":
            reveal = self.adapter.get_reveal(ev_id)
            if not reveal:
                return False, f"Unknown reveal_id: {ev_id}"
            if ts is not None and reveal.timestamp_ms != ts:
                return False, f"Reveal {ev_id} timestamp {ts} does not match canonical {reveal.timestamp_ms}"

        else:
            return False, f"Unknown evidence_type: {ev_type}"

        return True, None

    def validate_content_item(self, item: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validates an article, post, or counterclaim against canonical evidence.
        """
        evidence_refs = item.get("evidence_refs", [])
        if not evidence_refs and not item.get("tagged_reveal_ids"):
            return False, "Content must provide evidence_refs or tagged_reveal_ids."

        for ref in evidence_refs:
            ok, err = self.validate_evidence_ref(ref)
            if not ok:
                return False, err

        for rev_id in item.get("tagged_reveal_ids", []):
            reveal = self.adapter.get_reveal(rev_id)
            if not reveal:
                return False, f"Tagged reveal not found in canonical catalog: {rev_id}"

        # Text forbidden strings check
        body_text = str(item.get("body", "")) + str(item.get("body_sections", "")) + str(item.get("title", ""))
        for forbidden in FORBIDDEN_CANON_CLAIMS:
            if forbidden.lower() in body_text.lower():
                return False, f"Forbidden phrase found in content: '{forbidden}'"

        return True, None

    def derive_spoiler_scope_ms(
        self,
        cited_timestamps: List[int],
        tagged_reveal_ids: List[str],
    ) -> int:
        """
        Derives maximum timestamp for server-derived SpoilerScope.
        """
        max_ts = 0
        if cited_timestamps:
            max_ts = max(cited_timestamps)
        for rev_id in tagged_reveal_ids:
            rev = self.adapter.get_reveal(rev_id)
            if rev and rev.timestamp_ms > max_ts:
                max_ts = rev.timestamp_ms
        return max_ts

    def generate_validation_report(self) -> Dict[str, Any]:
        """
        Validates all curated content assets and returns a comprehensive validation report.
        """
        from src.reframe.simulation.content_factory import (
            CURATED_MAGAZINE_ARTICLES,
            CURATED_COMMUNITY_POSTS,
            CURATED_COUNTERCLAIMS,
        )

        report = {
            "version": "grounded_content_validation_v2",
            "validation_timestamp_utc": "2026-08-21T06:30:00Z",
            "total_articles_validated": len(CURATED_MAGAZINE_ARTICLES),
            "total_posts_validated": len(CURATED_COMMUNITY_POSTS),
            "total_counterclaims_validated": len(CURATED_COUNTERCLAIMS),
            "all_assets_passed": True,
            "validated_assets": [],
        }

        for category, items in [
            ("MAGAZINE_ARTICLE", CURATED_MAGAZINE_ARTICLES),
            ("COMMUNITY_POST", CURATED_COMMUNITY_POSTS),
            ("COUNTERCLAIM", CURATED_COUNTERCLAIMS),
        ]:
            for item in items:
                ok, err = self.validate_content_item(item)
                if not ok:
                    report["all_assets_passed"] = False
                report["validated_assets"].append({
                    "category": category,
                    "stable_key": item.get("stable_key"),
                    "title": item.get("title"),
                    "valid": ok,
                    "error": err,
                    "verified_refs": item.get("evidence_refs", []),
                })

        return report


content_validator = ContentValidator()
