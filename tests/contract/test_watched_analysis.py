"""Opt-in analysis responses never include unwatched markers or locked placeholders."""
from unittest.mock import AsyncMock
from httpx import ASGITransport, AsyncClient
from apps.api.main import app
from src.reframe.identity.auth import get_viewer_context, ViewerContext
from src.reframe.proof.store import canonical_proof_store

FILM = 'the-bat-whispers-1930'
EDITION = 'tbw-fullscreen-archive'


async def test_watched_markers_use_saved_edition_progress_even_with_global_spoiler_override(monkeypatch):
    viewer = ViewerContext(spoiler_preferences={'default_mode': 'ALL'})
    monkeypatch.setitem(app.dependency_overrides, get_viewer_context, lambda: viewer)
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        path = f'/api/v1/films/{FILM}/reveals?watched_only=true'
        for progress, expected in [(0, 0), (2867000, 0), (3660000, 1), (5119080, 4)]:
            viewer.work_progress_by_edition = {f'{FILM}:{EDITION}': progress}
            response = await client.get(path)
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload['meta']['total'] == expected
            assert len(payload['data']) == expected
            assert all(max(item['timestamp_ms'], item['spoiler_cutoff_ms']) <= progress for item in payload['data'])
        viewer.work_progress_by_edition = {f'{FILM}:another-edition': 9999999}
        assert (await client.get(path)).json() == {'data': [], 'meta': {'total': 0}}


async def test_watched_proofs_omit_locked_future_missing_cutoff_and_other_edition_records(monkeypatch):
    viewer = ViewerContext(work_progress_by_edition={f'{FILM}:{EDITION}': 30000})
    monkeypatch.setitem(app.dependency_overrides, get_viewer_context, lambda: viewer)
    base = {'work_id': FILM, 'edition_id': EDITION, 'visibility': 'VISIBLE', 'spoiler_cutoff_ms': 20000}
    records = [{**base, 'proof_id': 'seen'}, {**base, 'proof_id': 'future', 'spoiler_cutoff_ms': 40000},
        {**base, 'proof_id': 'locked', 'is_locked': True}, {**base, 'proof_id': 'missing', 'spoiler_cutoff_ms': None},
        {**base, 'proof_id': 'other-edition', 'edition_id': 'other'}]
    monkeypatch.setattr(canonical_proof_store, 'get_proofs_for_reveal', AsyncMock(return_value=records))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get('/api/v1/reveals/test-reveal/proofs?watched_only=true')
        assert response.status_code == 200
        assert [record['proof_id'] for record in response.json()['data']] == ['seen']
        assert response.json()['meta']['total'] == 1
