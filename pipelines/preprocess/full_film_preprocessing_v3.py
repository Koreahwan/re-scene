from __future__ import annotations
import os
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import time
import json
import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
from pydantic import BaseModel, Field

# Ensure src in path
sys.path.insert(0, "src")
from reframe.domain.models import Scene, Event, Fact
from reframe.domain.enums import FactType

logger = structlog.get_logger(__name__)

FFMPEG_CMD = "ffmpeg"
CANONICAL_MEDIA_PATH = Path(r"data/external/raw/the_bat_whispers/The_Bat_Whispers_(1930,_fullscreen_version).webm")
CANONICAL_ASSET_SHA256 = "8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948"

CHECKPOINT_PATH = Path(r"data/manifests/preprocessing_checkpoint_v3_gemini36.json")
FRAME_MANIFEST_PATH = Path(r"data/manifests/v3_frame_manifest.json")

MODEL_ID = "gemini-3.6-flash"
GCP_LOCATION = "global"
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
PROMPT_VERSION = "v3.0-grounded-observable"
SCHEMA_VERSION = "v3.0"
PREPROCESSING_VERSION = "v3.0"
DATASET_VERSION = "the_bat_whispers_v3_gemini36"

TOTAL_DURATION_SEC = 5119
CHUNK_DURATION_SEC = 120
SAMPLING_INTERVAL_SEC = 15  # 9 frames per 120s chunk: 0, 15, 30, 45, 60, 75, 90, 105, 119
MAX_CUMULATIVE_COST_KRW = 150_000.0

PASS_A_SYSTEM_INSTRUCTION = """
You are an objective, expert video scene observable analyzer for 1930 mystery cinema ('The Bat Whispers').
Analyze the attached chronological keyframes sampled across this 2-minute film chunk.
Extract ONLY directly observable visual actions, physical objects, present characters, actual scene locations, and factual states.
DO NOT infer secret motives, do not speculate on unrevealed identities, and do not label actions as foreshadowing or deception.

For every event and fact:
1. You MUST cite the specific `evidence_frame_ids` (e.g. ["frame_c001_015", "frame_c001_030"]) where the action or state is directly visible.
2. Ground `evidence_start_ms` and `evidence_end_ms` directly to the millisecond timestamps of the supporting frames.
3. Specify the concrete, observable `location` (e.g., 'Bank Vault Interior', 'Police Dispatch Office', 'Oakdale Manor Great Hall', 'Oakdale Manor Upstairs Bedroom', 'Manor Library', 'Manor Ground Floor Hallway', 'Exterior Manor Lawn / Storm', 'Basement Secret Staircase', etc.) based on visual architecture and props.

Output strict JSON matching the schema:
{
  "summary": "Objective description of what occurs visually and audibly in this scene group.",
  "location": "Observable physical location",
  "characters": ["Character Name 1", "Character Name 2"],
  "objects": ["Object 1", "Object 2"],
  "events": [
    {
      "event_id": "ev-cXXX-YY",
      "actor": "Character Name",
      "action": "action_verb",
      "target": "Target Entity / None",
      "object": "Object Manipulated / None",
      "description": "Concrete observable action description",
      "evidence_frame_ids": ["frame_cXXX_ZZZ"],
      "evidence_start_ms": 12345,
      "evidence_end_ms": 27345,
      "temporal_precision_ms": 15000
    }
  ],
  "facts": [
    {
      "fact_id": "fact-cXXX-YY",
      "subject": "Subject Entity",
      "predicate": "observable_predicate",
      "object": "Object / State / Location",
      "fact_type": "OBSERVATION",
      "evidence_frame_ids": ["frame_cXXX_ZZZ"],
      "evidence_start_ms": 12345,
      "evidence_end_ms": 27345,
      "confidence": 0.95
    }
  ]
}
""".strip()


class PassAEventV3(BaseModel):
    event_id: str
    actor: str
    action: str
    target: Optional[str] = "None"
    object: Optional[str] = "None"
    description: str
    evidence_frame_ids: List[str] = Field(default_factory=list)
    evidence_start_ms: int
    evidence_end_ms: int
    temporal_precision_ms: int = 15000


class PassAFactV3(BaseModel):
    fact_id: str
    subject: str
    predicate: str
    object: str
    fact_type: str = "OBSERVATION"
    evidence_frame_ids: List[str] = Field(default_factory=list)
    evidence_start_ms: int
    evidence_end_ms: int
    confidence: float = 0.95


