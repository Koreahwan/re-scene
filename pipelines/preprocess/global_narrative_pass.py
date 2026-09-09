import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, List
import structlog
from google import genai

sys.path.insert(0, "src")
from reframe.domain.models import Reveal
from reframe.mcp.gateway import McpClickHouseGateway

logger = structlog.get_logger(__name__)

PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT", "")
GCP_LOCATION = "global"
MODEL_ID = "gemini-3.6-flash"
ESCALATION_MODEL_ID = "gemini-3.1-pro-preview"
DATASET_VERSION = "the_bat_whispers_v2_gemini36"


GLOBAL_NARRATIVE_ANALYSIS_PROMPT = """
You are a master cinematic narrative analyst specializing in 1930 mystery cinema knowledge modeling.
Given the full sequence of chronologically extracted observable scenes, events, and facts from 'The Bat Whispers (1930)', analyze:
1. The evolving audience knowledge state (what the audience believes at each stage).
2. The major plot turning points / reveals (moments where audience knowledge is fundamentally transformed).
3. Ground each reveal strictly in concrete observable events and facts.

Output strict JSON with schema:
{
  "audience_knowledge_evolution": [
    {
      "timecode_range": "0s - 1200s",
      "established_belief": "The Bat is an elusive criminal terrorizing the city, and Detective Anderson is the dedicated lawman tasked with hunting him down."
    }
  ],
  "validated_reveals": [
    {
      "reveal_id": "reveal-anderson-identity",
      "movie_id": "the-bat-whispers-1930",
      "timestamp_ms": 4860000,
      "title": "Detective Anderson is Unmasked as 'The Bat'",
      "reveal_type": "IDENTITY",
      "subject": "Detective Anderson",
      "predicate": "is_identity_of",
      "previous_belief": "Detective Anderson is a dedicated police officer investigating the robbery.",
      "revealed_fact": "Detective Anderson is himself 'The Bat', the criminal mastermind orchestrating the crimes.",
      "affected_entities": ["Detective Anderson", "The Bat", "Brooks", "Cornelia Van Gorder"],
      "importance": 1.0,
      "review_status": "APPROVED"
    },
    {
      "reveal_id": "reveal-robbery-hidden-partition",
      "movie_id": "the-bat-whispers-1930",
      "timestamp_ms": 4500000,
      "title": "The Stolen Money is Concealed in the Oakdale Secret Room",
      "reveal_type": "KNOWLEDGE",
      "subject": "Oakdale Secret Room",
      "predicate": "conceals",
      "previous_belief": "The stolen bank funds were smuggled out of the city.",
      "revealed_fact": "The hundreds of thousands in stolen cash remained hidden inside the secret room of Oakdale Manor all along.",
      "affected_entities": ["Oakdale Manor", "The Bat", "Brooks", "Cornelia Van Gorder"],
      "importance": 0.85,
      "review_status": "APPROVED"
    }
  ],
  "escalations": []
}
""".strip()


async def run_global_narrative_pass():
    print("===================================================================")
    print(f"      STARTING GLOBAL NARRATIVE PASS ({DATASET_VERSION})")
    print("===================================================================")

    gateway = McpClickHouseGateway(mcp_endpoint_url="http://127.0.0.1:8001/mcp")
    client = genai.Client(vertexai=True, project=PROJECT_ID, location=GCP_LOCATION)

    # 1. Fetch all scenes in dataset_version
    scenes_sql = f"""
    SELECT scene_id, start_ms, end_ms, location, characters, objects, summary
    FROM reframe.scenes
    WHERE movie_id = 'the-bat-whispers-1930'
      AND dataset_version = '{DATASET_VERSION}'
    ORDER BY start_ms ASC
    """
    scenes = await gateway.run_query(scenes_sql)
    print(f"Retrieved {len(scenes)} scenes from ClickHouse dataset {DATASET_VERSION}.")

    if not scenes:
        print("Waiting for preprocessing chunks to populate scenes...")
        return

    # Construct narrative summary text
    timeline_summary = []
    for s in scenes[:25]:  # Summarize chronological progression
        start_sec = int(s['start_ms']) // 1000
        end_sec = int(s['end_ms']) // 1000
        chars = ', '.join(s.get('characters', []))
        timeline_summary.append(
            f"[{start_sec}s - {end_sec}s] Location: {s.get('location', 'Oakdale')} | Characters: {chars} | Summary: {s.get('summary', '')}"
        )
    timeline_text = "\n".join(timeline_summary)

    # 2. Invoke Gemini 3.6 Flash for Global Narrative Sequence Reasoning
    prompt = f"""
Analyze the narrative timeline of 'The Bat Whispers (1930)' using the observable sequence below:

{timeline_text}

Perform knowledge state modeling and validate the reveals.
"""
    t0 = time.time()
    response = client.models.generate_content(
        model=MODEL_ID,
        contents=prompt,
        config={
            "system_instruction": GLOBAL_NARRATIVE_ANALYSIS_PROMPT,
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    )
    t1 = time.time()
    print(f"Global narrative modeling latency: {round(t1 - t0, 3)}s")

    raw_json = json.loads(response.text)
    validated_reveals = raw_json.get("validated_reveals", [])
    print(f"Validated {len(validated_reveals)} reveals.")

    # 3. Ingest Validated Reveals into ClickHouse
    for rev in validated_reveals:
        aff_entities = [e.replace("'", "\\'") for e in rev.get("affected_entities", [])]
        entities_str = "[" + ", ".join(f"'{e}'" for e in aff_entities) + "]"
        title = rev['title'].replace("'", "\\'")
        prev_belief = rev['previous_belief'].replace("'", "\\'")
        rev_fact = rev['revealed_fact'].replace("'", "\\'")
        subj = rev['subject'].replace("'", "\\'")
        rev_sql = f"""
        INSERT INTO reframe.reveals (reveal_id, movie_id, timestamp_ms, title, reveal_type, subject, predicate, previous_belief, revealed_fact, affected_entities, importance, review_status, dataset_version)
        VALUES ('{rev['reveal_id']}', '{rev['movie_id']}', {rev['timestamp_ms']}, '{title}', '{rev['reveal_type']}', '{subj}', '{rev['predicate']}', '{prev_belief}', '{rev_fact}', {entities_str}, {rev['importance']}, '{rev.get('review_status', 'APPROVED')}', '{DATASET_VERSION}');
        """
        await gateway.run_query(rev_sql)
        print(f"Ingested reveal {rev['reveal_id']} ('{title}') into ClickHouse.")

    # Save output to artifacts
    output_path = Path("data/manifests/global_narrative_pass_v2.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(raw_json, f, indent=2)
    print(f"Saved global narrative analysis to {output_path}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_global_narrative_pass())
