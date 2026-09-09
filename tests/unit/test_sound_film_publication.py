"""Edition-pinned AI disclosure, tamper rejection and spoiler separation. No calls."""
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import types
from src.reframe.catalog.service import catalog_service
from src.reframe.cost.invoker import GuardedGeminiInvoker, PaidCallGuardException
from src.reframe.identity.auth import ViewerContext
from src.reframe.proof.ai_publication import ai_publication_digest, is_public_ai_analysis
from src.reframe.proof.models import ProofRecord
from src.reframe.proof.store import canonical_proof_store, is_verified_canonical_proof
from src.reframe.shared.config import settings


@pytest.fixture
def bound_record(monkeypatch):
    for key, value in list(catalog_service.__dict__.items()):
        monkeypatch.setattr(catalog_service, key, deepcopy(value))
    record = dict(proof_id='test-sound-ai', work_id='test-sound-1929', edition_id='test-sound-edition',
        dataset_version='test-v1', reveal_id='test-sound-reveal', proof_type='HIDDEN_PLAN_CHAIN',
        title='Ending sentinel', blind_explanation='Earlier observations', reveal_explanation='Ending explanation sentinel',
        evidence_chain=[{'event_id': 'e1', 'timestamp_ms': 1000}, {'event_id': 'e2', 'timestamp_ms': 2000}],
        observed_premises=[], alternative_explanations=['Alternative A', 'Alternative B'],
        counterfactual_results={'ai_provenance': {'analysis_run_id': 'run', 'model_call_id': 'call',
            'response_sha256': 'b' * 64, 'validation': 'EVIDENCE_REFERENCES_VALIDATED'}},
        human_review_status='NOT_REVIEWED', presentation_status='PUBLIC_AI_ANALYSIS', trust_namespace='AI_INTERPRETATION',
        trust_label='Gemini-generated interpretation; not human reviewed', generation_mode='LIVE_GOOGLE',
        asset_sha256='a' * 64, correction_overlay_sha='b' * 64, evidence_bundle_hash='c' * 64,
        model_id='gemini-3.6-flash', prompt_hash='d' * 64, retrieval_config_hash='e' * 64,
        proof_schema_version='1.0.0', proof_strength=0.0, fan_impact=0.0)
    entry = dict(movie_id=record['work_id'], edition_id=record['edition_id'], title='Test Film', year=1929,
        runtime_ms=10000, synopsis_safe='Safe summary', analysis_status='READY', rights_status='UNCONFIRMED',
        dataset_version='test-v1', canonical_asset_sha256='a' * 64,
        _ai_publications={record['proof_id']: ai_publication_digest(record)})
    reveal = dict(reveal_id=record['reveal_id'], movie_id=record['work_id'], edition_id=record['edition_id'],
        title='Ending reveal sentinel', safe_title='Protected analysis', safe_preview='After the film',
        timestamp_ms=9000, spoiler_cutoff_ms=10000, proof_count=1)
    catalog_service.register_film_dataset(record['work_id'], entry, [reveal])
    return record


def test_bound_ai_record_is_not_canon_and_cannot_be_relabelled(bound_record):
    assert is_public_ai_analysis(bound_record)
    assert is_public_ai_analysis(SimpleNamespace(**bound_record))
    assert not is_verified_canonical_proof(bound_record)
    for key in ('title', 'work_id', 'edition_id', 'dataset_version', 'asset_sha256', 'prompt_hash',
                'human_review_status', 'generation_mode', 'reveal_explanation', 'reveal_id'):
        changed = dict(bound_record, **{key: 'tampered'})
        assert not is_public_ai_analysis(changed), key
    changed = deepcopy(bound_record)
    changed['evidence_chain'][0]['timestamp_ms'] += 1
    assert not is_public_ai_analysis(changed)
    changed = deepcopy(bound_record)
    changed['counterfactual_results']['ai_provenance']['model_call_id'] = 'another-call'
    assert not is_public_ai_analysis(changed)


@pytest.mark.asyncio
async def test_both_read_surfaces_require_this_editions_completed_progress(bound_record):
    record = ProofRecord(**bound_record)
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    result.scalars.return_value.all.return_value = [record]
    db = AsyncMock()
    db.execute.return_value = result
    key = f'{record.work_id}:{record.edition_id}'
    for progress, visible in [({}, False), ({key: 9999}, False), ({'other-film:other-edition': 10000}, False), ({key: 10000}, True)]:
        viewer = ViewerContext(session_id='sound-read-contract', work_progress_by_edition=progress)
        listed = await canonical_proof_store.get_proofs_for_reveal(db, record.reveal_id, viewer)
        detail = await canonical_proof_store.get_proof_by_id(db, record.proof_id, viewer)
        assert len(listed) == 1 and detail
        for payload in [listed[0], detail]:
            assert (payload['visibility'] == 'VISIBLE') is visible
            assert ('Ending explanation sentinel' in str(payload)) is visible
            if visible:
                assert payload['proof_badge'] == 'AI Analysis'
                assert payload['human_review_status'] == 'NOT_REVIEWED'
                assert payload['verification_status'] == 'AI_EVIDENCE_LINKED'


@pytest.mark.asyncio
async def test_media_requires_admin_full_context_reservation_and_inline_only(monkeypatch):
    for field, value in [('PAID_CALLS_ENABLED', True), ('SPEND_KILL_SWITCH_ACTIVE', False),
                         ('LIVE_AGENT_ENABLED', True), ('EXECUTION_MODE', 'LIVE_GOOGLE')]:
        monkeypatch.setattr(settings, field, value)
    for admin, estimate, parts, code in [
        (False, 1048576, [types.Part.from_bytes(data=b'audio', mime_type='audio/mpeg')], 'MEDIA_RESERVATION_REQUIRED'),
        (True, 1000, [types.Part.from_bytes(data=b'audio', mime_type='audio/mpeg')], 'MEDIA_RESERVATION_REQUIRED'),
        (True, 1048576, [types.Part.from_uri(file_uri='https://example.invalid/a.mp3', mime_type='audio/mpeg')], 'INLINE_MEDIA_REQUIRED'),
    ]:
        with pytest.raises(PaidCallGuardException) as caught:
            await GuardedGeminiInvoker.invoke_guarded_generation('', '', 'intake', 'gemini-3.6-flash', 'test',
                estimated_input_tokens=estimate, is_admin=admin, media_parts=parts)
        assert caught.value.code == code


def test_observation_normalizer_drops_unbound_rows_without_inventing_references():
    from scripts.analyze_sound_films import validate_observations
    chunk = {'start_ms': 0, 'end_ms': 600000,
             'frames': [{'filename': 'frames/a.jpg', 'timestamp_ms': 1000}]}
    template = {'timestamp_ms': 1000, 'actor': 'Person', 'action': 'Speaks',
                'description': 'An observed claim', 'modality': 'AUDIO',
                'frame_filenames': ['a.jpg'], 'uncertainty': 'Speaker identity uncertain'}
    bad = dict(template, timestamp_ms=100000)
    value = validate_observations({'events': [dict(template) for _ in range(4)] + [bad]}, chunk)
    assert len(value['events']) == 4
    assert value['excluded_events'][0]['event'] == bad
    assert all(event['frame_filenames'] == ['a.jpg'] for event in value['events'])
