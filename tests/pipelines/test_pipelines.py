from pathlib import Path
import pytest
from pipelines.asset_lock.verify_asset import verify_asset_manifest
from pipelines.ingest.clickhouse_loader import generate_insert_statements


def test_asset_manifest_verification():
    manifest_path = Path(__file__).resolve().parent.parent.parent / "data" / "manifests" / "asset_manifest.json"
    result = verify_asset_manifest(manifest_path)
    assert result["status"] == "APPROVED"
    assert result["movie_id"] == "the-bat-whispers-1930"
    assert "US" in result["territories"]


def test_clickhouse_insert_generation():
    fixture_path = Path(__file__).resolve().parent.parent.parent / "data" / "fixtures" / "the_bat_whispers_golden.json"
    statements = generate_insert_statements(fixture_path)
    assert len(statements["films"]) == 1
    assert len(statements["scenes"]) >= 5
    assert "INSERT INTO reframe.films" in statements["films"][0]
    assert "INSERT INTO reframe.scenes" in statements["scenes"][0]
