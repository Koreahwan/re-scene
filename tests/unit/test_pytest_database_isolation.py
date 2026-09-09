import os
import pathlib
import pytest
from sqlalchemy import text
from sqlalchemy.engine.url import make_url
from unittest.mock import patch

from src.reframe.shared.config import settings
from src.reframe.shared.database import async_engine, sync_engine, AsyncSessionLocal

@pytest.fixture
def forbidden_boundaries():
    """Ensure no model or network calls are made during the DB test."""
    with patch("src.reframe.agents.runtime.get_google_genai_client", side_effect=AssertionError("get_google_genai_client called!")) as m_rt, \
         patch("src.reframe.agents.adk_gateway.get_adk_execution_gateway", side_effect=AssertionError("get_adk_execution_gateway called!")) as m_gw, \
         patch("google.genai.Client", side_effect=AssertionError("genai.Client called!")) as m_genai, \
         patch("httpx.AsyncClient", side_effect=AssertionError("httpx.AsyncClient called!")) as m_http:
        yield
        m_rt.assert_not_called()
        m_gw.assert_not_called()
        m_genai.assert_not_called()
        m_http.assert_not_called()

def test_database_urls_point_to_temp_dir(database_isolation_metadata):
    """Parse and compare all four exact DB paths"""
    meta = database_isolation_metadata
    temp_db_path = meta["temp_db_path"]
    repo_root = meta["repo_root"]
    repo_db_path = meta["repo_db_path"]

    # 1. settings.DATABASE_URL
    async_db_str = make_url(settings.DATABASE_URL).database
    assert async_db_str is not None
    assert pathlib.Path(async_db_str).resolve() == temp_db_path

    # 2. settings.SYNC_DATABASE_URL
    sync_db_str = make_url(settings.SYNC_DATABASE_URL).database
    assert sync_db_str is not None
    assert pathlib.Path(sync_db_str).resolve() == temp_db_path

    # 3. async_engine.url
    engine_async_db_str = async_engine.url.database
    assert engine_async_db_str is not None
    assert pathlib.Path(engine_async_db_str).resolve() == temp_db_path

    # 4. sync_engine.url
    engine_sync_db_str = sync_engine.url.database
    assert engine_sync_db_str is not None
    assert pathlib.Path(engine_sync_db_str).resolve() == temp_db_path

    # Path properties
    assert repo_root not in temp_db_path.parents
    assert repo_root != temp_db_path.parent
    assert temp_db_path.name != "reframe_v7.db"
    assert temp_db_path != repo_db_path

def test_zero_paid_live_flags():
    """Prove all zero-cost flags are active."""
    assert settings.EXECUTION_MODE == "OFFLINE_FIXTURE"
    assert settings.PAID_CALLS_ENABLED is False
    assert settings.SPEND_KILL_SWITCH_ACTIVE is True
    assert settings.LIVE_AGENT_ENABLED is False
    assert settings.LIVE_EVAL_ENABLED is False
    assert int(settings.PUBLIC_REFRAME_MODEL_CALLS) == 0
    assert int(settings.PUBLIC_PROOF_LOOKUP_MODEL_CALLS) == 0
    assert int(settings.PUBLIC_COMMUNITY_MODEL_CALLS) == 0

@pytest.mark.asyncio
async def test_async_session_db_operations(database_isolation_metadata, forbidden_boundaries):
    """Write/read using AsyncSessionLocal and compare fingerprint before and after"""
    meta = database_isolation_metadata
    repo_db_path = meta["repo_db_path"]
    initial_fp = meta["initial_fingerprint"]

    # read/write query
    async with AsyncSessionLocal() as session:
        await session.execute(text("CREATE TABLE IF NOT EXISTS _pytest_isolation_test (id INTEGER PRIMARY KEY, val TEXT)"))
        await session.execute(text("INSERT INTO _pytest_isolation_test (val) VALUES ('isolated')"))
        await session.commit()

        result = await session.execute(text("SELECT val FROM _pytest_isolation_test LIMIT 1"))
        row = result.fetchone()
        assert row is not None
        assert row[0] == 'isolated'

    # Check fingerprint dynamically to ensure no mutation occurred mid-session
    import hashlib
    def get_current_fp(p):
        if not p.exists():
            return {"exists": False}
        st = p.stat()
        with open(p, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        return {"exists": True, "sha256": h, "size": st.st_size, "st_mtime_ns": st.st_mtime_ns}

    current_fp = get_current_fp(repo_db_path)
    assert current_fp == initial_fp
