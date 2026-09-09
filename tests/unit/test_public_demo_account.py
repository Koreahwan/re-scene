from fastapi.testclient import TestClient

from apps.api.main import app
from src.reframe.identity.demo_account import DEMO_EMAIL, DEMO_PASSWORD, DEMO_USER_ID
from src.reframe.shared.config import settings


def test_demo_account_is_opt_in(monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_DEMO_ACCOUNT_ENABLED', False)
    with TestClient(app) as client:
        response = client.get('/api/v1/auth/demo-account')
        assert response.json()['data'] == {'enabled': False}
        assert response.headers['cache-control'] == 'no-store'


def test_shared_demo_login_and_browser_isolation(monkeypatch):
    monkeypatch.setattr(settings, 'AUTH_DEMO_ACCOUNT_ENABLED', True)
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    with TestClient(app) as first, TestClient(app) as second:
        config = first.get('/api/v1/auth/demo-account').json()['data']
        assert config['email'] == DEMO_EMAIL and config['password'] == DEMO_PASSWORD
        for client in (first, second):
            login = client.post('/api/v1/auth/login', json={'email': DEMO_EMAIL, 'password': DEMO_PASSWORD})
            assert login.status_code == 200, login.text
            client.headers['X-CSRF-Token'] = login.json()['data']['csrf_token']
            profile = client.get('/api/v1/auth/me').json()['data']
            assert profile['id'] == str(DEMO_USER_ID) and profile['role'] == 'USER'
        response = first.put('/api/v1/me/watch-progress/the-bat-whispers-1930', json={
            'edition_id': 'tbw-fullscreen-archive', 'state': 'IN_PROGRESS',
            'progress_ms': 12345, 'completed_reveal_ids': []})
        assert response.status_code == 200, response.text
        assert first.get('/api/v1/films/the-bat-whispers-1930').json()['data']['viewer_progress_ms'] == 12345
        assert second.get('/api/v1/films/the-bat-whispers-1930').json()['data']['viewer_progress_ms'] == 0
        for route in ('email-verification/request', 'password-reset/request'):
            blocked = first.post('/api/v1/auth/' + route, json={'email': DEMO_EMAIL})
            assert blocked.status_code == 409, blocked.text
        preferences = first.put('/api/v1/me/spoiler-preferences', json={
            'default_mode': 'ALL', 'mask_titles': False, 'mask_thumbnails': False, 'mask_comments': False})
        assert preferences.status_code == 409
        created = first.post('/api/v1/community/posts', json={
            'work_id': 'the-bat-whispers-1930', 'content_type': 'REVIEW',
            'title': 'Demo review', 'body_markdown': 'Test-owned review', 'rating': 4})
        assert created.status_code == 201, created.text
        post_id = created.json()['data']['post_id']
        posts = first.get('/api/v1/community/posts?work_id=the-bat-whispers-1930').json()['data']
        own = next(p for p in posts if p['post_id'] == post_id)
        assert own['can_edit'] is True and own['author_id'] == str(DEMO_USER_ID)
        edited = first.patch(f'/api/v1/community/posts/{post_id}', json={
            'expected_version': 1, 'body_markdown': 'Edited own review', 'author_cutoff_ms': 50000})
        assert edited.status_code == 200, edited.text
        updated = first.get(f'/api/v1/community/posts/{post_id}').json()['data']
        assert updated['body_markdown'] == 'Edited own review' and updated['visibility'] == 'VISIBLE'
        comment = first.post(f'/api/v1/community/posts/{post_id}/comments', json={'body_markdown': 'Own reply'})
        assert comment.status_code == 201, comment.text
        comments = first.get(f'/api/v1/community/posts/{post_id}/comments').json()['data']
        assert comments[0]['visibility'] == 'VISIBLE' and comments[0]['can_edit'] is True
        with TestClient(app) as guest:
            guest_posts = guest.get('/api/v1/community/posts?work_id=the-bat-whispers-1930').json()['data']
            public = next(p for p in guest_posts if p['post_id'] == post_id)
            assert public['can_edit'] is False and public['is_spoiler_masked'] is True
            assert 'body_markdown' not in public
        assert first.delete(f'/api/v1/community/posts/{post_id}').status_code == 200
        monkeypatch.setattr(settings, 'AUTH_DEMO_ACCOUNT_ENABLED', False)
        assert first.get('/api/v1/auth/me').json()['meta']['is_authenticated'] is False
        assert first.post('/api/v1/auth/login', json={'email': DEMO_EMAIL, 'password': DEMO_PASSWORD}).status_code == 401
