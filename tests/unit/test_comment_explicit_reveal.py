"""Spoiler consent is version-scoped, independent of paid inspection availability."""
import uuid
from types import SimpleNamespace

import pytest
import httpx
from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import Response

from apps.api.routers.auth import ContentUnlockRequest, unlock_content
from apps.api.routers.community import get_comment_detail
from src.reframe.community.comment_visibility import comment_masked
from src.reframe.community.models import Comment, Post
from src.reframe.community.service import CommunityService
from src.reframe.identity.auth import ViewerContext, get_viewer_context
from src.reframe.shared.config import settings
from src.reframe.identity.models import BrowserContentUnlock, User
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.shared.exceptions import ReframeException

STATUSES = ['CURATED_DEMO_NO_PLOT', 'UNVERIFIED_CALLS_DISABLED', 'PENDING',
            'FAILED', 'UNVERIFIED_BUDGET_EXCEEDED', 'UNVERIFIED_EVIDENCE_INSUFFICIENT',
            'AI_SPOILER', 'AI_CLEAR', 'VERIFIED']


@pytest.mark.parametrize('status', STATUSES)
def test_only_matching_comment_version_consent_reveals(status):
    comment = SimpleNamespace(id=uuid.uuid4(), author_id=uuid.uuid4(), version_no=2,
                              inspection_status=status, contains_spoilers=True, author_cutoff_ms=1000)
    viewer = ViewerContext()
    assert comment_masked(comment, viewer, True)
    viewer.explicit_unlocks = [f'COMMENT:{comment.id}:1', 'POST:unrelated:2']
    assert comment_masked(comment, viewer, True)
    viewer.explicit_unlocks = [f'COMMENT:{comment.id}:2']
    assert not comment_masked(comment, viewer, True)
    assert comment_masked(comment, ViewerContext(), True)


@pytest.mark.asyncio
@pytest.mark.parametrize('status', STATUSES)
async def test_list_detail_unlock_and_reply_isolation(status):
    async with AsyncSessionLocal() as db:
        owner = User(id=uuid.uuid4(), email_normalized=f'{uuid.uuid4()}@example.test')
        db.add(owner)
        await db.flush()
        post = Post(id=uuid.uuid4(), author_id=owner.id, status='PUBLISHED',
                    work_id='the-bat-whispers-1930', edition_id='tbw-fullscreen-archive')
        db.add(post)
        await db.flush()
        root = Comment(id=uuid.uuid4(), post_id=post.id, author_id=owner.id,
                       body_markdown='Hidden root text', body_sanitized_html='<p>Hidden root text</p>',
                       contains_spoilers=True, inspection_status=status)
        db.add(root)
        await db.flush()
        reply = Comment(id=uuid.uuid4(), post_id=post.id, author_id=owner.id, parent_comment_id=root.id,
                        body_markdown='Hidden reply text', body_sanitized_html='<p>Hidden reply text</p>',
                        contains_spoilers=True, inspection_status=status)
        db.add(reply)
        await db.commit()
        viewer = ViewerContext(session_id=f'reveal-test-{uuid.uuid4()}')
        rows = await CommunityService.list_comments(db, post.id, viewer)
        assert all(c['is_spoiler_masked'] and c['can_reveal'] for c in rows)
        assert all('Hidden' not in c['body_markdown'] for c in rows)
        for comment in [root, reply]:
            detail = await get_comment_detail(comment.id, viewer=viewer, db=db)
            assert detail['data']['is_spoiler_masked'] and detail['data']['can_reveal']
            result = await unlock_content(ContentUnlockRequest(content_type='COMMENT', content_id=comment.id, version_no=1), viewer, None, db)
            assert result['data']['unlocked']
            stored = (await db.scalars(select(BrowserContentUnlock).where(BrowserContentUnlock.session_id == viewer.session_id))).all()
            viewer.explicit_unlocks = [f'{u.content_type}:{u.content_id}:{u.version_no}' for u in stored]
            detail = await get_comment_detail(comment.id, viewer=viewer, db=db)
            assert detail['data']['body_markdown'] == comment.body_markdown
            assert detail['data']['inspection_status'] == status
            if comment is root:
                rows = await CommunityService.list_comments(db, post.id, viewer)
                assert next(c for c in rows if c['comment_id'] == str(reply.id))['is_spoiler_masked']
        reply.version_no = 2
        await db.commit()
        assert (await get_comment_detail(reply.id, viewer=viewer, db=db))['data']['is_spoiler_masked']
        with pytest.raises(ReframeException):
            await unlock_content(ContentUnlockRequest(content_type='COMMENT', content_id=reply.id, version_no=1), viewer, None, db)
        reply.status = 'DELETED'
        await db.commit()
        with pytest.raises(ReframeException):
            await unlock_content(ContentUnlockRequest(content_type='COMMENT', content_id=reply.id, version_no=2), viewer, None, db)
        root.status = 'REMOVED'
        await db.commit()
        with pytest.raises(ReframeException):
            await unlock_content(ContentUnlockRequest(content_type='COMMENT', content_id=root.id, version_no=1), viewer, None, db)
        root.status = 'PUBLISHED'
        post.status = 'REMOVED'
        await db.commit()
        with pytest.raises(ReframeException):
            await unlock_content(ContentUnlockRequest(content_type='COMMENT', content_id=root.id, version_no=1), viewer, None, db)


@pytest.mark.asyncio
async def test_guest_reloads_consent_without_author_privileges(monkeypatch):
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', False)
    session_id = f'guest-reveal-{uuid.uuid4()}'
    content_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        db.add(BrowserContentUnlock(session_id=session_id, content_type='COMMENT', content_id=content_id, version_no=1))
        await db.commit()
        request = Request({'type': 'http', 'headers': [(b'cookie', f'{settings.BROWSER_SESSION_COOKIE_NAME}={session_id}'.encode())]})
        viewer = await get_viewer_context(request, Response(), db)
        assert viewer.explicit_unlocks == [f'COMMENT:{content_id}:1']
        assert not viewer.is_authenticated and not viewer.is_public_author and not viewer.is_admin


@pytest.mark.asyncio
async def test_http_unlock_with_auth_cookie_still_requires_csrf():
    from apps.api.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost',
                                cookies={settings.SESSION_COOKIE_NAME: 'invalid-test-token'}) as client:
        response = await client.post('/api/v1/viewer/unlock', json={
            'content_type': 'COMMENT', 'content_id': str(uuid.uuid4()), 'version_no': 1})
        assert response.status_code == 403
