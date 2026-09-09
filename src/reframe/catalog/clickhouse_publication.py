"""Edition-pinned analysis delivery through the official ClickHouse MCP server.

Live reads never fall back to the bundled file. Only segments completed by the
viewer's saved progress are fetched, and every payload is checked against its
immutable publication manifest before it can reach the response.
"""
import hashlib
import json
import os
import re

from src.reframe.catalog.selected_portion import selected_portion_from_film, validate_package
from src.reframe.shared.config import settings
from src.reframe.spoiler.analysis_boundary import SEPARATED_ANALYSIS_EDITIONS, current_position


class NarrativeMemoryUnavailable(RuntimeError):
    """Safe public error; provider details and secrets must not reach the UI."""


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def content_hash(value):
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def sql_text(value):
    """Encode values, never identifiers, as SQL string expressions."""
    if not isinstance(value, str):
        raise ValueError('Expected a string SQL value')
    return "unhex('" + value.encode('utf-8').hex() + "')"


def publication_rows(package):
    """Build immutable rows without changing observation text or provenance."""
    validate_package(package)
    publication_id = content_hash({'version': package['version'], 'films': package['films']})
    publications, segments = [], []
    for film in package['films']:
        manifest = []
        for segment in film['segments']:
            digest = content_hash(segment)
            manifest.append({k: segment[k] for k in ('segment_id', 'start_ms', 'input_end_ms', 'available_after_ms')}
                            | {'payload_sha256': digest})
            segments.append({
                'publication_id': publication_id, 'work_id': film['work_id'], 'edition_id': film['edition_id'],
                'segment_id': segment['segment_id'], 'start_ms': segment['start_ms'],
                'input_end_ms': segment['input_end_ms'], 'available_after_ms': segment['available_after_ms'],
                'payload_sha256': digest, 'payload_json': canonical_json(segment),
            })
        metadata = {k: v for k, v in film.items() if k != 'segments'}
        metadata['segment_manifest'] = manifest
        publications.append({
            'publication_id': publication_id, 'work_id': film['work_id'], 'edition_id': film['edition_id'],
            'metadata_json': canonical_json(metadata), 'metadata_sha256': content_hash(metadata),
        })
    return publication_id, publications, segments


def official_gateway():
    if settings.CLICKHOUSE_ALLOW_WRITE_ACCESS or settings.CLICKHOUSE_DATABASE != 'reframe':
        raise NarrativeMemoryUnavailable('Read-only narrative memory configuration required')
    # Pydantic reads .env; the official server reads process environment. Bridge
    # only this application's database configuration before loading the server.
    for key in ('HOST', 'PORT', 'USER', 'PASSWORD', 'DATABASE', 'SECURE', 'VERIFY'):
        value = getattr(settings, 'CLICKHOUSE_' + key)
        os.environ['CLICKHOUSE_' + key] = str(value).lower() if isinstance(value, bool) else str(value)
    os.environ['CLICKHOUSE_ALLOW_WRITE_ACCESS'] = 'false'
    from src.reframe.mcp.gateway import OfficialMcpNarrativeMemoryGateway
    return OfficialMcpNarrativeMemoryGateway(timeout_seconds=settings.CLICKHOUSE_QUERY_TIMEOUT_SECONDS)


def validate_metadata(metadata, work_id, edition_id):
    if (metadata.get('work_id'), metadata.get('edition_id')) != (work_id, edition_id):
        raise ValueError('Publication edition mismatch')
    if type(metadata.get('runtime_ms')) is not int or metadata['runtime_ms'] <= 0:
        raise ValueError('Invalid publication runtime')
    manifest = metadata['segment_manifest']
    if not isinstance(manifest, list) or not manifest:
        raise ValueError('Missing segment manifest')
    ids, end = set(), -1
    for item in manifest:
        start, stop, available = (item[k] for k in ('start_ms', 'input_end_ms', 'available_after_ms'))
        if (any(type(v) is not int for v in (start, stop, available))
                or not 0 <= start < stop <= available <= metadata['runtime_ms'] or start < end
                or item['segment_id'] in ids or not re.fullmatch('[0-9a-f]{64}', item['payload_sha256'])):
            raise ValueError('Invalid segment manifest')
        ids.add(item['segment_id'])
        end = stop
    return metadata


