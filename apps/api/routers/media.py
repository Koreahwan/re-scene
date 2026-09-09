"""Manifest-allowlisted evidence frames, gated by this browser's watch progress."""
import json
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from src.reframe.identity.auth import ViewerContext, get_viewer_context
from src.reframe.catalog.service import catalog_service
from src.reframe.catalog.runtime_state import synchronized

router = APIRouter(prefix='/media', tags=['Evidence media'])
ROOT = Path(__file__).resolve().parents[3]

# Dynamic in-memory registry for multi-film test/import frames
_DYNAMIC_FRAME_REGISTRY: Dict[str, Dict[str, Any]] = {}


@synchronized
def register_evidence_frame(work_id: str, edition_id: str, frame_id: str, timestamp_ms: int, filename: str) -> None:
    key = f"{work_id}:{edition_id}:{frame_id}"
    _DYNAMIC_FRAME_REGISTRY[key] = {
        "work_id": work_id,
        "edition_id": edition_id,
        "frame_id": frame_id,
        "absolute_timestamp_ms": timestamp_ms,
        "filename": filename,
    }


@synchronized
def _load_manifest_frames() -> Dict[str, Dict[str, Any]]:
    frames = dict(_DYNAMIC_FRAME_REGISTRY)
    manifest_file = ROOT / 'data/manifests/v3_frame_manifest.json'
    if manifest_file.is_file():
        try:
            rows = json.loads(manifest_file.read_text(encoding='utf-8'))
            for row in rows:
                key = f"the-bat-whispers-1930:tbw-fullscreen-archive:{row['frame_id']}"
                if key not in frames:
                    frames[key] = {
                        "work_id": "the-bat-whispers-1930",
                        "edition_id": "tbw-fullscreen-archive",
                        "frame_id": row['frame_id'],
                        "absolute_timestamp_ms": int(row['absolute_timestamp_ms']),
                        "filename": row['frame_id'] + '.jpg',
                    }
        except Exception:
            pass
    return frames


@router.get('/{work_id}/{edition_id}/frames/{frame_id}')
async def evidence_frame(
    work_id: str,
    edition_id: str,
    frame_id: str,
    viewer: ViewerContext = Depends(get_viewer_context)
):
    norm_work_id = catalog_service.normalize_movie_id(work_id)
    entry = catalog_service.get_film_entry(norm_work_id, edition_id)
    if entry is None:
        raise HTTPException(404, 'Unknown evidence edition')

    lookup_key = f"{norm_work_id}:{edition_id}:{frame_id}"
    all_frames = _load_manifest_frames()
    frame = all_frames.get(lookup_key)
    if frame is None:
        raise HTTPException(404, 'Unknown evidence frame')

    cutoff = int(frame['absolute_timestamp_ms'])
    current_progress = viewer.work_progress_by_edition.get(f'{norm_work_id}:{edition_id}', 0)
    if current_progress < cutoff:
        raise HTTPException(
            403,
            'Watch progress is below this evidence frame',
            headers={'Cache-Control': 'private, no-store', 'Vary': 'Cookie'}
        )

    base_dir = (Path(entry.get('_asset_root', ROOT)) / 'data/production/evidence_frames').resolve()
    filename = frame.get('filename', f"{frame_id}.jpg")
    path = (base_dir / filename).resolve()

    if not path.is_relative_to(base_dir) or not path.is_file():
        raise HTTPException(404, 'Evidence frame asset unavailable')

    return FileResponse(
        path,
        media_type='image/jpeg',
        headers={'Cache-Control': 'private, no-store', 'Vary': 'Cookie'}
    )
