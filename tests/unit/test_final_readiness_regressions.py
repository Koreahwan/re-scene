import json
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
from src.reframe.identity.models import PUBLIC_AUTHOR_USER_ID, User
from src.reframe.ai.inspection import spoiler_inspection_service, cost_service


@pytest.fixture
def author_client(monkeypatch):
    monkeypatch.setattr(settings, 'PHASE1_SUBMISSION_PROFILE_ENABLED', True)
    monkeypatch.setattr(settings, 'AUTH_DEV_MODE', True)
    with TestClient(app, raise_server_exceptions=False) as client:
        login = client.post('/api/v1/auth/dev-login', json={'email': f'review-{uuid.uuid4()}@example.test', 'role': 'USER'})
        assert login.status_code == 200, login.text
        client.headers['X-CSRF-Token'] = login.json()['data']['csrf_token']
        yield client


def post_payload(**kwargs):
    return {'content_type':'FAN_THEORY','title':'Isolated audit fixture','body_markdown':'Isolated audit fixture','work_id':'the-bat-whispers-1930','edition_id':'tbw-fullscreen-archive',**kwargs}


@pytest.mark.parametrize('method',['PATCH','DELETE'])
def test_user_cannot_modify_other_accounts_comments(author_client, method):
    pid = author_client.post('/api/v1/community/posts', json=post_payload()).json()['data']['post_id']
    uid, cid = uuid.uuid4(), uuid.uuid4()
    with SyncSessionLocal() as db:
        db.add(User(id=uid,email_normalized=f'{uid}@example.invalid',role='USER'))
        db.flush()
        db.add(Comment(id=cid,post_id=uuid.UUID(pid),author_id=uid,body_markdown='OTHER_ACCOUNT_CONTENT',body_sanitized_html='<p>OTHER_ACCOUNT_CONTENT</p>',status='PUBLISHED',version_no=1))
        db.commit()
    kwargs = {'json':{'body_markdown':'AUDIT_REPLACEMENT','expected_version':1}} if method=='PATCH' else {}
    response = author_client.request(method, f'/api/v1/community/comments/{cid}', **kwargs)
    with SyncSessionLocal() as db:
        c=db.get(Comment,cid)
        observed={'status':response.status_code,'body':c.body_markdown,'comment_status':c.status}
    assert response.status_code in (403,404), observed


def test_create_retry_same_idempotency_key_does_not_duplicate(author_client):
    key=str(uuid.uuid4())
    a=author_client.post('/api/v1/community/posts',headers={'Idempotency-Key':key},json=post_payload())
    b=author_client.post('/api/v1/community/posts',headers={'Idempotency-Key':key},json=post_payload())
    assert a.status_code==201 and b.status_code in (200,201),(a.text,b.text)
    assert a.json()['data']['post_id']==b.json()['data']['post_id'],(a.json(),b.json())


@pytest.mark.parametrize('method',['PATCH','DELETE'])
def test_internal_proof_anchor_is_not_a_public_review(author_client,method):
    pid=author_client.post('/api/v1/community/posts',json=post_payload()).json()['data']['post_id']
    with SyncSessionLocal() as db:
        db.get(Post,uuid.UUID(pid)).content_type='PROOF_ANALYSIS'
        db.commit()
    rows=author_client.get('/api/v1/community/posts?work_id=the-bat-whispers-1930').json()['data']
    assert pid not in [x['post_id'] for x in rows]
    kwargs={'json':{'body_markdown':'Must not change','expected_version':1}} if method=='PATCH' else {}
    response=author_client.request(method,'/api/v1/community/posts/'+pid,**kwargs)
    assert response.status_code==403,response.text


@pytest.mark.asyncio
async def test_disabled_inspection_creates_no_fake_run(monkeypatch):
    monkeypatch.setattr(settings,'PAID_CALLS_ENABLED',False)
    reserve=AsyncMock()
    monkeypatch.setattr(cost_service,'reserve_budget',reserve)
    result=await spoiler_inspection_service.inspect_content(db=NS(),subject_id=uuid.uuid4(),version_no=1,raw_text='Unverified local content',work_id='the-bat-whispers-1930',edition_id='tbw-fullscreen-archive')
    assert result.status=='UNVERIFIED_CALLS_DISABLED'
    assert result.analysis_run_id is None
    reserve.assert_not_called()


@pytest.mark.parametrize('overrides',[
    {'work_id':'AUDIT_NONEXISTENT_WORK'},
    {'edition_id':'AUDIT_NONEXISTENT_EDITION'},
    {'author_cutoff_ms':999999999},
    {'content_type':'PROOF_ANALYSIS'},
])
def test_invalid_review_contract_is_rejected(author_client,overrides):
    r=author_client.post('/api/v1/community/posts',json=post_payload(**overrides))
    assert r.status_code in (400,403,404,422),{'input':overrides,'http':r.status_code,'body':r.text}


@pytest.mark.parametrize('reply',[
    {'contains_spoiler':True,'confidence':1,'flags':[]},
    {'contains_spoiler':True,'detected_cutoff_ms':-10,'confidence':1,'flags':[]},
    {'contains_spoiler':True,'detected_cutoff_ms':999999999,'confidence':1,'flags':[]},
    {'contains_spoiler':False,'detected_cutoff_ms':0,'confidence':2,'flags':[]},
])
@pytest.mark.asyncio
async def test_invalid_model_contract_cannot_be_verified(monkeypatch,reply):
    monkeypatch.setattr(settings,'PAID_CALLS_ENABLED',True)
    monkeypatch.setattr(settings,'SPEND_KILL_SWITCH_ACTIVE',False)
    for method in ['reserve_budget','check_budget_preflight','record_usage','settle_reservation','cancel_reservation']:
        monkeypatch.setattr(cost_service,method,AsyncMock())
    monkeypatch.setattr(spoiler_inspection_service,'_get_gemini_client',lambda:NS(models=NS(generate_content=lambda **kwargs:NS(text=json.dumps(reply)))))
    result=await spoiler_inspection_service.inspect_content(db=NS(),subject_id=uuid.uuid4(),version_no=1,raw_text='Audit fixture',work_id='the-bat-whispers-1930',edition_id='tbw-fullscreen-archive')
    assert result.status!='VERIFIED',result.model_dump()
