import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

from apps.api.routers.health import live_probe, ready_probe, admin_health, GeminiHealthStatus
from src.reframe.identity.auth import ViewerContext

@pytest.fixture
def forbidden_boundaries():
    """Mock out model/external call boundaries to raise AssertionError if called."""
    with patch("src.reframe.agents.runtime.get_google_genai_client", side_effect=AssertionError("get_google_genai_client was called!")) as m_rt, \
         patch("src.reframe.agents.adk_gateway.get_adk_execution_gateway", side_effect=AssertionError("get_adk_execution_gateway was called!")) as m_gw, \
         patch("google.genai.Client", side_effect=AssertionError("genai.Client was called!")) as m_genai:
        yield (m_rt, m_gw, m_genai)
        m_rt.assert_not_called()
        m_gw.assert_not_called()
        m_genai.assert_not_called()

@pytest.fixture
def forbidden_io_boundaries(forbidden_boundaries):
    with patch("apps.api.routers.health.httpx.AsyncClient", side_effect=AssertionError("httpx.AsyncClient was called!")) as m_http, \
         patch("apps.api.routers.health.redis_client.get", side_effect=AssertionError("redis get was called!")) as m_r_get, \
         patch("apps.api.routers.health.redis_client.set", side_effect=AssertionError("redis set was called!")) as m_r_set, \
         patch("apps.api.routers.health.v3_adapter.get_scenes", side_effect=AssertionError("dataset was called!")) as m_v3, \
         patch("apps.api.routers.health.Path.exists", side_effect=AssertionError("path exists was called!")) as m_path:
        yield
        m_http.assert_not_called()
        m_r_get.assert_not_called()
        m_r_set.assert_not_called()
        m_v3.assert_not_called()
        m_path.assert_not_called()

@pytest.mark.asyncio
async def test_live_probe_no_external_calls(forbidden_io_boundaries):
    """
    1. /live performs no datastore, network, or model call.
    5. /live test must install forbidden-boundary mocks before calling live_probe and assert none were called.
    """
    res = await live_probe()
    assert res["status"] == "ALIVE"
    assert res["version"] == "v7.0.0"

@pytest.fixture
def mock_db():
    db = AsyncMock()
    # 1. Patch the real Alembic lookup location
    with patch("src.reframe.shared.database.get_expected_alembic_head", return_value="test_head"):
        db.execute = AsyncMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = ("test_head",)
        db.execute.return_value = mock_result
        yield db

@pytest.fixture
def mock_redis():
    with patch("apps.api.routers.health.redis_client") as rc:
        rc.set = AsyncMock()
        rc.get = AsyncMock(return_value="ok")
        rc.is_real_redis = True
        yield rc

