import pytest
from fastapi import HTTPException
from apps.api.routers.media import evidence_frame
from src.reframe.identity.auth import ViewerContext

WORK='the-bat-whispers-1930'
EDITION='tbw-fullscreen-archive'


@pytest.mark.asyncio
async def test_evidence_frame_requires_watch_progress():
    with pytest.raises(HTTPException) as exc:
        await evidence_frame(WORK,EDITION,'frame_c017_000',ViewerContext())
    assert exc.value.status_code==403
    assert exc.value.headers['Cache-Control']=='private, no-store'


@pytest.mark.asyncio
async def test_evidence_frame_serves_original_and_does_not_cache_across_viewers():
    viewer=ViewerContext(work_progress_by_edition={f'{WORK}:{EDITION}':1920000})
    response=await evidence_frame(WORK,EDITION,'frame_c017_000',viewer)
    assert response.path.read_bytes()[:3]==b'\xff\xd8\xff'
    assert response.headers['vary']=='Cookie'
    assert response.headers['cache-control']=='private, no-store'


@pytest.mark.asyncio
@pytest.mark.parametrize('work,edition,frame',[(WORK,'wrong','frame_c017_000'),(WORK,EDITION,'../secrets'),('wrong',EDITION,'frame_c017_000')])
async def test_evidence_frame_scope_and_allowlist(work,edition,frame):
    with pytest.raises(HTTPException) as exc:
        await evidence_frame(work,edition,frame,ViewerContext())
    assert exc.value.status_code==404