class PassAObservableOutputV3(BaseModel):
    summary: str
    location: str
    characters: List[str] = Field(default_factory=list)
    objects: List[str] = Field(default_factory=list)
    events: List[PassAEventV3] = Field(default_factory=list)
    facts: List[PassAFactV3] = Field(default_factory=list)


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1024 * 1024 * 16):
            h.update(chunk)
    return h.hexdigest()


def load_checkpoint() -> Dict[str, Any]:
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "dataset_version": DATASET_VERSION,
        "canonical_asset_sha256": CANONICAL_ASSET_SHA256,
        "model_id": MODEL_ID,
        "gcp_location": GCP_LOCATION,
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "preprocessing_version": PREPROCESSING_VERSION,
        "total_chunks": 43,
        "processed_chunks": {},
        "cumulative_prompt_tokens": 0,
        "cumulative_candidate_tokens": 0,
        "cumulative_cost_krw": 0.0,
        "total_model_calls": 0,
        "failed_chunks": {},
        "created_at": datetime.now(timezone.utc).isoformat(),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def save_checkpoint(data: Dict[str, Any]) -> None:
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def extract_full_chunk_frames(
    video_path: Path,
    chunk_idx: int,
    start_sec: int,
    duration_sec: int,
    output_dir: Path,
) -> List[Dict[str, Any]]:
    """
    Extracts keyframes across the entire 120s chunk at 15s intervals (0, 15, 30, 45, 60, 75, 90, 105, 119s).
    Returns list of frame metadata dictionaries.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    chunk_id = f"chunk-{chunk_idx+1:03d}"

    # Sample points across the chunk
    sample_offsets = []
    curr = 0
    while curr < duration_sec:
        sample_offsets.append(curr)
        curr += SAMPLING_INTERVAL_SEC
    # Ensure final boundary frame
    if duration_sec - 1 > sample_offsets[-1]:
        sample_offsets.append(duration_sec - 1)

    frame_records = []

    for offset in sample_offsets:
        abs_sec = start_sec + offset
        abs_ms = int(abs_sec * 1000)
        frame_id = f"frame_c{chunk_idx+1:03d}_{offset:03d}"
        frame_path = output_dir / f"{frame_id}.jpg"

        if not frame_path.exists():
            cmd = [
                FFMPEG_CMD,
                "-y",
                "-ss", str(abs_sec),
                "-i", str(video_path),
                "-vframes", "1",
                "-vf", "scale=640:-1",
                "-q:v", "4",
                str(frame_path),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        if frame_path.exists():
            frame_records.append({
                "frame_id": frame_id,
                "chunk_id": chunk_id,
                "chunk_idx": chunk_idx + 1,
                "relative_sec": offset,
                "absolute_sec": abs_sec,
                "absolute_timestamp_ms": abs_ms,
                "file_path": str(frame_path),
                "width": 640,
                "height": 486,
            })

    return frame_records


def format_timestamp_ms(ms: int) -> str:
    total_seconds = ms / 1000.0
    minutes = int(total_seconds // 60)
    seconds = total_seconds % 60
    return f"{minutes:02d}:{seconds:06.3f}"


async def run_v3_preprocessing():
    from google import genai
    from PIL import Image

    print("===================================================================")
    print(f"   STARTING V3 FULL-FILM NARRATIVE PREPROCESSING ({DATASET_VERSION})")
    print(f"   Model: {MODEL_ID} | Vertex Location: {GCP_LOCATION} | Project: {GCP_PROJECT}")
    print("===================================================================")

    if not CANONICAL_MEDIA_PATH.exists():
        raise FileNotFoundError(f"Canonical media not found at: {CANONICAL_MEDIA_PATH}")

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)
    checkpoint = load_checkpoint()

    total_chunks = (TOTAL_DURATION_SEC // CHUNK_DURATION_SEC) + (1 if TOTAL_DURATION_SEC % CHUNK_DURATION_SEC > 0 else 0)
    print(f"Total film duration: {TOTAL_DURATION_SEC}s ({total_chunks} chunks of {CHUNK_DURATION_SEC}s)")
    print(f"Already processed chunks: {len(checkpoint['processed_chunks'])} / {total_chunks}")

    all_frame_manifest: List[Dict[str, Any]] = []

    for chunk_idx in range(total_chunks):
        start_sec = chunk_idx * CHUNK_DURATION_SEC
        duration_sec = min(CHUNK_DURATION_SEC, TOTAL_DURATION_SEC - start_sec)
        if duration_sec <= 0:
            break

        chunk_id = f"chunk-{chunk_idx+1:03d}"
        scene_id = f"scene-tbw-c{chunk_idx+1:03d}"
        start_ms = start_sec * 1000
        end_ms = (start_sec + duration_sec) * 1000

        temp_dir = Path(f"scratch/v3_frames_{chunk_id}")
        frames = extract_full_chunk_frames(CANONICAL_MEDIA_PATH, chunk_idx, start_sec, duration_sec, temp_dir)
        all_frame_manifest.extend(frames)

        if chunk_id in checkpoint["processed_chunks"]:
            print(f"[{chunk_idx+1}/{total_chunks}] Skipping already processed {chunk_id} ({start_sec}s - {start_sec+duration_sec}s)")
            continue

        if checkpoint["cumulative_cost_krw"] > MAX_CUMULATIVE_COST_KRW:
            print(f"BUDGET CAP REACHED: Cumulative cost KRW {checkpoint['cumulative_cost_krw']:.2f} > KRW {MAX_CUMULATIVE_COST_KRW}")
            break

        print(f"\n--- Processing Chunk {chunk_idx+1}/{total_chunks}: {chunk_id} [{start_sec}s - {start_sec+duration_sec}s] ({len(frames)} frames) ---")

        # Build frame timestamp index for fallback grounding
        frame_time_map = {f["frame_id"]: f["absolute_timestamp_ms"] for f in frames}
        first_frame_ms = frames[0]["absolute_timestamp_ms"]
        last_frame_ms = frames[-1]["absolute_timestamp_ms"]

        # Build prompt with explicit frame labels and timestamps
        prompt_lines = [
            f"Film: 'The Bat Whispers (1930)'",
            f"Chunk ID: {chunk_id}",
            f"Chunk Timecode: {format_timestamp_ms(start_ms)} to {format_timestamp_ms(end_ms)} ({start_ms}ms - {end_ms}ms)",
            f"Attached Keyframes (sampled across entire 120s chunk):",
        ]
        images = []
        for f in frames:
            prompt_lines.append(f"- FRAME `{f['frame_id']}` @ {format_timestamp_ms(f['absolute_timestamp_ms'])} ({f['absolute_timestamp_ms']} ms)")
            images.append(Image.open(f["file_path"]))

        prompt_lines.append("\nPerform Pass A objective observable extraction according to the system instruction.")
        full_user_prompt = "\n".join(prompt_lines)

        contents = [PASS_A_SYSTEM_INSTRUCTION, full_user_prompt] + images

        # Call Gemini 3.6 Flash with bounded retry
        max_retries = 3
        success = False
        for attempt in range(1, max_retries + 1):
            try:
                t0 = time.perf_counter()
                response = client.models.generate_content(
                    model=MODEL_ID,
                    contents=contents,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": PassAObservableOutputV3,
                        "temperature": 0.1,
                    },
                )
                latency_ms = int((time.perf_counter() - t0) * 1000)

                # Token & Cost tracking (Gemini 3.6 Flash pricing: ~$0.075 / 1M prompt, ~$0.30 / 1M output)
                usage = response.usage_metadata
                prompt_tokens = getattr(usage, "prompt_token_count", 1500)
                cand_tokens = getattr(usage, "candidates_token_count", 500)
                call_cost_krw = ((prompt_tokens / 1_000_000 * 0.075) + (cand_tokens / 1_000_000 * 0.30)) * 1450.0

                parsed_json = json.loads(response.text)
                obs = PassAObservableOutputV3(**parsed_json)

                # Validate & enforce real temporal grounding (no synthetic frame 0 substitution)
                grounded_events = []
                for ev in obs.events:
                    if not ev.evidence_frame_ids:
                        raise ValueError(f"Event {ev.event_id} in {chunk_id} missing evidence_frame_ids citation")
                    valid_frame_times = [frame_time_map[fid] for fid in ev.evidence_frame_ids if fid in frame_time_map]
                    if not valid_frame_times:
                        raise ValueError(f"Event {ev.event_id} in {chunk_id} cited unknown frames: {ev.evidence_frame_ids}")
                    ev.evidence_start_ms = min(valid_frame_times)
                    ev.evidence_end_ms = max(valid_frame_times)
                    ev.temporal_precision_ms = max(1000, ev.evidence_end_ms - ev.evidence_start_ms + 15000)

                    grounded_events.append({
                        "event_id": ev.event_id,
                        "movie_id": "the-bat-whispers-1930",
                        "scene_id": scene_id,
                        "dataset_version": DATASET_VERSION,
                        "timestamp_ms": ev.evidence_start_ms,
                        "evidence_start_ms": ev.evidence_start_ms,
                        "evidence_end_ms": ev.evidence_end_ms,
                        "actor": ev.actor,
                        "action": ev.action,
                        "target": ev.target or "None",
                        "object": ev.object or "None",
                        "description": ev.description,
                        "evidence_frame_ids": [fid for fid in ev.evidence_frame_ids if fid in frame_time_map],
                        "temporal_precision_ms": ev.temporal_precision_ms,
                    })

                grounded_facts = []
                for fct in obs.facts:
                    if not fct.evidence_frame_ids:
                        raise ValueError(f"Fact {fct.fact_id} in {chunk_id} missing evidence_frame_ids citation")
                    valid_frame_times = [frame_time_map[fid] for fid in fct.evidence_frame_ids if fid in frame_time_map]
                    if not valid_frame_times:
                        raise ValueError(f"Fact {fct.fact_id} in {chunk_id} cited unknown frames: {fct.evidence_frame_ids}")
                    fct.evidence_start_ms = min(valid_frame_times)
                    fct.evidence_end_ms = max(valid_frame_times)

                    grounded_facts.append({
                        "fact_id": fct.fact_id,
                        "movie_id": "the-bat-whispers-1930",
                        "scene_id": scene_id,
                        "dataset_version": DATASET_VERSION,
                        "timestamp_ms": fct.evidence_start_ms,
                        "evidence_start_ms": fct.evidence_start_ms,
                        "evidence_end_ms": fct.evidence_end_ms,
                        "subject": fct.subject,
                        "predicate": fct.predicate,
                        "object": fct.object,
                        "fact_type": fct.fact_type,
                        "evidence_frame_ids": [fid for fid in fct.evidence_frame_ids if fid in frame_time_map],
                        "confidence": fct.confidence,
                    })

                chunk_record = {
                    "chunk_id": chunk_id,
                    "scene_id": scene_id,
                    "movie_id": "the-bat-whispers-1930",
                    "dataset_version": DATASET_VERSION,
                    "start_ms": start_ms,
                    "end_ms": end_ms,
                    "duration_ms": end_ms - start_ms,
                    "summary": obs.summary,
                    "location": obs.location,
                    "characters": obs.characters,
                    "objects": obs.objects,
                    "events": grounded_events,
                    "facts": grounded_facts,
                    "evidence_frame_count": len(frames),
                    "model_id": MODEL_ID,
                    "latency_ms": latency_ms,
                    "prompt_tokens": prompt_tokens,
                    "candidate_tokens": cand_tokens,
                    "cost_krw": call_cost_krw,
                }

                checkpoint["processed_chunks"][chunk_id] = chunk_record
                checkpoint["cumulative_prompt_tokens"] += prompt_tokens
                checkpoint["cumulative_candidate_tokens"] += cand_tokens
                checkpoint["cumulative_cost_krw"] += call_cost_krw
                checkpoint["total_model_calls"] += 1
                save_checkpoint(checkpoint)

                print(f"[OK] [{chunk_id}] Success: Location='{obs.location}', Characters={obs.characters[:3]}, Events={len(grounded_events)}, Facts={len(grounded_facts)}, Latency={latency_ms}ms, Cost=KRW {call_cost_krw:.3f}")
                success = True
                break

            except Exception as e:
                print(f"[FAIL] [{chunk_id}] Attempt {attempt}/{max_retries} failed: {e}")
                time.sleep(2 * attempt)

        if not success:
            checkpoint["failed_chunks"][chunk_id] = f"Failed after {max_retries} attempts"
            save_checkpoint(checkpoint)
            print(f"ERROR: Chunk {chunk_id} permanently failed!")

    # Save frame manifest
    FRAME_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FRAME_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(all_frame_manifest, f, indent=2)

    print("\n===================================================================")
    print(f"   V3 FULL-FILM PREPROCESSING COMPLETED!")
    print(f"   Processed Chunks: {len(checkpoint['processed_chunks'])} / {total_chunks}")
    print(f"   Total Model Calls: {checkpoint['total_model_calls']}")
    print(f"   Cumulative Prompt Tokens: {checkpoint['cumulative_prompt_tokens']}")
    print(f"   Cumulative Output Tokens: {checkpoint['cumulative_candidate_tokens']}")
    print(f"   Total Cumulative Cost: KRW {checkpoint['cumulative_cost_krw']:.2f}")
    print("===================================================================")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_v3_preprocessing())
