"""Approved QA behavior, isolated DB and simulated provider only."""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from apps.api.main import app
from src.reframe.shared.database import AsyncSessionLocal, Base
from src.reframe.shared.config import settings
from src.reframe.community.models import Comment, Post
from src.reframe.identity.models import User
from src.reframe.community.moderation_models import CommentModerationJob as Job, CommentModerationBudget as Budget
from src.reframe.community.comment_moderation import reserve, process_one, ALLOWANCE, DAILY_LIMIT, TOTAL_LIMIT
from src.reframe.catalog.dataset_import import load_imported_datasets_from_disk
from tests.contract.test_approved_engagement import login, review_payload, POSTS


@pytest.mark.parametrize('work,edition', [('the-greene-murder-case-1929', 'gmc-archive-1929'), ('the-thirteenth-chair-1929', 'ttc-archive-1929')])
async def test_imported_film_spoiler_review_saves_edits_and_masks(work, edition):
    load_imported_datasets_from_disk(Path('data/production/imported_datasets'))
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as owner, AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as guest:
        await login(owner)
        payload = {**review_payload(), 'work_id': work, 'edition_id': edition}
        invalid = await owner.post(POSTS, json={**payload, 'edition_id': 'tbw-fullscreen-archive'})
        assert invalid.status_code == 422
        saved = await owner.post(POSTS, json=payload)
        assert saved.status_code == 201, saved.text
        post_id = saved.json()['data']['post_id']
        public = (await guest.get(f'{POSTS}/{post_id}')).json()['data']
        assert public['is_spoiler_masked'] and payload['body_markdown'] not in public.get('body_markdown', '')
        edited = await owner.patch(f'{POSTS}/{post_id}', json={'expected_version': 1, 'body_markdown': 'My revised spoiler review', 'contains_spoilers': True})
        assert edited.status_code == 200, edited.text
        assert (await owner.get(f'{POSTS}/{post_id}')).json()['data']['body_markdown'] == 'My revised spoiler review'


async def test_unverified_reply_requires_explicit_versioned_reveal():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as owner, AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as guest:
        await login(owner)
        await login(guest)
        post_id = (await owner.post(POSTS, json=review_payload())).json()['data']['post_id']
        url = f'{POSTS}/{post_id}/comments'
        root = (await owner.post(url, json={'body_markdown': 'A root spoiler', 'contains_spoilers': True})).json()['data']['comment_id']
        reply = (await owner.post(url, json={'body_markdown': 'A reply spoiler', 'parent_comment_id': root})).json()['data']['comment_id']
        payload = {'content_type': 'COMMENT', 'content_id': reply, 'version_no': 1}
        assert (await guest.get(f'{url}/{reply}')).json()['data']['is_spoiler_masked']
        revealed = await guest.post('/api/v1/viewer/unlock', json=payload)
        assert revealed.status_code == 200, revealed.text
        rows = (await guest.get(url)).json()['data']
        assert next(row for row in rows if row['comment_id'] == reply)['body_markdown'] == 'A reply spoiler'
        assert next(row for row in rows if row['comment_id'] == root)['is_spoiler_masked']
        await owner.patch(f'{url}/{reply}', json={'expected_version': 1, 'body_markdown': 'A newly edited spoiler'})
        assert (await guest.get(f'{url}/{reply}')).json()['data']['is_spoiler_masked']
        assert (await guest.post('/api/v1/viewer/unlock', json=payload)).status_code == 400
        assert (await guest.post('/api/v1/viewer/unlock', json={**payload, 'version_no': 2})).status_code == 200


async def test_top_box_exact_release_and_owner_permissions():
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as owner, AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as other:
        await login(owner); await login(other)
        target = await owner.get('/api/v1/community/top-box/65419000/review-target')
        assert target.status_code == 200, target.text
        data = target.json()['data']
        assert data['own_post_id'] is None
        payload = {**review_payload(), 'work_id': data['work_id'], 'edition_id': data['edition_id']}
        saved = await owner.post(POSTS, json=payload)
        assert saved.status_code == 201, saved.text
        post_id = saved.json()['data']['post_id']
        assert (await owner.get('/api/v1/community/top-box/65419000/review-target')).json()['data']['own_post_id'] == post_id
        assert (await owner.post(POSTS, json=payload)).status_code == 409
        assert (await other.delete(f'{POSTS}/{post_id}')).status_code == 403
        assert (await owner.patch(f'{POSTS}/{post_id}', json={'expected_version': 1, 'rating': 5})).status_code == 200
        mine = (await owner.get('/api/v1/me/reviews')).json()['data']
        assert mine[0]['title'] == data['title'] and 'pageId=65419000' in mine[0]['destination']
        assert (await owner.get('/api/v1/community/top-box/999999999/review-target')).status_code == 404
        assert (await owner.post(POSTS, json={**payload, 'work_id': 'topbox-Q1', 'edition_id': 'topbox-Q1-catalog'})).status_code == 422


