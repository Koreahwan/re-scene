"""
Reframe Phase 1 Live Independent Audit Regression Tests
Verifies fixes for defects B01, B02, and B05 identified during independent audit:
- B01: Magazine comments must be masked for unverified comments and non-articles rejected with 404
- B02: Magazine comment creation must return 201 with proper data (not 500)
- B05: AI inspection must fail-closed on empty JSON or nonexistent works/reveals
"""
import uuid
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import app
from src.reframe.shared.config import settings
from src.reframe.shared.database import SyncSessionLocal
from src.reframe.community.models import Post, PostVersion, Comment
from src.reframe.identity.models import PUBLIC_AUTHOR_USER_ID
from src.reframe.ai.inspection import spoiler_inspection_service, cost_service


@pytest.fixture
def article(monkeypatch):
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    pid, vid = uuid.uuid4(), uuid.uuid4()
    with SyncSessionLocal() as db:
        db.add(Post(
            id=pid,
            author_id=PUBLIC_AUTHOR_USER_ID,
            content_type='MAGAZINE_ARTICLE',
            status='PUBLISHED',
            current_version_id=vid,
            ai_disclosure='AI_ASSISTED'
        ))
        db.flush()
        db.add(PostVersion(
            id=vid,
            post_id=pid,
            version_no=1,
            title='Audit-only editorial fixture',
            body_markdown='{"paragraphs":["Audit fixture"]}',
            body_sanitized_html='<p>Audit fixture</p>',
            created_by=PUBLIC_AUTHOR_USER_ID
        ))
        db.commit()
    return str(pid)


def test_magazine_comment_create_returns_success(article):
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(f'/api/v1/magazine/{article}/comments', json={'body_markdown': 'AUDIT_ONLY_CREATE_SENTINEL'})
        with SyncSessionLocal() as db:
            persisted = db.execute(select(Comment).where(Comment.post_id == uuid.UUID(article))).scalars().all()
        assert r.status_code == 201, f'Expected 201, actual={r.status_code}; persisted={len(persisted)}; body={r.text}'
        res_data = r.json()
        assert res_data.get("status") == "SUCCESS"
        assert "id" in res_data.get("data", {})


def test_magazine_unverified_comment_is_masked(article):
    marker = 'AUDIT_ONLY_UNVERIFIED_SECRET_SENTINEL'
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post(f'/api/v1/community/posts/{article}/comments', json={'body_markdown': marker})
        assert r.status_code == 201, r.text
        standard = client.get(f'/api/v1/community/posts/{article}/comments')
        magazine = client.get(f'/api/v1/magazine/{article}/comments')
        assert marker not in standard.text, standard.text
        assert marker not in magazine.text, magazine.text


def test_magazine_route_rejects_non_article(monkeypatch):
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    marker = 'AUDIT_NON_ARTICLE_SECRET_SENTINEL'
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.post('/api/v1/community/posts', json={
            'content_type': 'FAN_THEORY',
            'title': 'Audit-only review',
            'body_markdown': 'Fixture',
            'work_id': 'the-bat-whispers-1930',
            'edition_id': 'tbw-fullscreen-archive'
        })
        assert r.status_code == 201, r.text
        pid = r.json()['data']['post_id']
        r = client.post(f'/api/v1/community/posts/{pid}/comments', json={'body_markdown': marker})
        assert r.status_code == 201, r.text
        wrong = client.get(f'/api/v1/magazine/{pid}/comments')
        assert wrong.status_code == 404 and marker not in wrong.text, wrong.text


@pytest.mark.parametrize('work,reply', [
    ('the-bat-whispers-1930', '{}'),
    ('citizen-kane-1941', '{"contains_spoiler":false,"detected_reveal_id":"NONEXISTENT_EVIDENCE","detected_cutoff_ms":0,"confidence":1,"flags":[]}')
])
@pytest.mark.asyncio
async def test_unsubstantiated_model_output_cannot_be_verified(monkeypatch, work, reply):
    monkeypatch.setattr(settings, 'PAID_CALLS_ENABLED', True)
    monkeypatch.setattr(settings, 'SPEND_KILL_SWITCH_ACTIVE', False)
    for method in ['reserve_budget', 'check_budget_preflight', 'record_usage', 'settle_reservation', 'cancel_reservation']:
        monkeypatch.setattr(cost_service, method, AsyncMock())
    prompts = []

    def fake_generate(**kwargs):
        prompts.append(kwargs['contents'])
        return NS(text=reply, usage_metadata=NS(prompt_token_count=12, candidates_token_count=5))

    monkeypatch.setattr(spoiler_inspection_service, '_get_gemini_client', lambda: NS(models=NS(generate_content=fake_generate)))
    result = await spoiler_inspection_service.inspect_content(
        db=NS(),
        subject_id=uuid.uuid4(),
        version_no=1,
        raw_text='Audit fixture',
        work_id=work,
        edition_id='audit-edition'
    )
    assert result.status != 'VERIFIED', f'No validated evidence; actual={result.model_dump()}'
