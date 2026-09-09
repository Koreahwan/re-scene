import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import structlog
from pydantic import BaseModel, Field

sys.path.insert(0, "src")
from reframe.domain.models import Scene, Event, Fact
from reframe.domain.enums import FactType
from reframe.mcp.gateway import McpClickHouseGateway

logger = structlog.get_logger(__name__)

FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg")
VIDEO_PATH = r"data\external\raw\the_bat_whispers\The_Bat_Whispers_(1930,_fullscreen_version).webm"
CHECKPOINT_PATH = Path(r"data\manifests\preprocessing_checkpoint.json")

TOTAL_DURATION_SEC = 5119
CHUNK_DURATION_SEC = 120
MAX_CUMULATIVE_COST_KRW = 100_000.0

OBSERVABLE_EXTRACTION_PROMPT = """
You are an objective video scene observable analyzer for 1930 mystery cinema.
Analyze the provided scene description and sequence context.
Extract ONLY directly observable visual actions, physical objects, present characters, and factual states.
DO NOT infer character secret motives or label any action as foreshadowing or deception.

Output strict JSON with schema:
{
  "summary": "Objective description of what occurs visually and audibly in this scene.",
  "location": "Estimated location within Oakdale Manor or city",
  "characters": ["Character 1", "Character 2"],
  "objects": ["Object 1", "Object 2"],
  "events": [
    {
      "event_id": "ev-unique-id",
      "timestamp_ms": 12345,
      "actor": "Character Name",
      "action": "action_verb",
      "description": "Concrete observable action description"
    }
  ],
  "facts": [
    {
      "fact_id": "fact-unique-id",
      "timestamp_ms": 12345,
      "subject": "Character/Object",
      "predicate": "observable_predicate",
      "object": "Target Object/Location",
      "fact_type": "OBSERVATION",
      "confidence": 0.95
    }
  ]
}
""".strip()


class PassAObservableOutput(BaseModel):
    summary: str
    location: str = "Oakdale Manor"
    characters: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    facts: List[Dict[str, Any]] = Field(default_factory=list)


def load_checkpoint() -> Dict[str, Any]:
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "movie_id": "the-bat-whispers-1930",
        "processed_chunks": {},
        "cumulative_prompt_tokens": 0,
        "cumulative_candidate_tokens": 0,
        "cumulative_cost_krw": 0.0,
        "last_updated": time.time(),
    }