@pytest.fixture
def mock_httpx():
    with patch("apps.api.routers.health.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.get = AsyncMock()
        client.get.return_value.status_code = 200
        client.get.return_value.text = "Ok."

        client_cls.return_value.__aenter__.return_value = client
        yield client

@pytest.fixture
def mock_v3_adapter():
    with patch("apps.api.routers.health.v3_adapter") as v3:
        v3.get_scenes.return_value = [1] * 43
        v3.get_events.return_value = [1]
        v3.get_facts.return_value = [1]
        v3.get_evidence_frames.return_value = [1]
        v3.get_reveals.return_value = [1] * 2
        yield v3

@pytest.fixture
def mock_path():
    with patch("apps.api.routers.health.Path") as path_cls:
        path_inst = MagicMock()
        path_inst.exists.return_value = True
        path_cls.return_value = path_inst
        yield path_inst

@pytest.fixture
def base_mocks(mock_db, mock_redis, mock_httpx, mock_v3_adapter, mock_path):
    pass

@pytest.mark.asyncio
async def test_ready_happy_path(base_mocks, mock_db, mock_redis):
    """
    2. Add a fully green happy-path test proving:
       - all required dependencies true
       - migration_head true
       - agent_runtime_configured true
       - overall_ready true
    """
    mock_redis.get.side_effect = lambda k: "worker123" if k == "worker:heartbeat" else "ok"

    with patch("apps.api.routers.health.settings.EXECUTION_MODE", "OFFLINE_FIXTURE"):
        res = await ready_probe(db=mock_db)
        data = res["data"]

        assert data["postgres"] is True
        assert data["clickhouse"] is True
        assert data["redis"] is True
        assert data["dataset_ready"] is True
        assert data["runtime_db_readonly"] is True
        assert data["media_available"] is True
        assert data["worker_heartbeat"] is True

        assert data["migration_head"] is True
        assert data["agent_runtime_configured"] is True
        assert data["overall_ready"] is True

@pytest.mark.asyncio
async def test_ready_contains_nine_frozen_fields_and_booleans(base_mocks, mock_db):
    """
    /ready contains all nine frozen fields.
    Required fields are booleans.
    """
    res = await ready_probe(db=mock_db)
    data = res["data"]

    required_fields = [
        "postgres", "clickhouse", "redis", "worker_heartbeat",
        "dataset_ready", "runtime_db_readonly",
        "agent_runtime_configured", "media_available", "overall_ready"
    ]

    for f in required_fields:
        assert f in data, f"Missing required field: {f}"
        assert isinstance(data[f], bool), f"Field {f} is not a boolean"

@pytest.mark.asyncio
async def test_worker_heartbeat_missing(base_mocks, mock_db, mock_redis):
    """Missing/expired heartbeat produces worker_heartbeat == false."""
    mock_redis.get.side_effect = lambda k: None if k == "worker:heartbeat" else "ok"
    res = await ready_probe(db=mock_db)
    assert res["data"]["worker_heartbeat"] is False
    assert res["data"]["overall_ready"] is False

@pytest.mark.asyncio
async def test_production_redis_fallback_fails(base_mocks, mock_db, mock_redis):
    """Production Redis fallback cannot pass Redis readiness."""
    mock_redis.is_real_redis = False
    with patch("apps.api.routers.health.settings.ENVIRONMENT", "production"):
        res = await ready_probe(db=mock_db)
    assert res["data"]["redis"] is False
    assert res["data"]["overall_ready"] is False

@pytest.mark.asyncio
async def test_agent_runtime_oidc_client_id_has_no_effect(base_mocks, mock_db, forbidden_boundaries):
    """3. OIDC client ID alone never makes runtime configured; changing GOOGLE_CLIENT_ID does not change the result."""
    with patch("apps.api.routers.health.settings.EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("apps.api.routers.health.settings.LIVE_AGENT_ENABLED", True), \
         patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", True), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", False), \
         patch("apps.api.routers.health.settings.GOOGLE_CLOUD_PROJECT", ""), \
         patch("apps.api.routers.health.settings.GOOGLE_CLOUD_LOCATION", ""), \
         patch("apps.api.routers.health.settings.GEMINI_MODEL_ID", ""):

        # Test with one GOOGLE_CLIENT_ID
        with patch("apps.api.routers.health.settings.GOOGLE_CLIENT_ID", "fake_client_id"):
            res1 = await ready_probe(db=mock_db)
            assert res1["data"]["agent_runtime_configured"] is False

        # Test with another GOOGLE_CLIENT_ID
        with patch("apps.api.routers.health.settings.GOOGLE_CLIENT_ID", "another_fake_client_id"):
            res2 = await ready_probe(db=mock_db)
            assert res2["data"]["agent_runtime_configured"] is False

@pytest.mark.asyncio
async def test_agent_runtime_missing_live_config_fields(base_mocks, mock_db, forbidden_boundaries):
    """3. missing project, location, or model makes live configuration false."""
    with patch("apps.api.routers.health.settings.EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("apps.api.routers.health.settings.LIVE_AGENT_ENABLED", True), \
         patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", True), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", False):

        # Missing project
        with patch("apps.api.routers.health.settings.GOOGLE_CLOUD_PROJECT", ""), \
             patch("apps.api.routers.health.settings.GOOGLE_CLOUD_LOCATION", "us-central1"), \
             patch("apps.api.routers.health.settings.GEMINI_MODEL_ID", "gemini-1.5-pro"):
            res = await ready_probe(db=mock_db)
            assert res["data"]["agent_runtime_configured"] is False

        # Missing location
        with patch("apps.api.routers.health.settings.GOOGLE_CLOUD_PROJECT", "test-project"), \
             patch("apps.api.routers.health.settings.GOOGLE_CLOUD_LOCATION", ""), \
             patch("apps.api.routers.health.settings.GEMINI_MODEL_ID", "gemini-1.5-pro"):
            res = await ready_probe(db=mock_db)
            assert res["data"]["agent_runtime_configured"] is False

        # Missing model
        with patch("apps.api.routers.health.settings.GOOGLE_CLOUD_PROJECT", "test-project"), \
             patch("apps.api.routers.health.settings.GOOGLE_CLOUD_LOCATION", "us-central1"), \
             patch("apps.api.routers.health.settings.GEMINI_MODEL_ID", ""):
            res = await ready_probe(db=mock_db)
            assert res["data"]["agent_runtime_configured"] is False

@pytest.mark.asyncio
async def test_agent_runtime_valid_live_config(base_mocks, mock_db, forbidden_boundaries):
    """3. all live flags and project/location/model present makes configuration true.
       Note: No assertion claims ADC credentials were verified.
    """
    with patch("apps.api.routers.health.settings.EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("apps.api.routers.health.settings.LIVE_AGENT_ENABLED", True), \
         patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", True), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", False), \
         patch("apps.api.routers.health.settings.GOOGLE_CLOUD_PROJECT", "test-project"), \
         patch("apps.api.routers.health.settings.GOOGLE_CLOUD_LOCATION", "us-central1"), \
         patch("apps.api.routers.health.settings.GEMINI_MODEL_ID", "gemini-1.5-pro"):

        res = await ready_probe(db=mock_db)
        # This proves the configuration is present, not that ADC is actually verified.
        assert res["data"]["agent_runtime_configured"] is True

@pytest.mark.asyncio
async def test_ready_performs_no_model_calls(base_mocks, mock_db, forbidden_boundaries):
    """4. /ready performs zero Gemini/model calls."""
    res = await ready_probe(db=mock_db)
    # The fixture will assert non-use upon teardown

@pytest.fixture
def admin_viewer():
    return ViewerContext(
        user_id=uuid.uuid4(),
        roles=["ADMIN"]
    )

@pytest.mark.asyncio
async def test_admin_health_default_zero_cost_state(base_mocks, mock_db, admin_viewer, forbidden_boundaries):
    """default zero-cost state -> DISABLED"""
    with patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", False), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", True):
        res = await admin_health(viewer=admin_viewer, db=mock_db)
        assert res["data"]["gemini_status"] == GeminiHealthStatus.DISABLED.value

