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
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

V3_CHECKPOINT_PATH = Path(r"data/manifests/preprocessing_checkpoint_v3_gemini36.json")
GLOBAL_V3_OUTPUT_PATH = Path(r"data/manifests/global_narrative_pass_v3.json")

MODEL_ID = "gemini-3.6-flash"
GCP_LOCATION = "global"
GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "")
DATASET_VERSION = "the_bat_whispers_v3_gemini36"

GLOBAL_WINDOW_SYSTEM_INSTRUCTION = """
You are a global narrative memory analyzer for 1930 cinematic mystery narratives.
You will be provided with sequential objective scene summaries, present characters, key events, and factual states from a section of 'The Bat Whispers (1930)'.

Analyze the narrative arc, character relationships, and evolving factual states across this section.
DO NOT assume unrevealed future outcomes. Focus on how audience knowledge and apparent character motivations evolve strictly within this section.

Output strict JSON matching schema:
{
  "section_title": "Descriptive title of this dramatic section",
  "key_characters": ["Character 1", "Character 2"],
  "apparent_plot_developments": [
    "Plot development 1",
    "Plot development 2"
  ],
  "knowledge_states": [
    {
      "state_id": "ks-unique-id",
      "entity": "Character Name",
      "believed_fact": "What this character/audience currently believes",
      "grounded_chunk_id": "chunk-XXX",
      "timestamp_ms": 12345
    }
  ]
}
""".strip()


class KnowledgeStateItem(BaseModel):
    state_id: str
    entity: str
    believed_fact: str
    grounded_chunk_id: str
    timestamp_ms: int


class GlobalSectionOutput(BaseModel):
    section_title: str
    key_characters: List[str] = Field(default_factory=list)
    apparent_plot_developments: List[str] = Field(default_factory=list)
    knowledge_states: List[KnowledgeStateItem] = Field(default_factory=list)


async def run_global_narrative_pass_v3():
    from google import genai

    print("===================================================================")
    print(f"   STARTING V3 GLOBAL NARRATIVE PASS ({DATASET_VERSION})")
    print(f"   Model: {MODEL_ID} | Vertex: {GCP_LOCATION} | Project: {GCP_PROJECT}")
    print("===================================================================")

    if not V3_CHECKPOINT_PATH.exists():
        raise FileNotFoundError(f"V3 Checkpoint not found at {V3_CHECKPOINT_PATH}. Run full_film_preprocessing_v3.py first.")

    with open(V3_CHECKPOINT_PATH, "r", encoding="utf-8") as f:
        checkpoint = json.load(f)

    chunks = checkpoint.get("processed_chunks", {})
    if not chunks:
        raise ValueError("No processed chunks found in checkpoint.")

    sorted_chunk_keys = sorted(chunks.keys(), key=lambda k: int(k.split("-")[1]))
    total_chunks = len(sorted_chunk_keys)
    print(f"Loaded {total_chunks} SceneGroups covering full film timeline.")

    client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

    # Hierarchical 3-Act window processing (NO truncation, ALL 43 chunks covered)
    # Act 1: chunks 1..14 (0s - 1680s)
    # Act 2: chunks 15..29 (1680s - 3480s)
    # Act 3: chunks 30..43 (3480s - 5119s)
    windows = [
        ("Act 1: Bank Heist, Panic, and Arrival at Oakdale Manor", sorted_chunk_keys[:14]),
        ("Act 2: Manor Murders, The Bat's Infiltration, and Investigation", sorted_chunk_keys[14:29]),
        ("Act 3: Midnight Search, Secret Compartments, and Climax Confrontation", sorted_chunk_keys[29:]),
    ]

    all_section_results = []
    all_knowledge_states = []

    for act_title, act_chunks in windows:
        print(f"\n--- Analyzing {act_title} ({len(act_chunks)} chunks: {act_chunks[0]} to {act_chunks[-1]}) ---")
        act_summary_lines = [f"### Section: {act_title}"]
        for cid in act_chunks:
            cdata = chunks[cid]
            act_summary_lines.append(
                f"- [{cid}] ({cdata['start_ms']}ms - {cdata['end_ms']}ms) Location: '{cdata.get('location', 'Unknown')}': "
                f"{cdata['summary']} Characters: {', '.join(cdata.get('characters', []))}"
            )

        prompt_content = "\n".join(act_summary_lines)
        contents = [
            GLOBAL_WINDOW_SYSTEM_INSTRUCTION,
            prompt_content,
        ]

        response = client.models.generate_content(
            model=MODEL_ID,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_schema": GlobalSectionOutput,
                "temperature": 0.1,
            },
        )

        parsed = json.loads(response.text)
        section_out = GlobalSectionOutput(**parsed)
        print(f"[OK] Section Analyzed: '{section_out.section_title}', {len(section_out.apparent_plot_developments)} plot points, {len(section_out.knowledge_states)} knowledge states")

        all_section_results.append(section_out.model_dump())
        for ks in section_out.knowledge_states:
            all_knowledge_states.append({
                "state_id": ks.state_id,
                "movie_id": "the-bat-whispers-1930",
                "dataset_version": DATASET_VERSION,
                "entity": ks.entity,
                "believed_fact": ks.believed_fact,
                "grounded_chunk_id": ks.grounded_chunk_id,
                "timestamp_ms": ks.timestamp_ms,
            })

    final_global_manifest = {
        "dataset_version": DATASET_VERSION,
        "movie_id": "the-bat-whispers-1930",
        "model_id": MODEL_ID,
        "total_chunks_analyzed": total_chunks,
        "sections": all_section_results,
        "knowledge_states": all_knowledge_states,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    GLOBAL_V3_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GLOBAL_V3_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_global_manifest, f, indent=2)

    print("\n===================================================================")
    print(f"   V3 GLOBAL NARRATIVE PASS COMPLETED!")
    print(f"   Total Sections: {len(all_section_results)}")
    print(f"   Total Knowledge States Extracted: {len(all_knowledge_states)}")
    print(f"   Saved to: {GLOBAL_V3_OUTPUT_PATH}")
    print("===================================================================")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_global_narrative_pass_v3())
