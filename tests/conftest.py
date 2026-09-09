"""
Pytest global fixtures for Reframe V7 test suite
Zero Paid Model Calls.
"""
import asyncio
import os
import socket
import tempfile
import pathlib
import pytest
import pytest_asyncio
import hashlib
import sys
import threading
from unittest.mock import patch
from typing import Any, Optional, Dict, List
import google.genai
import google.genai.client

# Guarantee single module identity whether imported as conftest or tests.conftest
sys.modules["tests.conftest"] = sys.modules[__name__]

# 1. Resolve repository root and repository-local reframe_v7.db
_repo_root = pathlib.Path(__file__).parent.parent.resolve()
_repo_db_path = _repo_root / "reframe_v7.db"

# 2. Define the fingerprint helper.
def _get_db_fingerprint(db_path: pathlib.Path):
    if not db_path.exists():
        return {"exists": False}
    st = db_path.stat()
    with open(db_path, "rb") as f:
        h = hashlib.sha256(f.read()).hexdigest()
    return {
        "exists": True,
        "sha256": h,
        "size": st.st_size,
        "st_mtime_ns": st.st_mtime_ns
    }

# 3. Capture the original repository DB fingerprint before project imports.
_initial_db_fingerprint = _get_db_fingerprint(_repo_db_path)

# 4. Store original process environment values using a missing-value sentinel.
_overridden_keys = [
    "DATABASE_URL", "SYNC_DATABASE_URL",
    "EXECUTION_MODE", "PAID_CALLS_ENABLED", "SPEND_KILL_SWITCH_ACTIVE",
    "LIVE_AGENT_ENABLED", "LIVE_EVAL_ENABLED", "PUBLIC_REFRAME_MODEL_CALLS",
    "PUBLIC_PROOF_LOOKUP_MODEL_CALLS", "PUBLIC_COMMUNITY_MODEL_CALLS",
    "PUBLIC_AGENT_MODEL_CALLS", "PUBLIC_EVAL_MODEL_CALLS",
    "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "GOOGLE_APPLICATION_CREDENTIALS", "COMMENT_MODERATION_ENABLED", "COMMENT_MODERATION_API_KEY"
]
_MISSING_SENTINEL = object()
_orig_environ = {k: os.environ.get(k, _MISSING_SENTINEL) for k in _overridden_keys}

# 5. Create one tempfile.TemporaryDirectory
_temp_dir = tempfile.TemporaryDirectory(prefix="reframe-pytest-")

# 6. Resolve and validate the exact temporary directory.
_temp_dir_path = pathlib.Path(_temp_dir.name).resolve()

# 7. Verify it is outside the repository.
if _repo_root in _temp_dir_path.parents or _temp_dir_path == _repo_root:
    raise RuntimeError(f"Temp DB directory must be outside repository root: {_temp_dir_path}")

# 8. Define one exact DB path
_test_db_path = _temp_dir_path / "pytest-session.db"

# 9. Set absolute async and sync SQLite URLs.
_db_url_path = str(_test_db_path).replace('\\', '/')
_async_url = f"sqlite+aiosqlite:///{_db_url_path}"
_sync_url = f"sqlite:///{_db_url_path}"

# 10. Override values
os.environ["DATABASE_URL"] = _async_url
os.environ["SYNC_DATABASE_URL"] = _sync_url

os.environ["EXECUTION_MODE"] = "OFFLINE_FIXTURE"
os.environ["PAID_CALLS_ENABLED"] = "false"
os.environ["SPEND_KILL_SWITCH_ACTIVE"] = "true"
os.environ["LIVE_AGENT_ENABLED"] = "false"
os.environ["LIVE_EVAL_ENABLED"] = "false"
os.environ["PUBLIC_REFRAME_MODEL_CALLS"] = "0"
os.environ["PUBLIC_PROOF_LOOKUP_MODEL_CALLS"] = "0"
os.environ["PUBLIC_COMMUNITY_MODEL_CALLS"] = "0"
os.environ["PUBLIC_AGENT_MODEL_CALLS"] = "0"
os.environ["PUBLIC_EVAL_MODEL_CALLS"] = "0"