@pytest_asyncio.fixture
async def moderation_db(tmp_path, monkeypatch):
    engine = create_async_engine(f'sqlite+aiosqlite:///{(tmp_path / "moderation.db").as_posix()}')
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(settings, 'COMMENT_MODERATION_ENABLED', True)
    monkeypatch.setattr(settings, 'COMMENT_MODERATION_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setattr(settings, 'SPEND_KILL_SWITCH_ACTIVE', False)
    monkeypatch.setattr(settings, 'EXECUTION_MODE', 'LIVE_GOOGLE')
    try: yield factory
    finally: await engine.dispose()


async def add_job(factory, *, marked=False):
    async with factory() as db:
        user = User(id=uuid.uuid4(), email_normalized=f'{uuid.uuid4()}@example.test')
        post = Post(id=uuid.uuid4(), author_id=user.id, work_id='the-bat-whispers-1930', edition_id='tbw-fullscreen-archive', status='PUBLISHED')
        comment = Comment(id=uuid.uuid4(), post_id=post.id, author_id=user.id, body_markdown='Original comment', body_sanitized_html='Original comment', contains_spoilers=marked, inspection_status='PENDING')
        job = Job(id=uuid.uuid4(), comment_id=comment.id, version_no=1)
        db.add_all([user, post, comment, job]); await db.commit()
        return job.id, comment.id


async def test_budget_concurrent_last_allowance_and_restart(moderation_db):
    factory = moderation_db
    jobs = [(await add_job(factory))[0] for _ in range(5)]
    now = datetime(2026, 9, 9, 4, tzinfo=timezone.utc)
    async with factory() as db:
        db.add_all([Budget(bucket='total', liability_micros=TOTAL_LIMIT - ALLOWANCE), Budget(bucket='2026-09-09', liability_micros=0)])
        await db.commit()
    async def attempt(job):
        async with factory() as db: return await reserve(db, job, now)
    assert sum(await asyncio.gather(*(attempt(job) for job in jobs))) == 1
    # A new session after restart sees the retained liability and cannot spend tomorrow either.
    async with factory() as db:
        assert (await db.get(Budget, 'total')).liability_micros == TOTAL_LIMIT
        assert not await reserve(db, jobs[-1], now + timedelta(days=1))


async def test_daily_boundary_is_seoul_and_does_not_reset_total(moderation_db):
    factory = moderation_db
    first, _ = await add_job(factory); second, _ = await add_job(factory)
    async with factory() as db:
        db.add(Budget(bucket='2026-09-09', liability_micros=DAILY_LIMIT))
        await db.commit()
        assert not await reserve(db, first, datetime(2026, 9, 9, 14, 59, tzinfo=timezone.utc))
        assert await reserve(db, second, datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc))
        assert (await db.get(Budget, 'total')).liability_micros == ALLOWANCE
        assert (await db.get(Budget, '2026-09-10')).liability_micros == ALLOWANCE


@pytest.mark.parametrize('verdict,expected', [('CLEAR', 'AI_CLEAR'), ('SPOILER', 'AI_SPOILER'), ('UNCERTAIN', 'UNVERIFIED_EVIDENCE_INSUFFICIENT')])
async def test_worker_keeps_text_and_author_flag(moderation_db, verdict, expected):
    factory = moderation_db
    job_id, comment_id = await add_job(factory, marked=True)
    async def provider(prompt): return verdict, 800
    assert await process_one(factory, provider)
    async with factory() as db:
        comment = await db.get(Comment, comment_id)
        assert comment.inspection_status == expected
        assert comment.contains_spoilers and comment.body_markdown == 'Original comment'
        assert (await db.get(Job, job_id)).actual_micros == 800
        assert (await db.get(Budget, 'total')).liability_micros == ALLOWANCE


async def test_failed_call_is_not_refunded_or_retried(moderation_db):
    factory = moderation_db
    job_id, comment_id = await add_job(factory)
    calls = []
    async def provider(prompt): calls.append(prompt); raise TimeoutError()
    assert await process_one(factory, provider)
    assert not await process_one(factory, provider)
    async with factory() as db:
        assert (await db.get(Comment, comment_id)).inspection_status == 'FAILED'
        assert (await db.get(Job, job_id)).reserved_micros == ALLOWANCE
        assert (await db.get(Budget, 'total')).liability_micros == ALLOWANCE
    assert len(calls) == 1


