import os
import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List

sys.path.insert(0, "src")
from reframe.mcp.gateway import McpClickHouseGateway

DATASET_VERSION = "the_bat_whispers_v2_gemini36"
CHECKPOINT_PATH = Path("data/manifests/preprocessing_checkpoint_v2_gemini36.json")


async def run_audit():
    print("===================================================================")
    print(f"      POST-FILM DATA QUALITY AUDIT ({DATASET_VERSION})")
    print("===================================================================")
    gateway = McpClickHouseGateway(mcp_endpoint_url="http://127.0.0.1:8001/mcp")

    if not CHECKPOINT_PATH.exists():
        print("Checkpoint file not found!")
        return

    with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)

    # 1. Checkpoint Metrics
    total_chunks = 43
    processed_count = len(checkpoint.get("processed_chunks", {}))
    failed_count = len(checkpoint.get("failed_chunks", {}))
    total_calls = checkpoint.get("total_model_calls", 0)
    prompt_tokens = checkpoint.get("cumulative_prompt_tokens", 0)
    candidate_tokens = checkpoint.get("cumulative_candidate_tokens", 0)
    cost_krw = checkpoint.get("cumulative_cost_krw", 0.0)

    # 2. ClickHouse Table Counts for DATASET_VERSION
    scenes_count = (await gateway.run_query(
        f"SELECT count() as cnt FROM reframe.scenes WHERE dataset_version = '{DATASET_VERSION}'"
    ))[0]["cnt"]

    events_count = (await gateway.run_query(
        f"SELECT count() as cnt FROM reframe.events WHERE scene_id LIKE 'scene-tbw-v2-%'"
    ))[0]["cnt"]

    facts_count = (await gateway.run_query(
        f"SELECT count() as cnt FROM reframe.facts WHERE scene_id LIKE 'scene-tbw-v2-%'"
    ))[0]["cnt"]

    # Unique characters and objects
    all_scenes = await gateway.run_query(
        f"SELECT scene_id, start_ms, end_ms, characters, objects FROM reframe.scenes WHERE dataset_version = '{DATASET_VERSION}' ORDER BY start_ms ASC"
    )

    unique_characters = set()
    unique_objects = set()
    timestamp_errors = 0
    duplicate_scenes = len(all_scenes) - len(set(s["scene_id"] for s in all_scenes))

    for s in all_scenes:
        if int(s["start_ms"]) >= int(s["end_ms"]):
            timestamp_errors += 1
        for c in s.get("characters", []):
            if c:
                unique_characters.add(c)
        for o in s.get("objects", []):
            if o:
                unique_objects.add(o)

    print("\n--- SUMMARY REPORT ---")
    print(f"Total Chunks:              {total_chunks}")
    print(f"Successful Chunks:         {processed_count}")
    print(f"Failed Chunks:             {failed_count}")
    print(f"Total Real 3.6 Calls:      {total_calls}")
    print(f"Prompt Tokens:             {prompt_tokens}")
    print(f"Candidate Tokens:          {candidate_tokens}")
    print(f"Actual Total Cost:         KRW {cost_krw:.2f} (~ ${cost_krw/1380:.4f} USD)")
    print(f"ClickHouse Scenes:         {scenes_count}")
    print(f"ClickHouse Events:         {events_count}")
    print(f"ClickHouse Facts:          {facts_count}")
    print(f"Unique Characters:         {len(unique_characters)} ({sorted(list(unique_characters))[:8]}...)")
    print(f"Unique Objects:            {len(unique_objects)} ({sorted(list(unique_objects))[:8]}...)")
    print(f"Timestamp Errors:          {timestamp_errors}")
    print(f"Duplicate Scenes:          {duplicate_scenes}")
    print("===================================================================")


if __name__ == "__main__":
    asyncio.run(run_audit())
