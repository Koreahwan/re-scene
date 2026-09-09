from typing import List, Tuple, Dict, Any


def get_entity_candidates_sql() -> str:
    """
    Returns the parameterized SQL template for entity-based scene retrieval in ClickHouse.
    Mandates: movie_id match, start_ms < cutoff_ms, and character/object entity match.
    """
    return """
SELECT
    scene_id,
    movie_id,
    start_ms,
    end_ms,
    location,
    characters,
    objects,
    summary,
    dialogue_summary
FROM reframe.scenes
WHERE movie_id = {movie_id:String}
  AND start_ms < {cutoff_ms:UInt64}
  AND (
      hasAny(characters, {entities:Array(String)})
      OR hasAny(objects, {entities:Array(String)})
  )
ORDER BY start_ms ASC
LIMIT {limit:UInt32};
""".strip()


def get_events_for_scenes_sql() -> str:
    """
    Returns SQL template to fetch supporting events for retrieved pre-cutoff scenes.
    """
    return """
SELECT
    event_id,
    movie_id,
    scene_id,
    timestamp_ms,
    actor,
    action,
    target,
    object,
    event_type,
    description,
    entities,
    confidence
FROM reframe.events
WHERE movie_id = {movie_id:String}
  AND timestamp_ms < {cutoff_ms:UInt64}
  AND scene_id IN ({scene_ids:Array(String)})
ORDER BY timestamp_ms ASC;
""".strip()


def get_facts_for_scenes_sql() -> str:
    """
    Returns SQL template to fetch supporting facts for retrieved pre-cutoff scenes.
    """
    return """
SELECT
    fact_id,
    movie_id,
    scene_id,
    timestamp_ms,
    subject,
    predicate,
    object,
    fact_type,
    confidence,
    evidence_event_ids
FROM reframe.facts
WHERE movie_id = {movie_id:String}
  AND timestamp_ms < {cutoff_ms:UInt64}
  AND scene_id IN ({scene_ids:Array(String)})
ORDER BY timestamp_ms ASC;
""".strip()


def build_entity_query_params(
    movie_id: str,
    cutoff_ms: int,
    entities: List[str],
    limit: int = 30,
) -> Dict[str, Any]:
    """Generates strictly typed query parameters for entity search."""
    return {
        "movie_id": movie_id,
        "cutoff_ms": int(cutoff_ms),
        "entities": [str(e) for e in entities],
        "limit": int(min(limit, 50)),
    }
