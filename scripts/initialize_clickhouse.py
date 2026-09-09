"""Initialize approved narrative data without deleting or overwriting records.

Default is an offline plan. --apply uses a separate bootstrap account; normal
application reads continue through official MCP with a read-only account.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.reframe.catalog.clickhouse_publication import canonical_json, publication_rows, sql_text


TABLE_KEYS = {
    'films': ('movie_id',), 'scenes': ('movie_id', 'scene_id'),
    'events': ('movie_id', 'event_id'), 'facts': ('movie_id', 'fact_id'),
    'reveals': ('movie_id', 'reveal_id'), 'knowledge_states': ('movie_id', 'knowledge_id'),
    'analysis_segments': ('publication_id', 'work_id', 'edition_id', 'segment_id'),
    'analysis_publications': ('publication_id', 'work_id', 'edition_id'),
}


def canonical_rows(export):
    version, film = export['dataset_version'], export['film']
    work_id = film['movie_id']
    if work_id != 'the-bat-whispers-1930' or not version or not export['scenes']:
        raise ValueError('Unexpected canonical dataset')
    result = {'films': [{k: film[k] for k in ('movie_id', 'title', 'year', 'runtime_ms', 'language', 'rights_status', 'source_url')}
                       | {'dataset_version': version}], 'scenes': [], 'events': [], 'facts': [],
              'reveals': [], 'knowledge_states': []}
    fields = {
        'scenes': ('scene_id', 'movie_id', 'dataset_version', 'start_ms', 'end_ms', 'location', 'characters', 'objects', 'summary', 'dialogue_summary', 'source_chunk_id', 'extraction_version'),
        'events': ('event_id', 'movie_id', 'scene_id', 'dataset_version', 'timestamp_ms', 'evidence_start_ms', 'evidence_end_ms', 'actor', 'action', 'target', 'object', 'event_type', 'description', 'entities', 'confidence', 'evidence_frame_ids', 'evidence_frame_timestamps_ms', 'extraction_version'),
        'facts': ('fact_id', 'movie_id', 'scene_id', 'dataset_version', 'timestamp_ms', 'evidence_start_ms', 'evidence_end_ms', 'subject', 'predicate', 'object', 'fact_type', 'confidence', 'evidence_frame_ids', 'evidence_frame_timestamps_ms', 'evidence_event_ids', 'extraction_version'),
        'reveals': ('reveal_id', 'movie_id', 'timestamp_ms', 'title', 'reveal_type', 'subject', 'predicate', 'previous_belief', 'revealed_fact', 'affected_entities', 'evidence_scene_ids', 'importance', 'dataset_version'),
    }
    for table, columns in fields.items():
        for source in export[table]:
            row = {k: source[k] for k in columns}
            if row['movie_id'] != work_id or row['dataset_version'] != version:
                raise ValueError('Mixed canonical work or dataset version')
            if table == 'reveals':
                row['review_status'] = 'NOT_REVIEWED'
            result[table].append(row)
    scenes = {row['scene_id']: row for row in result['scenes']}
    chunks = {row['source_chunk_id']: row['scene_id'] for row in result['scenes']}
    for row in result['scenes']:
        if not 0 <= row['start_ms'] < row['end_ms'] <= film['runtime_ms']:
            raise ValueError('Canonical scene outside edition bounds')
    for table in ('events', 'facts'):
        for row in result[table]:
            scene = scenes[row['scene_id']]
            if not scene['start_ms'] <= row['timestamp_ms'] <= scene['end_ms']:
                raise ValueError('Canonical event outside its scene')
            if not 0 <= row['evidence_start_ms'] <= row['evidence_end_ms'] <= film['runtime_ms']:
                raise ValueError('Canonical evidence outside edition bounds')
    for source in export['knowledge_states']:
        scene_id = chunks.get(source['grounded_chunk_id'], source['grounded_chunk_id'])
        if scene_id not in scenes or source['movie_id'] != work_id or source['dataset_version'] != version:
            raise ValueError('Unresolved knowledge-state provenance')
        result['knowledge_states'].append({
            'movie_id': work_id, 'knowledge_id': source['state_id'], 'subject': source['entity'],
            'predicate': 'believes', 'object': source['believed_fact'], 'status': 'INFERRED',
            'valid_from_ms': source['timestamp_ms'], 'valid_until_ms': None,
            'source_scene_id': scene_id, 'confidence': 0.0, 'extraction_version': 'v3-import',
            'dataset_version': version,
        })
    return result


def build_plan(root=ROOT):
    package = json.loads((root / 'data/production/selected_portion_analysis.json').read_text(encoding='utf-8'))
    publication_id, publications, segments = publication_rows(package)
    export = json.loads((root / 'data/production/v3_dataset_export.json').read_text(encoding='utf-8'))
    rows = canonical_rows(export)
    rows.update(analysis_segments=segments, analysis_publications=publications)
    for table, records in rows.items():
        keys = [tuple(row[key] for key in TABLE_KEYS[table]) for row in records]
        if len(set(keys)) != len(keys):
            raise ValueError('Duplicate input keys in ' + table)
    return publication_id, rows


def same_value(actual, expected):
    if isinstance(expected, float):
        return isinstance(actual, (int, float)) and math.isclose(actual, expected, rel_tol=1e-6, abs_tol=1e-6)
    return actual == expected


def existing_rows(client, table, columns):
    if table not in TABLE_KEYS or any(not column.replace('_', '').isalnum() for column in columns):
        raise ValueError('Invalid bootstrap schema identifier')
    result = client.query(f"SELECT {', '.join(columns)} FROM reframe.{table} FINAL")
    # clickhouse-connect returns FixedString hashes as bytes, unlike the MCP
    # JSON transport. Normalize those UTF-8 identifiers before key comparison.
    return [dict(zip(columns, [value.decode('utf-8') if isinstance(value, bytes) else value for value in values]))
            for values in result.result_rows]


def missing_rows(client, table, records):
    columns = list(records[0])
    existing = existing_rows(client, table, columns)
    key = lambda row: tuple(row[k] for k in TABLE_KEYS[table])
    lookup = {}
    for row in existing:
        if key(row) in lookup:
            raise ValueError('Ambiguous existing keys in ' + table)
        lookup[key(row)] = row
    missing = []
    for record in records:
        previous = lookup.get(key(record))
        if previous is None:
            missing.append(record)
        elif any(not same_value(previous[column], record[column]) for column in columns):
            raise ValueError('Existing data conflicts with approved input in ' + table + '; nothing will be overwritten')
    return missing


def apply_plan(client, rows, root=ROOT):
    # Apply only CREATE statements. The historical schema's passwordless user
    # block is deliberately excluded: operator-created identities stay intact.
    for name in ('001_initial_schema.sql', '002_analysis_publication.sql'):
        sql = (root / 'db/clickhouse/ddl' / name).read_text(encoding='utf-8')
        sql = '\n'.join(line for line in sql.splitlines() if not line.lstrip().startswith('--'))
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement.startswith(('CREATE DATABASE IF NOT EXISTS ', 'CREATE TABLE IF NOT EXISTS ')):
                client.command(statement)
            elif statement and not statement.startswith(('CREATE USER ', 'GRANT ')):
                raise ValueError('Unexpected bootstrap statement')
    # Check every table before inserting any row. Existing records are preserved.
    pending = {table: missing_rows(client, table, records) for table, records in rows.items()}
    receipt = {}
    for table, records in rows.items():
        missing = pending[table]
        if missing:
            columns = list(records[0])
            client.insert('reframe.' + table, [[row[column] for column in columns] for row in missing], column_names=columns)
        if missing_rows(client, table, records):
            raise RuntimeError('Post-insert verification failed for ' + table)
        receipt[table] = {'expected_records': len(records), 'inserted_records': len(missing), 'verified': True}
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Explicitly create missing schema and insert approved data')
    args = parser.parse_args()
    publication_id, rows = build_plan()
    report = {'publication_id': publication_id, 'records': {k: len(v) for k, v in rows.items()},
              'data_deletions': 0, 'model_calls': 0, 'mode': 'PLAN_ONLY'}
    if args.apply:
        from src.reframe.shared.config import settings
        import clickhouse_connect
        user, password = os.getenv('CLICKHOUSE_BOOTSTRAP_USER'), os.getenv('CLICKHOUSE_BOOTSTRAP_PASSWORD')
        if not user or not password or user == settings.CLICKHOUSE_USER:
            raise ValueError('Set a separate CLICKHOUSE_BOOTSTRAP_USER and CLICKHOUSE_BOOTSTRAP_PASSWORD')
        if settings.CLICKHOUSE_DATABASE != 'reframe':
            raise ValueError('This schema targets the reframe database only')
        client = clickhouse_connect.get_client(host=settings.CLICKHOUSE_HOST, port=settings.CLICKHOUSE_PORT,
            username=user, password=password, secure=settings.CLICKHOUSE_SECURE, verify=settings.CLICKHOUSE_VERIFY,
            connect_timeout=10, send_receive_timeout=30)
        try:
            report['tables'] = apply_plan(client, rows)
            report['mode'] = 'APPLIED_AND_VERIFIED'
        finally:
            client.close()
    print(canonical_json(report))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # Never echo connection exceptions that may carry credential material.
        print(json.dumps({'status': 'FAILED', 'error_type': type(exc).__name__, 'model_calls': 0}), file=sys.stderr)
        raise SystemExit(1)
