"""Register the bundled demonstration readings in a local SQLite database."""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.reframe.shared.config import settings


def main():
    if settings.ENVIRONMENT not in {'development', 'test', 'local'}:
        raise SystemExit('Demo registration is restricted to local development.')
    if not (settings.DATABASE_URL.startswith('sqlite+aiosqlite:///')
            and settings.SYNC_DATABASE_URL.startswith('sqlite:///')):
        raise SystemExit('Demo registration requires local SQLite URLs.')
    if settings.PAID_CALLS_ENABLED:
        raise SystemExit('Disable paid calls before registering demo data.')

    # Import the application to register all table models, without starting it.
    from apps.api.main import app  # noqa: F401
    from src.reframe.shared.database import Base, sync_engine
    from src.reframe.catalog.repository import FilmCatalogRepository
    from src.reframe.catalog.dataset_import import load_imported_datasets_from_disk
    from src.reframe.proof.models import ProofRecord
    from src.reframe.proof.ai_publication import is_public_ai_analysis

    root = Path(__file__).resolve().parents[1]
    load_imported_datasets_from_disk(root / 'data/production/imported_datasets')
    rows = json.loads((root / 'data/production/demo_analyses.json').read_text(encoding='utf-8'))
    for row in rows:
        if not is_public_ai_analysis(row):
            raise SystemExit(f"Invalid demonstration reading: {row['proof_id']}")
    Path(sync_engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(sync_engine)
    added = 0
    with Session(sync_engine) as db:
        films = json.loads((root / 'data/catalog/films_wikidata_v3.json').read_text(encoding='utf-8'))['films']
        FilmCatalogRepository.sync_import_films(db, films)
        for row in rows:
            existing = db.execute(select(ProofRecord).where(ProofRecord.proof_id == row['proof_id'])).scalar_one_or_none()
            if existing is None:
                db.add(ProofRecord(**row))
                added += 1
        db.commit()
    sync_engine.dispose()
    print(f'Registered {added} demonstration readings; existing readings were preserved.')


if __name__ == '__main__':
    main()