def save_checkpoint(data: Dict[str, Any]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = time.time()
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def extract_sample_frames(video_path: str, start_sec: int, duration_sec: int, output_dir: Path) -> List[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = str(output_dir / "frame_%03d.jpg")
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration_sec),
        "-vf", "fps=1/15,scale=640:-1",
        "-q:v", "4",
        frame_pattern,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    frames = sorted(str(p) for p in output_dir.glob("frame_*.jpg"))
    return frames


async def run_full_film_preprocessing():
    from google import genai
    from PIL import Image

    print("=== STARTING FULL-FILM PREPROCESSING (THE BAT WHISPERS 1930) ===")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    model_id = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    client = genai.Client(vertexai=True, project=project, location=location)
    gateway = McpClickHouseGateway(mcp_endpoint_url="http://127.0.0.1:8001/mcp")

    checkpoint = load_checkpoint()
    total_chunks = (TOTAL_DURATION_SEC // CHUNK_DURATION_SEC) + 1
    print(f"Total film duration: {TOTAL_DURATION_SEC}s ({total_chunks} chunks of {CHUNK_DURATION_SEC}s)")
    print(f"Already processed chunks: {len(checkpoint['processed_chunks'])} / {total_chunks}")

    for chunk_idx in range(total_chunks):
        start_sec = chunk_idx * CHUNK_DURATION_SEC
        duration_sec = min(CHUNK_DURATION_SEC, TOTAL_DURATION_SEC - start_sec)
        if duration_sec <= 0:
            break

        chunk_id = f"chunk-{chunk_idx+1:03d}"
        if chunk_id in checkpoint["processed_chunks"]:
            print(f"Skipping already processed chunk {chunk_id} ({start_sec}s - {start_sec+duration_sec}s)")
            continue

        # Budget check
        if checkpoint["cumulative_cost_krw"] > MAX_CUMULATIVE_COST_KRW:
            print(f"BUDGET CAP REACHED: Cumulative cost KRW {checkpoint['cumulative_cost_krw']:.2f} > KRW {MAX_CUMULATIVE_COST_KRW}")
            break

        print(f"\n--- Processing Chunk {chunk_idx+1}/{total_chunks}: {chunk_id} [{start_sec}s - {start_sec+duration_sec}s] ---")
        temp_dir = Path(f"scratch/full_frames_{chunk_id}")
        frames = extract_sample_frames(VIDEO_PATH, start_sec, duration_sec, temp_dir)
        print(f"Extracted {len(frames)} keyframes.")

        images = [Image.open(f) for f in frames[:5]]  # Sample 5 frames per 2-min chunk to optimize latency & tokens

        prompt = f"""
Analyze this 2-minute film segment from 'The Bat Whispers (1930)' starting at timecode {start_sec}s.
Keyframes sampled across this segment are attached.
Perform Pass A objective observable extraction.
"""
        contents = [prompt] + images

        t0 = time.time()
        response = client.models.generate_content(
            model=model_id,
            contents=contents,
            config={
                "system_instruction": OBSERVABLE_EXTRACTION_PROMPT,
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        )
        t1 = time.time()

        usage = response.usage_metadata
        p_tokens = getattr(usage, "prompt_token_count", 0) or 0
        c_tokens = getattr(usage, "candidates_token_count", 0) or 0

        # Cost tracking
        chunk_cost_usd = (p_tokens * (0.15 / 1_000_000)) + (c_tokens * (0.60 / 1_000_000))
        chunk_cost_krw = chunk_cost_usd * 1380

        checkpoint["cumulative_prompt_tokens"] += p_tokens
        checkpoint["cumulative_candidate_tokens"] += c_tokens
        checkpoint["cumulative_cost_krw"] += chunk_cost_krw

        print(f"Latency: {round(t1 - t0, 3)}s | Tokens: {p_tokens} in, {c_tokens} out | Cost: KRW {chunk_cost_krw:.2f} (Cumulative: KRW {checkpoint['cumulative_cost_krw']:.2f})")

        # Validate Schema
        raw_json = json.loads(response.text)
        validated = PassAObservableOutput(**raw_json)

        scene_id = f"scene-tbw-full-{chunk_idx+1:03d}"
        start_ms = start_sec * 1000
        end_ms = (start_sec + duration_sec) * 1000

        scene_record = Scene(
            scene_id=scene_id,
            movie_id="the-bat-whispers-1930",
            start_ms=start_ms,
            end_ms=end_ms,
            location=validated.location or "Oakdale Manor",
            summary=validated.summary,
            characters=validated.characters,
            objects=validated.objects,
        )

        event_records = []
        for idx, ev in enumerate(validated.events, 1):
            event_records.append(Event(
                event_id=f"ev-{scene_id}-{idx}",
                scene_id=scene_id,
                movie_id="the-bat-whispers-1930",
                timestamp_ms=start_ms + (idx * 5000),
                actor=ev.get("actor", "Unknown"),
                action=ev.get("action", "action"),
                description=ev.get("description", ""),
            ))

        fact_records = []
        for idx, f in enumerate(validated.facts, 1):
            fact_records.append(Fact(
                fact_id=f"fact-{scene_id}-{idx}",
                scene_id=scene_id,
                movie_id="the-bat-whispers-1930",
                timestamp_ms=start_ms + (idx * 5000),
                subject=f.get("subject", "Unknown"),
                predicate=f.get("predicate", "is"),
                object=f.get("object", "Unknown"),
                fact_type=FactType.OBSERVATION.value,
                confidence=float(f.get("confidence", 0.95)),
            ))

        # Ingest into ClickHouse via MCP
        chars_list = [c.replace("'", "\\'") for c in scene_record.characters]
        chars = "[" + ", ".join(f"'{c}'" for c in chars_list) + "]"
        objs_list = [o.replace("'", "\\'") for o in scene_record.objects]
        objs = "[" + ", ".join(f"'{o}'" for o in objs_list) + "]"
        loc = (scene_record.location or "Oakdale Manor").replace("'", "\\'")
        summary = scene_record.summary.replace("'", "\\'")

        insert_scene_sql = f"""
        INSERT INTO reframe.scenes (scene_id, movie_id, start_ms, end_ms, location, characters, objects, summary, dataset_version)
        VALUES ('{scene_record.scene_id}', '{scene_record.movie_id}', {scene_record.start_ms}, {scene_record.end_ms}, '{loc}', {chars}, {objs}, '{summary}', 'v1.0-full');
        """
        await gateway.run_query(insert_scene_sql)

        for ev in event_records:
            actor = ev.actor.replace("'", "\\'")
            action = ev.action.replace("'", "\\'")
            desc = ev.description.replace("'", "\\'")
            insert_ev_sql = f"""
            INSERT INTO reframe.events (event_id, scene_id, movie_id, timestamp_ms, actor, action, description)
            VALUES ('{ev.event_id}', '{ev.scene_id}', '{ev.movie_id}', {ev.timestamp_ms}, '{actor}', '{action}', '{desc}');
            """
            await gateway.run_query(insert_ev_sql)

        for f in fact_records:
            subj = f.subject.replace("'", "\\'")
            pred = f.predicate.replace("'", "\\'")
            obj = f.object.replace("'", "\\'")
            insert_fact_sql = f"""
            INSERT INTO reframe.facts (fact_id, scene_id, movie_id, timestamp_ms, subject, predicate, object, fact_type, confidence)
            VALUES ('{f.fact_id}', '{f.scene_id}', '{f.movie_id}', {f.timestamp_ms}, '{subj}', '{pred}', '{obj}', '{f.fact_type}', {f.confidence});
            """
            await gateway.run_query(insert_fact_sql)

        # Checkpoint
        checkpoint["processed_chunks"][chunk_id] = {
            "scene_id": scene_id,
            "events_count": len(event_records),
            "facts_count": len(fact_records),
            "p_tokens": p_tokens,
            "c_tokens": c_tokens,
            "cost_krw": chunk_cost_krw,
        }
        save_checkpoint(checkpoint)
        print(f"Checkpoint saved for {chunk_id}. Ingested into ClickHouse.")

    print("\n=======================================================")
    print("      FULL-FILM PREPROCESSING COMPLETED               ")
    print("=======================================================")
    print(f"Total chunks processed: {len(checkpoint['processed_chunks'])} / {total_chunks}")
    print(f"Total prompt tokens: {checkpoint['cumulative_prompt_tokens']}")
    print(f"Total candidate tokens: {checkpoint['cumulative_candidate_tokens']}")
    print(f"Total cumulative cost: KRW {checkpoint['cumulative_cost_krw']:.2f}")
    print("=======================================================")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_full_film_preprocessing())
