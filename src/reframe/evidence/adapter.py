"""
Reframe V7 V3 Artifact Adapter & Version Pinning Engine
"""
import os
import json
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import structlog

from src.reframe.shared.config import settings
from src.reframe.evidence.schemas import (
    SceneDTO,
    EventDTO,
    FactDTO,
    RevealDTO,
    EvidenceFrameDTO,
    CanonicalCorrectionDTO,
    EvidenceRefDTO
)

logger = structlog.get_logger(__name__)


def compute_content_hash(data: Any) -> str:
    raw = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class V3EvidenceAdapter:
    def __init__(self, data_root: Optional[str] = None):
        self.data_root = Path(data_root) if data_root else Path(__file__).parent.parent.parent.parent / "data"
        self.v3_checkpoint_path = self.data_root / "manifests" / "preprocessing_checkpoint_v3_gemini36.json"
        self.v3_export_path = self.data_root / "production" / "v3_dataset_export.json"
        self.reveals_registry_path = self.data_root / "production" / "reveals_registry.json"
        self.frame_manifest_path = self.data_root / "manifests" / "v3_frame_manifest.json"
        self.corrections_path = self.data_root / "production" / "canonical_corrections_v3.json"

        self.work_id = "the-bat-whispers-1930"
        self.edition_id = "tbw-fullscreen-archive"
        self.dataset_version = "v3"
        self.canonical_asset_sha256 = settings.CANONICAL_ASSET_SHA256

        # In-memory stores
        self._scenes: Dict[str, SceneDTO] = {}
        self._events: Dict[str, EventDTO] = {}
        self._facts: Dict[str, FactDTO] = {}
        self._reveals: Dict[str, RevealDTO] = {}
        self._frames: Dict[str, EvidenceFrameDTO] = {}
        self._corrections: List[CanonicalCorrectionDTO] = []
        self._overlay_sha256: Optional[str] = None

        self._load_and_validate()

    def _load_and_validate(self):
        # 1. Load corrections overlay if present
        if self.corrections_path.exists():
            with open(self.corrections_path, "r", encoding="utf-8") as f:
                corr_raw = json.load(f)
                raw_bytes = json.dumps(corr_raw, sort_keys=True).encode("utf-8")
                self._overlay_sha256 = hashlib.sha256(raw_bytes).hexdigest()
                self._corrections = [
                    CanonicalCorrectionDTO(**item, overlay_sha256=self._overlay_sha256)
                    for item in corr_raw
                ]

        # 2. Load Frame Manifest (385 records)
        frame_time_map: Dict[str, int] = {}
        if self.frame_manifest_path.exists():
            with open(self.frame_manifest_path, "r", encoding="utf-8") as f:
                frame_data = json.load(f)
                frames_list = frame_data if isinstance(frame_data, list) else frame_data.get("frames", [])
                for fm in frames_list:
                    fid = fm["frame_id"]
                    ts = fm.get("absolute_timestamp_ms", int(fm.get("relative_sec", 0) * 1000))
                    frame_time_map[fid] = ts
                    self._frames[fid] = EvidenceFrameDTO(
                        frame_id=fid,
                        scene_id=fm.get("scene_id", ""),
                        work_id=self.work_id,
                        edition_id=self.edition_id,
                        timestamp_ms=ts,
                        canonical_asset_sha256=self.canonical_asset_sha256,
                        file_sha256=fm.get("sha256")
                    )

        # 3. Load V3 Checkpoint (43 scenes, 187 events, 94 facts)
        if self.v3_checkpoint_path.exists():
            with open(self.v3_checkpoint_path, "r", encoding="utf-8") as f:
                checkpoint = json.load(f)

            chunks = checkpoint.get("processed_chunks", {})
            sorted_chunks = sorted(chunks.keys(), key=lambda k: int(k.split("-")[1]))

            for cid in sorted_chunks:
                cdata = chunks[cid]
                sid = cdata["scene_id"]
                scene_content = {
                    "scene_id": sid,
                    "work_id": self.work_id,
                    "edition_id": self.edition_id,
                    "dataset_version": self.dataset_version,
                    "start_ms": cdata["start_ms"],
                    "end_ms": cdata["end_ms"],
                    "duration_ms": cdata.get("duration_ms", cdata["end_ms"] - cdata["start_ms"]),
                    "summary": cdata["summary"],
                    "location": cdata.get("location", "Oakdale Manor"),
                    "characters": cdata.get("characters", []),
                    "objects": cdata.get("objects", [])
                }
                scene_hash = compute_content_hash(scene_content)
                self._scenes[sid] = SceneDTO(**scene_content, evidence_hash=scene_hash)

                # Events
                for ev in cdata.get("events", []):
                    eid = ev["event_id"]
                    ev_start = ev.get("evidence_start_ms", ev.get("timestamp_ms", cdata["start_ms"]))
                    ev_end = ev.get("evidence_end_ms", ev_start)
                    ev_fids = ev.get("evidence_frame_ids", [])
                    ev_timestamps = [frame_time_map.get(fid, ev_start) for fid in ev_fids]

                    actor = ev.get("actor", "None")
                    desc = ev.get("description", "")
                    entities = list(ev.get("entities", []))

                    # Apply canonical correction overlay if applicable
                    is_corrected = False
                    corr_overlay_sha = None
                    matching_corr = next((c for c in self._corrections if c.target_id == eid), None)
                    if matching_corr:
                        is_corrected = True
                        corr_overlay_sha = self._overlay_sha256
                        if matching_corr.field == "actor":
                            actor = str(matching_corr.corrected_value)
                        if matching_corr.description_corrected:
                            desc = matching_corr.description_corrected

                    ev_content = {
                        "event_id": eid,
                        "scene_id": sid,
                        "work_id": self.work_id,
                        "edition_id": self.edition_id,
                        "dataset_version": self.dataset_version,
                        "timestamp_ms": ev_start,
                        "evidence_start_ms": ev_start,
                        "evidence_end_ms": ev_end,
                        "actor": actor,
                        "action": ev.get("action", ""),
                        "target": ev.get("target"),
                        "object": ev.get("object"),
                        "description": desc,
                        "evidence_frame_ids": ev_fids,
                        "evidence_frame_timestamps_ms": ev_timestamps
                    }
                    ev_hash = compute_content_hash(ev_content)
                    self._events[eid] = EventDTO(
                        **ev_content,
                        evidence_hash=ev_hash,
                        is_corrected=is_corrected,
                        correction_overlay_sha=corr_overlay_sha
                    )

                # Facts
                for fc in cdata.get("facts", []):
                    fid = fc["fact_id"]
                    fc_content = {
                        "fact_id": fid,
                        "scene_id": sid,
                        "work_id": self.work_id,
                        "edition_id": self.edition_id,
                        "dataset_version": self.dataset_version,
                        "timestamp_ms": fc.get("timestamp_ms", cdata["start_ms"]),
                        "subject": fc.get("subject", ""),
                        "predicate": fc.get("predicate", ""),
                        "object": fc.get("object", ""),
                        "confidence": float(fc.get("confidence", 1.0)),
                        "evidence_frame_ids": fc.get("evidence_frame_ids", [])
                    }
                    fc_hash = compute_content_hash(fc_content)
                    self._facts[fid] = FactDTO(**fc_content, evidence_hash=fc_hash)

        # 4. Load Reveals (4 reveals)
        if self.reveals_registry_path.exists():
            with open(self.reveals_registry_path, "r", encoding="utf-8") as f:
                reveals_raw = json.load(f)
            for r in reveals_raw:
                rid = r["reveal_id"]
                ts = r["timestamp_ms"]
                self._reveals[rid] = RevealDTO(
                    reveal_id=rid,
                    work_id=self.work_id,
                    edition_id=self.edition_id,
                    dataset_version=self.dataset_version,
                    title=r["title"],
                    reveal_type=r["reveal_type"],
                    timestamp_ms=ts,
                    spoiler_cutoff_ms=ts,
                    subject=r.get("subject", ""),
                    predicate=r.get("predicate", ""),
                    previous_belief=r.get("previous_belief", ""),
                    revealed_fact=r.get("revealed_fact", ""),
                    affected_entities=r.get("affected_entities", []),
                    evidence_scene_ids=r.get("evidence_scene_ids", []),
                    importance=float(r.get("importance", 1.0)),
                    canonical_asset_sha256=self.canonical_asset_sha256
                )

        logger.info(
            "V3 Evidence Adapter loaded successfully",
            scenes=len(self._scenes),
            events=len(self._events),
            facts=len(self._facts),
            reveals=len(self._reveals),
            frames=len(self._frames),
            corrections=len(self._corrections)
        )

    # Retrieval API
    def get_scenes(self, cutoff_ms: Optional[int] = None) -> List[SceneDTO]:
        scenes = list(self._scenes.values())
        if cutoff_ms is not None:
            scenes = [s for s in scenes if s.start_ms < cutoff_ms]
        return sorted(scenes, key=lambda s: s.start_ms)

    def get_scene(self, scene_id: str) -> Optional[SceneDTO]:
        return self._scenes.get(scene_id)

    def get_events(self, cutoff_ms: Optional[int] = None, scene_id: Optional[str] = None) -> List[EventDTO]:
        events = list(self._events.values())
        if scene_id:
            events = [e for e in events if e.scene_id == scene_id]
        if cutoff_ms is not None:
            events = [e for e in events if e.timestamp_ms < cutoff_ms]
        return sorted(events, key=lambda e: e.timestamp_ms)

    def get_event(self, event_id: str) -> Optional[EventDTO]:
        return self._events.get(event_id)

    def get_facts(self, cutoff_ms: Optional[int] = None, scene_id: Optional[str] = None) -> List[FactDTO]:
        facts = list(self._facts.values())
        if scene_id:
            facts = [f for f in facts if f.scene_id == scene_id]
        if cutoff_ms is not None:
            facts = [f for f in facts if f.timestamp_ms < cutoff_ms]
        return sorted(facts, key=lambda f: f.timestamp_ms)

    def get_fact(self, fact_id: str) -> Optional[FactDTO]:
        return self._facts.get(fact_id)

    def get_reveals(self) -> List[RevealDTO]:
        return list(self._reveals.values())

    def get_reveal(self, reveal_id: str) -> Optional[RevealDTO]:
        return self._reveals.get(reveal_id)

    def get_frame(self, frame_id: str) -> Optional[EvidenceFrameDTO]:
        return self._frames.get(frame_id)

    def get_evidence_frames(self) -> List[EvidenceFrameDTO]:
        return list(self._frames.values())


    def get_evidence_ref(self, evidence_type: str, evidence_id: str) -> Optional[EvidenceRefDTO]:
        content_hash = None
        corr_sha = None
        ev_type = (evidence_type or "").lower().strip()

        if ev_type == "scene":
            item = self.get_scene(evidence_id)
            if item:
                content_hash = item.evidence_hash
        elif ev_type == "event":
            item = self.get_event(evidence_id)
            if item:
                content_hash = item.evidence_hash
                corr_sha = item.correction_overlay_sha
        elif ev_type == "fact":
            item = self.get_fact(evidence_id)
            if item:
                content_hash = item.evidence_hash
        elif ev_type == "frame":
            item = self.get_frame(evidence_id)
            if item:
                content_hash = item.file_sha256 or item.canonical_asset_sha256

        if not content_hash:
            return None

        return EvidenceRefDTO(
            work_id=self.work_id,
            edition_id=self.edition_id,
            dataset_version=self.dataset_version,
            evidence_type=ev_type,
            evidence_id=evidence_id,
            evidence_content_hash=content_hash,
            correction_overlay_sha=corr_sha
        )


v3_adapter = V3EvidenceAdapter()
