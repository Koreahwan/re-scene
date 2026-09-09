from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
import pytest
from src.reframe.proof.ai_publication import is_public_ai_analysis, label_ai_analysis
from src.reframe.proof.store import is_verified_canonical_proof
from src.reframe.evidence.adapter import v3_adapter as adapter


def candidate():
    events=adapter.get_events()[:2]
    return {'presentation_status':'PUBLIC_AI_ANALYSIS','trust_namespace':'AI_INTERPRETATION',
        'human_review_status':'NOT_REVIEWED','generation_mode':'LIVE_GOOGLE',
        'work_id':adapter.work_id,'edition_id':adapter.edition_id,
        'reveal_id':'reveal-anderson-identity','prompt_hash':'a'*64,
        'counterfactual_results':{'ai_provenance':{'model_call_id':'test-call','analysis_run_id':'test-run',
            'response_sha256':'b'*64,'validation':'EVIDENCE_REFERENCES_VALIDATED'}},
        'evidence_chain':[{'event_id':e.event_id,'scene_id':e.scene_id,'timestamp_ms':e.timestamp_ms,
                           'evidence_hash':e.evidence_hash} for e in events]}


def test_ai_interpretation_is_not_promoted_to_canon():
    record=candidate()
    assert is_public_ai_analysis(record)
    assert not is_verified_canonical_proof(record)
    result=label_ai_analysis({},record)
    assert result['verification_status']=='AI_EVIDENCE_LINKED'
    assert result['trust_namespace']=='AI_INTERPRETATION'


def test_changed_or_missing_evidence_is_not_public():
    for field,value in [('event_id','invented'),('timestamp_ms',-1),('evidence_hash','changed')]:
        record=candidate(); record['evidence_chain'][0][field]=value
        assert not is_public_ai_analysis(record)


def test_fixture_and_fake_human_approval_are_not_ai_publications():
    for field,value in [('generation_mode','OFFLINE_FIXTURE'),('human_review_status','APPROVED'),
                         ('edition_id','wrong-edition'),('counterfactual_results',{})]:
        record=candidate(); record[field]=value
        assert not is_public_ai_analysis(record)


@pytest.mark.asyncio
async def test_public_interpretation_list_and_detail_use_same_read_policy():
    from src.reframe.proof.store import canonical_proof_store
    from src.reframe.proof.models import ProofRecord
    from src.reframe.identity.auth import ViewerContext

    record = ProofRecord(**candidate(), proof_id="test-public-interpretation", proof_type="MULTI_SCENE_PATTERN",
        title="Read contract sentinel", blind_explanation="Before", reveal_explanation="After",
        observed_premises=[], alternative_explanations=[], proof_strength=0.5, fan_impact=0.5,
        trust_label="Evidence-linked interpretation", asset_sha256="a" * 64)
    result = MagicMock()
    result.scalar_one_or_none.return_value = record
    result.scalars.return_value.all.return_value = [record]
    db = AsyncMock()
    db.execute.return_value = result
    viewer = ViewerContext(session_id="read-contract", work_progress_by_edition={
        f"{adapter.work_id}:{adapter.edition_id}": 5119080,
    })
    items = await canonical_proof_store.get_proofs_for_reveal(db, record.reveal_id, viewer)
    item = await canonical_proof_store.get_proof_by_id(db, record.proof_id, viewer)
    listed = next(p for p in items if p["proof_id"] == record.proof_id)
    for response in (listed, item):
        assert response["visibility"] == "VISIBLE"
        assert response["title"] == "Read contract sentinel"
        assert response["trust_namespace"] == "AI_INTERPRETATION"
        assert response["verification_status"] == "AI_EVIDENCE_LINKED"
    record.counterfactual_results = {}
    assert await canonical_proof_store.get_proof_by_id(db, record.proof_id, viewer) is None
    assert not any(p["proof_id"] == record.proof_id for p in
        await canonical_proof_store.get_proofs_for_reveal(db, record.reveal_id, viewer))
