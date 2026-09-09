import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any, Optional


def compute_deterministic_scene_id(movie_id: str, source_hash: str, start_ms: int, end_ms: int) -> str:
    """
    Generates deterministic scene_id using SHA-256 over movie metadata and exact timestamps.
    Formula: sha256(movie_id + source_hash + start_ms + end_ms)[:24]
    """
    raw_str = f"{movie_id}:{source_hash}:{start_ms}:{end_ms}"
    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    return f"scene-{h[:20]}"


def compute_deterministic_event_id(scene_id: str, timestamp_ms: int, actor: str, action: str) -> str:
    raw_str = f"{scene_id}:{timestamp_ms}:{actor}:{action}"
    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    return f"ev-{h[:16]}"


def compute_deterministic_fact_id(scene_id: str, timestamp_ms: int, subject: str, predicate: str, object_: str) -> str:
    raw_str = f"{scene_id}:{timestamp_ms}:{subject}:{predicate}:{object_}"
    h = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    return f"fact-{h[:16]}"


def segment_video_timestamps(
    runtime_ms: int,
    avg_scene_duration_ms: int = 120000,
    min_scene_duration_ms: int = 15000,
) -> List[Dict[str, int]]:
    """
    Creates deterministic scene time intervals for segment extraction.
    """
    scenes = []
    current_start = 0
    while current_start < runtime_ms:
        current_end = min(current_start + avg_scene_duration_ms, runtime_ms)
        if current_end - current_start >= min_scene_duration_ms or not scenes:
            scenes.append({"start_ms": current_start, "end_ms": current_end})
        current_start = current_end
    return scenes
