"""AI interpretations are public evidence-linked hypotheses, never human canon."""
import hashlib
import json
from src.reframe.evidence.adapter import v3_adapter


PUBLICATION_FIELDS = (
    'proof_id', 'work_id', 'edition_id', 'dataset_version', 'reveal_id', 'proof_type',
    'title', 'blind_explanation', 'reveal_explanation', 'evidence_chain', 'observed_premises',
    'alternative_explanations', 'counterfactual_results', 'human_review_status',
    'presentation_status', 'trust_namespace', 'trust_label', 'generation_mode',
    'asset_sha256', 'correction_overlay_sha', 'evidence_bundle_hash', 'model_id',
    'prompt_hash', 'retrieval_config_hash', 'proof_schema_version', 'proof_strength', 'fan_impact',
)


def ai_publication_digest(record) -> str:
    """Exclude generated DB IDs/dates; bind all published content and provenance."""
    values = {key: record.get(key) if isinstance(record, dict) else getattr(record, key, None)
              for key in PUBLICATION_FIELDS}
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def is_public_ai_analysis(record) -> bool:
    def value(key, default=None):
        return record.get(key, default) if isinstance(record, dict) else getattr(record, key, default)
    if not (value('presentation_status') == 'PUBLIC_AI_ANALYSIS'
            and value('trust_namespace') == 'AI_INTERPRETATION'
            and value('human_review_status') == 'NOT_REVIEWED'
            and value('generation_mode') == 'LIVE_GOOGLE'):
        return False
    provenance = (value('counterfactual_results') or {}).get('ai_provenance', {})
    if not (provenance.get('model_call_id') and provenance.get('analysis_run_id')
            and provenance.get('validation') == 'EVIDENCE_REFERENCES_VALIDATED'
            and provenance.get('response_sha256') and value('prompt_hash')):
        return False
    if (value('work_id'), value('edition_id')) != (v3_adapter.work_id, v3_adapter.edition_id):
        from src.reframe.catalog.service import catalog_service
        entry = catalog_service.get_film_entry(value('work_id'), value('edition_id'))
        if not entry or entry.get('analysis_status') != 'READY':
            return False
        expected = entry.get('_ai_publications', {}).get(value('proof_id'))
        return bool(expected and expected == ai_publication_digest(record)
                    and value('asset_sha256') == entry.get('canonical_asset_sha256')
                    and value('dataset_version') == entry.get('dataset_version'))
    reveal = v3_adapter.get_reveal(value('reveal_id'))
    chain = value('evidence_chain') or []
    if not reveal or len(chain) < 2:
        return False
    for item in chain:
        event = v3_adapter.get_event(item.get('event_id'))
        if not event or event.scene_id != item.get('scene_id') or event.timestamp_ms != item.get('timestamp_ms'):
            return False
        if event.evidence_hash != item.get('evidence_hash'):
            return False
    return any(item['timestamp_ms'] < reveal.timestamp_ms for item in chain)


def label_ai_analysis(payload, record):
    if is_public_ai_analysis(record):
        counterfactual = record.get('counterfactual_results', {}) if isinstance(record, dict) else record.counterfactual_results
        sampled = (counterfactual or {}).get('ai_provenance', {}).get('source_method') == 'complete_audio_and_10_second_stills'
        payload.update(proof_badge='AI Analysis', verification_status='AI_EVIDENCE_LINKED',
                       trust_namespace='AI_INTERPRETATION',
                       trust_label=('Gemini · audio and sampled frames · not human reviewed' if sampled
                                    else 'Gemini-generated interpretation · not human reviewed'),
                       live_analysis_pending_approval=False)
    return payload
