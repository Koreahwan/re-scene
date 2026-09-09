"""Spoiler-checkbox isolation and explicit consent for shared-demo browsers."""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app
from src.reframe.identity.demo_account import DEMO_EMAIL, DEMO_PASSWORD
from src.reframe.shared.config import settings


@pytest.mark.parametrize('kind', ['review', 'comment', 'reply'])
def test_shared_demo_spoiler_checkbox_visibility(monkeypatch, kind):
    monkeypatch.setattr(settings, 'AUTH_DEMO_ACCOUNT_ENABLED', True)
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    with TestClient(app) as author, TestClient(app) as other_demo, TestClient(app) as guest:
        for client in (author, other_demo):
            login = client.post('/api/v1/auth/login', json={'email': DEMO_EMAIL, 'password': DEMO_PASSWORD})
            assert login.status_code == 200, login.text
            client.headers['X-CSRF-Token'] = login.json()['data']['csrf_token']
        base = '/api/v1/community/posts'
        review = author.post(base, json={
            'work_id': 'the-bat-whispers-1930', 'edition_id': 'tbw-fullscreen-archive',
            'content_type': 'REVIEW', 'title': 'Isolated spoiler checkbox audit',
            'body_markdown': 'QA review spoiler body', 'rating': 4, 'contains_spoilers': True})
        assert review.status_code == 201, review.text
        post_id = review.json()['data']['post_id']
        if kind != 'review':
            root = author.post(f'{base}/{post_id}/comments', json={
                'body_markdown': 'QA comment spoiler body', 'contains_spoilers': True})
            assert root.status_code == 201, root.text
            target_id = root.json()['data']['comment_id']
            if kind == 'reply':
                reply = author.post(f'{base}/{post_id}/comments', json={
                    'body_markdown': 'QA reply spoiler body', 'contains_spoilers': True,
                    'parent_comment_id': target_id})
                assert reply.status_code == 201, reply.text
                target_id = reply.json()['data']['comment_id']

        def read(client):
            if kind == 'review':
                rows = client.get(base, params={'work_id': 'the-bat-whispers-1930'}).json()['data']
                return next(row for row in rows if row['post_id'] == post_id)
            rows = client.get(f'{base}/{post_id}/comments').json()['data']
            return next(row for row in rows if row['comment_id'] == target_id)

        body = f'QA {kind} spoiler body'
        detail_url = f'{base}/{post_id}' if kind == 'review' else f'{base}/{post_id}/comments/{target_id}'
        for client in (author, guest, other_demo):
            for row in (read(client), client.get(detail_url).json()['data']):
                assert row['is_spoiler_masked'] and body not in row.get('body_markdown', '')
        assert read(author)['can_edit'] and read(other_demo)['can_edit']

        # Completing the film must not override an explicit spoiler checkbox.
        completed = other_demo.put('/api/v1/me/watch-progress/the-bat-whispers-1930', json={
            'edition_id': 'tbw-fullscreen-archive', 'state': 'COMPLETED',
            'progress_ms': 5119080, 'completed_reveal_ids': []})
        assert completed.status_code == 200, completed.text
        assert read(other_demo)['is_spoiler_masked']

        unlock = {'content_type': 'POST' if kind == 'review' else 'COMMENT',
                  'content_id': post_id if kind == 'review' else target_id, 'version_no': 1}
        response = other_demo.post('/api/v1/viewer/unlock', json=unlock)
        assert response.status_code == 200, response.text
        visible = read(other_demo)
        assert visible['body_markdown'] == body and visible['contains_spoilers']
        assert read(author)['is_spoiler_masked'] and read(guest)['is_spoiler_masked']
        if kind == 'reply':
            rows = other_demo.get(f'{base}/{post_id}/comments').json()['data']
            assert next(row for row in rows if row['comment_id'] == root.json()['data']['comment_id'])['is_spoiler_masked']

        # Editing creates a new protected version, without revoking editing rights.
        edit = author.patch(detail_url, json={'expected_version': 1, 'body_markdown': body + ' edited', 'contains_spoilers': True})
        assert edit.status_code == 200, edit.text
        assert read(other_demo)['is_spoiler_masked']
        assert other_demo.post('/api/v1/viewer/unlock', json=unlock).status_code == 400
        assert author.delete(f'{base}/{post_id}').status_code == 200
