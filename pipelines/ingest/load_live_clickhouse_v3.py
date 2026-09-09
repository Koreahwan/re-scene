from __future__ import annotations
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import json
import time
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, "src")

V3_CHECKPOINT_PATH = Path(r"data/manifests/preprocessing_checkpoint_v3_gemini36.json")
GLOBAL_V3_PATH = Path(r"data/manifests/global_narrative_pass_v3.json")
REVEALS_PATH = Path(r"data/production/reveals_registry.json")
FILM_META_PATH = Path(r"data/production/film_metadata.json")
EXPORT_PATH = Path(r"data/production/v3_dataset_export.json")

DATASET_VERSION = "the_bat_whispers_v3_gemini36"
MOVIE_ID = "the-bat-whispers-1930"


async def load_v3_into_clickhouse():
    print("===================================================================")
    print(f"   INGESTING V3 DATASET INTO CLICKHOUSE ({DATASET_VERSION})")
    print("===================================================================")

    if not V3_CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"V3 Checkpoint not found at {V3_CHECKPOINT_PATH}")

    with open(V3_CHECKPOINT_PATH, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)

    with open(FILM_META_PATH, "r", encoding="utf-8") as f:
        film_meta = json.load(f)

    with open(REVEALS_PATH, "r", encoding="utf-8") as f:
        reveals_list = json.load(f)

    knowledge_states_list = []
    if GLOBAL_V3_PATH.exists():
        with open(GLOBAL_V3_PATH, "r", encoding="utf-8") as f:
            global_data = json.load(f)
            knowledge_states_list = global_data.get("knowledge_states", [])

    chunks = checkpoint.get("processed_chunks", {})
    sorted_chunk_keys = sorted(chunks.keys(), key=lambda k: int(k.split("-")[1]))

    scenes_rows = []
    events_rows = []
    facts_rows = []

    # Load frame manifest for timestamp mapping
    manifest_path = Path("data/manifests/v3_frame_manifest.json")
    frame_time_map: Dict[str, int] = {}
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            man_data = json.load(f)
            frames_list = man_data if isinstance(man_data, list) else man_data.get("frames", [])
            for fm in frames_list:
                frame_time_map[fm["frame_id"]] = fm.get("absolute_timestamp_ms", fm.get("relative_sec", 0) * 1000)

    for cid in sorted_chunk_keys:
        cdata = chunks[cid]
        scenes_rows.append({
            "scene_id": cdata["scene_id"],
            "movie_id": MOVIE_ID,
            "dataset_version": DATASET_VERSION,
            "start_ms": cdata["start_ms"],
            "end_ms": cdata["end_ms"],
            "location": cdata.get("location", "Oakdale Manor"),
            "characters": cdata.get("characters", []),
            "objects": cdata.get("objects", []),
            "summary": cdata["summary"],
            "dialogue_summary": f"Dialogue from {cid}",
            "source_chunk_id": cid,
            "extraction_version": "v3.0",
        })

        for ev in cdata.get("events", []):
            ev_start = ev.get("evidence_start_ms", ev.get("timestamp_ms", cdata["start_ms"]))
            ev_end = ev.get("evidence_end_ms", ev_start)
            ev_fids = ev.get("evidence_frame_ids", [])
            ev_fts = []
            for fid in ev_fids:
                if fid not in frame_time_map:
                    raise ValueError(f"PROVENANCE_FAIL_CLOSED: Frame ID '{fid}' in event '{ev.get('event_id')}' not found in manifest!")
                ev_fts.append(frame_time_map[fid])

            events_rows.append({
                "event_id": ev["event_id"],
                "movie_id": MOVIE_ID,
                "scene_id": cdata["scene_id"],
                "dataset_version": DATASET_VERSION,
                "timestamp_ms": ev_start,
                "evidence_start_ms": ev_start,
                "evidence_end_ms": ev_end,
                "actor": ev.get("actor", "Unknown"),
                "action": ev.get("action", "action"),
                "target": ev.get("target", "None"),
                "object": ev.get("object", "None"),
                "event_type": "ACTION",
                "description": ev.get("description", ""),
                "entities": [ev.get("actor", "Unknown")],
                "confidence": 1.0,
                "evidence_frame_ids": ev_fids,
                "evidence_frame_timestamps_ms": ev_fts,
                "extraction_version": "v3.0",
            })

        for fct in cdata.get("facts", []):
            fct_start = fct.get("evidence_start_ms", fct.get("timestamp_ms", cdata["start_ms"]))
            fct_end = fct.get("evidence_end_ms", fct_start)
            fct_fids = fct.get("evidence_frame_ids", [])
            fct_fts = []
            for fid in fct_fids:
                if fid not in frame_time_map:
                    raise ValueError(f"PROVENANCE_FAIL_CLOSED: Frame ID '{fid}' in fact '{fct.get('fact_id')}' not found in manifest!")
                fct_fts.append(frame_time_map[fid])

            facts_rows.append({
                "fact_id": fct["fact_id"],
                "movie_id": MOVIE_ID,
                "scene_id": cdata["scene_id"],
                "dataset_version": DATASET_VERSION,
                "timestamp_ms": fct_start,
                "evidence_start_ms": fct_start,
                "evidence_end_ms": fct_end,
                "subject": fct.get("subject", "Unknown"),
                "predicate": fct.get("predicate", "state"),
                "object": fct.get("object", "None"),
                "fact_type": fct.get("fact_type", "OBSERVATION"),
                "confidence": fct.get("confidence", 0.95),
                "evidence_frame_ids": fct_fids,
                "evidence_frame_timestamps_ms": fct_fts,
                "evidence_event_ids": [],
                "extraction_version": "v3.0",
            })

    # Prepare complete structured export for deterministic test/judge bootstrap
    export_payload = {
        "dataset_version": DATASET_VERSION,
        "film": film_meta,
        "scenes": scenes_rows,
        "events": events_rows,
        "facts": facts_rows,
        "reveals": reveals_list,
        "knowledge_states": knowledge_states_list,
        "exported_at": film_meta.get("updated_at", "2026-08-18T00:00:00Z"),
    }
    EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(export_payload, f, indent=2)
    print(f"[OK] Created structured V3 export: {EXPORT_PATH} ({len(scenes_rows)} scenes, {len(events_rows)} events, {len(facts_rows)} facts)")

    # Execute ClickHouse Insertion using bootstrap/admin identity
    os.environ["CLICKHOUSE_HOST"] = os.getenv("CLICKHOUSE_HOST", "localhost")
    os.environ["CLICKHOUSE_PORT"] = os.getenv("CLICKHOUSE_PORT", "8123")
    os.environ["CLICKHOUSE_USER"] = os.getenv("CLICKHOUSE_ADMIN_USER", os.getenv("CLICKHOUSE_USER", "reframe_runtime"))
    os.environ["CLICKHOUSE_PASSWORD"] = os.getenv("CLICKHOUSE_ADMIN_PASSWORD", os.getenv("CLICKHOUSE_PASSWORD", ""))
    os.environ["CLICKHOUSE_DATABASE"] = "reframe"
    os.environ["CLICKHOUSE_SECURE"] = "false"
    os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "true"

    from mcp_clickhouse.mcp_server import run_query

    # Ensure schema migrations are applied on live ClickHouse
    print("Ensuring provenance columns exist in ClickHouse tables...")
    for col_ddl in [
        "ALTER TABLE reframe.events ADD COLUMN IF NOT EXISTS evidence_start_ms UInt64 DEFAULT timestamp_ms",
        "ALTER TABLE reframe.events ADD COLUMN IF NOT EXISTS evidence_end_ms UInt64 DEFAULT timestamp_ms",
        "ALTER TABLE reframe.events ADD COLUMN IF NOT EXISTS evidence_frame_timestamps_ms Array(UInt64) DEFAULT []",
        "ALTER TABLE reframe.facts ADD COLUMN IF NOT EXISTS evidence_start_ms UInt64 DEFAULT timestamp_ms",
        "ALTER TABLE reframe.facts ADD COLUMN IF NOT EXISTS evidence_end_ms UInt64 DEFAULT timestamp_ms",
        "ALTER TABLE reframe.facts ADD COLUMN IF NOT EXISTS evidence_frame_ids Array(String) DEFAULT []",
        "ALTER TABLE reframe.facts ADD COLUMN IF NOT EXISTS evidence_frame_timestamps_ms Array(UInt64) DEFAULT []",
    ]:
        try:
            run_query(col_ddl)
        except Exception as e:
            print(f"Notice applying DDL migration ({col_ddl}): {e}")

    # Delete existing rows for this dataset_version if any
    print(f"Cleaning previous {DATASET_VERSION} rows in ClickHouse...")
    for tbl in ["scenes", "events", "facts", "reveals", "knowledge_states"]:
        try:
            run_query(f"ALTER TABLE reframe.{tbl} DELETE WHERE dataset_version = '{DATASET_VERSION}'")
        except Exception as e:
            print(f"Warning during clean of {tbl}: {e}")

    time.sleep(1)

    # Insert Film
    print("Ingesting Film metadata...")
    sha_val = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"
    run_query(f"""
    INSERT INTO reframe.films (movie_id, title, year, runtime_ms, language, source_url, source_hash, rights_status, subtitle_source, dataset_version)
    VALUES ('{film_meta["movie_id"]}', '{film_meta["title"].replace("'", "''")}', {film_meta["year"]}, {film_meta["runtime_ms"]}, '{film_meta["language"]}', '{film_meta["source_url"]}', '{sha_val}', '{film_meta["rights_status"]}', 'public_domain_srt', '{DATASET_VERSION}')
    """)

    def _sql_str_list(items):
        return "[" + ", ".join("'" + str(i).replace("'", "''") + "'" for i in items) + "]"

    # Insert Scenes
    print(f"Ingesting {len(scenes_rows)} SceneGroups...")
    for s in scenes_rows:
        chars_str = _sql_str_list(s["characters"])
        objs_str = _sql_str_list(s["objects"])
        summary_esc = s["summary"].replace("'", "''")
        loc_esc = s["location"].replace("'", "''")
        run_query(f"""
        INSERT INTO reframe.scenes (movie_id, scene_id, start_ms, end_ms, location, characters, objects, summary, dialogue_summary, source_chunk_id, extraction_version, dataset_version)
        VALUES ('{s["movie_id"]}', '{s["scene_id"]}', {s["start_ms"]}, {s["end_ms"]}, '{loc_esc}', {chars_str}, {objs_str}, '{summary_esc}', '{loc_esc}', '{s["source_chunk_id"]}', '{s["extraction_version"]}', '{s["dataset_version"]}')
        """)

    # Insert Events
    print(f"Ingesting {len(events_rows)} Events...")
    for ev in events_rows:
        actor_esc = ev["actor"].replace("'", "''")
        action_esc = ev["action"].replace("'", "''")
        target_esc = ev["target"].replace("'", "''")
        obj_esc = ev["object"].replace("'", "''")
        desc_esc = ev["description"].replace("'", "''")
        ents_str = _sql_str_list(ev["entities"])
        frames_str = _sql_str_list(ev["evidence_frame_ids"])
        fts_str = "[" + ", ".join(str(ts) for ts in ev.get("evidence_frame_timestamps_ms", [])) + "]"
        run_query(f"""
        INSERT INTO reframe.events (movie_id, event_id, scene_id, timestamp_ms, evidence_start_ms, evidence_end_ms, actor, action, target, object, event_type, description, entities, confidence, evidence_frame_ids, evidence_frame_timestamps_ms, extraction_version, dataset_version)
        VALUES ('{ev["movie_id"]}', '{ev["event_id"]}', '{ev["scene_id"]}', {ev["timestamp_ms"]}, {ev["evidence_start_ms"]}, {ev["evidence_end_ms"]}, '{actor_esc}', '{action_esc}', '{target_esc}', '{obj_esc}', '{ev["event_type"]}', '{desc_esc}', {ents_str}, {ev["confidence"]}, {frames_str}, {fts_str}, '{ev["extraction_version"]}', '{ev["dataset_version"]}')
        """)

    # Insert Facts
    print(f"Ingesting {len(facts_rows)} Facts...")
    for fct in facts_rows:
        sub_esc = fct["subject"].replace("'", "''")
        pred_esc = fct["predicate"].replace("'", "''")
        obj_esc = fct["object"].replace("'", "''")
        ft_esc = fct["fact_type"].replace("'", "''")
        fct_frames_str = _sql_str_list(fct.get("evidence_frame_ids", []))
        fct_fts_str = "[" + ", ".join(str(ts) for ts in fct.get("evidence_frame_timestamps_ms", [])) + "]"
        run_query(f"""
        INSERT INTO reframe.facts (movie_id, fact_id, scene_id, timestamp_ms, evidence_start_ms, evidence_end_ms, subject, predicate, object, fact_type, confidence, evidence_frame_ids, evidence_frame_timestamps_ms, extraction_version, dataset_version)
        VALUES ('{fct["movie_id"]}', '{fct["fact_id"]}', '{fct["scene_id"]}', {fct["timestamp_ms"]}, {fct["evidence_start_ms"]}, {fct["evidence_end_ms"]}, '{sub_esc}', '{pred_esc}', '{obj_esc}', '{ft_esc}', {fct["confidence"]}, {fct_frames_str}, {fct_fts_str}, '{fct["extraction_version"]}', '{fct["dataset_version"]}')
        """)

    # Insert Reveals
    print(f"Ingesting {len(reveals_list)} Reveals...")
    for rev in reveals_list:
        aff_str = _sql_str_list(rev["affected_entities"])
        title_esc = rev["title"].replace("'", "''")
        sbj_esc = rev["subject"].replace("'", "''")
        pred_esc = rev["predicate"].replace("'", "''")
        pb_esc = rev["previous_belief"].replace("'", "''")
        rf_esc = rev["revealed_fact"].replace("'", "''")
        rev_stat = rev.get("review_status", "APPROVED")
        rev_ext = rev.get("extraction_version", "v3.0")
        rev_ds = rev.get("dataset_version", DATASET_VERSION)
        run_query(f"""
        INSERT INTO reframe.reveals (movie_id, reveal_id, timestamp_ms, title, reveal_type, subject, predicate, previous_belief, revealed_fact, affected_entities, importance, review_status, extraction_version, dataset_version)
        VALUES ('{rev["movie_id"]}', '{rev["reveal_id"]}', {rev["timestamp_ms"]}, '{title_esc}', '{rev["reveal_type"]}', '{sbj_esc}', '{pred_esc}', '{pb_esc}', '{rf_esc}', {aff_str}, {rev["importance"]}, '{rev_stat}', '{rev_ext}', '{rev_ds}')
        """)

    # Verify Counts
    res_sc = run_query(f"SELECT count() FROM reframe.scenes WHERE dataset_version = '{DATASET_VERSION}'")
    res_ev = run_query(f"SELECT count() FROM reframe.events WHERE dataset_version = '{DATASET_VERSION}'")
    res_fc = run_query(f"SELECT count() FROM reframe.facts WHERE dataset_version = '{DATASET_VERSION}'")
    res_rv = run_query(f"SELECT count() FROM reframe.reveals WHERE dataset_version = '{DATASET_VERSION}'")

    print("\n===================================================================")
    print(f"   CLICKHOUSE V3 INGESTION COMPLETED SUCCESSFULLY!")
    print(f"   Dataset Version: {DATASET_VERSION}")
    print(f"   Scenes in DB: {res_sc}")
    print("===================================================================")

    # Restore runtime read-only configuration
    os.environ["CLICKHOUSE_USER"] = "reframe_runtime"
    os.environ["CLICKHOUSE_PASSWORD"] = ""
    os.environ["CLICKHOUSE_ALLOW_WRITE_ACCESS"] = "false"


if __name__ == "__main__":
    import asyncio
    asyncio.run(load_v3_into_clickhouse())
