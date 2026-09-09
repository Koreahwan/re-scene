"""
Unit Tests for Global Google Provider Call Tripwire Architecture (V7-P1-GATE-002-D-R2)

Scope & Truthfulness Declaration:
- Enforces fail-closed blocking of Google GenAI / Vertex production model calls across
  all ordinary pytest execution paths in this repository.
- Does NOT claim "all external network is 0"; ClickHouse localhost connections, SQLite,
  and local mocks remain outside Google model tripwire scope.
- Replaces google.genai.Client and google.genai.client.Client at conftest import time
  with a process-lifetime bootstrap sentinel factory before any production module import.
- No original Client constructor is saved, exposed, or restored anywhere in ordinary pytest.
- Protects thread attempts, session fixtures, pre-fixture collection, and post-finalizer lifecycle.

Verifies:
A. google.genai.Client is replaced by a bound sentinel factory, not original constructor
B. Sync generate_content is immediately blocked with AssertionError
C. Async generate_content is immediately blocked with AssertionError
D. Swallowed exceptions still record attempts in TripwireState
E. assert_clean fails when attempts are recorded
F. assert_clean succeeds when no attempts are recorded
G. Test-scoped unittest.mock.patch functions safely and restores sentinel
H. EvidenceVerifier offline initialization and deterministic verification succeeds without provider calls
I. Offline ADK reasoning pipeline functions cleanly without hitting provider tripwires
Child Probes & Parent Subprocess Tests:
- Pre-fixture/import-time probe proving bootstrap sentinel is installed before any fixture or production import
- Post-session-finalizer probe proving bootstrap sentinel persists and blocks generation after session teardown
- Swallowed-call probe proving real fixture teardown fails when exception is caught
- Cross-thread probe proving attempts in spawned threads bind to the exact test nodeid
"""
import os
import sys
import pathlib
import threading
import subprocess
import pytest
import asyncio
from unittest.mock import patch, AsyncMock

import google.genai
import google.genai.client

from tests.conftest import (
    TripwireState,
    SentinelGenAiClient,
    create_sentinel_factory,
    _bootstrap_factory,
)
from src.reframe.verification.verifier import EvidenceVerifier
from reframe.domain.models import Reveal, ReframeCandidate, Event, Fact
from reframe.domain.enums import RelationType
from src.reframe.agents.runtime import agent_runtime


# ===========================================================================
# 1. Core Unit Invariant Tests (A through I)
# ===========================================================================

def test_a_client_is_replaced_by_sentinel_factory():
    """A. Verify google.genai.Client is replaced by sentinel factory, not original constructor."""
    assert getattr(google.genai.Client, "__is_tripwire_sentinel__", False) is True, (
        "google.genai.Client must have __is_tripwire_sentinel__ marker"
    )
    assert getattr(google.genai.client.Client, "__is_tripwire_sentinel__", False) is True, (
        "google.genai.client.Client must have __is_tripwire_sentinel__ marker"
    )

    # Client instantiation succeeds without calling original constructor
    client = google.genai.Client(vertexai=True, project="test-project", location="us-central1")
    assert isinstance(client, SentinelGenAiClient)
    assert hasattr(client, "models")
    assert hasattr(client, "aio")
    assert hasattr(client.models, "generate_content")
    assert hasattr(client.aio.models, "generate_content")

    # Direct SentinelGenAiClient instantiation without valid state must fail cleanly
    with pytest.raises(RuntimeError, match="untracked fallback is forbidden"):
        SentinelGenAiClient(None)


def test_b_sync_generate_content_immediately_blocked():
    """B. Verify sentinel client sync generate_content call is immediately blocked."""
    local_state = TripwireState(nodeid="test_b_sync_node")
    client = SentinelGenAiClient(local_state)

    with pytest.raises(AssertionError) as exc_info:
        client.models.generate_content(model="gemini-3.6-flash", contents="test sync prompt")

    err_msg = str(exc_info.value)
    assert "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS" in err_msg
    assert "models.generate_content" in err_msg
    assert len(local_state.attempts) == 1

    attempt = local_state.attempts[0]
    assert attempt["is_async"] is False
    assert attempt["mode"] == "sync"
    assert attempt["method_name"] == "models.generate_content"
    assert attempt["test_nodeid"] == "test_b_sync_node"
    assert attempt["call_count"] == 1

    # Also test sync generate_content_stream
    with pytest.raises(AssertionError, match="REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS"):
        list(client.models.generate_content_stream(model="gemini-3.6-flash", contents="test stream"))

    assert len(local_state.attempts) == 2