os.environ["GOOGLE_CLIENT_ID"] = ""
os.environ["GOOGLE_CLIENT_SECRET"] = ""
os.environ["GEMINI_API_KEY"] = ""
os.environ["GOOGLE_API_KEY"] = ""
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""
os.environ["COMMENT_MODERATION_ENABLED"] = "false"
os.environ["COMMENT_MODERATION_API_KEY"] = ""

# ---------------------------------------------------------------------------
# Global Google Model Call Tripwire Architecture (V7-P1-GATE-002-D-R2)
# Fail-closed blocking of Google GenAI / Vertex production model calls in ordinary tests.
# ---------------------------------------------------------------------------

class TripwireState:
    """Thread-safe state tracking for model generation attempts during tests."""
    def __init__(self, nodeid: str = ""):
        self.nodeid = nodeid
        self._lock = threading.Lock()
        self._attempts: List[Dict[str, Any]] = []

    @property
    def attempts(self) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._attempts)

    def record_attempt(self, is_async: bool, method_name: str) -> None:
        with self._lock:
            call_count = len(self._attempts) + 1
            record = {
                "is_async": is_async,
                "mode": "async" if is_async else "sync",
                "method_name": method_name,
                "test_nodeid": self.nodeid,
                "call_count": call_count,
            }
            self._attempts.append(record)
        raise AssertionError(
            f"REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS: "
            f"Blocked forbidden Google model generation attempt in test '{self.nodeid}'. "
            f"Method: {method_name} (is_async={is_async}, attempt #{call_count})."
        )

    def assert_clean(self) -> None:
        with self._lock:
            count = len(self._attempts)
            records = list(self._attempts)
        if count > 0:
            raise AssertionError(
                f"REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS: "
                f"Teardown tripwire detected {count} unhandled provider model call attempt(s) "
                f"during test '{self.nodeid}': {records}"
            )


class SyncSentinelModels:
    def __init__(self, state: TripwireState):
        self._state = state

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=False, method_name="models.generate_content")

    def generate_content_stream(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=False, method_name="models.generate_content_stream")
        yield


class AsyncSentinelModels:
    def __init__(self, state: TripwireState):
        self._state = state

    async def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=True, method_name="aio.models.generate_content")

    async def generate_content_stream(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=True, method_name="aio.models.generate_content_stream")
        yield


class SentinelAio:
    def __init__(self, state: TripwireState):
        self._state = state
        self.models = AsyncSentinelModels(state)

    async def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=True, method_name="aio.generate_content")

    async def generate_content_stream(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=True, method_name="aio.generate_content_stream")
        yield


class SentinelGenAiClient:
    __is_tripwire_sentinel__ = True

    def __init__(self, state: TripwireState, *args: Any, **kwargs: Any):
        if not isinstance(state, TripwireState):
            raise RuntimeError(
                "SentinelGenAiClient requires an explicit TripwireState; untracked fallback is forbidden."
            )
        self._state = state
        self.models = SyncSentinelModels(state)
        self.aio = SentinelAio(state)
        self._init_args = args
        self._init_kwargs = kwargs

    def generate_content(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=False, method_name="generate_content")

    def generate_content_stream(self, *args: Any, **kwargs: Any) -> Any:
        self._state.record_attempt(is_async=False, method_name="generate_content_stream")
        yield


def create_sentinel_factory(state: TripwireState):
    """Creates a bound factory callable that instantiates SentinelGenAiClient capturing `state` in closure."""
    if not isinstance(state, TripwireState):
        raise RuntimeError("create_sentinel_factory requires an explicit TripwireState.")

    def factory(*args: Any, **kwargs: Any) -> SentinelGenAiClient:
        return SentinelGenAiClient(state, *args, **kwargs)

    factory.__is_tripwire_sentinel__ = True
    factory._state = state
    return factory


# ---------------------------------------------------------------------------
# Process-Lifetime Bootstrap Sentinel Installation (V7-P1-GATE-002-D-R2)
# Replaces google.genai.Client and google.genai.client.Client BEFORE any production
# module import. No original Client constructor is saved, exposed, or restored.
# ---------------------------------------------------------------------------
_bootstrap_tripwire_state = TripwireState(nodeid="process-lifetime-bootstrap")
_bootstrap_factory = create_sentinel_factory(_bootstrap_tripwire_state)

google.genai.Client = _bootstrap_factory
google.genai.client.Client = _bootstrap_factory

