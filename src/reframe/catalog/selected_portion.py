"""Fail-closed delivery of independent, completed input segments."""
from functools import lru_cache
import json
from pathlib import Path

from src.reframe.spoiler.analysis_boundary import SEPARATED_ANALYSIS_EDITIONS, current_position

DATA_PATH = Path(__file__).resolve().parents[3]/'data/production/selected_portion_analysis.json'


def validate_package(package):
    if package.get('version') != 'selected-portion-v1-20260909':
        raise ValueError('Unsupported selected-portion publication')
    films = package['films']
    if {(f['work_id'],f['edition_id']) for f in films} != SEPARATED_ANALYSIS_EDITIONS or len(films) != 3:
        raise ValueError('Unexpected selected-portion editions')
    for film in films:
        runtime = film['runtime_ms']
        if type(runtime) is not int or runtime <= 0:
            raise ValueError('Invalid edition runtime')
        seen = set()
        previous = -1
        for segment in film['segments']:
            bounds = [segment[k] for k in ('start_ms','input_end_ms','available_after_ms')]
            if any(type(v) is not int for v in bounds) or not 0 <= bounds[0] < bounds[1] <= bounds[2] <= runtime:
                raise ValueError('Invalid segment input boundary')
            if bounds[0] < previous or segment['segment_id'] in seen:
                raise ValueError('Duplicate or overlapping segments')
            previous = bounds[1]
            seen.add(segment['segment_id'])
            if segment['source_scope'] != 'INDEPENDENT_SEGMENT_ONLY':
                raise ValueError('Full-film synthesis is not a watched-portion source')
            if len(segment['source_response_sha256']) != 64:
                raise ValueError('Missing immutable observation provenance')
            if not segment['summary'] or not segment['observations']:
                raise ValueError('Missing segment observations')
            for observation in segment['observations']:
                for key in ('timestamp_ms','evidence_end_ms'):
                    v = observation[key]
                    if type(v) is not int or not bounds[0] <= v <= bounds[1]:
                        raise ValueError('Observation exceeds its source input')
    return package


@lru_cache(maxsize=1)
def load_package():
    return validate_package(json.loads(DATA_PATH.read_text(encoding='utf-8')))


def selected_portion(work_id, edition_id, viewer, selected_ms=None):
    if (work_id, edition_id) not in SEPARATED_ANALYSIS_EDITIONS:
        return None
    film = next(f for f in load_package()['films'] if (f['work_id'],f['edition_id']) == (work_id,edition_id))
    return selected_portion_from_film(film, viewer, selected_ms)


def selected_portion_from_film(film, viewer, selected_ms=None):
    """Shape already validated observations with the same per-edition boundary."""
    work_id, edition_id = film['work_id'], film['edition_id']
    saved = min(film['runtime_ms'], current_position(viewer,work_id,edition_id))
    if selected_ms is not None and (type(selected_ms) is not int or selected_ms < 0):
        raise ValueError('Invalid selected position')
    position = saved if selected_ms is None else min(saved,selected_ms)
    # Filter BEFORE constructing a DTO. No future summary, title, ID, frame,
    # count, or text is delivered and then merely hidden by the browser.
    completed = [s for s in film['segments'] if 0 < s['available_after_ms'] <= position]
    return {
        'work_id':work_id, 'edition_id':edition_id, 'selected_progress_ms':position,
        'covered_until_ms':max((s['input_end_ms'] for s in completed),default=0),
        'segment_interval_ms':film['segment_interval_ms'], 'mode':'SELECTED_PORTION',
        'human_review_status':'NOT_REVIEWED', 'model_id':film['model_id'],
        'retrospective_available':position >= film['runtime_ms'],
        'segments':[{
            'segment_id':s['segment_id'], 'start_ms':s['start_ms'], 'end_ms':s['input_end_ms'],
            'available_after_ms':s['available_after_ms'], 'summary':s['summary'],
            'reading':s['reading'], 'observations':[dict(o) for o in s['observations']],
            'source_method':s['source_method'], 'source_response_sha256':s['source_response_sha256'],
        } for s in completed],
    }