@pytest.mark.asyncio
async def test_c_async_generate_content_immediately_blocked():
    """C. Verify sentinel client async generate_content call is immediately blocked."""
    local_state = TripwireState(nodeid="test_c_async_node")
    client = SentinelGenAiClient(local_state)

    with pytest.raises(AssertionError) as exc_info:
        await client.aio.models.generate_content(model="gemini-3.6-flash", contents="test async prompt")

    err_msg = str(exc_info.value)
    assert "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS" in err_msg
    assert "aio.models.generate_content" in err_msg
    assert len(local_state.attempts) == 1

    attempt = local_state.attempts[0]
    assert attempt["is_async"] is True
    assert attempt["mode"] == "async"
    assert attempt["method_name"] == "aio.models.generate_content"
    assert attempt["test_nodeid"] == "test_c_async_node"
    assert attempt["call_count"] == 1

    # Also test async generate_content_stream
    with pytest.raises(AssertionError, match="REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS"):
        async for _ in client.aio.models.generate_content_stream(model="gemini-3.6-flash", contents="test stream"):
            pass

    assert len(local_state.attempts) == 2


@pytest.mark.asyncio
async def test_d_swallowed_exception_still_records_attempt():
    """D. Verify that even if caller catches/swallows the exception, attempt is recorded in state."""
    local_state = TripwireState(nodeid="test_d_swallowed_node")
    client = SentinelGenAiClient(local_state)

    # Sync attempt swallowed
    try:
        client.models.generate_content(contents="swallowed-sync")
    except Exception:
        pass

    assert len(local_state.attempts) == 1
    assert local_state.attempts[0]["call_count"] == 1

    # Async attempt swallowed
    try:
        await client.aio.models.generate_content(contents="swallowed-async")
    except Exception:
        pass

    assert len(local_state.attempts) == 2
    assert local_state.attempts[1]["call_count"] == 2


def test_e_assert_clean_fails_when_attempts_recorded():
    """E. Verify assert_clean fails when attempts have been recorded."""
    local_state = TripwireState(nodeid="test_e_dirty_node")
    client = SentinelGenAiClient(local_state)

    try:
        client.models.generate_content(contents="attempt")
    except Exception:
        pass

    assert len(local_state.attempts) == 1

    with pytest.raises(AssertionError) as exc_info:
        local_state.assert_clean()

    assert "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS" in str(exc_info.value)
    assert "Teardown tripwire detected 1 unhandled provider model call attempt(s)" in str(exc_info.value)


def test_f_assert_clean_passes_when_no_attempts():
    """F. Verify assert_clean succeeds cleanly when no generation attempts occurred."""
    clean_state = TripwireState(nodeid="test_f_clean_node")
    clean_client = SentinelGenAiClient(clean_state)

    # Creating client does not record an attempt
    assert len(clean_state.attempts) == 0
    # assert_clean must not raise
    clean_state.assert_clean()


def test_g_scoped_unittest_mock_patch_works_and_restores_sentinel():
    """G. Verify test-scoped mock patch of google.genai.Client works and restores sentinel on exit."""
    assert getattr(google.genai.Client, "__is_tripwire_sentinel__", False) is True

    # Test patch on google.genai.Client
    with patch("google.genai.Client") as mock_client_cls:
        mock_instance = AsyncMock()
        mock_instance.aio.models.generate_content = AsyncMock()
        mock_client_cls.return_value = mock_instance

        client = google.genai.Client()
        assert client is mock_instance
        assert mock_client_cls.called

    # After exiting with patch block, sentinel factory is fully restored
    assert getattr(google.genai.Client, "__is_tripwire_sentinel__", False) is True
    restored_client = google.genai.Client()
    assert isinstance(restored_client, SentinelGenAiClient)

    # Test patch on google.genai.client.Client
    with patch("google.genai.client.Client") as mock_client_sub_cls:
        mock_sub_instance = AsyncMock()
        mock_client_sub_cls.return_value = mock_sub_instance

        sub_client = google.genai.client.Client()
        assert sub_client is mock_sub_instance
        assert mock_client_sub_cls.called

    assert getattr(google.genai.client.Client, "__is_tripwire_sentinel__", False) is True


