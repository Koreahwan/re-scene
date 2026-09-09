"""
Standalone API test suite for /api/v1/films catalog and search endpoints.
Uses ephemeral SQLite database populated with the 20 harvested Wikidata films.
Can be executed directly with:
    python -I -B tests/unit/test_catalog_api_standalone.py
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

from starlette.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from src.reframe.catalog.models import FilmCatalog
from src.reframe.catalog.repository import FilmCatalogRepository
from tools.catalog.import_wikidata_catalog import run_importer
from apps.api.routers.catalog import router as catalog_router
from src.reframe.shared.database import get_db
from src.reframe.identity.auth import get_viewer_context, ViewerContext


class TestCatalogAPIStandalone(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        custom_tmp = os.environ.get("REFRAME_TEST_TMP")
        if custom_tmp and not Path(custom_tmp).exists():
            Path(custom_tmp).mkdir(parents=True, exist_ok=True)
        cls.temp_dir = tempfile.TemporaryDirectory(prefix="catalog-api-test-", dir=custom_tmp)
        cls.db_path = Path(cls.temp_dir.name) / "ephemeral_api_catalog.db"
        cls.sync_db_url = f"sqlite:///{cls.db_path.as_posix()}"
        cls.async_db_url = f"sqlite+aiosqlite:///{cls.db_path.as_posix()}"

        # Initialize schema & seed 20 films
        sync_engine = create_engine(cls.sync_db_url, echo=False)
        FilmCatalog.metadata.create_all(sync_engine)
        from sqlalchemy import text
        with sync_engine.begin() as conn:
            conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
            conn.execute(text("INSERT OR REPLACE INTO alembic_version (version_num) VALUES ('0013_v7_film_catalog_metadata')"))
        sync_engine.dispose()

        catalog_path = REPO_ROOT / "data" / "catalog" / "films_wikidata_v1.json"
        run_importer(cls.sync_db_url, catalog_path, dry_run=False, expected_target=str(cls.db_path))

        # Setup test FastAPI app
        cls.async_engine = create_async_engine(cls.async_db_url, echo=False)
        cls.async_session_factory = async_sessionmaker(cls.async_engine, expire_on_commit=False)

        cls.app = FastAPI()
        cls.app.include_router(catalog_router, prefix="/api/v1")

        # Mock viewer context dependency
        async def mock_viewer():
            return ViewerContext()

        # Mock DB dependency
        async def override_get_db():
            async with cls.async_session_factory() as session:
                yield session

        cls.app.dependency_overrides[get_viewer_context] = mock_viewer
        cls.app.dependency_overrides[get_db] = override_get_db

    @classmethod
    def tearDownClass(cls):
        asyncio.run(cls.async_engine.dispose())
        try:
            cls.temp_dir.cleanup()
        except Exception:
            pass

    def test_list_all_films(self):
        """Test GET /api/v1/films returns 20 films with The Bat Whispers ranked first."""
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/films")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["meta"]["total"], 20)
            films = data["data"]
            self.assertEqual(len(films), 20)
            # Bat Whispers is first
            self.assertEqual(films[0]["movie_id"], "the-bat-whispers-1930")
            self.assertTrue(films[0]["core_demo_supported"])

    def test_search_films(self):
        """Test search query filters accurately across titles."""
        with TestClient(self.app) as client:
            # 1. Search 'inception'
            resp = client.get("/api/v1/films?q=inception")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["meta"]["total"], 1)
            self.assertEqual(data["data"][0]["title"], "Inception")

            # 2. Search SQL-injection shaped input safely
            resp_sqli = client.get("/api/v1/films?q=' OR '1'='1")
            self.assertEqual(resp_sqli.status_code, 200)
            self.assertEqual(resp_sqli.json()["meta"]["total"], 0)

            # 3. Empty search result is 200 with []
            resp_empty = client.get("/api/v1/films?q=no-such-film-9f4ac69e")
            self.assertEqual(resp_empty.status_code, 200)
            self.assertEqual(resp_empty.json()["meta"]["total"], 0)
            self.assertEqual(len(resp_empty.json()["data"]), 0)

    def test_film_detail(self):
        """Test GET /api/v1/films/{movie_id} for Bat, non-Bat, and unknown."""
        with TestClient(self.app) as client:
            # Bat Whispers
            resp_bat = client.get("/api/v1/films/the-bat-whispers-1930")
            self.assertEqual(resp_bat.status_code, 200)
            data_bat = resp_bat.json()["data"]
            self.assertEqual(data_bat["movie_id"], "the-bat-whispers-1930")
            self.assertEqual(data_bat["analysis_status"], "READY")

            # Inception (non-bat)
            resp_inc = client.get("/api/v1/films/wd-q25188")
            self.assertEqual(resp_inc.status_code, 200)
            data_inc = resp_inc.json()["data"]
            self.assertEqual(data_inc["movie_id"], "wd-q25188")
            self.assertEqual(data_inc["title"], "Inception")
            self.assertEqual(data_inc["analysis_status"], "NOT_SUPPORTED")
            self.assertIn("The Bat Whispers", data_inc["analysis_notice"])

            # Unknown movie_id -> 404
            resp_404 = client.get("/api/v1/films/unknown-movie-id-123")
            self.assertEqual(resp_404.status_code, 404)

    def test_registered_metadata_film_has_empty_reveals_without_fallback(self):
        """Known catalog films have an empty collection until their analysis is imported."""
        with TestClient(self.app) as client:
            resp = client.get("/api/v1/films/wd-q25188/reveals")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["data"], [])
            self.assertEqual(resp.json()["meta"]["total"], 0)
            self.assertEqual(client.get("/api/v1/films/unregistered-film/reveals").status_code, 404)

    def test_invalid_pagination(self):
        """Test invalid limit or negative offset returns 422."""
        with TestClient(self.app) as client:
            resp_limit = client.get("/api/v1/films?limit=100")
            self.assertEqual(resp_limit.status_code, 422)

            resp_offset = client.get("/api/v1/films?offset=-5")
            self.assertEqual(resp_offset.status_code, 422)


if __name__ == "__main__":
    unittest.main()