async def test_stale_result_and_kill_switch(moderation_db, monkeypatch):
    factory = moderation_db
    job_id, comment_id = await add_job(factory)
    async def provider(prompt):
        async with factory() as db:
            await db.execute(update(Comment).where(Comment.id == comment_id).values(version_no=2, inspection_status='PENDING'))
            await db.commit()
        return 'CLEAR', 800
    assert await process_one(factory, provider)
    async with factory() as db: assert (await db.get(Comment, comment_id)).inspection_status == 'PENDING'
    await add_job(factory)
    monkeypatch.setattr(settings, 'SPEND_KILL_SWITCH_ACTIVE', True)
    async def must_not_call(prompt): raise AssertionError('Killed dispatch must never call provider')
    assert not await process_one(factory, must_not_call)


async def test_sent_job_survives_restart_without_redispatch(moderation_db):
    factory = moderation_db
    job_id, comment_id = await add_job(factory)
    async with factory() as db:
        assert await reserve(db, job_id, datetime.now(timezone.utc) - timedelta(hours=1))
    calls = []
    async def provider(prompt): calls.append(prompt); return 'CLEAR', 800
    assert not await process_one(factory, provider)
    assert not calls
    async with factory() as db:
        assert (await db.get(Job, job_id)).status == 'SENT'
        assert (await db.get(Comment, comment_id)).inspection_status == 'PENDING'
        assert (await db.get(Budget, 'total')).liability_micros == ALLOWANCE


@pytest.mark.parametrize('case', ['valid', 'truncated', 'extra-field', 'missing-usage', 'unexpected-usage'])
async def test_provider_receipt_validation_without_network(monkeypatch, case):
    import httpx
    from src.reframe.community import comment_moderation as moderation
    monkeypatch.setattr(settings, 'COMMENT_MODERATION_API_KEY', 'test-only-not-a-real-key')
    body = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"verdict":"CLEAR"}'}]}}],
            'usageMetadata': {'promptTokenCount': 100, 'totalTokenCount': 120}}
    if case == 'truncated': body['candidates'][0]['finishReason'] = 'MAX_TOKENS'
    if case == 'extra-field': body['candidates'][0]['content']['parts'][0]['text'] = '{"verdict":"CLEAR","body":"rewritten"}'
    if case == 'missing-usage': body.pop('usageMetadata')
    if case == 'unexpected-usage': body['usageMetadata']['totalTokenCount'] = 1000000
    captured = []
    real_client = httpx.AsyncClient
    def handler(request):
        captured.append(request)
        return httpx.Response(200, json=body)
    monkeypatch.setattr(moderation.httpx, 'AsyncClient', lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw))
    if case == 'valid': assert await moderation.call_provider('Test data only') == ('CLEAR', 55)
    else:
        with pytest.raises(ValueError): await moderation.call_provider('Test data only')
    assert len(captured) == 1


@pytest.mark.parametrize('work,edition,count', [('the-greene-murder-case-1929', 'gmc-archive-1929', 6), ('the-thirteenth-chair-1929', 'ttc-archive-1929', 9)])
async def test_imported_actor_portraits_and_attribution(work, edition, count):
    import json
    load_imported_datasets_from_disk(Path('data/production/imported_datasets'))
    original = json.loads(Path(f'data/production/imported_datasets/{work}_{edition}.json').read_text(encoding='utf-8'))['film']
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get(f'/api/v1/films/{work}')
        assert response.status_code == 200, response.text
        cast = response.json()['data']['cast']
        assert [member['name_en'] for member in cast] == original['cast']
        assert len(cast) == count
        for member in cast:
            assert member['image'].startswith('/assets/catalog/cast/Q')
            assert Path('apps/web/public' + member['image']).is_file()
            assert member['image_source'].startswith('https://commons.wikimedia.org/wiki/File:')
        assert response.json()['data']['directors'] == original['directors']


def test_portrait_identity_matching_does_not_rewrite_other_credits():
    from src.reframe.catalog.featured_credits import featured_cast
    cast = [{'name_en': 'John Davidson', 'qid': 'Q1', 'role': 'Keep this role'}, 'Unknown actor']
    assert featured_cast('the-thirteenth-chair-1929', cast) == [cast[0], {'name_en': cast[1]}]
    assert featured_cast('other-film', cast) is cast