def test_h_evidence_verifier_offline_execution_succeeds():
    """H. Verify EvidenceVerifier offline initialization and deterministic verification works cleanly."""
    verifier = EvidenceVerifier()
    # EvidenceVerifier.__init__ instantiates genai.Client(), which returns SentinelGenAiClient
    assert isinstance(verifier.client, SentinelGenAiClient)

    sample_reveal = Reveal(
        reveal_id="reveal-anderson-identity",
        movie_id="the-bat-whispers-1930",
        timestamp_ms=4860000,
        title="Detective Anderson is 'The Bat'",
        subject="Detective Anderson",
        predicate="is_identity_of",
        previous_belief="Detective Anderson is a dedicated police officer.",
        revealed_fact="Detective Anderson is himself 'The Bat'.",
        affected_entities=["Detective Anderson", "The Bat"],
    )
    sample_candidate = ReframeCandidate(
        reveal_id="reveal-anderson-identity",
        scene_id="scene-tbw-003",
        movie_id="the-bat-whispers-1930",
        start_ms=350000,
        summary="Anderson inspects the blueprints alone.",
    )

    verified = verifier.verify_candidate_deterministic(
        reveal=sample_reveal,
        candidate=sample_candidate,
        events=[],
        facts=[],
        pre_annotated_relation=RelationType.DIRECT_FORESHADOWING
    )
    assert verified is not None
    assert verified.relation_type == RelationType.DIRECT_FORESHADOWING


@pytest.mark.asyncio
async def test_i_offline_adk_pipeline_succeeds_normally():
    """I. Verify Offline ADK pipeline runs to completion without triggering provider tripwires."""
    result = await agent_runtime.execute_adk_analysis(
        work_id="the-bat-whispers-1930",
        edition_id="tbw-fullscreen-archive",
        reveal_id="reveal-anderson-identity",
        cutoff_ms=4860000,
        analysis_run_id="test-tripwire-offline-adk",
        provided_seeds=[]
    )
    assert result is not None
    assert result["status"] in ("COMPLETED", "ABSTAINED")
    assert result["runner_name"] == "OfflineAdkRunner"
    assert result["execution_mode"] in ("OFFLINE_FIXTURE", "offline_fixture")


# ===========================================================================
# 2. Subprocess Probes: Lifecycle, Pre-Fixture, Post-Finalizer & Cross-Thread
# ===========================================================================

def test_child_probe_swallowed_call():
    """Child probe: executed only via parent subprocess to prove teardown fails on swallowed call."""
    if os.environ.get("_REFRAME_TRIPWIRE_PROBE") != "swallowed_call":
        pytest.skip("Child probe intended for subprocess execution only.")
    client = google.genai.Client()
    try:
        client.models.generate_content(model="gemini-3.6-flash", contents="swallow me in child probe")
    except AssertionError:
        pass
    # Test body ends cleanly; global_provider_tripwire teardown assert_clean MUST fail the test!


def test_child_probe_cross_thread():
    """Child probe: executed only via parent subprocess to prove thread attempts bind to the test state."""
    if os.environ.get("_REFRAME_TRIPWIRE_PROBE") != "cross_thread":
        pytest.skip("Child probe intended for subprocess execution only.")

    def thread_worker():
        c = google.genai.Client()
        try:
            c.models.generate_content(model="gemini-3.6-flash", contents="cross-thread attempt in child probe")
        except AssertionError:
            pass

    t = threading.Thread(target=thread_worker)
    t.start()
    t.join()
    # Child test body ends cleanly; global_provider_tripwire teardown assert_clean MUST catch the thread attempt!