@pytest.mark.asyncio
async def test_admin_health_oidc_client_id_alone(base_mocks, mock_db, admin_viewer, forbidden_boundaries):
    """OIDC client ID alone -> NOT_TESTED, never CONFIGURED_NOT_VERIFIED"""
    with patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", True), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", False), \
         patch("apps.api.routers.health.settings.GOOGLE_CLIENT_ID", "fake-oidc"), \
         patch("apps.api.routers.health.settings.GEMINI_API_KEY", ""):
        res = await admin_health(viewer=admin_viewer, db=mock_db)
        assert res["data"]["gemini_status"] == GeminiHealthStatus.NOT_TESTED.value

@pytest.mark.asyncio
async def test_admin_health_gemini_api_key_alone(base_mocks, mock_db, admin_viewer, forbidden_boundaries):
    """GEMINI_API_KEY alone -> NOT_TESTED"""
    with patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", True), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", False), \
         patch("apps.api.routers.health.settings.GEMINI_API_KEY", "fake-key"), \
         patch("apps.api.routers.health.settings.GOOGLE_CLIENT_ID", ""):
        res = await admin_health(viewer=admin_viewer, db=mock_db)
        assert res["data"]["gemini_status"] == GeminiHealthStatus.NOT_TESTED.value

@pytest.mark.asyncio
async def test_admin_health_complete_live_flags(base_mocks, mock_db, admin_viewer, forbidden_boundaries):
    """complete live flags plus project/location/model -> CONFIGURED_NOT_VERIFIED"""
    with patch("apps.api.routers.health.settings.EXECUTION_MODE", "LIVE_GOOGLE"), \
         patch("apps.api.routers.health.settings.LIVE_AGENT_ENABLED", True), \
         patch("apps.api.routers.health.settings.PAID_CALLS_ENABLED", True), \
         patch("apps.api.routers.health.settings.SPEND_KILL_SWITCH_ACTIVE", False), \
         patch("apps.api.routers.health.settings.GOOGLE_CLOUD_PROJECT", "test-project"), \
         patch("apps.api.routers.health.settings.GOOGLE_CLOUD_LOCATION", "us-central1"), \
         patch("apps.api.routers.health.settings.GEMINI_MODEL_ID", "gemini-1.5-pro"):
        res = await admin_health(viewer=admin_viewer, db=mock_db)
        assert res["data"]["gemini_status"] == GeminiHealthStatus.CONFIGURED_NOT_VERIFIED.value
