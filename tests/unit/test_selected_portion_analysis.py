"""Input-boundary separation, not just scene-time filtering of full-film text."""
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from src.reframe.catalog.selected_portion import load_package, selected_portion, validate_package
from src.reframe.identity.auth import ViewerContext, get_viewer_context
from src.reframe.spoiler.analysis_boundary import analysis_visibility, retrospective_cutoff
from src.reframe.spoiler.models import SpoilerScope

FILMS = load_package()['films']


def test_visual_identity_masking_does_not_replace_a_physical_bell():
    from scripts.build_selected_portion_analysis import observable_bat_text
    text = observable_bat_text('Mr. Bell enters. Doctor Wells reaches toward a desktop bell beside Brooks Bailey.')
    assert text == 'A man enters. A man in a suit reaches toward a desktop bell beside a young man.'
    assert 'Bailey' not in text and 'Wells' not in text


@pytest.fixture
def imported_editions(monkeypatch):
    from src.reframe.catalog.service import catalog_service
    from src.reframe.catalog import dataset_import as importer
    from src.reframe.proof import store
    from apps.api.routers import media
    for name,value in list(catalog_service.__dict__.items()):
        monkeypatch.setattr(catalog_service,name,deepcopy(value))
    monkeypatch.setattr(importer,'_APPLIED_BUNDLE_HASHES',{})
    monkeypatch.setattr(store,'_DYNAMIC_PROOFS_BY_ID',{})
    monkeypatch.setattr(store,'_DYNAMIC_PROOFS_BY_REVEAL',{})
    monkeypatch.setattr(media,'_DYNAMIC_FRAME_REGISTRY',{})
    importer.load_imported_datasets_from_disk(Path(__file__).resolve().parents[2]/'data/production/imported_datasets')


def viewer(film, position, **kwargs):
    return ViewerContext(work_progress_by_edition={f"{film['work_id']}:{film['edition_id']}":position}, **kwargs)


@pytest.mark.parametrize('film',FILMS,ids=lambda f:f['work_id'])
def test_every_segment_waits_for_its_entire_input_window(film):
    for segment in film['segments']:
        cutoff = segment['available_after_ms']
        before = selected_portion(film['work_id'],film['edition_id'],viewer(film,cutoff-1))
        after = selected_portion(film['work_id'],film['edition_id'],viewer(film,cutoff))
        assert segment['segment_id'] not in {s['segment_id'] for s in before['segments']}
        assert segment['summary'] not in json.dumps(before)
        assert segment['segment_id'] in {s['segment_id'] for s in after['segments']}
        assert all(s['available_after_ms'] <= cutoff for s in after['segments'])


@pytest.mark.parametrize('film',FILMS,ids=lambda f:f['work_id'])
def test_midpoint_has_only_completed_observations_and_no_retrospective_payload(film):
    midpoint = film['runtime_ms']//2
    result = selected_portion(film['work_id'],film['edition_id'],viewer(film,midpoint))
    assert result['segments'] and result['mode'] == 'SELECTED_PORTION'
    assert result['covered_until_ms'] <= midpoint
    assert not result['retrospective_available']
    serialized = json.dumps(result)
    assert all(key not in serialized for key in ('reveal_explanation','blind_explanation','alternative_explanations','reveal_id','frame_url'))
    for future in film['segments']:
        if future['available_after_ms'] > midpoint:
            assert future['summary'] not in serialized
    end = selected_portion(film['work_id'],film['edition_id'],viewer(film,film['runtime_ms']))
    assert end['retrospective_available'] and len(end['segments']) == len(film['segments'])


@pytest.mark.parametrize('film',FILMS,ids=lambda f:f['work_id'])
def test_rewind_selected_cap_other_edition_and_all_preferences_cannot_bypass(film):
    work, edition, runtime = film['work_id'],film['edition_id'],film['runtime_ms']
    assert selected_portion(work,edition,viewer(film,runtime),0)['segments'] == []
    assert selected_portion(work,edition,viewer(film,0),runtime)['segments'] == []
    assert selected_portion(work,edition,ViewerContext(work_progress_by_edition={'other:edition':runtime}))['segments'] == []
    permissive = viewer(film,0,spoiler_preferences={'default_mode':'ALL'},completed_reveal_ids=['all'],admin_override=True)
    assert selected_portion(work,edition,permissive,runtime)['segments'] == []
    scope = SpoilerScope(work_id=work,edition_id=edition,minimum_progress_ms=runtime,required_reveal_ids=['all'])
    assert analysis_visibility(scope,permissive) == 'LOCKED'
    assert analysis_visibility(scope,viewer(film,runtime)) == 'VISIBLE'
    assert retrospective_cutoff(work,edition,1000,runtime) == runtime


