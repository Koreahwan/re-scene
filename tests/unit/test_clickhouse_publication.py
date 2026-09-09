"""MCP delivery parity, spoiler boundaries and append-only initialization."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from scripts.initialize_clickhouse import apply_plan, build_plan
from src.reframe.catalog.clickhouse_publication import (
    NarrativeMemoryUnavailable, content_hash, publication_rows, read_selected_portion, sql_text,
)
from src.reframe.catalog.selected_portion import load_package, selected_portion
from src.reframe.identity.auth import ViewerContext, get_viewer_context
from src.reframe.shared.config import settings


PACKAGE = load_package()
PUBLICATION, HEADERS, SEGMENTS = publication_rows(PACKAGE)


def viewer(film, position):
    return ViewerContext(work_progress_by_edition={f"{film['work_id']}:{film['edition_id']}": position})


def fake_gateway(film, position):
    header = next(row for row in HEADERS if row['work_id'] == film['work_id'])
    segments = [row for row in SEGMENTS if row['work_id'] == film['work_id'] and row['available_after_ms'] <= position]
    gateway = SimpleNamespace(run_query=AsyncMock(side_effect=[[deepcopy(header)], deepcopy(segments)]))
    return gateway


@pytest.mark.asyncio
@pytest.mark.parametrize('film', PACKAGE['films'], ids=lambda film: film['work_id'])
async def test_mcp_delivery_matches_existing_content_at_every_boundary(monkeypatch, film):
    monkeypatch.setattr(settings, 'CLICKHOUSE_PUBLICATION_ID', PUBLICATION)
    positions = {0, film['runtime_ms']//2, film['runtime_ms']}
    positions.update(segment['available_after_ms'] for segment in film['segments'])
    positions.update(segment['available_after_ms']-1 for segment in film['segments'])
    for position in sorted(positions):
        gateway = fake_gateway(film, position)
        data, meta = await read_selected_portion(film['work_id'], film['edition_id'], viewer(film, position), gateway=gateway)
        assert data == selected_portion(film['work_id'], film['edition_id'], viewer(film, position))
        assert meta['source'] == 'CLICKHOUSE_MCP' and meta['mcp_queries'] == 2
        assert meta['paid_model_calls'] == 0
        query = gateway.run_query.call_args_list[1].args[0]
        assert 'toString(metadata_sha256) AS metadata_sha256' in gateway.run_query.call_args_list[0].args[0]
        assert 'toString(payload_sha256) AS payload_sha256' in query
        assert f'available_after_ms <= {position}' in query
        assert sql_text(film['edition_id']) in query
        for segment in film['segments']:
            if segment['available_after_ms'] > position:
                assert segment['summary'] not in json.dumps(data)


@pytest.mark.asyncio
async def test_selected_position_and_unrelated_edition_cannot_bypass_saved_progress(monkeypatch):
    monkeypatch.setattr(settings, 'CLICKHOUSE_PUBLICATION_ID', PUBLICATION)
    film = PACKAGE['films'][0]
    for active in (viewer(film, 0), ViewerContext(work_progress_by_edition={'other:edition': film['runtime_ms']})):
        data, _ = await read_selected_portion(film['work_id'], film['edition_id'], active, film['runtime_ms'], gateway=fake_gateway(film, 0))
        assert not data['segments']
    gateway = fake_gateway(film, 0)
    data, _ = await read_selected_portion(film['work_id'], 'unknown', viewer(film, film['runtime_ms']), gateway=gateway)
    assert data is None
    gateway.run_query.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['missing_header', 'missing_segment', 'changed_payload', 'future_segment', 'duplicate', 'metadata_hash', 'provider_error'])
async def test_live_failures_never_fall_back_to_file(monkeypatch, failure):
    monkeypatch.setattr(settings, 'CLICKHOUSE_PUBLICATION_ID', PUBLICATION)
    film = PACKAGE['films'][0]
    position = film['segments'][0]['available_after_ms']
    header = deepcopy(HEADERS[0])
    rows = [deepcopy(SEGMENTS[0])]
    if failure == 'missing_header': header = None
    if failure == 'missing_segment': rows = []
    if failure == 'changed_payload': rows[0]['payload_json'] = rows[0]['payload_json'].replace('summary', 'tampered_summary', 1)
    if failure == 'future_segment': rows = [deepcopy(SEGMENTS[1])]
    if failure == 'duplicate': rows *= 2
    if failure == 'metadata_hash': header['metadata_sha256'] = '0'*64
    gateway = SimpleNamespace(run_query=AsyncMock(side_effect=RuntimeError('provider-secret') if failure == 'provider_error' else [[header] if header else [], rows]))
    with pytest.raises(NarrativeMemoryUnavailable) as exc:
        await read_selected_portion(film['work_id'], film['edition_id'], viewer(film, position), gateway=gateway)
    assert 'provider-secret' not in str(exc.value)


@pytest.mark.asyncio
async def test_unpinned_live_publication_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, 'CLICKHOUSE_PUBLICATION_ID', '')
    film = PACKAGE['films'][0]
    gateway = fake_gateway(film, 0)
    with pytest.raises(NarrativeMemoryUnavailable):
        await read_selected_portion(film['work_id'], film['edition_id'], viewer(film, 0), gateway=gateway)
    gateway.run_query.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_returns_safe_failure_instead_of_offline_success(monkeypatch):
    from apps.api.main import app
    from src.reframe.catalog import clickhouse_publication
    monkeypatch.setattr(settings, 'NARRATIVE_MEMORY_BACKEND', 'CLICKHOUSE_MCP')
    monkeypatch.setattr(clickhouse_publication, 'read_selected_portion', AsyncMock(side_effect=NarrativeMemoryUnavailable('secret')))
    original = dict(app.dependency_overrides)
    app.dependency_overrides[get_viewer_context] = lambda: ViewerContext()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost') as client:
            response = await client.get('/api/v1/films/the-bat-whispers-1930/selected-portion-analysis?edition_id=tbw-fullscreen-archive')
        assert response.status_code == 503
        assert 'secret' not in response.text
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(original)


class BootstrapClient:
    def __init__(self):
        self.rows = {}
        self.inserts = []
        self.commands = []

    def command(self, sql):
        assert sql.startswith(('CREATE DATABASE IF NOT EXISTS ', 'CREATE TABLE IF NOT EXISTS '))
        self.commands.append(sql)

    def query(self, sql):
        columns, table = sql.removeprefix('SELECT ').split(' FROM reframe.')
        table = table.removesuffix(' FINAL')
        columns = columns.split(', ')
        def transport(value, column):
            return value.encode('utf-8') if column in ('publication_id', 'metadata_sha256', 'payload_sha256') else value
        return SimpleNamespace(result_rows=[[transport(row[column], column) for column in columns] for row in self.rows.get(table, [])])

    def insert(self, table, values, column_names):
        table = table.removeprefix('reframe.')
        self.rows.setdefault(table, []).extend(dict(zip(column_names, row)) for row in values)
        self.inserts.append(table)


def test_bootstrap_loads_real_data_and_is_idempotent():
    publication, rows = build_plan()
    assert publication == PUBLICATION
    assert len(rows['scenes']) == 43 and len(rows['analysis_segments']) == 58
    client = BootstrapClient()
    first = apply_plan(client, rows)
    assert all(value['verified'] for value in first.values())
    assert client.inserts[-1] == 'analysis_publications'
    second = apply_plan(client, rows)
    assert sum(value['inserted_records'] for value in second.values()) == 0


def test_bootstrap_refuses_conflicting_data_before_any_insert():
    _, rows = build_plan()
    client = BootstrapClient()
    client.rows['facts'] = [deepcopy(rows['facts'][0])]
    client.rows['facts'][0]['object'] = 'EXISTING_USER_CONTENT'
    with pytest.raises(ValueError, match='conflicts'):
        apply_plan(client, rows)
    assert not client.inserts
    assert client.rows['facts'][0]['object'] == 'EXISTING_USER_CONTENT'


def test_sql_values_are_hex_encoded_not_interpolated():
    malicious = "'; DROP TABLE scenes; --"
    assert malicious not in sql_text(malicious)
    assert bytes.fromhex(sql_text(malicious)[7:-2]).decode() == malicious
