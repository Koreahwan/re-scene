import uuid

from fastapi.testclient import TestClient

from apps.api.main import app
from src.reframe.shared.config import settings


def test_guest_writes_require_login_but_viewing_progress_remains_available(monkeypatch):
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    with TestClient(app) as client:
        csrf = client.get('/api/v1/auth/csrf').json()['data']['csrf_token']
        client.headers['X-CSRF-Token'] = csrf
        profile = client.get('/api/v1/auth/me').json()
        assert profile['meta']['is_authenticated'] is False
        assert profile['data']['role'] == 'GUEST'
        review = {'content_type': 'FAN_THEORY', 'title': 'Guest review',
                  'body_markdown': 'Not allowed', 'work_id': 'the-bat-whispers-1930',
                  'edition_id': 'tbw-fullscreen-archive'}
        assert client.post('/api/v1/community/posts', json=review).status_code == 401
        assert client.post(f'/api/v1/community/posts/{uuid.uuid4()}/comments',
                           json={'body_markdown': 'Not allowed'}).status_code == 401
        assert client.delete(f'/api/v1/community/comments/{uuid.uuid4()}').status_code == 401
        for endpoint, payload in [
            ('/api/v1/proofs/test-proof/comments', {'body_markdown': 'Not allowed'}),
            ('/api/v1/proofs/test-proof/comments', {'body_markdown': 'Not allowed', 'parent_comment_id': str(uuid.uuid4())}),
            (f'/api/v1/magazine/{uuid.uuid4()}/comments', {'body_markdown': 'Not allowed'}),
            (f'/api/v1/magazine/{uuid.uuid4()}/comments', {'body_markdown': 'Not allowed', 'parent_comment_id': str(uuid.uuid4())}),
            ('/api/v1/theories', {'work_id': 'the-bat-whispers-1930', 'edition_id': 'tbw-fullscreen-archive',
                                  'target_reveal_id': 'reveal-anderson-identity', 'title': 'Guest analysis',
                                  'hypothesis_explanation': 'Not allowed'}),
            ('/api/v1/theory-runs', {'theory_id': str(uuid.uuid4()), 'target_reveal_id': 'reveal-anderson-identity'}),
            ('/api/v1/reframe-runs', {'reveal_id': 'reveal-anderson-identity'}),
            (f'/api/v1/community/posts/{uuid.uuid4()}/counterclaims', {}),
        ]:
            rejected = client.post(endpoint, json=payload)
            assert rejected.status_code == 401, (endpoint, rejected.text)
        progress = {'edition_id': 'tbw-fullscreen-archive', 'state': 'IN_PROGRESS',
                    'progress_ms': 12345, 'completed_reveal_ids': []}
        response = client.put('/api/v1/me/watch-progress/the-bat-whispers-1930', json=progress)
        assert response.status_code == 200, response.text
        detail = client.get('/api/v1/films/the-bat-whispers-1930').json()['data']
        assert detail['viewer_progress_ms'] == 12345
        scenes = client.get('/api/v1/films/the-bat-whispers-1930/scene-index')
        assert scenes.status_code == 200, scenes.text
        media = client.get('/api/v1/films/the-bat-whispers-1930/media', headers={'Range': 'bytes=0-9'})
        assert media.status_code == 410, media.text
        assert 'video/' not in media.headers.get('content-type', '')


def test_logged_in_progress_survives_another_browser_session(monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_DEV_MODE', True)
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    email = f'progress-{uuid.uuid4()}@example.test'
    with TestClient(app) as first, TestClient(app) as second:
        for client in (first, second):
            login = client.post('/api/v1/auth/dev-login', json={'email': email, 'role': 'USER'})
            assert login.status_code == 200, login.text
            client.headers['X-CSRF-Token'] = login.json()['data']['csrf_token']
        progress = {'edition_id': 'tbw-fullscreen-archive', 'state': 'IN_PROGRESS',
                    'progress_ms': 23456, 'completed_reveal_ids': []}
        saved = first.put('/api/v1/me/watch-progress/the-bat-whispers-1930', json=progress)
        assert saved.status_code == 200, saved.text
        detail = second.get('/api/v1/films/the-bat-whispers-1930').json()['data']
        assert detail['viewer_progress_ms'] == 23456
