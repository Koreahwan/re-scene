import json
import subprocess
from pathlib import Path
import structlog

logger = structlog.get_logger(__name__)


def execute_sql(sql: str) -> str:
    cmd = ["docker", "exec", "reframe-clickhouse", "clickhouse-client", "--query", sql]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"ClickHouse Error: {res.stderr}\nQuery: {sql}")
    return res.stdout


def initialize_and_load():
    logger.info("initializing_live_clickhouse_database")
    # 1. Create database
    execute_sql("CREATE DATABASE IF NOT EXISTS reframe;")

    # 2. Run DDL
    ddl_path = Path(__file__).resolve().parent.parent.parent / "db" / "clickhouse" / "ddl" / "001_initial_schema.sql"
    ddl_content = ddl_path.read_text(encoding="utf-8")
    
    statements = [s.strip() for s in ddl_content.split(";") if s.strip()]
    for stmt in statements:
        execute_sql(stmt)

    logger.info("ddl_schemas_applied_successfully")

    # 3. Load Fixture data into ClickHouse
    fixture_path = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "the_bat_whispers_golden.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ingest movie
    movie = data["movie"]
    movie_sql = f"""
    INSERT INTO reframe.films (movie_id, title, year, runtime_ms, language, rights_status, dataset_version)
    VALUES ('{movie['movie_id']}', '{movie['title']}', {movie['year']}, {movie['runtime_ms']}, '{movie['language']}', '{movie['rights_status']}', '{data['dataset_version']}');
    """
    execute_sql(movie_sql)

    # Ingest reveals
    for rev in data.get("reveals", []):
        aff_entities = [e.replace("'", "\\'") for e in rev.get("affected_entities", [])]
        entities_str = "[" + ", ".join(f"'{e}'" for e in aff_entities) + "]"
        title = rev['title'].replace("'", "\\'")
        prev_belief = rev['previous_belief'].replace("'", "\\'")
        rev_fact = rev['revealed_fact'].replace("'", "\\'")
        subj = rev['subject'].replace("'", "\\'")
        rev_sql = f"""
        INSERT INTO reframe.reveals (reveal_id, movie_id, timestamp_ms, title, reveal_type, subject, predicate, previous_belief, revealed_fact, affected_entities, importance, review_status)
        VALUES ('{rev['reveal_id']}', '{rev['movie_id']}', {rev['timestamp_ms']}, '{title}', '{rev['reveal_type']}', '{subj}', '{rev['predicate']}', '{prev_belief}', '{rev_fact}', {entities_str}, {rev['importance']}, '{rev.get('review_status', 'APPROVED')}');
        """
        execute_sql(rev_sql)

    # Ingest scenes
    for scn in data.get("scenes", []):
        chars_list = [c.replace("'", "\\'") for c in scn.get("characters", [])]
        chars = "[" + ", ".join(f"'{c}'" for c in chars_list) + "]"
        objs_list = [o.replace("'", "\\'") for o in scn.get("objects", [])]
        objs = "[" + ", ".join(f"'{o}'" for o in objs_list) + "]"
        loc = scn['location'].replace("'", "\\'")
        summary = scn['summary'].replace("'", "\\'")
        scn_sql = f"""
        INSERT INTO reframe.scenes (scene_id, movie_id, start_ms, end_ms, location, characters, objects, summary, dataset_version)
        VALUES ('{scn['scene_id']}', '{scn['movie_id']}', {scn['start_ms']}, {scn['end_ms']}, '{loc}', {chars}, {objs}, '{summary}', '{data['dataset_version']}');
        """
        execute_sql(scn_sql)

    # Ingest events
    for ev in data.get("events", []):
        ents_list = [e.replace("'", "\\'") for e in ev.get("entities", [])]
        ents = "[" + ", ".join(f"'{e}'" for e in ents_list) + "]"
        actor = ev['actor'].replace("'", "\\'")
        target = ev.get('target', '').replace("'", "\\'")
        obj = ev.get('object', '').replace("'", "\\'")
        desc = ev['description'].replace("'", "\\'")
        ev_sql = f"""
        INSERT INTO reframe.events (event_id, movie_id, scene_id, timestamp_ms, actor, action, target, object, description, entities)
        VALUES ('{ev['event_id']}', '{ev['movie_id']}', '{ev['scene_id']}', {ev['timestamp_ms']}, '{actor}', '{ev['action']}', '{target}', '{obj}', '{desc}', {ents});
        """
        execute_sql(ev_sql)

    # Ingest facts
    for fact in data.get("facts", []):
        fact_sql = f"""
        INSERT INTO reframe.facts (fact_id, movie_id, scene_id, timestamp_ms, subject, predicate, object, fact_type)
        VALUES ('{fact['fact_id']}', '{fact['movie_id']}', '{fact['scene_id']}', {fact['timestamp_ms']}, '{fact['subject'].replace("'", "\\'")}', '{fact['predicate']}', '{fact['object'].replace("'", "\\'")}', '{fact['fact_type']}');
        """
        execute_sql(fact_sql)

    # Verify counts
    film_count = execute_sql("SELECT count() FROM reframe.films").strip()
    scene_count = execute_sql("SELECT count() FROM reframe.scenes").strip()
    reveal_count = execute_sql("SELECT count() FROM reframe.reveals").strip()
    event_count = execute_sql("SELECT count() FROM reframe.events").strip()
    fact_count = execute_sql("SELECT count() FROM reframe.facts").strip()

    logger.info(
        "clickhouse_ingestion_complete",
        films=film_count,
        scenes=scene_count,
        reveals=reveal_count,
        events=event_count,
        facts=fact_count,
    )
    return {
        "films": int(film_count),
        "scenes": int(scene_count),
        "reveals": int(reveal_count),
        "events": int(event_count),
        "facts": int(fact_count),
    }


if __name__ == "__main__":
    res = initialize_and_load()
    print("LIVE CLICKHOUSE INGESTION SUMMARY:", json.dumps(res, indent=2))
