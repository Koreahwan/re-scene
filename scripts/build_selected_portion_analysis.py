"""Publish only independent Pass-A segment observations, never full-film synthesis.

No model calls. Original request/response files remain unchanged. Every card is
withheld until the entire source input window (not just an event) has been seen.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def observable_bat_text(value):
    # A still-only call can import a character name (including a later alias)
    # from model knowledge. Do not publish those inferred identities as if the
    # selected segment had established them. Preserve only neutral references.
    labels = {
        r"(?:Miss\s+)?Cornelia(?:\s+van\s+Gorder)?":'the older woman',
        r"(?:Miss\s+)?Dale(?:\s+(?:van\s+Gorder|Ogden))?":'the young woman',
        r"(?:maid\s+)?Lizzie(?:\s+Allen)?":'the maid',
        r"(?:Detective\s+)?Anderson":'a man in a suit',
        r"(?:Dr\.?|Doctor)\s+(?:Wells|Sterling)":'a man in a suit',
        r"(?:Jack\s+)?Brooks?(?:\s+Bailey)?":'a young man',
        r"Richard(?:\s+Fleming)?":'a man',
        r"(?:Caretaker\s+)?Billy":'the caretaker',
        r"Mr\.?\s+Bell":'a man',
    }
    for pattern, label in labels.items():
        value = re.sub(r'\b'+pattern+r'\b',label,value,flags=re.IGNORECASE)
    value = re.sub(r'\bBell\b','a man',value)
    value = re.sub(r'([.!?]\s+)([a-z])',lambda match:match[1]+match[2].upper(),value)
    return value[:1].upper()+value[1:]


BAT_READINGS = {
    'chunk-003':'The written warning and the clock make waiting visible. The hand at the window adds a separate piece of visual information; it does not identify the person behind it.',
    'chunk-008':'The scene alternates an interior search with exterior silhouettes. That alternation gives the viewer more locations to track without establishing that the figures have the same identity.',
    'chunk-015':'The switch and the gap between the doors make visibility part of the scene: who can see into the room is distinct from what anyone knows.',
    'chunk-016':'The partially closed doors separate the seated conversation from the observer. This is a difference in vantage point, not evidence of an undisclosed motive.',
    'chunk-017':'Note-taking establishes the visible form of an interview. The stills support that activity, but cannot verify the questions, answers, or their truth.',
    'chunk-018':'Entrances interrupt the people already in the room. Tracking those interruptions is more reliable here than assigning a cause to a startled reaction.',
    'chunk-019':'The alternation between corridors and basement divides attention across spaces. The comic physical mishap in one space does not explain the movements in another.',
    'chunk-020':'A bookcase and a rolled paper become objects of attention during the conversation. Examining them is visible; the purpose of that examination is not independently established by these stills.',
    'chunk-021':'Displaying a plan makes the layout a shared object of attention. Holding or showing it does not establish who knows the house best.',
    'chunk-031':'The moving fireplace changes the observable layout of the room. This supports the existence of an opening, not a conclusion about who has previously used it.',
    'chunk-033':'A hand extinguishing the candle changes what the room allows the viewer to see. Darkness restricts observation; it does not itself identify the hand.',
}

SOUND_READINGS = {
    'gmc-archive-1929':[
        'The will puts money and enforced proximity into the same conversation. Resentment is expressed openly, but an expressed grievance is not evidence that its speaker fired a shot.',
        'The discussion tests the burglary account against timing and physical traces. Keep the investigators\' reasoning separate from the family members\' accounts: neither a confident accusation nor a footprint identifies a shooter by itself.',
        'The telephone links the investigators to a distant event without giving them a view of the room. What they hear and what they later find are different kinds of evidence.',
        'The investigation combines household testimony, physical traces, and access to objects. Those strands need to agree before a single explanation can carry them all.',
        'A reported sighting and a physical condition are not yet the same kind of evidence. Vance asks for an examination and an alibi check rather than treating an account as settled fact.',
        'The segment moves from testimony to tests and a mechanical demonstration. Distinguish what those tests rule out from the additional interpretation in the investigator\'s accusation.',
        'The explanation is now retrospective, while the rooftop action supplies a new visible event. The explanatory speech and the action should not be treated as interchangeable forms of proof.',
    ],
    'ttc-archive-1929':[
        'A claim to know something creates pressure without disclosing the information itself. The private conversation at the house operates on a different footing from the telephone discussion of the case.',
        'The medium demonstrates how an apparently mysterious effect can be produced. Her demonstration establishes a method for that effect, not the truth or falsity of every subsequent claim.',
        'Searching, locking the doors, and joining hands are attempts to control the conditions of an observation. A private conversation is available to the viewer without necessarily being available to everyone in the circle.',
        'Darkness makes the sequence difficult to observe directly. Reconstructing the seating arrangement is an attempt to recover a spatial account, not an identification by itself.',
        'The questioning exposes differences between a planned performance, the names participants supply, and personal relationships. An accusation remains an accusation until it is supported independently.',
        'A bluff can change what someone is willing to say without making the alleged evidence real. The competing accounts in the interrogation still need to be distinguished from the inspector\'s conclusion.',
        'The repeated setup creates a controlled opportunity for speech under pressure. The reaction and confession occur in this segment; they should not be read backward into the earlier setup as if the viewer already knew them.',
        'The closing exchange distinguishes a physical staging method from the explanations offered for the experience. That distinction is now discussable because this segment has been completed.',
    ],
}


def build():
    films = []
    checkpoint_path = ROOT/'data/manifests/preprocessing_checkpoint_v3_gemini36.json'
    checkpoint = read(checkpoint_path)
    metadata = read(ROOT/'data/production/film_metadata.json')
    frame_rows = read(ROOT/'data/manifests/v3_frame_manifest.json')
    frame_times = {r['frame_id']:r['absolute_timestamp_ms'] for r in frame_rows}
    segments = []
    # Observable-only output from independent two-minute, sampled-image calls.
    # Do not import global narrative export, reveal registry, or proof records.
    for chunk_id, chunk in sorted(checkpoint['processed_chunks'].items()):
        start, end = chunk['start_ms'], chunk['end_ms']
        observations = []
        for event in chunk['events']:
            refs = event['evidence_frame_ids']
            if not refs or any(ref not in frame_times for ref in refs):
                continue
            times = [frame_times[ref] for ref in refs]
            if not (start <= min(times) <= max(times) <= end):
                continue
            # Known correction descriptions are local observations; never copy
            # their retrospective reviewer rationale into a watched-part card.
            description = event['description']
            if event['event_id'] == 'ev-c041-02':
                description = 'Police and household members tackle the fleeing cloaked figure onto the lawn.'
            elif event['event_id'] == 'ev-c041-03':
                description = 'Police officers bind the captured cloaked figure on the lawn.'
            observations.append({'timestamp_ms':event['timestamp_ms'], 'text':observable_bat_text(description),
                                 'evidence_end_ms':max(times), 'uncertainty':'Sampled stills; dialogue is not established.'})
        segments.append({'segment_id':chunk_id, 'start_ms':start, 'input_end_ms':end,
            'available_after_ms':end, 'summary':observable_bat_text(chunk['summary']), 'observations':observations,
            'source_scope':'INDEPENDENT_SEGMENT_ONLY', 'source_method':'SAMPLED_STILLS_ONLY',
            'source_response_sha256':hashlib.sha256(json.dumps(chunk,sort_keys=True).encode()).hexdigest(),
            'reading':BAT_READINGS.get(chunk_id,'Read the visible placement of people and objects as spatial information. A glance or a movement does not, by itself, establish a motive or a hidden identity.')})
    films.append({'work_id':metadata['movie_id'], 'edition_id':'tbw-fullscreen-archive',
        'runtime_ms':metadata['runtime_ms'], 'asset_sha256':checkpoint['canonical_asset_sha256'],
        'source_sha256':sha(checkpoint_path), 'model_id':checkpoint['model_id'],
        'segment_interval_ms':120000, 'segments':segments})

    for slug, work, edition in (
        ('the-greene-murder-case_1929','the-greene-murder-case-1929','gmc-archive-1929'),
        ('the-thirteenth-chair_1929','the-thirteenth-chair-1929','ttc-archive-1929'),
    ):
        directory = ROOT/'data/manifests/selected-portion-sources-20260909'/slug
        observations_path = directory/'observations.json'
        data = read(observations_path)
        manifest = data['manifest']
        segments = []
        for index, chunk in enumerate(manifest['chunks']):
            raw_path = directory/f'observe-{index:02d}.raw.json'
            request_path = directory/f'observe-{index:02d}.request.json'
            request, raw = read(request_path), read(raw_path)
            prompt = request['prompt']
            assert 'Describe only what this specific segment shows or says.' in prompt
            assert 'Do not infer future identity or motive.' in prompt
            assert f"segment end is {chunk['end_ms']} ms" in prompt
            observations = []
            for event in data['events']:
                if event['source_chunk'] != index:
                    continue
                evidence_end = max(f['timestamp_ms'] for f in event['frames'])
                assert chunk['start_ms'] <= event['timestamp_ms'] < chunk['end_ms']
                assert evidence_end <= chunk['end_ms']
                description = event['description'].replace('Inspector Donohue','the inspector')
                if edition == 'gmc-archive-1929' and index == 0 and event['timestamp_ms'] == 590590:
                    description = 'Members of the household hurry between rooms after the gunfire; shouted reports describe people being shot.'
                observations.append({'timestamp_ms':event['timestamp_ms'], 'text':description,
                    'evidence_end_ms':evidence_end, 'uncertainty':event['uncertainty']})
            # Audio encoding can include padding; retain a one-second guard at
            # internal boundaries, clamped to the verified edition's end.
            cutoff = min(manifest['runtime_ms'], chunk['end_ms'] + 1000)
            summary = raw['summary'].replace('Inspector Donohue','the inspector')
            if edition == 'gmc-archive-1929' and index == 0:
                summary = ('An attorney reviews the will with the family at the mansion. Its terms require them to remain in the house to receive their inheritance. Later, a woman brings broth to the bedridden older woman and reads beside her. Gunfire sends the household into alarm.')
            segments.append({'segment_id':f'segment-{index+1:02d}', 'start_ms':chunk['start_ms'],
                'input_end_ms':chunk['end_ms'], 'available_after_ms':cutoff,
                'summary':summary, 'observations':observations,
                'source_scope':'INDEPENDENT_SEGMENT_ONLY', 'source_method':'AUDIO_AND_SAMPLED_STILLS',
                'source_response_sha256':sha(raw_path), 'source_request_sha256':sha(request_path),
                'reading':SOUND_READINGS[edition][index]})
        films.append({'work_id':work,'edition_id':edition,'runtime_ms':manifest['runtime_ms'],
            'asset_sha256':manifest['source_sha256'],'source_sha256':sha(observations_path),
            'model_id':'gemini-3.6-flash','segment_interval_ms':600000,'segments':segments})
    return {'version':'selected-portion-v1-20260909',
        'provenance':'Adapted from previously generated independent segment observations; no full-film synthesis reused. Unverified visual identities are replaced with neutral references. Reading prompts are AI-assisted editorial guidance, not additional film facts or human verification.',
        'human_review_status':'NOT_REVIEWED', 'new_paid_model_calls':0, 'films':films}


if __name__ == '__main__':
    package = build()
    destination = ROOT/'data/production/selected_portion_analysis.json'
    destination.write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'films':len(package['films']), 'segments':sum(len(f['segments']) for f in package['films']),
                      'sha256':sha(destination),'new_paid_model_calls':0}))
