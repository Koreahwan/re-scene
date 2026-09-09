"""
REFRAME-MASTER-R1: Ephemeral DB and API Boundary Verification Suite.
Tests:
1. Alembic migration upgrade on clean ephemeral DB
2. Importer preflight safety (fails before migration, succeeds after)
3. Importer transaction safety: atomic rollback, idempotency no-op, conflict rejection, immutability
4. Empty DB boundary (no Bat fallback)
5. Out-of-bounds pagination (offset=20, offset=50 -> data=[], total=20)
6. All 20 films detail retrieval, bilingual search, and Bat vs non-Bat boundary
7. Database error handling boundary
"""
import asyncio
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from alembic.config import Config
from alembic import command
from fastapi import FastAPI
from starlette.testclient import TestClient
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from src.reframe.catalog.models import FilmCatalog
from src.reframe.catalog.repository import FilmCatalogRepository
from tools.catalog.import_wikidata_catalog import run_importer, validate_catalog_payload
from apps.api.routers.catalog import router as catalog_router
from src.reframe.shared.database import get_db
from src.reframe.identity.auth import get_viewer_context, ViewerContext


class TestCatalogR1Ephemeral(unittest.TestCase):
    def setUp(self):
        custom_tmp = os.environ.get("REFRAME_TEST_TMP")
        if custom_tmp and not Path(custom_tmp).exists():
            Path(custom_tmp).mkdir(parents=True, exist_ok=True)
        self.temp_dir = tempfile.TemporaryDirectory(prefix="catalog-r1-", dir=custom_tmp)
        self.db_path = Path(self.temp_dir.name) / "ephemeral_r1.db"
        self.sync_db_url = f"sqlite:///{self.db_path.as_posix()}"
        self.async_db_url = f"sqlite+aiosqlite:///{self.db_path.as_posix()}"
        self.catalog_path = REPO_ROOT / "data" / "catalog" / "films_wikidata_v1.json"

        from src.reframe.shared.config import settings
        self.orig_db_url = settings.DATABASE_URL
        self.orig_sync_url = settings.SYNC_DATABASE_URL
        settings.DATABASE_URL = self.async_db_url
        settings.SYNC_DATABASE_URL = self.sync_db_url

    def tearDown(self):
        from src.reframe.shared.config import settings
        settings.DATABASE_URL = self.orig_db_url
        settings.SYNC_DATABASE_URL = self.orig_sync_url
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _get_alembic_config(self):
        ini_path = REPO_ROOT / "alembic.ini"
        migrations_dir = REPO_ROOT / "db" / "postgres" / "migrations"
        cfg = Config(str(ini_path))
        cfg.set_main_option("script_location", str(migrations_dir))
        cfg.set_main_option("sqlalchemy.url", self.sync_db_url)
        return cfg

    def test_01_importer_fails_without_migration_and_succeeds_after(self):
        """Preflight check: importer rejects writing to a DB where migration hasn't run."""
        # Clean engine without tables
        engine = create_engine(self.sync_db_url)
        engine.dispose()

        # 1. Importer must raise RuntimeError due to missing table
        with self.assertRaises(RuntimeError) as ctx:
            run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))
        self.assertIn("Target table 'film_catalog' does not exist", str(ctx.exception))

        # 2. Apply Alembic migration up to 0013
        cfg = self._get_alembic_config()
        command.upgrade(cfg, "0013_v7_film_catalog_metadata")

        # Table must now exist in DB
        engine = create_engine(self.sync_db_url)
        insp = inspect(engine)
        self.assertTrue(insp.has_table("film_catalog"))
        engine.dispose()

        # 3. Importer now succeeds
        stats = run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))
        self.assertEqual(stats["inserted"], 20)
        self.assertEqual(stats["skipped"], 0)

    def test_02_idempotency_and_mutation_rejections_with_rollback(self):
        """Test strict immutability, conflict rejection, and transaction rollback."""
        # Run migration
        cfg = self._get_alembic_config()
        command.upgrade(cfg, "0013_v7_film_catalog_metadata")

        # Initial import
        run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))

        # 1. Re-running with identical payload must be a pure no-op (20 skipped, 0 inserted)
        stats2 = run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))
        self.assertEqual(stats2["inserted"], 0)
        self.assertEqual(stats2["skipped"], 20)

        # Disconnect and verify persistence across fresh connection
        engine = create_engine(self.sync_db_url)
        with Session(engine) as session:
            count = session.query(FilmCatalog).count()
            self.assertEqual(count, 20)

            # 2. Mutating content on same revision MUST be rejected
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                payload = json.load(f)

            mutated = copy.deepcopy(payload)
            # Alter title of first film without bumping revision
            mutated["films"][0]["title_en"] = "Tampered Inception"

            with self.assertRaises(ValueError) as ctx_mutation:
                FilmCatalogRepository.sync_import_films(session, mutated["films"])
            self.assertIn("Content mutation rejected", str(ctx_mutation.exception))
            session.rollback()

            # Verify no mutation occurred
            row = session.query(FilmCatalog).filter(FilmCatalog.movie_id == mutated["films"][0]["movie_id"]).first()
            self.assertNotEqual(row.title_en, "Tampered Inception")

            # 2b. Mutating title_ko under same revision MUST be rejected
            mutated_ko = copy.deepcopy(payload)
            mutated_ko["films"][0]["title_ko"] = "변조된 제목"
            with self.assertRaises(ValueError) as ctx_ko:
                FilmCatalogRepository.sync_import_films(session, mutated_ko["films"])
            self.assertIn("Content mutation rejected", str(ctx_ko.exception))
            session.rollback()

            # 2c. Mutating runtime_minutes under same revision MUST be rejected
            mutated_rt = copy.deepcopy(payload)
            mutated_rt["films"][0]["runtime_minutes"] = 999
            with self.assertRaises(ValueError) as ctx_rt:
                FilmCatalogRepository.sync_import_films(session, mutated_rt["films"])
            self.assertIn("Content mutation rejected", str(ctx_rt.exception))
            session.rollback()

            # 2d. Mutating poster metadata under same revision MUST be rejected
            mutated_poster = copy.deepcopy(payload)
            mutated_poster["films"][0]["poster"]["sha256"] = "tampered_sha256"
            with self.assertRaises(ValueError) as ctx_poster:
                FilmCatalogRepository.sync_import_films(session, mutated_poster["films"])
            self.assertIn("Content mutation rejected", str(ctx_poster.exception))
            session.rollback()

            # 3. Revision overwrite MUST be rejected
            rev_overwritten = copy.deepcopy(payload)
            rev_overwritten["films"][0]["source_revision"] = rev_overwritten["films"][0]["source_revision"] + 1
            with self.assertRaises(ValueError) as ctx_rev:
                FilmCatalogRepository.sync_import_films(session, rev_overwritten["films"])
            self.assertIn("Revision overwrite rejected", str(ctx_rev.exception))
            session.rollback()

            # 4. ID / QID conflict MUST be rejected
            qid_conflict = copy.deepcopy(payload)
            qid_conflict["films"][0]["qid"] = "Q99999999"  # same movie_id, different QID
            with self.assertRaises(ValueError) as ctx_qid:
                FilmCatalogRepository.sync_import_films(session, qid_conflict["films"])
            self.assertIn("ID/QID conflict", str(ctx_qid.exception))
            session.rollback()

            # 5. Atomic rollback on batch invalid input:
            # Add 1 valid new film + 1 invalid film (missing revision)
            test_batch = [
                {
                    "movie_id": "wd-q9999901",
                    "qid": "Q9999901",
                    "title_en": "New Valid Film",
                    "source_revision": 1234567,
                    "fetched_at_utc": "2026-09-06T12:00:00Z",
                    "source_url": "https://example.com",
                    "year": 2026,
                },
                {
                    "movie_id": "wd-q9999902",
                    "qid": "Q9999902",
                    "title_en": "Invalid Film Missing Revision",
                    # missing source_revision
                    "fetched_at_utc": "2026-09-06T12:00:00Z",
                    "source_url": "https://example.com",
                    "year": 2026,
                }
            ]
            with self.assertRaises(ValueError) as ctx_batch:
                FilmCatalogRepository.sync_import_films(session, test_batch)
            session.rollback()

            # The valid new film must NOT have been persisted
            new_row = session.query(FilmCatalog).filter(FilmCatalog.movie_id == "wd-q9999901").first()
            self.assertIsNone(new_row)
            self.assertEqual(session.query(FilmCatalog).count(), 20)

        engine.dispose()

    def test_03_api_empty_db_and_pagination_boundaries(self):
        """Test API behavior on empty DB (no Bat fallback) and out-of-bounds pagination."""
        cfg = self._get_alembic_config()
        command.upgrade(cfg, "0013_v7_film_catalog_metadata")

        async_engine = create_async_engine(self.async_db_url, echo=False)
        async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

        app = FastAPI()
        app.include_router(catalog_router, prefix="/api/v1")
        app.dependency_overrides[get_viewer_context] = lambda: ViewerContext()
        async def override_get_db():
            async with async_session_factory() as session:
                yield session
        app.dependency_overrides[get_db] = override_get_db

        with TestClient(app) as client:
            # 1. Empty DB: GET /api/v1/films
            resp_empty = client.get("/api/v1/films")
            self.assertEqual(resp_empty.status_code, 200)
            body_empty = resp_empty.json()
            self.assertEqual(body_empty["data"], [])
            self.assertEqual(body_empty["meta"]["total"], 0)
            self.assertEqual(body_empty["meta"]["offset"], 0)

            # 2. Empty DB: GET /api/v1/films/the-bat-whispers-1930 MUST return 404 (not fake Bat)
            resp_bat_empty = client.get("/api/v1/films/the-bat-whispers-1930")
            self.assertEqual(resp_bat_empty.status_code, 404)

            # Populate DB with the 20 films
            run_importer(self.sync_db_url, self.catalog_path, dry_run=False, expected_target=str(self.db_path))

            # 3. Full catalog: GET /api/v1/films
            resp_full = client.get("/api/v1/films?limit=20&offset=0")
            self.assertEqual(resp_full.status_code, 200)
            body_full = resp_full.json()
            self.assertEqual(body_full["meta"]["total"], 20)
            self.assertEqual(len(body_full["data"]), 20)
            # Core demo film is ranked first
            self.assertEqual(body_full["data"][0]["movie_id"], "the-bat-whispers-1930")

            # 4. Out-of-bounds pagination: offset=20 (exact end)
            resp_off20 = client.get("/api/v1/films?limit=20&offset=20")
            self.assertEqual(resp_off20.status_code, 200)
            body_off20 = resp_off20.json()
            self.assertEqual(body_off20["meta"]["total"], 20)
            self.assertEqual(body_off20["data"], [])  # MUST BE EMPTY, NOT Bat!

            # 5. Out-of-bounds pagination: offset=50 (far beyond end)
            resp_off50 = client.get("/api/v1/films?limit=20&offset=50")
            self.assertEqual(resp_off50.status_code, 200)
            body_off50 = resp_off50.json()
            self.assertEqual(body_off50["meta"]["total"], 20)
            self.assertEqual(body_off50["data"], [])  # MUST BE EMPTY!

            # 6. Invalid pagination parameters
            self.assertEqual(client.get("/api/v1/films?limit=0").status_code, 422)
            self.assertEqual(client.get("/api/v1/films?limit=100").status_code, 422)
            self.assertEqual(client.get("/api/v1/films?offset=-1").status_code, 422)

            # 7. Bilingual search (English and Korean titles)
            # English search
            resp_q_en = client.get("/api/v1/films?q=inception")
            self.assertEqual(resp_q_en.status_code, 200)
            self.assertEqual(resp_q_en.json()["meta"]["total"], 1)
            self.assertEqual(resp_q_en.json()["data"][0]["title"], "Inception")

            # Korean searches: Parasite (기생충), Inception (인셉션), Gaslight (가스등)
            resp_q_ko = client.get("/api/v1/films?q=기생충")
            self.assertEqual(resp_q_ko.status_code, 200)
            self.assertEqual(resp_q_ko.json()["meta"]["total"], 1)
            self.assertEqual(resp_q_ko.json()["data"][0]["title"], "Parasite")

            resp_q_inc = client.get("/api/v1/films?q=인셉션")
            self.assertEqual(resp_q_inc.status_code, 200)
            self.assertEqual(resp_q_inc.json()["meta"]["total"], 1)
            self.assertEqual(resp_q_inc.json()["data"][0]["title"], "Inception")

            resp_q_gas = client.get("/api/v1/films?q=가스등")
            self.assertEqual(resp_q_gas.status_code, 200)
            self.assertEqual(resp_q_gas.json()["meta"]["total"], 1)
            self.assertEqual(resp_q_gas.json()["data"][0]["title"], "Gaslight")

            # Empty search result
            resp_q_none = client.get("/api/v1/films?q=no-such-film-xyz")
            self.assertEqual(resp_q_none.status_code, 200)
            self.assertEqual(resp_q_none.json()["meta"]["total"], 0)
            self.assertEqual(resp_q_none.json()["data"], [])

            # 8. All 20 films detail lookup
            with open(self.catalog_path, "r", encoding="utf-8") as f:
                catalog_data = json.load(f)
            for film_item in catalog_data["films"]:
                m_id = film_item["movie_id"]
                resp_d = client.get(f"/api/v1/films/{m_id}")
                self.assertEqual(resp_d.status_code, 200, f"Detail lookup failed for {m_id}")
                d_body = resp_d.json()["data"]
                self.assertEqual(d_body["movie_id"], m_id)
                if m_id == "the-bat-whispers-1930":
                    self.assertTrue(d_body["core_demo_supported"])
                    self.assertEqual(d_body["analysis_status"], "READY")
                else:
                    self.assertFalse(d_body["core_demo_supported"])
                    self.assertEqual(d_body["analysis_status"], "NOT_SUPPORTED")
                    self.assertIn("The Bat Whispers", d_body.get("analysis_notice", ""))

            # 9. Non-Bat reveal endpoint guard
            resp_rev_inc = client.get("/api/v1/films/wd-q25188/reveals")
            self.assertEqual(resp_rev_inc.status_code, 404)
            self.assertIn("The Bat Whispers", resp_rev_inc.json()["detail"]["message"])

        asyncio.run(async_engine.dispose())

    def test_04_api_db_error_handling(self):
        """Test API returns 503/500 cleanly when database connection fails, without fallback."""
        app = FastAPI()
        app.include_router(catalog_router, prefix="/api/v1")
        app.dependency_overrides[get_viewer_context] = lambda: ViewerContext()

        # Database session that throws error
        async def broken_db():
            raise RuntimeError("Simulated DB connection failure")
            yield None
        app.dependency_overrides[get_db] = broken_db

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/api/v1/films")
            self.assertIn(resp.status_code, [500, 503])

            resp_detail = client.get("/api/v1/films/the-bat-whispers-1930")
            self.assertIn(resp_detail.status_code, [500, 503])


if __name__ == "__main__":
    unittest.main()
