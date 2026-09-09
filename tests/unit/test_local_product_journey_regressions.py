"""Regression checks from the real local-browser journey audit (no live models)."""
import os
import subprocess
import sys
import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from apps.api.main import app
from src.reframe.shared.database import AsyncSessionLocal
from src.reframe.community.models import Post, Claim, ClaimVersion
from src.reframe.spoiler.models import SpoilerScope
from src.reframe.proof.store import is_verified_canonical_proof
from src.reframe.narrative.theory_engine import theory_engine
from scripts.local_product_profile import claim_database, deny_outbound
from scripts.local_process import process_identity, stop_owned_process


@pytest_asyncio.fixture
async def local_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post('/api/v1/auth/dev-login', json={
            'role': 'USER', 'email': f'journey-{uuid.uuid4().hex}@example.test'})
        assert response.status_code == 200
        client.headers['X-CSRF-Token'] = response.json()['data']['csrf_token']
        yield client


@pytest.mark.parametrize('mode', ['PIPELINE_VALIDATED_TEST_DOUBLE', 'SEED_FIXTURE', 'OFFLINE_CANONICAL_FIXTURE', 'DEVELOPMENT_PREVIEW'])
def test_no_synthetic_generation_mode_can_be_canon(mode):
    assert not is_verified_canonical_proof({'proof_id': 'new-test-id', 'generation_mode': mode,
        'human_review_status': 'VERIFIED_CANONICAL', 'trust_namespace': 'CANONICAL_VERIFIED',
        'proof_type': 'KNOWLEDGE_LEAK', 'counterfactual_results': {'wrong_reveal_delta': -.85}})


def test_keyword_search_is_not_semantic_validation():
    for text in ['fireplace painting detective mantel', '벽난로 위 그림은 숨겨진 방과 관련이 있을까?']:
        result = theory_engine.validate_theory({'theory_text': text, 'target_reveal_id': 'reveal-secret-room-location'})
        assert result.validation_mode == 'LOCAL_KEYWORD_RETRIEVAL'
        assert result.validation_verdict in ('RELATED_EVIDENCE', 'NO_MATCH')
        assert result.uncertainty is None
        assert result.counterfactual_results == {'status': 'NOT_RUN'}
        assert result.live_model_used is False


def test_launcher_refuses_unowned_existing_database(tmp_path):
    existing = tmp_path / 'existing.db'
    existing.write_bytes(b'user data')
    with pytest.raises(ValueError, match='unowned'):
        claim_database(existing)
    assert existing.read_bytes() == b'user data'
    owned = claim_database(tmp_path / 'owned.db')
    owned.write_bytes(b'local data')
    assert claim_database(owned) == owned


def test_outbound_dns_and_service_connections_fail_closed():
    for event, args in [('socket.getaddrinfo', ('example.com', 443)), ('socket.connect', (None, ('127.0.0.1', 6379))), ('socket.sendto', ())]:
        with pytest.raises(PermissionError):
            deny_outbound(event, args)


@pytest.mark.skipif(os.name != 'nt', reason='Windows verified-handle implementation')
def test_stop_checks_process_birth_before_termination():
    process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'], creationflags=subprocess.CREATE_NO_WINDOW)
    receipt = process_identity(process.pid)
    try:
        wrong = dict(receipt, created=receipt['created'] + 1)
        with pytest.raises(ValueError, match='identity changed'):
            stop_owned_process(wrong)
        assert process.poll() is None
        stop_owned_process(receipt)
        process.wait(timeout=5)
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


@pytest.mark.asyncio
async def test_video_disabled_for_guest_and_account_but_scene_index_remains(local_user):
    url = '/api/v1/films/the-bat-whispers-1930/media'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as guest:
        assert (await guest.get(url, headers={'Range': 'bytes=0-1023'})).status_code == 410
    media = await local_user.get(url, headers={'Range': 'bytes=0-1023'})
    assert media.status_code == 410
    assert 'content-range' not in media.headers
    assert (await local_user.get(url, headers={'Range': 'bytes=999999999999-'})).status_code == 410
    assert (await local_user.get('/api/v1/films/unrelated-film/media')).status_code == 410
    assert (await local_user.get('/api/v1/films/the-bat-whispers-1930/scene-index')).json()['data'] == []


@pytest.mark.asyncio
async def test_draft_revision_claim_scope_and_single_publish(local_user):
    response = await local_user.post('/api/v1/theories', json={'title': 'First title',
        'hypothesis_explanation': 'The fireplace contains a mechanism.', 'target_reveal_id': 'reveal-anderson-identity'})
    assert response.status_code == 201
    theory_id = response.json()['data']['theory_id']
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as guest:
        assert (await guest.get(f'/api/v1/community/posts/{theory_id}')).status_code == 404
    body = 'The painting above the fireplace is examined from a stepladder.'
    change = {'title': 'Edited title', 'hypothesis_explanation': body, 'target_reveal_id': 'reveal-secret-room-location'}
    revision = await local_user.patch(f'/api/v1/theories/{theory_id}', json=change)
    assert revision.status_code == 200
    assert revision.json()['data']['version_no'] == 2
    assert (await local_user.patch(f'/api/v1/theories/{theory_id}', json=change)).json()['data']['version_no'] == 2
    draft = (await local_user.get(f'/api/v1/theories/{theory_id}')).json()['data']
    assert draft['body_markdown'] == body and draft['target_reveal_id'] == 'reveal-secret-room-location'
    for _ in range(2):
        published = await local_user.post(f'/api/v1/theories/{theory_id}/publish')
        assert published.status_code == 200
        assert published.json()['data']['theory_id'] == theory_id
    async with AsyncSessionLocal() as session:
        post = await session.get(Post, uuid.UUID(theory_id))
        scope = await session.get(SpoilerScope, post.spoiler_scope_id)
        assert scope.required_reveal_ids == ['reveal-secret-room-location']
        claim = (await session.execute(select(Claim).where(Claim.post_id == post.id))).scalar_one()
        claim_version = await session.get(ClaimVersion, claim.current_version_id)
        assert claim_version.text == body
    detail = (await local_user.get(f'/api/v1/community/posts/{theory_id}')).json()['data']
    assert detail['title'] == 'Edited title' and detail['claims'][0]['text'] == body
    assert detail['likes_count'] == 0
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://testserver') as guest:
        locked = (await guest.get(f'/api/v1/community/posts/{theory_id}')).json()['data']
        assert locked['is_locked'] is True and isinstance(locked['safe_preview'], dict)
        assert 'body_markdown' not in locked and 'claims' not in locked
        assert 'validation_summary' not in locked and 'counterclaims' not in locked
    listed = (await local_user.get('/api/v1/community/posts?work_id=the-bat-whispers-1930')).json()['data']
    assert sum(post['post_id'] == theory_id for post in listed) == 1


@pytest.mark.asyncio
async def test_theory_search_requires_reveal_progress(local_user):
    created = await local_user.post('/api/v1/theories', json={'title': 'Locked theory',
        'hypothesis_explanation': 'The detective examines the fireplace.', 'target_reveal_id': 'reveal-secret-room-location'})
    theory_id = created.json()['data']['theory_id']
    response = await local_user.post('/api/v1/theory-runs', json={'theory_id': theory_id,
        'target_reveal_id': 'reveal-secret-room-location'}, headers={'Idempotency-Key': uuid.uuid4().hex})
    assert response.status_code == 403
