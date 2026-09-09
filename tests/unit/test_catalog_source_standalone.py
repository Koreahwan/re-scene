"""
Standalone unit test suite for Wikidata film catalog collection and schemas.
Tests offline parser fixtures, validation, safe hosts, and verifies harvested 20-film data.
Can be executed directly with:
    python -I -B tests/unit/test_catalog_source_standalone.py
"""
import hashlib
import json
import os
from pathlib import Path
import unittest

import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

DATA_DIR = REPO_ROOT / "data" / "catalog"
ASSETS_DIR = REPO_ROOT / "apps" / "web" / "public" / "assets" / "catalog" / "wikidata"

from tools.catalog.collect_wikidata_films import (
    ALLOWED_HOSTS,
    TARGET_FILMS,
    parse_year_from_snak,
    parse_duration_from_snak,
)


class TestCatalogSourceStandalone(unittest.TestCase):
    def test_allowed_hosts_whitelist(self):
        """Verify only official wikidata/commons/upload hosts are permitted."""
        self.assertIn("www.wikidata.org", ALLOWED_HOSTS)
        self.assertIn("commons.wikimedia.org", ALLOWED_HOSTS)
        self.assertIn("upload.wikimedia.org", ALLOWED_HOSTS)
        self.assertNotIn("imdb.com", ALLOWED_HOSTS)
        self.assertNotIn("themoviedb.org", ALLOWED_HOSTS)

    def test_parse_year_from_snak(self):
        """Test year extraction from valid and malformed Wikidata snaks."""
        valid_snak = {"datavalue": {"value": {"time": "+1930-11-13T00:00:00Z"}}}
        self.assertEqual(parse_year_from_snak(valid_snak), 1930)

        year_only_snak = {"datavalue": {"value": {"time": "+2010-00-00T00:00:00Z"}}}
        self.assertEqual(parse_year_from_snak(year_only_snak), 2010)

        malformed_snak = {"datavalue": {"value": {"time": "invalid"}}}
        self.assertIsNone(parse_year_from_snak(malformed_snak))

        empty_snak = {}
        self.assertIsNone(parse_year_from_snak(empty_snak))

    def test_parse_duration_from_snak(self):
        """Test duration parsing for minutes, seconds, hours, and invalid units."""
        min_snak = {"datavalue": {"value": {"amount": "+83", "unit": "http://www.wikidata.org/entity/Q7727"}}}
        self.assertEqual(parse_duration_from_snak(min_snak), 83)

        sec_snak = {"datavalue": {"value": {"amount": "+5040", "unit": "http://www.wikidata.org/entity/Q11574"}}}
        self.assertEqual(parse_duration_from_snak(sec_snak), 84)

        hour_snak = {"datavalue": {"value": {"amount": "+2", "unit": "http://www.wikidata.org/entity/Q25235"}}}
        self.assertEqual(parse_duration_from_snak(hour_snak), 120)

        invalid_snak = {"datavalue": {"value": {"amount": "abc", "unit": "Q9999"}}}
        self.assertIsNone(parse_duration_from_snak(invalid_snak))

    def test_target_films_qids_and_titles(self):
        """Verify all 20 target films have unique QIDs and non-empty titles."""
        self.assertEqual(len(TARGET_FILMS), 20)
        qids = [f["qid"] for f in TARGET_FILMS]
        self.assertEqual(len(set(qids)), 20)
        for f in TARGET_FILMS:
            self.assertTrue(f["qid"].startswith("Q"))
            self.assertTrue(len(f["title"]) > 0)
            self.assertGreater(f["year"], 1900)

    def test_harvested_films_json_integrity(self):
        """Verify integrity of data/catalog/films_wikidata_v1.json if already collected."""
        films_file = DATA_DIR / "films_wikidata_v1.json"
        if not films_file.exists():
            self.skipTest("films_wikidata_v1.json not yet collected")

        with open(films_file, "r", encoding="utf-8") as f:
            catalog = json.load(f)

        self.assertEqual(catalog.get("count"), 20)
        films = catalog.get("films", [])
        self.assertEqual(len(films), 20)

        seen_movie_ids = set()
        seen_qids = set()

        for film in films:
            m_id = film["movie_id"]
            qid = film["qid"]
            self.assertNotIn(m_id, seen_movie_ids, f"Duplicate movie_id {m_id}")
            self.assertNotIn(qid, seen_qids, f"Duplicate qid {qid}")
            seen_movie_ids.add(m_id)
            seen_qids.add(qid)

            self.assertTrue(len(film["title_en"]) > 0)
            self.assertIsInstance(film["year"], int)
            self.assertGreater(film["year"], 1900)

            # Bat Whispers specific invariants
            if qid == "Q3985804":
                self.assertEqual(m_id, "the-bat-whispers-1930")
                self.assertTrue(film["core_demo_supported"])
            else:
                self.assertEqual(m_id, f"wd-{qid.lower()}")
                self.assertFalse(film["core_demo_supported"])

            # Poster verification if present
            poster = film.get("poster")
            if poster:
                self.assertTrue(poster["local_path"].startswith("/assets/catalog/wikidata/"))
                self.assertTrue(len(poster["sha256"]) == 64)
                asset_file = REPO_ROOT / "apps" / "web" / "public" / poster["local_path"].lstrip("/")
                self.assertTrue(asset_file.exists(), f"Asset {asset_file} does not exist")
                disk_sha = hashlib.sha256(asset_file.read_bytes()).hexdigest()
                self.assertEqual(disk_sha, poster["sha256"], f"Hash mismatch for {asset_file}")


if __name__ == "__main__":
    unittest.main()
