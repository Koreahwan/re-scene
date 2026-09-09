"""
Tests for Alembic Version Table Width (VARCHAR(128)) Bootstrap.
Verifies that:
1. Fresh database creates alembic_version with version_num VARCHAR(>=128) and PK.
2. Existing database with VARCHAR(32) retains ability to store/retrieve exact long revision IDs.
3. In PostgreSQL, information_schema.columns character_maximum_length >= 128 is verified (disposable only).

Note: Complete fresh migration coverage belongs to:
    tests/db/test_fresh_clone_migration_reproducibility.py
"""
import os
import pathlib
import pytest
import sqlite3
import sqlalchemy as sa
from alembic.config import Config
from alembic.script import ScriptDirectory

# Allowlist import for testing logic
from db.postgres.migrations.env import ensure_version_table_width

def _get_longest_tracked_revision():
    _repo_root = pathlib.Path(__file__).parent.parent.parent.resolve()
    cfg = Config(str(_repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(_repo_root / "db/postgres/migrations"))
    script = ScriptDirectory.from_config(cfg)

    revisions = list(script.walk_revisions())
    longest = ""
    for rev in revisions:
        if len(rev.revision) > len(longest):
            longest = rev.revision
    return longest

def test_version_table_width_sql_bootstrap_logic():
    """Directly test the ensure_version_table_width logic on an in-memory database."""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        # 1. Assert alembic_version does not initially exist
        inspector = sa.inspect(conn)
        assert "alembic_version" not in inspector.get_table_names()

        # 2. Call ensure_version_table_width(connection)
        ensure_version_table_width(conn)

        # 3. Assert the table exists
        inspector = sa.inspect(conn)
        assert "alembic_version" in inspector.get_table_names()

        # 4. Inspect PRAGMA table_info(alembic_version)
        res = conn.execute(sa.text("PRAGMA table_info(alembic_version)")).fetchall()
        cols = {row[1]: row for row in res}

        # 5. Locate version_num
        assert "version_num" in cols
        v_col = cols["version_num"]

        # 6. Parse its declared type
        declared_type = v_col[2].upper()

        # 7. Require base type VARCHAR
        assert declared_type.startswith("VARCHAR"), f"Base type is not VARCHAR: {declared_type}"

        # 8. Require an explicit numeric width
        import re
        m = re.search(r'\((\d+)\)', declared_type)
        assert m is not None, f"Numeric length missing in {declared_type}"

        # 9. Require width >= 128
        parsed_length = int(m.group(1))
        assert parsed_length >= 128, f"Numeric length too short: {parsed_length} in {declared_type}"

        # 10. Require version_num to be the primary key
        # PRAGMA table_info pk column is at index 5
        assert v_col[5] >= 1, "version_num is not a primary key"

def test_existing_sqlite_varchar32_semantics():
    """Verify that long tracked revision IDs remain storable and retrievable exactly in existing SQLite."""
    # Create a separate in-memory SQLite database containing only:
    # alembic_version(version_num VARCHAR(32) PRIMARY KEY)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))

        # 1. Discover the longest tracked revision ID
        longest_rev = _get_longest_tracked_revision()

        # 2. Assert the discovered value is longer than 32 characters
        assert len(longest_rev) > 32, f"Longest tracked revision '{longest_rev}' is not > 32 chars"

        # 3. Call ensure_version_table_width(connection)
        ensure_version_table_width(conn)

        # 4. Insert the long tracked revision ID
        conn.execute(sa.text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": longest_rev})

        # 5. Read it back
        res = conn.execute(sa.text("SELECT version_num FROM alembic_version")).fetchall()

        # 6. Assert exact round-trip equality
        assert len(res) == 1
        assert res[0][0] == longest_rev

        # 7. Assert exactly one version row exists
        count = conn.execute(sa.text("SELECT COUNT(*) FROM alembic_version")).scalar()
        assert count == 1

def _postgres_skip_reason():
    if os.getenv("RUN_DISPOSABLE_POSTGRES_TESTS") != "1":
        return "RUN_DISPOSABLE_POSTGRES_TESTS is not 1"
    if not os.getenv("TEST_POSTGRES_URL"):
        return "TEST_POSTGRES_URL is not set"
    return None

@pytest.mark.skipif(_postgres_skip_reason() is not None, reason="PostgreSQL test explicitly skipped: " + str(_postgres_skip_reason()))
def test_postgres_information_schema_width():
    """Verify character_maximum_length >= 128 in PostgreSQL information_schema."""
    pg_url = os.getenv("TEST_POSTGRES_URL")
    engine = sa.create_engine(pg_url)
    with engine.connect() as conn:
        ensure_version_table_width(conn)
        res = conn.execute(sa.text("""
            SELECT character_maximum_length
            FROM information_schema.columns
            WHERE table_name = 'alembic_version' AND column_name = 'version_num'
        """)).scalar()
        assert res is not None
        assert res >= 128