@pytest.mark.parametrize('mutation',['source_scope','future_observation','bad_cutoff','duplicate'])
def test_publication_rejects_invalid_input_provenance(mutation):
    package = deepcopy(load_package())
    segment = package['films'][0]['segments'][0]
    if mutation == 'source_scope': segment['source_scope'] = 'FULL_FILM_SYNTHESIS'
    if mutation == 'future_observation': segment['observations'][0]['evidence_end_ms'] = segment['input_end_ms']+1
    if mutation == 'bad_cutoff': segment['available_after_ms'] = segment['input_end_ms']-1
    if mutation == 'duplicate': package['films'][0]['segments'].append(deepcopy(segment))
    with pytest.raises(ValueError): validate_package(package)


@pytest.mark.asyncio
async def test_actual_api_does_not_deliver_future_content_and_disables_caching(imported_editions):
    from apps.api.main import app
    previous = dict(app.dependency_overrides)
    active = ViewerContext()
    app.dependency_overrides[get_viewer_context] = lambda:active
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://localhost') as client:
            for film in FILMS:
                path = f"/api/v1/films/{film['work_id']}/selected-portion-analysis?edition_id={film['edition_id']}"
                for position in (0,film['runtime_ms']//2,film['runtime_ms'],0):
                    active = viewer(film,position,spoiler_preferences={'default_mode':'ALL'})
                    response = await client.get(path)
                    assert response.status_code == 200
                    assert response.headers['cache-control'] == 'private, no-store'
                    data = response.json()['data']
                    assert bool(data['segments']) is (position > 0)
                    assert all(s['available_after_ms'] <= position for s in data['segments'])
                    reveals = await client.get(f"/api/v1/films/{film['work_id']}/reveals?edition_id={film['edition_id']}")
                    assert reveals.status_code == 200
                    assert bool(reveals.json()['data']) is (position == film['runtime_ms'])
                assert (await client.get(path+'&selected_ms=-1')).status_code == 422
                assert (await client.get(path+'&selected_ms=nan')).status_code == 422
            assert (await client.get('/api/v1/films/the-bat-whispers-1930/selected-portion-analysis?edition_id=foreign')).status_code == 404
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
@pytest.mark.parametrize('film',FILMS,ids=lambda f:f['work_id'])
async def test_full_context_record_is_locked_on_every_read_until_end(monkeypatch,imported_editions,film):
    from src.reframe.proof import store
    from src.reframe.proof.models import ProofRecord
    from src.reframe.catalog.service import catalog_service
    reveal = catalog_service.get_reveals(film['work_id'],viewer(film,film['runtime_ms']),film['edition_id'])[0]
    record = ProofRecord(proof_id='boundary-test-proof',work_id=film['work_id'],edition_id=film['edition_id'],
        reveal_id=reveal.reveal_id,title='FUTURE_TITLE_SENTINEL',blind_explanation='FUTURE_BLIND_SENTINEL',
        reveal_explanation='FUTURE_ENDING_SENTINEL',evidence_chain=[{'frame_url':'FUTURE_FRAME_SENTINEL'}],
        observed_premises=[{'text':'FUTURE_PREMISE_SENTINEL'}],alternative_explanations=['FUTURE_ALTERNATIVE_SENTINEL'],
        counterfactual_results={},presentation_status='PUBLIC',human_review_status='APPROVED')
    monkeypatch.setattr(store,'is_verified_canonical_proof',lambda value:True)
    mocked = MagicMock()
    mocked.scalar_one_or_none.return_value = record
    mocked.scalars.return_value.all.return_value = [record]
    db = AsyncMock()
    db.execute.return_value = mocked
    for position in (0,film['runtime_ms']//2,film['runtime_ms']-1,film['runtime_ms'],0):
        active = viewer(film,position,spoiler_preferences={'default_mode':'ALL'},completed_reveal_ids=[reveal.reveal_id])
        detail = await store.canonical_proof_store.get_proof_by_id(db,record.proof_id,active)
        listing = await store.canonical_proof_store.get_proofs_for_reveal(db,reveal.reveal_id,active)
        for payload in (detail,listing[0]):
            assert ('FUTURE_ENDING_SENTINEL' in json.dumps(payload)) is (position == film['runtime_ms'])
            if position < film['runtime_ms']:
                assert 'FUTURE_' not in json.dumps(payload)