# ---------------------------------------------------------------------------
# Production Module Imports (Executed strictly after bootstrap sentinel installation)
# ---------------------------------------------------------------------------
from src.reframe.shared.config import settings
from src.reframe.shared.database import Base, async_engine, sync_engine, AsyncSessionLocal
import src.reframe.identity.models
import src.reframe.spoiler.models
import src.reframe.evidence.models
import src.reframe.jobs.models
import src.reframe.cost.models
import src.reframe.audit.models
import src.reframe.moderation.models
import src.reframe.community.models
import src.reframe.proof.models
import src.reframe.catalog.models
from src.reframe.catalog.repository import FilmCatalogRepository
from src.reframe.proof.store import canonical_proof_store


_session_tripwire_registry: List[TripwireState] = []
_session_tripwire_lock = threading.Lock()


@pytest.fixture(scope="session", autouse=True)
def global_session_provider_guard():
    """
    Session-scoped autouse provider guard.
    Inspects process-lifetime bootstrap state and all registered per-test states.
    Does NOT start patcher or call patch.stop() / restore original Client in teardown;
    bootstrap sentinel remains active for the entire process lifetime.
    """
    try:
        yield _bootstrap_tripwire_state
    finally:
        session_errors = []
        try:
            _bootstrap_tripwire_state.assert_clean()
        except AssertionError as e:
            session_errors.append(f"Bootstrap state error: {e}")

        with _session_tripwire_lock:
            registered_states = list(_session_tripwire_registry)

        for st in registered_states:
            try:
                st.assert_clean()
            except AssertionError as e:
                session_errors.append(f"Late attempt detected in test '{st.nodeid}': {e}")

        # Verify both Client attributes remain bootstrap sentinels
        if not getattr(google.genai.Client, "__is_tripwire_sentinel__", False):
            session_errors.append("google.genai.Client lost __is_tripwire_sentinel__ marker!")
        if not getattr(google.genai.client.Client, "__is_tripwire_sentinel__", False):
            session_errors.append("google.genai.client.Client lost __is_tripwire_sentinel__ marker!")

        if session_errors:
            raise AssertionError(
                "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS: "
                "Session final check detected unhandled provider call attempts or corrupted sentinel:\n"
                + "\n".join(session_errors)
            )


@pytest.fixture(autouse=True)
def global_provider_tripwire(request):
    """
    Function-scoped autouse guard that replaces google.genai.Client with a bound factory
    capturing the test's TripwireState.
    1. Creates TripwireState for this test nodeid and registers it in session registry.
    2. Uses create_sentinel_factory(state) to patch google.genai.Client and google.genai.client.Client.
    3. Any thread or TestClient executing in this test calls the bound factory and records to this state.
    4. In teardown, runs state.assert_clean() before stopping the patch.
    5. In finally, safely stops the patchers so google.genai.Client reverts to process-lifetime bootstrap sentinel.
    6. Verifies that both Client paths reverted to bootstrap sentinel.
    """
    nodeid = getattr(request.node, "nodeid", str(request.node))
    state = TripwireState(nodeid=nodeid)
    with _session_tripwire_lock:
        _session_tripwire_registry.append(state)

    factory = create_sentinel_factory(state)
    patcher_genai = patch("google.genai.Client", new=factory)
    patcher_client = patch("google.genai.client.Client", new=factory)

    patcher_genai.start()
    patcher_client.start()

    try:
        yield state
    finally:
        try:
            state.assert_clean()
        finally:
            try:
                patcher_client.stop()
            except Exception:
                pass
            try:
                patcher_genai.stop()
            except Exception:
                pass

            assert getattr(google.genai.Client, "__is_tripwire_sentinel__", False) is True, (
                "google.genai.Client must revert to bootstrap sentinel"
            )
            assert getattr(google.genai.client.Client, "__is_tripwire_sentinel__", False) is True, (
                "google.genai.client.Client must revert to bootstrap sentinel"
            )
            assert google.genai.Client is _bootstrap_factory, (
                "google.genai.Client must revert to _bootstrap_factory"
            )
            assert google.genai.client.Client is _bootstrap_factory, (
                "google.genai.client.Client must revert to _bootstrap_factory"
            )

@pytest.fixture(scope="session")
def database_isolation_metadata():
    return {
        "repo_root": _repo_root,
        "repo_db_path": _repo_db_path,
        "temp_dir": _temp_dir_path,
        "temp_db_path": _test_db_path,
        "initial_fingerprint": _initial_db_fingerprint,
    }