def test_parent_probe_swallowed_call_fails_in_teardown():
    """Parent test: executes test_child_probe_swallowed_call in a subprocess and verifies teardown failure."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["_REFRAME_TRIPWIRE_PROBE"] = "swallowed_call"
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_global_provider_call_tripwire.py::test_child_probe_swallowed_call",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
    )
    assert res.returncode != 0, (
        f"Expected non-zero exit code but got {res.returncode}.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )
    output = res.stdout + "\n" + res.stderr
    assert "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS" in output, (
        f"Output missing tripwire forbidden string:\n{output}"
    )
    assert "Teardown tripwire detected 1 unhandled provider model call attempt" in output, (
        f"Output missing teardown detection string:\n{output}"
    )


def test_parent_probe_cross_thread_detected_with_exact_nodeid():
    """Parent test: executes test_child_probe_cross_thread in subprocess and verifies thread attempt detection."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    env = os.environ.copy()
    env["_REFRAME_TRIPWIRE_PROBE"] = "cross_thread"
    res = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_global_provider_call_tripwire.py::test_child_probe_cross_thread",
            "-q",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
    )
    assert res.returncode != 0, (
        f"Expected non-zero exit code but got {res.returncode}.\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    )
    output = res.stdout + "\n" + res.stderr
    assert "untracked-sentinel" not in output, "Must not fall back to untracked-sentinel"
    assert "test_child_probe_cross_thread" in output, (
        f"Exact child nodeid must be reported in teardown failure:\n{output}"
    )
    assert "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS" in output, (
        f"Output missing tripwire forbidden string:\n{output}"
    )
    assert "Teardown tripwire detected 1 unhandled provider model call attempt" in output, (
        f"Output missing teardown detection string:\n{output}"
    )


def test_pre_fixture_import_time_bootstrap_probe():
    """Probe A (R2): verifies in an isolated subprocess that tests.conftest immediately installs
    bootstrap sentinel before any fixture runs and persists across production module imports."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "sys.path.insert(0, '.')\n"
        "import tests.conftest\n"
        "import google.genai\n"
        "import google.genai.client\n"
        "assert getattr(google.genai.Client, '__is_tripwire_sentinel__', False) is True, 'google.genai.Client not sentinel!'\n"
        "assert getattr(google.genai.client.Client, '__is_tripwire_sentinel__', False) is True, 'google.genai.client.Client not sentinel!'\n"
        "# Now import production modules\n"
        "import src.reframe.verification.verifier\n"
        "import src.reframe.cost.invoker\n"
        "import src.reframe.agents.runtime\n"
        "assert getattr(google.genai.Client, '__is_tripwire_sentinel__', False) is True\n"
        "assert getattr(google.genai.client.Client, '__is_tripwire_sentinel__', False) is True\n"
        "print('PRE_FIXTURE_BOOTSTRAP_VERIFIED')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert res.returncode == 0, f"Pre-fixture bootstrap probe failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "PRE_FIXTURE_BOOTSTRAP_VERIFIED" in res.stdout


def test_post_session_finalizer_persistence_probe():
    """Probe B (R2): verifies in an isolated subprocess that after global_session_provider_guard
    finalizer runs, bootstrap sentinel persists and blocks generation without restoring original SDK client."""
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    code = (
        "import sys\n"
        "sys.path.insert(0, 'src')\n"
        "sys.path.insert(0, '.')\n"
        "import tests.conftest\n"
        "import google.genai\n"
        "import google.genai.client\n"
        "# Execute session guard fixture generator to teardown completion\n"
        "guard_gen = tests.conftest.global_session_provider_guard.__wrapped__()\n"
        "session_state = next(guard_gen)\n"
        "try:\n"
        "    next(guard_gen)\n"
        "except StopIteration:\n"
        "    pass\n"
        "# Verify sentinel persists post-finalizer\n"
        "assert getattr(google.genai.Client, '__is_tripwire_sentinel__', False) is True, 'Sentinel lost post-finalizer!'\n"
        "assert getattr(google.genai.client.Client, '__is_tripwire_sentinel__', False) is True\n"
        "# Verify generation is blocked\n"
        "client = google.genai.Client()\n"
        "try:\n"
        "    client.models.generate_content(contents='post finalizer attempt')\n"
        "    raise RuntimeError('Expected generation call to be blocked!')\n"
        "except AssertionError as e:\n"
        "    assert 'REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS' in str(e)\n"
        "print('POST_FINALIZER_PERSISTENCE_VERIFIED')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(repo_root),
    )
    assert res.returncode == 0, f"Post-session-finalizer probe failed:\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
    assert "POST_FINALIZER_PERSISTENCE_VERIFIED" in res.stdout