async def read_selected_portion(work_id, edition_id, viewer, selected_ms=None, *, gateway=None):
    if (work_id, edition_id) not in SEPARATED_ANALYSIS_EDITIONS:
        return None, {}
    publication_id = settings.CLICKHOUSE_PUBLICATION_ID
    if not re.fullmatch('[0-9a-f]{64}', publication_id):
        raise NarrativeMemoryUnavailable('A pinned analysis publication is required')
    if selected_ms is not None and (type(selected_ms) is not int or selected_ms < 0):
        raise ValueError('Invalid selected position')
    try:
        gateway = gateway or official_gateway()
        where = (f'publication_id = {sql_text(publication_id)} AND work_id = {sql_text(work_id)} '
                 f'AND edition_id = {sql_text(edition_id)}')
        headers = await gateway.run_query(
            'SELECT metadata_json, toString(metadata_sha256) AS metadata_sha256 '
            'FROM reframe.analysis_publications FINAL WHERE ' + where + ' LIMIT 2')
        if len(headers) != 1:
            raise ValueError('Analysis publication is missing or ambiguous')
        metadata = json.loads(headers[0]['metadata_json'])
        if content_hash(metadata) != headers[0]['metadata_sha256']:
            raise ValueError('Publication metadata checksum mismatch')
        validate_metadata(metadata, work_id, edition_id)
        saved = min(metadata['runtime_ms'], current_position(viewer, work_id, edition_id))
        position = saved if selected_ms is None else min(saved, selected_ms)
        expected = {s['segment_id']: s for s in metadata['segment_manifest'] if s['available_after_ms'] <= position}
        rows = await gateway.run_query(
            'SELECT segment_id, start_ms, input_end_ms, available_after_ms, toString(payload_sha256) AS payload_sha256, payload_json '
            'FROM reframe.analysis_segments FINAL WHERE ' + where
            + f' AND available_after_ms > 0 AND available_after_ms <= {int(position)} ORDER BY start_ms LIMIT 1000')
        if len(rows) != len(expected):
            raise ValueError('Incomplete published observations')
        seen, segments = set(), []
        for row in rows:
            segment = json.loads(row['payload_json'])
            pin = expected.get(row['segment_id'])
            if (pin is None or row['segment_id'] in seen or row['payload_sha256'] != pin['payload_sha256']
                    or content_hash(segment) != pin['payload_sha256']):
                raise ValueError('Observation checksum mismatch')
            for key in ('segment_id', 'start_ms', 'input_end_ms', 'available_after_ms'):
                if row[key] != pin[key] or segment[key] != pin[key]:
                    raise ValueError('Observation boundary mismatch')
            if segment.get('source_scope') != 'INDEPENDENT_SEGMENT_ONLY':
                raise ValueError('Wrong input provenance')
            if not segment.get('summary') or not segment.get('observations'):
                raise ValueError('Missing observation content')
            for observation in segment['observations']:
                for key in ('timestamp_ms', 'evidence_end_ms'):
                    stamp = observation[key]
                    if type(stamp) is not int or not segment['start_ms'] <= stamp <= segment['input_end_ms']:
                        raise ValueError('Observation exceeds its input window')
            seen.add(row['segment_id'])
            segments.append(segment)
        data = selected_portion_from_film(metadata | {'segments': segments}, viewer, selected_ms)
        return data, {'source': 'CLICKHOUSE_MCP', 'tool': 'run_query', 'mcp_queries': 2,
                      'publication_id': publication_id, 'returned_segments': len(segments), 'paid_model_calls': 0}
    except NarrativeMemoryUnavailable:
        raise
    except Exception as exc:
        # Do not include SQL, connection strings, raw provider errors or payloads.
        raise NarrativeMemoryUnavailable('Published analysis is temporarily unavailable') from exc
