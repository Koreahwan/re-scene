"""
Phase 1 Exit Gate Integration Test: Concurrently Live Two API Instances State Visibility (V7-P1-GATE-002-B)

Proves bidirectional durable state visibility between two concurrently live,
independent OS Python processes using the same SQLite database via production FastAPI routes:
- Process A creates an AnalysisRun via POST /api/v1/reframe-runs; Process B observes it via GET.
- Process B updates WatchProgress via PUT /api/v1/me/watch-progress/{work_id}; Process A observes it via GET.
- Both processes are concurrently alive during both operations.
- Zero shared in-memory state, zero cookie/token sharing between child processes.
- Zero real Gemini/Vertex/Google provider calls ($0.00 spend), zero real external Redis connections.

Scope & Limitations:
- Proves serialized API operations across two live independent Python processes sharing durable SQLite storage.
- Does NOT claim multi-host TCP load balancing, distributed Redis locking, or concurrent write race stress testing.
"""
import os
import sys
import time
import json
import uuid
import pathlib
import argparse
import subprocess
import threading
import pytest


def _wait_for_file(filepath: pathlib.Path, timeout_sec: float = 30.0) -> dict:
    """Polls until a JSON file exists and contains valid JSON data."""
    start = time.time()
    while time.time() - start < timeout_sec:
        if filepath.exists():
            try:
                content = filepath.read_text(encoding="utf-8").strip()
                if content:
                    return json.loads(content)
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.05)
    raise TimeoutError(f"Timed out waiting for file {filepath} after {timeout_sec}s")


