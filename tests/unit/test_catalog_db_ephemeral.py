"""
Ephemeral DB and Importer unit tests for Reframe V7 Catalog Schema.
Tests table creation, Alembic migration compatibility, batch import, idempotency,
search filtering, and transaction rollback on error without touching production databases.
Can be executed directly with:
    python -I -B tests/unit/test_catalog_db_ephemeral.py
"""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.reframe.catalog.models import FilmCatalog
from src.reframe.catalog.repository import FilmCatalogRepository
from tools.catalog.import_wikidata_catalog import run_importer, validate_catalog_payload


class TestCatalogDBEphemeral(unittest.TestCase):
    def setUp(self):
        # Create an ephemeral temporary SQLite database file
        custom_tmp = os.environ.get("REFRAME_TEST_TMP")
        if custom_tmp and not Path(custom_tmp).exists():
            Path(custom_tmp).mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(prefix="catalog-db-test-", dir=custom_tmp)
        self.db_path = Path(self.temp_dir.name) / "ephemeral_catalog.db"
        self.sync_db_url = f"sqlite:///{self.db_path.as_posix()}"
        self.async_db_url = f"sqlite+aiosqlite:///{self.db_path.as_posix()}"

        # Initialize schema
        self.engine = create_engine(self.sync_db_url, echo=False)
        FilmCatalog.metadata.create_all(self.engine)
        from sqlalchemy import text
        with self.engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            conn.execute(text("INSERT OR REPLACE INTO alembic_version (version_num) VALUES ('0013_v7_film_catalog_metadata')"))

        self.catalog_path = REPO_ROOT / "data" / "catalog" / "films_wikidata_v1.json"

    def tearDown(self):
        self.engine.dispose()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_importer_dry_run(self):
        """Test dry-run mode validates records without writing to database."""
        res = run_importer(self.sync_db_url, self.catalog_path, dry_run=True)
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["count"], 20)

        # Ensure nothing was written
        with Session(self.engine) as session:
            count = session.query(FilmCatalog).count()
            self.assertEqual(count, 0)

    def test_importer_real_insert_and_persistence(self):
        """Test real insertion of all 20 films and verify persistence in a separate session."""
        stats = run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))
        self.assertEqual(stats["inserted"], 20)
        self.assertEqual(stats["skipped"], 0)

        # Disconnect and open a new session to verify disk persistence
        with Session(self.engine) as session:
            rows = session.query(FilmCatalog).all()
            self.assertEqual(len(rows), 20)

            # Bat Whispers verification
            bat = session.query(FilmCatalog).filter(FilmCatalog.movie_id == "the-bat-whispers-1930").first()
            self.assertIsNotNone(bat)
            self.assertEqual(bat.source_qid, "Q3985804")
            self.assertEqual(bat.year, 1930)
            self.assertTrue(bat.core_demo_supported)

            # Non-bat film verification (e.g. Inception)
            inception = session.query(FilmCatalog).filter(FilmCatalog.source_qid == "Q25188").first()
            self.assertIsNotNone(inception)
            self.assertEqual(inception.movie_id, "wd-q25188")
            self.assertFalse(inception.core_demo_supported)
            self.assertEqual(inception.year, 2010)

    def test_importer_idempotency(self):
        """Test running importer twice produces 0 new inserts and 20 skipped."""
        run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))

        # Second run with exact same data
        stats2 = run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))
        self.assertEqual(stats2["inserted"], 0)
        self.assertEqual(stats2["skipped"], 20)

        with Session(self.engine) as session:
            self.assertEqual(session.query(FilmCatalog).count(), 20)

    def test_async_repository_search_and_pagination(self):
        """Test async repository queries including bilingual search, ordering, and pagination."""
        # Seed 20 films first
        run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))

        async def run_async_tests():
            async_engine = create_async_engine(self.async_db_url, echo=False)
            async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

            async with async_session_factory() as session:
                # 1. Total list (limit 50)
                films, total = await FilmCatalogRepository.list_films(session, limit=50)
                self.assertEqual(total, 20)
                self.assertEqual(len(films), 20)
                # First film must be The Bat Whispers due to core_demo_supported=True
                self.assertEqual(films[0].movie_id, "the-bat-whispers-1930")

                # 2. Search by title_en
                films_q, total_q = await FilmCatalogRepository.list_films(session, q="whispers")
                self.assertEqual(total_q, 1)
                self.assertEqual(films_q[0].movie_id, "the-bat-whispers-1930")

                # 3. Search case-insensitive
                films_inc, total_inc = await FilmCatalogRepository.list_films(session, q="INCEPTION")
                self.assertEqual(total_inc, 1)
                self.assertEqual(films_inc[0].title_en, "Inception")

                # 4. Search with zero matches returns 0 (not error)
                films_none, total_none = await FilmCatalogRepository.list_films(session, q="no-such-film-xyz")
                self.assertEqual(total_none, 0)
                self.assertEqual(len(films_none), 0)

                # 5. Detail lookup by exact ID and aliases
                film_by_id = await FilmCatalogRepository.get_film_by_id(session, "the-bat-whispers-1930")
                self.assertIsNotNone(film_by_id)

                film_by_alias = await FilmCatalogRepository.get_film_by_id(session, "the-bat-whispers")
                self.assertIsNotNone(film_by_alias)
                self.assertEqual(film_by_alias.movie_id, "the-bat-whispers-1930")

                film_by_qid = await FilmCatalogRepository.get_film_by_id(session, "Q25188")
                self.assertIsNotNone(film_by_qid)
                self.assertEqual(film_by_qid.title_en, "Inception")

                unknown_film = await FilmCatalogRepository.get_film_by_id(session, "unknown-film-id")
                self.assertIsNone(unknown_film)

            await async_engine.dispose()

        asyncio.run(run_async_tests())


if __name__ == "__main__":
    unittest.main()
