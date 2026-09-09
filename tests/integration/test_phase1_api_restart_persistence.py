"""
Phase 1 Exit Gate Integration Test: Process-Restart Persistence (V7-P1-GATE-002-A)

Proves that User and AnalysisRun created and committed via production FastAPI routes
in Process A persist in the shared SQLite database and are correctly retrieved
via production FastAPI routes in Process B after full process termination and restart.

Execution guarantees:
- Sequential independent subprocess execution (Process A -> Process B)
- Zero shared in-memory state or session cookies transferred across processes
- Process-lifetime fail-closed Google provider guard installed in both children
- Production app lifespan executed via TestClient context manager
- Real Redis calls mocked via AsyncMock on redis_client singleton methods
- Zero provider model calls, zero real external database calls
"""
import os
import sys
import json
import uuid
import pathlib
import argparse
import subprocess
import threading
import pytest


def _extract_receipt(output: str) -> dict:
    prefix = "PHASE1_RESTART_RECEIPT="
    receipts = []
    for line in output.splitlines():
        if line.startswith(prefix):
            receipts.append(json.loads(line[len(prefix):]))
    assert len(receipts) == 1, (
        f"Expected exactly 1 receipt with prefix '{prefix}', found {len(receipts)}.\n"
        f"Output:\n{output}"
    )
    return receipts[0]


def test_api_process_restart_preserves_user_and_analysis_run(tmp_path: pathlib.Path):
    """
    Parent test: coordinates sequential execution of Process A (create) and
    Process B (verify), asserting restart persistence, process isolation, and zero leakage.
    """
    repo_root = pathlib.Path(__file__).resolve().parent.parent.parent
    this_file = pathlib.Path(__file__).resolve()

    db_path = tmp_path / "phase1-api-restart.sqlite"
    assert not db_path.exists(), f"Temp database must not exist before test: {db_path}"
    assert repo_root not in db_path.resolve().parents and db_path.resolve() != repo_root, (
        f"Temp database must be outside repository root: {db_path}"
    )

    # 1. Execute Process A (Creation phase)
    cmd_a = [
        sys.executable,
        str(this_file),
        "--child-phase=create",
        f"--db-path={str(db_path)}"
    ]
    res_a = subprocess.run(
        cmd_a,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60
    )
    assert res_a.returncode == 0, (
        f"Process A (create) failed with exit code {res_a.returncode}.\n"
        f"STDOUT:\n{res_a.stdout}\n"
        f"STDERR:\n{res_a.stderr}"
    )
    receipt_a = _extract_receipt(res_a.stdout)

    # Verify temp DB was created and populated by Process A
    assert db_path.exists(), f"Database file missing after Process A: {db_path}"
    assert db_path.stat().st_size > 0, f"Database file is empty after Process A: {db_path}"

    # 2. Execute Process B (Verification phase)
    cmd_b = [
        sys.executable,
        str(this_file),
        "--child-phase=verify",
        f"--db-path={str(db_path)}",
        f"--expected-run-id={receipt_a['run_id']}"
    ]
    res_b = subprocess.run(
        cmd_b,
        capture_output=True,
        text=True,
        cwd=str(repo_root),
        timeout=60
    )
    assert res_b.returncode == 0, (
        f"Process B (verify) failed with exit code {res_b.returncode}.\n"
        f"STDOUT:\n{res_b.stdout}\n"
        f"STDERR:\n{res_b.stderr}"
    )
    receipt_b = _extract_receipt(res_b.stdout)

    # 3. Parent False-Green and Integrity Assertions
    assert receipt_a["phase"] == "create"
    assert receipt_b["phase"] == "verify"

    # Independence proofs
    assert receipt_a["process_nonce"] != receipt_b["process_nonce"]
    assert receipt_a["pid"] != receipt_b["pid"]
    assert receipt_a["pid"] != os.getpid()
    assert receipt_b["pid"] != os.getpid()
    assert receipt_a["fresh_import"] is True
    assert receipt_b["fresh_import"] is True

    # DB alignment proofs
    assert receipt_a["resolved_db_path"] == receipt_b["resolved_db_path"]
    assert receipt_a["database_url"] == receipt_b["database_url"]

    # Entity persistence proofs
    assert receipt_a["user_id"] == receipt_b["user_id"]
    assert receipt_a["email"] == receipt_b["email"]
    assert receipt_a["run_id"] == receipt_b["run_id"]
    assert receipt_a["run_status"] == receipt_b["run_status"]
    assert receipt_a["work_id"] == receipt_b["work_id"]
    assert receipt_a["edition_id"] == receipt_b["edition_id"]
    assert receipt_a["reveal_id"] == receipt_b["reveal_id"]
    assert receipt_a["input_hash"] == receipt_b["input_hash"]

    # Zero cost & zero provider calls
    assert receipt_a["usage_ledger_count"] == 0
    assert receipt_b["usage_ledger_count"] == 0
    assert receipt_a["provider_constructor_attempts"] == 0
    assert receipt_b["provider_constructor_attempts"] == 0

    # Lifespan execution proofs
    assert receipt_a["redis_connect_await_count"] == 1
    assert receipt_a["redis_close_await_count"] == 1
    assert receipt_b["redis_connect_await_count"] == 1
    assert receipt_b["redis_close_await_count"] == 1


