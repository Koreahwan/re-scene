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

OBSERVABLE_EXTRACTION_PROMPT = """
You are an objective video scene observable analyzer for 1930 mystery cinema.
Analyze the provided scene description and sequence context.
Extract ONLY directly observable visual actions, physical objects, present characters, and factual states.
DO NOT infer character secret motives or label any action as foreshadowing or deception.

Output strict JSON with schema:
{
  "summary": "Objective description of what occurs visually and audibly in this scene.",
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
    characters: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    events: List[Dict[str, Any]] = Field(default_factory=list)
    facts: List[Dict[str, Any]] = Field(default_factory=list)


def extract_sample_frames(video_path: str, start_sec: int, duration_sec: int, output_dir: Path) -> List[str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame_pattern = str(output_dir / "frame_%03d.jpg")
    cmd = [
        FFMPEG_PATH,
        "-y",
        "-ss", str(start_sec),
        "-i", video_path,
        "-t", str(duration_sec),
        "-vf", "fps=1/10,scale=640:-1",
        "-q:v", "4",
        frame_pattern,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    frames = sorted(str(p) for p in output_dir.glob("frame_*.jpg"))
    return frames


async def run_representative_extraction():
    from google import genai
    from PIL import Image

    print("=== STARTING REPRESENTATIVE PREPROCESSING (3 REAL CHUNKS) ===")
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
    model_id = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

    client = genai.Client(vertexai=True, project=project, location=location)
    gateway = McpClickHouseGateway(mcp_endpoint_url="http://127.0.0.1:8001/mcp")

    chunks = [
        {"chunk_id": "rep-chunk-01-early", "start_sec": 60, "duration_sec": 120, "region": "Early Film (Bank Robbery & City Alarm)"},
        {"chunk_id": "rep-chunk-02-middle", "start_sec": 1800, "duration_sec": 120, "region": "Middle Film (Oakdale Manor Investigation)"},
        {"chunk_id": "rep-chunk-03-prereveal", "start_sec": 4200, "duration_sec": 120, "region": "Pre-Reveal Region (Hidden Partition Search)"},
    ]

    total_prompt_tokens = 0
    total_candidate_tokens = 0
    total_model_calls = 0
    start_total_time = time.time()
    results = []

    for i, c in enumerate(chunks, 1):
        print(f"\n--- Processing Chunk {i}/3: {c['chunk_id']} ({c['region']}) [{c['start_sec']}s - {c['start_sec']+c['duration_sec']}s] ---")
        temp_dir = Path(f"scratch/frames_{c['chunk_id']}")
        frames = extract_sample_frames(VIDEO_PATH, c["start_sec"], c["duration_sec"], temp_dir)
        print(f"Extracted {len(frames)} sampled frames with ffmpeg.")

        # Load images for multimodal analysis
        images = [Image.open(f) for f in frames[:6]]  # Take top 6 keyframes to stay compact and cost-efficient

        prompt = f"""
Analyze this 2-minute film segment from 'The Bat Whispers (1930)' starting at timecode {c['start_sec']}s ({c['region']}).
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
        total_model_calls += 1

        usage = response.usage_metadata
        p_tokens = getattr(usage, "prompt_token_count", 0) or 0
        c_tokens = getattr(usage, "candidates_token_count", 0) or 0
        total_prompt_tokens += p_tokens
        total_candidate_tokens += c_tokens

        print(f"Model call latency: {round(t1 - t0, 3)}s")
        print(f"Tokens: prompt={p_tokens}, candidates={c_tokens}")

        # Validate Schema
        raw_json = json.loads(response.text)
        validated = PassAObservableOutput(**raw_json)
        print(f"Validated summary: {validated.summary[:120]}...")
        print(f"Extracted characters: {validated.characters}")
        print(f"Extracted objects: {validated.objects}")
        print(f"Extracted events: {len(validated.events)}, facts: {len(validated.facts)}")

        # Create Domain Models
        scene_id = f"scene-{c['chunk_id']}"
        start_ms = c["start_sec"] * 1000
        end_ms = (c["start_sec"] + c["duration_sec"]) * 1000

        scene_record = Scene(
            scene_id=scene_id,
            movie_id="the-bat-whispers-1930",
            start_ms=start_ms,
            end_ms=end_ms,
            location=c["region"],
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
        VALUES ('{scene_record.scene_id}', '{scene_record.movie_id}', {scene_record.start_ms}, {scene_record.end_ms}, '{loc}', {chars}, {objs}, '{summary}', 'v1.0-rep');
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

        results.append({
            "chunk_id": c["chunk_id"],
            "region": c["region"],
            "prompt_tokens": p_tokens,
            "candidate_tokens": c_tokens,
            "events_count": len(event_records),
            "facts_count": len(fact_records),
        })

    total_time = time.time() - start_total_time

    # Cost calculation: Gemini 2.5 Flash on Vertex AI is ~$0.15 per 1M input tokens, ~$0.60 per 1M output tokens (approx KRW 200 / KRW 800 per 1M tokens)
    # USD to KRW rate ≈ 1,380
    cost_usd = (total_prompt_tokens * (0.15 / 1_000_000)) + (total_candidate_tokens * (0.60 / 1_000_000))
    cost_krw = cost_usd * 1380

    avg_chunk_cost_krw = cost_krw / len(chunks)
    # Full film is ~42 chunks of 2-minutes each
    total_film_chunks = 43
    projected_full_film_cost_krw = avg_chunk_cost_krw * total_film_chunks

    print("\n=======================================================")
    print("      REPRESENTATIVE PREPROCESSING COST REPORT         ")
    print("=======================================================")
    print(f"Chunks processed: {len(chunks)} / {len(chunks)} SUCCESS")
    print(f"Total model calls: {total_model_calls}")
    print(f"Total prompt tokens: {total_prompt_tokens}")
    print(f"Total candidate tokens: {total_candidate_tokens}")
    print(f"Total elapsed time: {round(total_time, 2)}s")
    print(f"Observed 3-chunk cost: ${cost_usd:.6f} USD (~ KRW {cost_krw:.2f})")
    print(f"REPRESENTATIVE_CHUNK_COST: ~ KRW {avg_chunk_cost_krw:.2f} (~ ${avg_chunk_cost_krw / 1380:.6f} USD)")
    print(f"PROJECTED_FULL_FILM_COST: ~ KRW {projected_full_film_cost_krw:.2f} (~ ${projected_full_film_cost_krw / 1380:.4f} USD)")
    print(f"PROJECTED_CUMULATIVE_GROSS_USAGE: ~ KRW {projected_full_film_cost_krw:.2f}")
    print(f"Soft budget ceiling: KRW 80,000 | Spend Cap: KRW 116,000")
    print("=======================================================")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_representative_extraction())
