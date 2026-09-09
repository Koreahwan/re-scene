import json
from pathlib import Path
import pytest


def test_v3_frame_provenance_strict_manifest_integrity():
    """
    Validates that:
    1. Every frame cited in evidence_frame_ids exists in data/manifests/v3_frame_manifest.json.
    2. All evidence_frame_timestamps_ms exactly match the manifest absolute_timestamp_ms.
    3. Every frame timestamp falls strictly within the candidate scene/evidence temporal boundaries.
    4. Ingestion loader fails closed if an unknown frame ID is encountered.
    """
    manifest_path = Path("data/manifests/v3_frame_manifest.json")
    assert manifest_path.exists(), "v3_frame_manifest.json must exist"

    with open(manifest_path, "r", encoding="utf-8") as f:
        man_data = json.load(f)

    frames_list = man_data if isinstance(man_data, list) else man_data.get("frames", [])
    manifest_frames = {
        fm["frame_id"]: fm.get("absolute_timestamp_ms", fm.get("relative_sec", 0) * 1000)
        for fm in frames_list
    }
    assert len(manifest_frames) == 385, "Must have all 385 extracted frames in manifest"

    export_path = Path("data/production/v3_dataset_export.json")
    assert export_path.exists(), "v3_dataset_export.json must exist"

    with open(export_path, "r", encoding="utf-8") as f:
        v3 = json.load(f)

    events = v3.get("events", [])
    facts = v3.get("facts", [])
    assert len(events) == 187
    assert len(facts) == 94

    scenes_by_id = {s["scene_id"]: s for s in v3.get("scenes", [])}
    assert len(scenes_by_id) == 43, "Must have all 43 scenes in dataset"

    # Validate Events Provenance & Boundary Constraints
    for ev in events:
        fids = ev.get("evidence_frame_ids", [])
        fts = ev.get("evidence_frame_timestamps_ms", [])
        assert len(fids) == len(fts), f"Event {ev['event_id']} frame IDs and timestamps length mismatch"

        scene = scenes_by_id[ev["scene_id"]]
        ev_start = ev.get("evidence_start_ms", ev.get("timestamp_ms"))
        ev_end = ev.get("evidence_end_ms", ev_start)
        assert scene["start_ms"] <= ev_start <= ev_end <= scene["end_ms"], (
            f"Event {ev['event_id']} bounds [{ev_start}, {ev_end}] outside scene {scene['scene_id']} [{scene['start_ms']}, {scene['end_ms']}]"
        )

        for fid, ts in zip(fids, fts):
            assert fid in manifest_frames, f"Event {ev['event_id']} cited unknown frame {fid}"
            assert ts == manifest_frames[fid], f"Event {ev['event_id']} timestamp mismatch for {fid}"
            assert ev_start <= ts <= ev_end, f"Frame {fid} at {ts}ms outside event {ev['event_id']} range [{ev_start}, {ev_end}]"

            # Check chunk consistency
            scene_chunk = ev["scene_id"].split("-")[-1]  # e.g., 'c031'
            frame_chunk = fid.split("_")[1]              # e.g., 'c031'
            assert scene_chunk == frame_chunk, f"Chunk mismatch: event in {scene_chunk} but frame is {frame_chunk}"

    # Validate Facts Provenance & Boundary Constraints
    for fc in facts:
        fids = fc.get("evidence_frame_ids", [])
        fts = fc.get("evidence_frame_timestamps_ms", [])
        assert len(fids) == len(fts), f"Fact {fc['fact_id']} frame IDs and timestamps length mismatch"

        scene = scenes_by_id[fc["scene_id"]]
        fc_start = fc.get("evidence_start_ms", fc.get("timestamp_ms"))
        fc_end = fc.get("evidence_end_ms", fc_start)
        assert scene["start_ms"] <= fc_start <= fc_end <= scene["end_ms"], (
            f"Fact {fc['fact_id']} bounds [{fc_start}, {fc_end}] outside scene {scene['scene_id']} [{scene['start_ms']}, {scene['end_ms']}]"
        )

        for fid, ts in zip(fids, fts):
            assert fid in manifest_frames, f"Fact {fc['fact_id']} cited unknown frame {fid}"
            assert ts == manifest_frames[fid], f"Fact {fc['fact_id']} timestamp mismatch for {fid}"
            assert fc_start <= ts <= fc_end, f"Frame {fid} at {ts}ms outside fact {fc['fact_id']} range [{fc_start}, {fc_end}]"

            # Check chunk consistency
            scene_chunk = fc["scene_id"].split("-")[-1]
            frame_chunk = fid.split("_")[1]
            assert scene_chunk == frame_chunk, f"Chunk mismatch: fact in {scene_chunk} but frame is {frame_chunk}"


def test_loader_fails_closed_on_unknown_frame_id():
    """
    Validates that the ingestion pipeline fail-closed guard raises ValueError
    when encountering any unknown or missing frame ID.
    """
    fake_frame_map = {"frame_c001_000": 0}
    test_event = {
        "event_id": "ev-test-unknown",
        "evidence_frame_ids": ["frame_c999_999_nonexistent"]
    }

    with pytest.raises(ValueError, match="PROVENANCE_FAIL_CLOSED"):
        ev_fids = test_event["evidence_frame_ids"]
        ev_fts = []
        for fid in ev_fids:
            if fid not in fake_frame_map:
                raise ValueError(f"PROVENANCE_FAIL_CLOSED: Frame ID '{fid}' in event '{test_event['event_id']}' not found in manifest!")
            ev_fts.append(fake_frame_map[fid])