# ===========================================================================
# Child Process Implementation (Executed via CLI subprocess)
# ===========================================================================

def _run_child(phase: str, db_path: pathlib.Path, expected_run_id: str = None):
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
            "Provider client construction is forbidden in Gate A child processes."
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
    from sqlalchemy import select, func
    from sqlalchemy.orm import sessionmaker
    from src.reframe.shared.database import sync_engine
    from src.reframe.shared.config import settings
    from src.reframe.identity.models import User, Profile, SpoilerPreferences
    from src.reframe.jobs.models import AnalysisRun
    from src.reframe.cost.models import UsageLedger

    # Mock Redis methods to verify lifespan without contacting external Redis
    redis_connect_mock = AsyncMock()
    redis_close_mock = AsyncMock()
    apps.api.main.redis_client.connect = redis_connect_mock
    apps.api.main.redis_client.close = redis_close_mock

    user_email = "phase1.restart@reframe.test"
    user_display = "Phase1 Restart User"

    if phase == "create":
        # Process A: Create User and AnalysisRun via production API routes
        with TestClient(apps.api.main.app) as client:
            # A-1. Dev Login
            resp_login = client.post(
                "/api/v1/auth/dev-login",
                json={"email": user_email, "display_name": user_display}
            )
            assert resp_login.status_code == 200, f"Dev login failed: {resp_login.text}"
            login_data = resp_login.json()["data"]
            user_id = login_data["user_id"]
            assert login_data["email"] == user_email
            csrf_token = login_data["csrf_token"]
            assert csrf_token is not None
            assert settings.SESSION_COOKIE_NAME in client.cookies

            # A-2. Verify /me
            resp_me = client.get("/api/v1/me")
            assert resp_me.status_code == 200, f"/me failed: {resp_me.text}"
            me_json = resp_me.json()
            assert me_json["meta"]["is_authenticated"] is True
            assert me_json["data"]["id"] == user_id
            assert me_json["data"]["email"] == user_email
            assert me_json["data"]["display_name"] == user_display
            assert me_json["data"]["role"] == "USER"

            # A-3. Submit AnalysisRun
            resp_run = client.post(
                "/api/v1/reframe-runs",
                headers={
                    "Idempotency-Key": "phase1-restart-run-001",
                    "X-CSRF-Token": csrf_token
                },
                json={
                    "movie_id": "the-bat-whispers-1930",
                    "edition_id": "tbw-fullscreen-archive",
                    "reveal_id": "reveal-anderson-identity",
                    "mode": "STRICT_CANON",
                    "top_k": 1
                }
            )
            assert resp_run.status_code == 202, f"Create run failed: {resp_run.text}"
            run_data = resp_run.json()["data"]
            run_id = run_data["run_id"]
            run_status = run_data["status"]
            assert resp_run.json()["meta"]["idempotency_key"] == "phase1-restart-run-001"

        # Verify lifespan executed Redis connect and close
        assert redis_connect_mock.await_count == 1, "Redis connect not called in lifespan"
        assert redis_close_mock.await_count == 1, "Redis close not called in lifespan"

        # A-4. Independent DB readback via new sync session
        SyncSessionLocal = sessionmaker(bind=sync_engine)
        with SyncSessionLocal() as session:
            user = session.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            ).scalar_one_or_none()
            assert user is not None
            assert user.email_normalized == user_email
            assert user.status == "ACTIVE"
            assert user.role == "USER"

            user_count = session.execute(
                select(func.count()).select_from(User).where(User.email_normalized == user_email)
            ).scalar()
            assert user_count == 1

            profile_count = session.execute(
                select(func.count()).select_from(Profile).where(Profile.user_id == uuid.UUID(user_id))
            ).scalar()
            assert profile_count == 1

            spoiler_count = session.execute(
                select(func.count()).select_from(SpoilerPreferences).where(SpoilerPreferences.user_id == uuid.UUID(user_id))
            ).scalar()
            assert spoiler_count == 1

            run = session.execute(
                select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(run_id))
            ).scalar_one_or_none()
            assert run is not None
            assert str(run.owner_user_id) == user_id
            assert run.run_type == "REFRAME"
            assert run.status == run_status
            assert run.work_id == "the-bat-whispers-1930"
            assert run.edition_id == "tbw-fullscreen-archive"
            assert run.reveal_id == "reveal-anderson-identity"
            assert run.idempotency_key == "phase1-restart-run-001"
            assert run.dataset_version is not None
            assert run.model_id is not None
            input_hash = run.input_hash
            assert input_hash is not None and len(input_hash) > 0

            run_count = session.execute(
                select(func.count()).select_from(AnalysisRun).where(AnalysisRun.id == uuid.UUID(run_id))
            ).scalar()
            assert run_count == 1

            usage_count = session.execute(select(func.count()).select_from(UsageLedger)).scalar()
            assert usage_count == 0

        sync_engine.dispose()

        receipt = {
            "phase": "create",
            "pid": os.getpid(),
            "process_nonce": str(uuid.uuid4()),
            "fresh_import": fresh_import,
            "resolved_db_path": str(db_path.resolve()),
            "database_url": os.environ["DATABASE_URL"],
            "user_id": user_id,
            "email": user_email,
            "run_id": run_id,
            "run_status": run_status,
            "work_id": "the-bat-whispers-1930",
            "edition_id": "tbw-fullscreen-archive",
            "reveal_id": "reveal-anderson-identity",
            "input_hash": input_hash,
            "usage_ledger_count": usage_count,
            "provider_constructor_attempts": provider_constructor_attempts,
            "redis_connect_await_count": redis_connect_mock.await_count,
            "redis_close_await_count": redis_close_mock.await_count,
        }
        print(f"PHASE1_RESTART_RECEIPT={json.dumps(receipt)}", flush=True)

    elif phase == "verify":
        # Process B: Fresh process, fresh module graph, fresh engine
        assert expected_run_id is not None, "expected_run_id required for verify phase"

        # B-1. Assert in-memory stores are pristine empty
        assert apps.api.main.RUNS_STORE == {}, "RUNS_STORE not empty on fresh import"
        assert apps.api.main.TRACES_STORE == {}, "TRACES_STORE not empty on fresh import"
        assert apps.api.main.ANALYSIS_CACHE == {}, "ANALYSIS_CACHE not empty on fresh import"

        with TestClient(apps.api.main.app) as client:
            # B-2. Dev login with same identity (no Process A session cookie transferred)
            resp_login = client.post(
                "/api/v1/auth/dev-login",
                json={"email": user_email, "display_name": user_display}
            )
            assert resp_login.status_code == 200, f"Dev login in Process B failed: {resp_login.text}"
            login_data = resp_login.json()["data"]
            user_id = login_data["user_id"]
            assert login_data["email"] == user_email
            assert settings.SESSION_COOKIE_NAME in client.cookies

            # B-3. Verify both /me and /auth/me
            resp_me = client.get("/api/v1/me")
            assert resp_me.status_code == 200, f"/me failed: {resp_me.text}"
            me_json = resp_me.json()
            assert me_json["meta"]["is_authenticated"] is True
            assert me_json["data"]["id"] == user_id
            assert me_json["data"]["email"] == user_email
            assert me_json["data"]["role"] == "USER"

            resp_auth_me = client.get("/api/v1/auth/me")
            assert resp_auth_me.status_code == 200, f"/auth/me failed: {resp_auth_me.text}"
            auth_me_json = resp_auth_me.json()
            assert auth_me_json["meta"]["is_authenticated"] is True
            assert auth_me_json["data"]["id"] == user_id
            assert auth_me_json["data"]["email"] == user_email
            assert auth_me_json["data"]["role"] == "USER"

            # B-4. Query private Run API using Process B authentication
            resp_run = client.get(f"/api/v1/reframe-runs/{expected_run_id}")
            assert resp_run.status_code == 200, f"Get run failed in Process B: {resp_run.text}"
            run_data = resp_run.json()["data"]
            assert run_data["run_id"] == expected_run_id
            assert run_data["run_type"] == "REFRAME"
            assert run_data["status"] == "QUEUED"
            assert run_data["work_id"] == "the-bat-whispers-1930"
            assert run_data["edition_id"] == "tbw-fullscreen-archive"
            assert run_data["reveal_id"] == "reveal-anderson-identity"

        # Verify lifespan executed Redis connect and close
        assert redis_connect_mock.await_count == 1, "Redis connect not called in lifespan"
        assert redis_close_mock.await_count == 1, "Redis close not called in lifespan"

        # B-5. Independent DB readback via new sync session
        SyncSessionLocal = sessionmaker(bind=sync_engine)
        with SyncSessionLocal() as session:
            user_count = session.execute(select(func.count()).select_from(User)).scalar()
            assert user_count == 1, f"Expected exactly 1 User in DB, found {user_count}"

            profile_count = session.execute(select(func.count()).select_from(Profile)).scalar()
            assert profile_count == 1, f"Expected exactly 1 Profile in DB, found {profile_count}"

            spoiler_count = session.execute(select(func.count()).select_from(SpoilerPreferences)).scalar()
            assert spoiler_count == 1, f"Expected exactly 1 SpoilerPreferences in DB, found {spoiler_count}"

            run_count = session.execute(select(func.count()).select_from(AnalysisRun)).scalar()
            assert run_count == 1, f"Expected exactly 1 AnalysisRun in DB, found {run_count}"

            user = session.execute(
                select(User).where(User.id == uuid.UUID(user_id))
            ).scalar_one_or_none()
            assert user is not None
            assert user.email_normalized == user_email
            assert user.role == "USER"

            run = session.execute(
                select(AnalysisRun).where(AnalysisRun.id == uuid.UUID(expected_run_id))
            ).scalar_one_or_none()
            assert run is not None
            assert str(run.owner_user_id) == user_id
            assert run.status == "QUEUED"
            assert run.work_id == "the-bat-whispers-1930"
            assert run.edition_id == "tbw-fullscreen-archive"
            assert run.reveal_id == "reveal-anderson-identity"
            input_hash = run.input_hash
            assert input_hash is not None and len(input_hash) > 0

            usage_count = session.execute(select(func.count()).select_from(UsageLedger)).scalar()
            assert usage_count == 0

        sync_engine.dispose()

        receipt = {
            "phase": "verify",
            "pid": os.getpid(),
            "process_nonce": str(uuid.uuid4()),
            "fresh_import": fresh_import,
            "resolved_db_path": str(db_path.resolve()),
            "database_url": os.environ["DATABASE_URL"],
            "user_id": user_id,
            "email": user_email,
            "run_id": expected_run_id,
            "run_status": run.status,
            "work_id": run.work_id,
            "edition_id": run.edition_id,
            "reveal_id": run.reveal_id,
            "input_hash": input_hash,
            "usage_ledger_count": usage_count,
            "provider_constructor_attempts": provider_constructor_attempts,
            "redis_connect_await_count": redis_connect_mock.await_count,
            "redis_close_await_count": redis_close_mock.await_count,
        }
        print(f"PHASE1_RESTART_RECEIPT={json.dumps(receipt)}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase 1 API Restart Persistence Child Runner")
    parser.add_argument("--child-phase", choices=["create", "verify"], required=True)
    parser.add_argument("--db-path", required=True)
    parser.add_argument("--expected-run-id", default=None)
    args = parser.parse_args()

    _run_child(
        phase=args.child_phase,
        db_path=pathlib.Path(args.db_path),
        expected_run_id=args.expected_run_id
    )