def test_two_live_api_processes_observe_bidirectional_durable_state(tmp_path: pathlib.Path):
    """
    Parent test: launches Process A and Process B as concurrently running subprocesses,
    verifies mutual state visibility in both directions (A->B, B->A) while both
    subprocesses remain concurrently alive, and performs final independent DB reconciliation.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    this_file = pathlib.Path(__file__).resolve()

    db_path = tmp_path / "phase1-two-api-instances.sqlite"
    coord_dir = tmp_path / "coord"
    coord_dir.mkdir(parents=True, exist_ok=True)

    file_a_ready = coord_dir / "a_ready.json"
    file_b_ready = coord_dir / "b_ready.json"
    file_b_done = coord_dir / "b_done.json"
    file_a_done = coord_dir / "a_done.json"
    signal_go = coord_dir / "go.sig"
    signal_shutdown = coord_dir / "shutdown.sig"

    assert not db_path.exists(), f"Temp database must not exist prior to test: {db_path}"
    assert repo_root not in db_path.resolve().parents and db_path.resolve() != repo_root, (
        f"Database must be outside repository root: {db_path}"
    )

    proc_a = None
    proc_b = None

    try:
        # 1. Start Process A
        cmd_a = [
            sys.executable,
            str(this_file),
            "--child-role=A",
            f"--db-path={str(db_path)}",
            f"--coord-dir={str(coord_dir)}"
        ]
        proc_a = subprocess.Popen(
            cmd_a,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(repo_root)
        )

        # Wait for Process A to create Run and declare READY
        receipt_a_ready = _wait_for_file(file_a_ready, timeout_sec=30.0)
        assert proc_a.poll() is None, "Process A terminated unexpectedly before Process B started"
        a_run_id = receipt_a_ready["run_id"]

        # 2. Start Process B with A's run_id only (no expected response payloads passed)
        cmd_b = [
            sys.executable,
            str(this_file),
            "--child-role=B",
            f"--db-path={str(db_path)}",
            f"--coord-dir={str(coord_dir)}",
            f"--run-id={a_run_id}"
        ]
        proc_b = subprocess.Popen(
            cmd_b,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(repo_root)
        )

        # Wait for Process B to complete dev-login and declare READY
        receipt_b_ready = _wait_for_file(file_b_ready, timeout_sec=30.0)

        # 3. Verify Concurrent Liveness & Process Independence BEFORE GO signal
        assert proc_a.poll() is None, "Process A must be concurrently running"
        assert proc_b.poll() is None, "Process B must be concurrently running"

        pid_a = receipt_a_ready["pid"]
        pid_b = receipt_b_ready["pid"]
        parent_pid = os.getpid()

        assert pid_a != pid_b, f"PIDs must differ: A={pid_a}, B={pid_b}"
        assert pid_a != parent_pid, f"PID A cannot match parent PID: {pid_a}"
        assert pid_b != parent_pid, f"PID B cannot match parent PID: {pid_b}"

        assert receipt_a_ready["process_nonce"] != receipt_b_ready["process_nonce"]
        assert receipt_a_ready["fresh_import"] is True
        assert receipt_b_ready["fresh_import"] is True
        assert receipt_a_ready["resolved_db_path"] == receipt_b_ready["resolved_db_path"]
        assert receipt_a_ready["database_url"] == receipt_b_ready["database_url"]
        assert receipt_a_ready["user_id"] == receipt_b_ready["user_id"]

        # 4. Issue GO signal to start bidirectional cross-observation
        signal_go.write_text("GO", encoding="utf-8")

        # 5. Wait for Process B to read A's run, write WatchProgress, and declare B_DONE
        receipt_b_done = _wait_for_file(file_b_done, timeout_sec=30.0)

        # Wait for Process A to observe B's WatchProgress and declare A_DONE
        receipt_a_done = _wait_for_file(file_a_done, timeout_sec=30.0)

        # 6. Verify BOTH Processes remained concurrently alive throughout both operations
        assert proc_a.poll() is None, "Process A must still be concurrently alive while observing B"
        assert proc_b.poll() is None, "Process B must still be concurrently alive while A observes B"

        # 7. A -> B State Visibility Verification
        a_run_observed_by_a = receipt_a_ready["run_data"]
        a_run_observed_by_b = receipt_b_done["run_data"]

        fields_to_compare_run = [
            "run_id", "run_type", "status", "work_id",
            "edition_id", "reveal_id", "proof_ids", "error_code"
        ]
        for field in fields_to_compare_run:
            assert a_run_observed_by_a[field] == a_run_observed_by_b[field], (
                f"Mismatch in run field '{field}': "
                f"A observed {a_run_observed_by_a[field]}, B observed {a_run_observed_by_b[field]}"
            )

        # 8. B -> A State Visibility Verification
        b_wp_written_by_b = receipt_b_done["put_data"]
        b_wp_observed_by_a = receipt_a_done["watch_progress_data"]

        fields_to_compare_wp = [
            "work_id", "edition_id", "state", "progress_ms", "completed_reveal_ids"
        ]
        for field in fields_to_compare_wp:
            assert b_wp_written_by_b[field] == b_wp_observed_by_a[field], (
                f"Mismatch in watch progress field '{field}': "
                f"B wrote {b_wp_written_by_b[field]}, A observed {b_wp_observed_by_a[field]}"
            )

        # 9. Issue graceful shutdown signal to both processes
        signal_shutdown.write_text("SHUTDOWN", encoding="utf-8")

        # 10. Wait for clean shutdown of both processes
        stdout_a, stderr_a = proc_a.communicate(timeout=20)
        stdout_b, stderr_b = proc_b.communicate(timeout=20)

        assert proc_a.returncode == 0, (
            f"Process A failed on exit code {proc_a.returncode}.\nSTDOUT:\n{stdout_a}\nSTDERR:\n{stderr_a}"
        )
        assert proc_b.returncode == 0, (
            f"Process B failed on exit code {proc_b.returncode}.\nSTDOUT:\n{stdout_b}\nSTDERR:\n{stderr_b}"
        )

        file_a_final = coord_dir / "a_final.json"
        file_b_final = coord_dir / "b_final.json"
        receipt_a_final = json.loads(file_a_final.read_text(encoding="utf-8"))
        receipt_b_final = json.loads(file_b_final.read_text(encoding="utf-8"))

        assert receipt_a_final["provider_constructor_attempts"] == 0
        assert receipt_b_final["provider_constructor_attempts"] == 0
        assert receipt_a_final["redis_connect_await_count"] == 1
        assert receipt_a_final["redis_close_await_count"] == 1
        assert receipt_b_final["redis_connect_await_count"] == 1
        assert receipt_b_final["redis_close_await_count"] == 1

    finally:
        # Safeguard: ensure subprocesses are terminated if test fails early
        for p in (proc_a, proc_b):
            if p is not None and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=2)
                except Exception:
                    p.kill()

    # 11. Final Independent Database Reconciliation
    db_posix = db_path.resolve().as_posix()
    from sqlalchemy import create_engine, select, func
    from sqlalchemy.orm import sessionmaker
    from src.reframe.identity.models import User, Profile, SpoilerPreferences, WatchProgress
    from src.reframe.jobs.models import AnalysisRun
    from src.reframe.cost.models import UsageLedger

    temp_sync_engine = create_engine(f"sqlite:///{db_posix}")
    TempSessionLocal = sessionmaker(bind=temp_sync_engine)

    try:
        with TempSessionLocal() as session:
            user_count = session.execute(select(func.count()).select_from(User)).scalar()
            assert user_count == 1, f"Expected 1 User, found {user_count}"

            profile_count = session.execute(select(func.count()).select_from(Profile)).scalar()
            assert profile_count == 1, f"Expected 1 Profile, found {profile_count}"

            spoiler_count = session.execute(select(func.count()).select_from(SpoilerPreferences)).scalar()
            assert spoiler_count == 1, f"Expected 1 SpoilerPreferences, found {spoiler_count}"

            run_count = session.execute(select(func.count()).select_from(AnalysisRun)).scalar()
            assert run_count == 1, f"Expected 1 AnalysisRun, found {run_count}"

            wp_count = session.execute(select(func.count()).select_from(WatchProgress)).scalar()
            assert wp_count == 1, f"Expected 1 WatchProgress, found {wp_count}"

            usage_count = session.execute(select(func.count()).select_from(UsageLedger)).scalar()
            assert usage_count == 0, f"UsageLedger must be 0, found {usage_count}"

            run = session.execute(
                select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(a_run_id))
            ).scalar_one()
            assert str(run.owner_user_id) == receipt_a_ready["user_id"]
            assert run.input_hash is not None and len(run.input_hash) > 0

            wp = session.execute(
                select(WatchProgress).where(
                    WatchProgress.user_id == uuid.UUID(receipt_a_ready["user_id"])
                )
            ).scalar_one()
            assert wp.work_id == "the-bat-whispers-1930"
            assert wp.edition_id == "tbw-fullscreen-archive"
            assert wp.state == "WATCHING"
            assert wp.progress_ms == 12345
            assert wp.completed_reveal_ids == []
    finally:
        temp_sync_engine.dispose()


# ===========================================================================
# Child Process Implementation (Executed via CLI subprocess)
# ===========================================================================

def _run_child(role: str, db_path: pathlib.Path, coord_dir: pathlib.Path, run_id_arg: str = None):
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    src_dir = repo_root / "src"

    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    # Configure child environment before importing production modules
    db_posix = db_path.resolve().as_posix()
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_posix}"
    os.environ["SYNC_DATABASE_URL"] = f"sqlite:///{db_posix}"
    os.environ["ENVIRONMENT"] = "test"
    os.environ["AUTH_DEV_MODE"] = "true"
    os.environ["SCHEMA_INIT_MODE"] = "CREATE_ALL"
    os.environ["EMBEDDED_WORKER_ENABLED"] = "false"

    os.environ["EXECUTION_MODE"] = "OFFLINE_FIXTURE"
    os.environ["PAID_CALLS_ENABLED"] = "false"
    os.environ["SPEND_KILL_SWITCH_ACTIVE"] = "true"
    os.environ["LIVE_AGENT_ENABLED"] = "false"
    os.environ["LIVE_EVAL_ENABLED"] = "false"
    os.environ["LEGACY_PAID_PATH_ENABLED"] = "false"

    os.environ["PUBLIC_REFRAME_MODEL_CALLS"] = "0"
    os.environ["PUBLIC_PROOF_LOOKUP_MODEL_CALLS"] = "0"
    os.environ["PUBLIC_COMMUNITY_MODEL_CALLS"] = "0"
    os.environ["PUBLIC_AGENT_MODEL_CALLS"] = "0"
    os.environ["PUBLIC_EVAL_MODEL_CALLS"] = "0"

    os.environ["GEMINI_API_KEY"] = ""
    os.environ["GOOGLE_API_KEY"] = ""
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = ""
    os.environ["GOOGLE_CLIENT_ID"] = ""
    os.environ["GOOGLE_CLIENT_SECRET"] = ""
    os.environ["ADMIN_COST_UNLOCK"] = ""

    os.environ["REDIS_URL"] = "redis://127.0.0.1:1/15"
    os.environ["SECRET_KEY"] = "phase1-restart-test-secret-key-at-least-32-chars"
    os.environ["CSRF_SECRET"] = "phase1-restart-test-csrf-secret-at-least-32-chars"
    os.environ["SESSION_COOKIE_SECURE"] = "false"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    os.environ.pop("TEST_POSTGRES_URL", None)

    # Install child fail-closed provider constructor guard
    import google.genai
    import google.genai.client

    provider_constructor_attempts = 0
    provider_lock = threading.Lock()

    def fail_closed_client_factory(*args, **kwargs):
        nonlocal provider_constructor_attempts
        with provider_lock:
            provider_constructor_attempts += 1
        raise AssertionError(
            "REAL_PROVIDER_MODEL_CALL_FORBIDDEN_IN_ORDINARY_TESTS: "
            "Provider client construction is forbidden in Gate B child processes."
        )

    fail_closed_client_factory.__is_tripwire_sentinel__ = True
    google.genai.Client = fail_closed_client_factory
    google.genai.client.Client = fail_closed_client_factory

    # Verify fresh module graph before import
    assert "apps.api.main" not in sys.modules, "apps.api.main already in sys.modules before child import"
    fresh_import = True

    # Now import production modules
    import apps.api.main
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock
    from src.reframe.shared.config import settings

    # Mock Redis methods to verify lifespan without contacting external Redis
    redis_connect_mock = AsyncMock()
    redis_close_mock = AsyncMock()
    apps.api.main.redis_client.connect = redis_connect_mock
    apps.api.main.redis_client.close = redis_close_mock

    # Assert in-memory stores are pristine empty
    assert apps.api.main.RUNS_STORE == {}, "RUNS_STORE not empty on fresh import"
    assert apps.api.main.TRACES_STORE == {}, "TRACES_STORE not empty on fresh import"
    assert apps.api.main.ANALYSIS_CACHE == {}, "ANALYSIS_CACHE not empty on fresh import"

    user_email = "phase1.restart@reframe.test"
    user_display = "Phase1 Restart User"

    file_a_ready = coord_dir / "a_ready.json"
    file_b_ready = coord_dir / "b_ready.json"
    file_b_done = coord_dir / "b_done.json"
    file_a_done = coord_dir / "a_done.json"
    signal_go = coord_dir / "go.sig"
    signal_shutdown = coord_dir / "shutdown.sig"

    file_a_final = coord_dir / "a_final.json"
    file_b_final = coord_dir / "b_final.json"

    def _wait_sig(sig_file: pathlib.Path, timeout_sec: float = 35.0):
        start = time.time()
        while time.time() - start < timeout_sec:
            if sig_file.exists():
                return
            time.sleep(0.05)
        raise TimeoutError(f"Child timed out waiting for {sig_file}")

    if role == "A":
        with TestClient(apps.api.main.app) as client:
            # Dev-login
            resp_login = client.post(
                "/api/v1/auth/dev-login",
                json={"email": user_email, "display_name": user_display}
            )
            assert resp_login.status_code == 200, f"A dev-login failed: {resp_login.text}"
            login_data = resp_login.json()["data"]
            user_id = login_data["user_id"]
            csrf_token_a = login_data["csrf_token"]
            assert settings.SESSION_COOKIE_NAME in client.cookies

            # Create AnalysisRun
            resp_run = client.post(
                "/api/v1/reframe-runs",
                headers={
                    "Idempotency-Key": f"phase1-two-api-run-{uuid.uuid4().hex[:8]}",
                    "X-CSRF-Token": csrf_token_a
                },
                json={
                    "movie_id": "the-bat-whispers-1930",
                    "edition_id": "tbw-fullscreen-archive",
                    "reveal_id": "reveal-anderson-identity",
                    "mode": "STRICT_CANON",
                    "top_k": 5
                }
            )
            assert resp_run.status_code == 202, f"A create run failed: {resp_run.text}"
            run_id = resp_run.json()["data"]["run_id"]

            # Inspect run from A's own API
            resp_get_run = client.get(f"/api/v1/reframe-runs/{run_id}")
            assert resp_get_run.status_code == 200, f"A get run failed: {resp_get_run.text}"
            run_data_a = resp_get_run.json()["data"]

            # Record A ready receipt
            receipt_a_ready = {
                "role": "A",
                "pid": os.getpid(),
                "process_nonce": str(uuid.uuid4()),
                "fresh_import": fresh_import,
                "resolved_db_path": str(db_path.resolve()),
                "database_url": os.environ["DATABASE_URL"],
                "user_id": user_id,
                "run_id": run_id,
                "run_data": run_data_a,
                "provider_constructor_attempts": provider_constructor_attempts
            }
            file_a_ready.write_text(json.dumps(receipt_a_ready), encoding="utf-8")

            # Wait for Process B to finish its updates (b_done.json)
            _wait_sig(file_b_done, timeout_sec=35.0)

            # Observe B's updates via A's own API
            resp_wp = client.get("/api/v1/me/watch-progress")
            assert resp_wp.status_code == 200, f"A get watch-progress failed: {resp_wp.text}"
            items = resp_wp.json()["data"]
            target_wp = next(
                (item for item in items if item["work_id"] == "the-bat-whispers-1930" and item["edition_id"] == "tbw-fullscreen-archive"),
                None
            )
            assert target_wp is not None, f"A could not find watch progress updated by B: {items}"

            receipt_a_done = {
                "watch_progress_data": target_wp
            }
            file_a_done.write_text(json.dumps(receipt_a_done), encoding="utf-8")

            # Wait for shutdown signal while lifespan remains open
            _wait_sig(signal_shutdown, timeout_sec=35.0)

        # After TestClient context closes:
        assert redis_connect_mock.await_count == 1
        assert redis_close_mock.await_count == 1
        assert provider_constructor_attempts == 0

        final_receipt_a = {
            "role": "A",
            "provider_constructor_attempts": provider_constructor_attempts,
            "redis_connect_await_count": redis_connect_mock.await_count,
            "redis_close_await_count": redis_close_mock.await_count
        }
        file_a_final.write_text(json.dumps(final_receipt_a), encoding="utf-8")

    elif role == "B":
        assert run_id_arg is not None, "run_id_arg required for role B"

        with TestClient(apps.api.main.app) as client:
            # Dev-login with same email, independent cookies
            resp_login = client.post(
                "/api/v1/auth/dev-login",
                json={"email": user_email, "display_name": user_display}
            )
            assert resp_login.status_code == 200, f"B dev-login failed: {resp_login.text}"
            login_data = resp_login.json()["data"]
            user_id = login_data["user_id"]
            csrf_token_b = login_data["csrf_token"]
            assert settings.SESSION_COOKIE_NAME in client.cookies

            receipt_b_ready = {
                "role": "B",
                "pid": os.getpid(),
                "process_nonce": str(uuid.uuid4()),
                "fresh_import": fresh_import,
                "resolved_db_path": str(db_path.resolve()),
                "database_url": os.environ["DATABASE_URL"],
                "user_id": user_id,
                "provider_constructor_attempts": provider_constructor_attempts
            }
            file_b_ready.write_text(json.dumps(receipt_b_ready), encoding="utf-8")

            # Wait for Parent's GO signal while lifespan is open
            _wait_sig(signal_go, timeout_sec=35.0)

            # 1. A -> B: Retrieve Run created by A
            resp_get_run = client.get(f"/api/v1/reframe-runs/{run_id_arg}")
            assert resp_get_run.status_code == 200, f"B get run failed: {resp_get_run.text}"
            run_data_b = resp_get_run.json()["data"]

            # 2. B -> A: Update watch progress via B
            resp_put_wp = client.put(
                "/api/v1/me/watch-progress/the-bat-whispers-1930",
                headers={"X-CSRF-Token": csrf_token_b},
                json={
                    "edition_id": "tbw-fullscreen-archive",
                    "state": "WATCHING",
                    "progress_ms": 12345,
                    "completed_reveal_ids": []
                }
            )
            assert resp_put_wp.status_code == 200, f"B update watch-progress failed: {resp_put_wp.text}"
            put_data_b = resp_put_wp.json()["data"]

            receipt_b_done = {
                "run_data": run_data_b,
                "put_data": put_data_b
            }
            file_b_done.write_text(json.dumps(receipt_b_done), encoding="utf-8")

            # Wait for shutdown signal while lifespan remains open
            _wait_sig(signal_shutdown, timeout_sec=35.0)

        # After TestClient context closes:
        assert redis_connect_mock.await_count == 1
        assert redis_close_mock.await_count == 1
        assert provider_constructor_attempts == 0

        final_receipt_b = {
            "role": "B",
            "provider_constructor_attempts": provider_constructor_attempts,
            "redis_connect_await_count": redis_connect_mock.await_count,
            "redis_close_await_count": redis_close_mock.await_count
        }
        file_b_final.write_text(json.dumps(final_receipt_b), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1 Two API Instances Child Runner")
    parser.add_argument("--child-role", choices=["A", "B"], required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--coord-dir", required=True)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    _run_child(
        role=args.child_role,
        db_path=pathlib.Path(args.db_path),
        coord_dir=pathlib.Path(args.coord_dir),
        run_id_arg=args.run_id
    )
