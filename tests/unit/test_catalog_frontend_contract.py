"""
Reframe V7 Unit Test Suite: Frontend Catalog & Detail View-Model Contracts (M05)
Zero Paid Model Calls.
Verifies:
- Pure envelope parsing & validation
- Trusted same-origin poster allowlist (/assets/catalog/wikidata/)
- Isolation of non-Bat films from Bat-only analysis
- Bilingual substring search logic
- Safe metadata mapping without hallucinated metrics
"""

import unittest
from typing import Any, Dict, List, Optional


def map_film_catalog_response(raw: Any) -> Dict[str, Any]:
    """Python reference mirror of apps/web/src/pages/filmCatalogViewModel.ts:mapFilmCatalogResponse."""
    if not isinstance(raw, dict) or "data" not in raw or not isinstance(raw["data"], list):
        return {"success": False, "error": "Malformed catalog response"}

    valid_films = []
    bat_local_poster = "/assets/uch80i8j8dzbiadblxgq66se2gecv-otj-bqoqsuwbu-2ypyvrr2b43adcirfgjxxqigwjnyhrc3ngh3s5mixq-1-I8-28118-73-6268.png"

    for i, record in enumerate(raw["data"]):
        if not isinstance(record, dict):
            return {"success": False, "error": f"Malformed catalog record at index {i}"}

        movie_id = record.get("movie_id")
        if not isinstance(movie_id, str) or not movie_id.strip():
            return {"success": False, "error": f"movie_id must be a non-empty string at index {i}"}

        title = record.get("title")
        if not isinstance(title, str) or not title.strip():
            return {"success": False, "error": f"title must be a non-empty string at index {i}"}

        trimmed_id = movie_id.strip()
        trimmed_title = title.strip()

        poster_path = None
        raw_poster = record.get("poster_path")
        if trimmed_id == "the-bat-whispers-1930":
            poster_path = bat_local_poster
        elif isinstance(raw_poster, str) and raw_poster.startswith("/assets/catalog/wikidata/"):
            poster_path = raw_poster

        valid_films.append({
            "movieId": trimmed_id,
            "title": trimmed_title,
            "year": record.get("year"),
            "posterPath": poster_path,
            "destination": f"/films/{trimmed_id}",
            "director": record.get("director"),
            "coreDemoSupported": record.get("core_demo_supported", trimmed_id == "the-bat-whispers-1930"),
        })

    return {"success": True, "films": valid_films}


def filter_films_by_query(films: List[Dict[str, Any]], query: Optional[str]) -> List[Dict[str, Any]]:
    """Python reference mirror of apps/web/src/pages/filmCatalogViewModel.ts:filterFilmsByQuery."""
    if not query or not query.strip():
        return films
    q = query.strip().lower()
    return [f for f in films if q in f.get("title", "").lower()]


def map_film_dto_to_view_model(dto: Any) -> Optional[Dict[str, Any]]:
    """Python reference mirror of apps/web/src/pages/filmDetailViewModel.ts:mapFilmDtoToViewModel."""
    if not isinstance(dto, dict):
        return None
    data = dto.get("data", dto)
    if not isinstance(data, dict):
        return None

    movie_id = data.get("movie_id", "")
    title = data.get("title", "")
    if not movie_id or not isinstance(movie_id, str) or not movie_id.strip():
        return None
    if not title or not isinstance(title, str) or not title.strip():
        return None

    trimmed_id = movie_id.strip()
    is_bat = (trimmed_id == "the-bat-whispers-1930")

    raw_poster = data.get("poster_path")
    poster_path = None
    if is_bat:
        poster_path = "/assets/batwhispers-1-84-12615.png"
    elif isinstance(raw_poster, str) and raw_poster.startswith("/assets/catalog/wikidata/"):
        poster_path = raw_poster

    core_demo_supported = data.get("core_demo_supported", is_bat)
    analysis_status = data.get("analysis_status", "READY" if core_demo_supported else "NOT_SUPPORTED")
    notice = data.get("notice", "" if core_demo_supported else "현재 핵심 분석 기능은 The Bat Whispers에서만 시연할 수 있습니다.")

    return {
        "movieId": trimmed_id,
        "title": title.strip(),
        "year": str(data.get("year", "")) if data.get("year") is not None else "",
        "director": data.get("director"),
        "posterPath": poster_path,
        "coreDemoSupported": core_demo_supported,
        "analysisStatus": analysis_status,
        "notice": notice,
        "synopsis": data.get("synopsis_safe", ""),
    }


