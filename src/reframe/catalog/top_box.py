"""Exact-release review identities from the checked-in, attributed TOP BOX registry.

No client-provided title can create an identity. Existing catalog QIDs win, so
the same release is never given a second review slot.
"""
import json
from pathlib import Path
from urllib.parse import urlencode
from sqlalchemy import select
from src.reframe.catalog.models import FilmCatalog

REGISTRY = json.loads((Path(__file__).resolve().parents[3] / 'apps/web/src/services/topBoxMetadata.json').read_text(encoding='utf-8'))


async def release_by_page(db, page_id):
    metadata = REGISTRY.get(str(page_id))
    if not metadata:
        return None
    film = await db.scalar(select(FilmCatalog).where(FilmCatalog.source_qid == metadata['qid']))
    work_id = film.movie_id if film else f"topbox-{metadata['qid']}"
    from src.reframe.catalog.service import catalog_service
    registered = catalog_service.get_film_entry(work_id)
    return {'work_id': work_id, 'edition_id': registered['edition_id'] if registered else f'{work_id}-catalog',
        'title': metadata['title'], 'runtime_ms': (metadata.get('runtimeMinutes') or 0) * 60000,
        'page_id': int(page_id), 'destination': '/box-office/film?' + urlencode({'title': metadata['title'], 'pageId': page_id})}


async def release_by_work(db, work_id):
    for page_id, metadata in REGISTRY.items():
        if work_id == f"topbox-{metadata['qid']}":
            release = await release_by_page(db, page_id)
            return release if release and release['work_id'] == work_id else None
    return None