def is_clickhouse_available() -> bool:
    try:
        s = socket.create_connection(("localhost", 8123), timeout=0.3)
        s.close()
        return True
    except Exception:
        return False

def pytest_collection_modifyitems(config, items):
    has_live_integration = any("tests/live_integration" in item.nodeid.replace("\\", "/") for item in items)

    ch_available = False
    if has_live_integration:
        ch_available = is_clickhouse_available()

    skip_ch = pytest.mark.skip(reason="Live ClickHouse service not reachable on localhost:8123")
    skip_browser = pytest.mark.skip(reason="Live browser E2E test requires running web server")

    for item in items:
        if "tests/live_integration" in item.nodeid.replace("\\", "/"):
            if not ch_available:
                item.add_marker(skip_ch)
        if "test_real_browser_e2e.py" in item.nodeid.replace("\\", "/"):
            item.add_marker(skip_browser)

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_database(global_session_provider_guard):
    """Initializes database schema and seeds canonical proofs for the test session"""
    settings.AUTH_DEV_MODE = True

    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with AsyncSessionLocal() as session:
            from src.reframe.identity.models import User, Profile, PUBLIC_AUTHOR_USER_ID
            pub_user = await session.get(User, PUBLIC_AUTHOR_USER_ID)
            if not pub_user:
                session.add(User(
                    id=PUBLIC_AUTHOR_USER_ID,
                    email_normalized="public-author@reframe.local",
                    handle="public_audience",
                    handle_normalized="public_audience",
                    status="ACTIVE",
                    role="USER"
                ))
                session.add(Profile(
                    user_id=PUBLIC_AUTHOR_USER_ID,
                    display_name="Public Audience",
                    bio="Public Audience reviewer profile for Reframe Phase 1.",
                    locale="en-US"
                ))
                await session.commit()
            await canonical_proof_store.seed_canonical_proofs(session)

        # Seed canonical film catalog in test database
        catalog_path = _repo_root / "data" / "catalog" / "films_wikidata_v3.json"
        if not catalog_path.exists():
            catalog_path = _repo_root / "data" / "catalog" / "films_wikidata_v1.json"
        if catalog_path.exists():
            import json
            from sqlalchemy.orm import Session
            with open(catalog_path, "r", encoding="utf-8") as f:
                films_payload = json.load(f).get("films", [])
            with Session(sync_engine) as sync_session:
                FilmCatalogRepository.sync_import_films(sync_session, films_payload)
                sync_session.commit()

        yield
    finally:
        cleanup_errors = []

        try:
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
        except Exception as e:
            cleanup_errors.append(f"Drop schema failed: {e}")

        try:
            await async_engine.dispose()
        except Exception as e:
            cleanup_errors.append(f"async_engine.dispose failed: {e}")

        try:
            sync_engine.dispose()
        except Exception as e:
            cleanup_errors.append(f"sync_engine.dispose failed: {e}")

        try:
            final_fp = _get_db_fingerprint(_repo_db_path)
            fp_changed = False

            if _initial_db_fingerprint["exists"] != final_fp["exists"]:
                fp_changed = True
            elif _initial_db_fingerprint["exists"]:
                if _initial_db_fingerprint["sha256"] != final_fp["sha256"] or \
                   _initial_db_fingerprint["size"] != final_fp["size"] or \
                   _initial_db_fingerprint["st_mtime_ns"] != final_fp["st_mtime_ns"]:
                    fp_changed = True

            if fp_changed:
                cleanup_errors.append(
                    f"reframe_v7.db fingerprint changed! Before: {_initial_db_fingerprint} After: {final_fp}"
                )
        except Exception as e:
            cleanup_errors.append(f"Fingerprint check failed: {e}")

        try:
            _temp_dir.cleanup()
        except Exception as e:
            cleanup_errors.append(f"Temp dir cleanup failed: {e}")

        for k, v in _orig_environ.items():
            try:
                if v is _MISSING_SENTINEL:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            except Exception as e:
                cleanup_errors.append(f"Restore env {k} failed: {e}")

        if cleanup_errors:
            pytest.fail("Teardown failures:\n" + "\n".join(cleanup_errors))