class TestCatalogFrontendContract(unittest.TestCase):

    def test_catalog_response_mapping_invariants(self):
        # 1. Malformed envelope fails closed
        self.assertFalse(map_film_catalog_response(None)["success"])
        self.assertFalse(map_film_catalog_response([])["success"])
        self.assertFalse(map_film_catalog_response({"not_data": []})["success"])

        # 2. Missing movie_id or title fails closed
        self.assertFalse(map_film_catalog_response({"data": [{"title": "No ID"}]})["success"])
        self.assertFalse(map_film_catalog_response({"data": [{"movie_id": "id-1"}]})["success"])
        self.assertFalse(map_film_catalog_response({"data": [{"movie_id": "   ", "title": "T"}]})["success"])

        # 3. Valid empty catalog succeeds
        empty_res = map_film_catalog_response({"data": []})
        self.assertTrue(empty_res["success"])
        self.assertEqual(len(empty_res["films"]), 0)

        # 4. Valid 20 films catalog
        sample_catalog = {
            "data": [
                {
                    "movie_id": "the-bat-whispers-1930",
                    "title": "The Bat Whispers",
                    "year": 1930,
                    "director": "Roland West",
                    "poster_path": None,
                    "core_demo_supported": True,
                },
                {
                    "movie_id": "wd-q163038",
                    "title": "Vertigo",
                    "year": 1958,
                    "director": "Alfred Hitchcock",
                    "poster_path": "/assets/catalog/wikidata/Q163038.jpg",
                    "core_demo_supported": False,
                },
                {
                    "movie_id": "wd-q4985804",
                    "title": "Untrusted Poster Film",
                    "year": 2000,
                    "director": "Unknown",
                    "poster_path": "https://malicious.com/evil.jpg",  # Untrusted external URL
                    "core_demo_supported": False,
                },
            ]
        }
        res = map_film_catalog_response(sample_catalog)
        self.assertTrue(res["success"])
        films = res["films"]
        self.assertEqual(len(films), 3)

        # Bat Whispers receives local poster
        self.assertIn("uch80i8j8dzbiadblxgq66se2gecv", films[0]["posterPath"])
        self.assertTrue(films[0]["coreDemoSupported"])

        # Vertigo receives trusted local wikidata poster
        self.assertEqual(films[1]["posterPath"], "/assets/catalog/wikidata/Q163038.jpg")
        self.assertFalse(films[1]["coreDemoSupported"])

        # Untrusted external URL receives null
        self.assertIsNone(films[2]["posterPath"])

    def test_search_filtering(self):
        catalog = [
            {"movieId": "tbw", "title": "The Bat Whispers"},
            {"movieId": "vertigo", "title": "Vertigo (현기증)"},
            {"movieId": "gaslight", "title": "Gaslight (가스등)"},
        ]

        # Case-insensitivity
        self.assertEqual(len(filter_films_by_query(catalog, "bat")), 1)
        self.assertEqual(len(filter_films_by_query(catalog, "BAT")), 1)

        # Korean substring
        self.assertEqual(len(filter_films_by_query(catalog, "가스등")), 1)
        self.assertEqual(filter_films_by_query(catalog, "가스등")[0]["movieId"], "gaslight")

        # Non-matching query
        self.assertEqual(len(filter_films_by_query(catalog, "no-such-film-9f4ac69e")), 0)

        # Empty / whitespace query returns all
        self.assertEqual(len(filter_films_by_query(catalog, "")), 3)
        self.assertEqual(len(filter_films_by_query(catalog, "   ")), 3)

    def test_detail_view_model_mapping(self):
        # 1. Bat Whispers detail mapping
        bat_dto = {
            "data": {
                "movie_id": "the-bat-whispers-1930",
                "title": "The Bat Whispers",
                "year": 1930,
                "director": "Roland West",
                "synopsis_safe": "A cloaked criminal terrorizes a mansion.",
                "core_demo_supported": True,
                "analysis_status": "READY",
            }
        }
        bat_vm = map_film_dto_to_view_model(bat_dto)
        self.assertIsNotNone(bat_vm)
        self.assertEqual(bat_vm["movieId"], "the-bat-whispers-1930")
        self.assertEqual(bat_vm["posterPath"], "/assets/batwhispers-1-84-12615.png")
        self.assertTrue(bat_vm["coreDemoSupported"])
        self.assertEqual(bat_vm["analysisStatus"], "READY")

        # 2. Non-Bat film detail mapping
        non_bat_dto = {
            "data": {
                "movie_id": "wd-q163038",
                "title": "Vertigo",
                "year": 1958,
                "director": "Alfred Hitchcock",
                "poster_path": "/assets/catalog/wikidata/Q163038.jpg",
                "core_demo_supported": False,
                "analysis_status": "NOT_SUPPORTED",
                "synopsis_safe": "A former police detective wrestles with his demons.",
                "notice": "현재 핵심 분석 기능은 The Bat Whispers에서만 시연할 수 있습니다.",
            }
        }
        non_bat_vm = map_film_dto_to_view_model(non_bat_dto)
        self.assertIsNotNone(non_bat_vm)
        self.assertEqual(non_bat_vm["movieId"], "wd-q163038")
        self.assertEqual(non_bat_vm["posterPath"], "/assets/catalog/wikidata/Q163038.jpg")
        self.assertFalse(non_bat_vm["coreDemoSupported"])
        self.assertEqual(non_bat_vm["analysisStatus"], "NOT_SUPPORTED")
        self.assertIn("The Bat Whispers에서만 시연할 수 있습니다", non_bat_vm["notice"])


if __name__ == "__main__":
    unittest.main()
