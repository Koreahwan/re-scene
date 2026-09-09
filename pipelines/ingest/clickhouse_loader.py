import json
from pathlib import Path
from typing import Dict, Any, List


def generate_insert_statements(fixture_path: Path) -> Dict[str, List[str]]:
    """
    Generates deterministic SQL INSERT statements from a structured fixture for ClickHouse ingestion.
    """
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    statements: Dict[str, List[str]] = {
        "films": [],
        "scenes": [],
        "events": [],
        "facts": [],
        "reveals": [],
    }

    # Film
    movie = data.get("movie", {})
    film_sql = f"""
    INSERT INTO reframe.films (movie_id, title, year, runtime_ms, language, rights_status, dataset_version)
    VALUES ('{movie.get('movie_id')}', '{movie.get('title')}', {movie.get('year')}, {movie.get('runtime_ms')}, '{movie.get('language')}', '{movie.get('rights_status')}', '{data.get('dataset_version', 'tbw-0001')}');
    """.strip()
    statements["films"].append(film_sql)

    # Scenes
    for s in data.get("scenes", []):
        chars = str(s.get("characters", [])).replace('"', "'")
        objs = str(s.get("objects", [])).replace('"', "'")
        summary_esc = s.get("summary", "").replace("'", "''")
        scene_sql = f"""
        INSERT INTO reframe.scenes (movie_id, scene_id, start_ms, end_ms, location, characters, objects, summary, dataset_version)
        VALUES ('{s.get('movie_id')}', '{s.get('scene_id')}', {s.get('start_ms')}, {s.get('end_ms')}, '{s.get('location')}', {chars}, {objs}, '{summary_esc}', '{data.get('dataset_version', 'tbw-0001')}');
        """.strip()
        statements["scenes"].append(scene_sql)

    return statements
