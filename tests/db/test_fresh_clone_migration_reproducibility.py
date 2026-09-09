import os
import sys
import json
import pytest
import pathlib
import hashlib
import tempfile
import subprocess
import sqlite3
import socket

_repo_root = pathlib.Path(__file__).parent.parent.parent.resolve()
_repo_db_path = _repo_root / "reframe_v7.db"

_ZERO_COST_ENV = {
    "EXECUTION_MODE": "OFFLINE_FIXTURE",
    "PAID_CALLS_ENABLED": "false",
    "SPEND_KILL_SWITCH_ACTIVE": "true",
    "LIVE_AGENT_ENABLED": "false",
    "LIVE_EVAL_ENABLED": "false",
    "PUBLIC_REFRAME_MODEL_CALLS": "0",
    "PUBLIC_PROOF_LOOKUP_MODEL_CALLS": "0",
    "PUBLIC_COMMUNITY_MODEL_CALLS": "0",
    "GEMINI_API_KEY": "",
    "GOOGLE_API_KEY": "",
    "GOOGLE_APPLICATION_CREDENTIALS": "",
    "GOOGLE_CLIENT_ID": "",
    "GOOGLE_CLIENT_SECRET": "",
    "GOOGLE_CLOUD_PROJECT": "",
    "GOOGLE_CLOUD_LOCATION": "",
    "PYTHONDONTWRITEBYTECODE": "1"
}

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

def _get_head_from_alembic_script():
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    cfg = Config(str(_repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(_repo_root / "db/postgres/migrations"))
    script = ScriptDirectory.from_config(cfg)

    revisions = list(script.walk_revisions())
    assert len(revisions) == 12, f"Expected exactly 12 revisions, got {len(revisions)}"

    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly one head, got {len(heads)}"

    bases = script.get_bases()
    assert len(bases) == 1, f"Expected exactly one base, got {len(bases)}"

    expected_chain = [
        "0012_v7_audit_log_sqlite_pk",
        "0011_v7_analysis_run_events_sqlite_pk",
        "0010_v7_usage_ledger_unique",
        "0009_v7_auth_operations_saga",
        "0008_v7_auth_version_and_user_handle",
        "0007_v7_synthetic_persona_demo_user_mapping",
        "0006_v7_synthetic_lab",
        "0005_v7_auth_and_checkpoint",
        "0004_r4_1_final_sync",
        "0003_r4_schema_sync",
        "0002_add_canonical_proof_records",
        "0001_initial_v7_schema"
    ]

    chain = []
    visited = set()
    current_rev = heads[0]

    for rev in revisions:
        assert not rev.branch_labels, f"Revision {rev.revision} has branch labels"
        assert isinstance(rev.down_revision, str) or rev.down_revision is None, "down_revision must be string or None"

    while current_rev:
        chain.append(current_rev)
        visited.add(current_rev)
        rev_obj = script.get_revision(current_rev)
        current_rev = rev_obj.down_revision

    assert chain == expected_chain, f"Chain mismatch:\n{chain}\n!=\n{expected_chain}"
    assert len(visited) == 12, "Not all revisions were visited exactly once"

    print(f"Discovered full chain: {chain}")
    print(f"Discovered base: {bases[0]}")
    print(f"Discovered head: {heads[0]}")
    return heads[0]

def _install_network_blocker(td_path: pathlib.Path):
    blocker_code = """
import socket
import pathlib
import sys
import os
import atexit
import threading

run_id = os.environ.get("BOUNDARY_RUN_ID", "unknown")
guard_dir = pathlib.Path(os.environ.get("BOUNDARY_GUARD_DIR", "."))

def marker_path(name):
    return guard_dir / f"{name}-{run_id}"

expected_cwd = os.environ.get("EXPECTED_CHILD_CWD", ".")
actual_cwd = os.getcwd()
if pathlib.Path(actual_cwd).resolve() != pathlib.Path(expected_cwd).resolve():
    marker_path("isolation-failure").write_text(f"CWD mismatch: {actual_cwd} != {expected_cwd}", encoding="utf-8")
if (pathlib.Path(actual_cwd) / ".env").exists():
    marker_path("isolation-failure").write_text(".env exists in cwd", encoding="utf-8")
repo_root = os.environ.get("EXPECTED_REPO_ROOT", "")
db_url = os.environ.get("DATABASE_URL", "")
sync_db_url = os.environ.get("SYNC_DATABASE_URL", "")
if repo_root and repo_root in db_url:
    marker_path("isolation-failure").write_text("DB path inside repo", encoding="utf-8")
expected_db = os.environ.get("EXPECTED_DB_PATH", "")
if expected_db and expected_db not in db_url:
    marker_path("isolation-failure").write_text(f"DATABASE_URL does not resolve to {expected_db}", encoding="utf-8")
if expected_db and expected_db not in sync_db_url:
    marker_path("isolation-failure").write_text(f"SYNC_DATABASE_URL does not resolve to {expected_db}", encoding="utf-8")

class ForbiddenImportObserver:
    def find_spec(self, fullname, path, target=None):
        forbidden = [
            "src.reframe.agents.runtime",
            "src.reframe.agents.adk_gateway",
            "google.genai",
            "google.adk"
        ]
        for f in forbidden:
            if fullname == f or fullname.startswith(f + "."):
                with open(marker_path("forbidden-import"), "a", encoding="utf-8") as out:
                    out.write("from_observer:" + fullname + "\\n")
        return None

sys.meta_path.insert(0, ForbiddenImportObserver())

_orig_connect = socket.socket.connect
_orig_connect_ex = socket.socket.connect_ex
_orig_create_connection = socket.create_connection

tls = threading.local()

def _record_blocked(address, method):
    with open(marker_path("service-network-attempt"), "a", encoding="utf-8") as f:
        f.write(f"{method}:{address}\\n")
    raise RuntimeError(f"Network connection attempted to {address} during migration via {method}!")

def _is_loopback(address):
    if isinstance(address, tuple):
        return address[0] in ("127.0.0.1", "::1", "localhost")
    return False

def _blocked_connect(self, address):
    if getattr(tls, "in_socketpair", False) and _is_loopback(address):
        with open(marker_path("internal-socketpair-used"), "a", encoding="utf-8") as f:
            f.write(f"connect:{address}\\n")
        return _orig_connect(self, address)
    _record_blocked(address, "connect")

def _blocked_connect_ex(self, address):
    if getattr(tls, "in_socketpair", False) and _is_loopback(address):
        with open(marker_path("internal-socketpair-used"), "a", encoding="utf-8") as f:
            f.write(f"connect_ex:{address}\\n")
        return _orig_connect_ex(self, address)
    _record_blocked(address, "connect_ex")

def _blocked_create_connection(address, *args, **kwargs):
    _record_blocked(address, "create_connection")

socket.socket.connect = _blocked_connect
socket.socket.connect_ex = _blocked_connect_ex
socket.create_connection = _blocked_create_connection

_orig_socketpair = getattr(socket, "socketpair", None)
if _orig_socketpair:
    def _my_socketpair(*args, **kwargs):
        tls.in_socketpair = True
        try:
            return _orig_socketpair(*args, **kwargs)
        finally:
            tls.in_socketpair = False
    socket.socketpair = _my_socketpair

def _check_imports():
    forbidden = [
        "src.reframe.agents.runtime",
        "src.reframe.agents.adk_gateway",
        "google.genai",
        "google.adk"
    ]
    found = [mod for mod in forbidden if mod in sys.modules]
    if found:
        with open(marker_path("forbidden-import"), "a", encoding="utf-8") as f:
            f.write("from_sys_modules:" + ",".join(found) + "\\n")
atexit.register(_check_imports)

marker_path("blocker-loaded").write_text("loaded", encoding="utf-8")
"""
    (td_path / "sitecustomize.py").write_text(blocker_code, encoding="utf-8")


def _run_alembic_upgrade(temp_dir_path: pathlib.Path, db_path: pathlib.Path, run_id: str):
    env = {}
    for k in ["SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "LOCALAPPDATA"]:
        if k in os.environ:
            env[k] = os.environ[k]

    env.update(_ZERO_COST_ENV)

    env["PYTHONPATH"] = f"{temp_dir_path.as_posix()}{os.pathsep}{_repo_root.as_posix()}"
    env["BOUNDARY_RUN_ID"] = run_id
    env["BOUNDARY_GUARD_DIR"] = temp_dir_path.as_posix()
    env["EXPECTED_CHILD_CWD"] = temp_dir_path.as_posix()
    env["EXPECTED_REPO_ROOT"] = _repo_root.as_posix()
    env["EXPECTED_DB_PATH"] = db_path.as_posix()

    db_url_path = db_path.as_posix()
    async_url = f"sqlite+aiosqlite:///{db_url_path}"
    sync_url = f"sqlite:///{db_url_path}"

    env["DATABASE_URL"] = async_url
    env["SYNC_DATABASE_URL"] = sync_url

    import re
    repo_ini_text = (_repo_root / "alembic.ini").read_text(encoding="utf-8")

    abs_script = (_repo_root / "db/postgres/migrations").as_posix()
    abs_versions = (_repo_root / "db/postgres/migrations/versions").as_posix()

    temp_ini_text = re.sub(
        r'^script_location\s*=\s*.*$',
        f'script_location = {abs_script}',
        repo_ini_text,
        flags=re.MULTILINE
    )
    temp_ini_text = re.sub(
        r'^version_locations\s*=\s*.*$',
        f'version_locations = {abs_versions}',
        temp_ini_text,
        flags=re.MULTILINE
    )

    temp_ini_path = temp_dir_path / "alembic.ini"
    temp_ini_path.write_text(temp_ini_text, encoding="utf-8")

    # Assert markers are absent before run
    for marker in ["blocker-loaded", "service-network-attempt", "forbidden-import", "internal-socketpair-used", "isolation-failure"]:
        assert not (temp_dir_path / f"{marker}-{run_id}").exists()

    cmd = [
        sys.executable, "-m", "alembic",
        "-c", temp_ini_path.as_posix(),
        "upgrade", "head"
    ]

    result = subprocess.run(cmd, cwd=temp_dir_path.as_posix(), env=env, capture_output=True, text=True, timeout=120)

    assert (temp_dir_path / f"blocker-loaded-{run_id}").exists()
    assert not (temp_dir_path / f"forbidden-import-{run_id}").exists()
    assert not (temp_dir_path / f"isolation-failure-{run_id}").exists()

    return result

def _get_sqlite_schema_state(db_path: pathlib.Path):
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = set(row[0] for row in cur.fetchall())

        version = None
        declared_type = None
        parsed_length = None

        if "alembic_version" in tables:
            cur.execute("SELECT version_num FROM alembic_version")
            rows = cur.fetchall()
            assert len(rows) == 1, f"Expected exactly one row in alembic_version, got {len(rows)}"
            version = rows[0][0]

            cur.execute("PRAGMA table_info(alembic_version)")
            columns = {row[1]: row[2] for row in cur.fetchall()}
            declared_type = columns["version_num"]

            upper_type = declared_type.upper()
            assert upper_type.startswith("VARCHAR"), f"Base type is not VARCHAR: {declared_type}"

            import re
            m = re.search(r'\((\d+)\)', upper_type)
            assert m is not None, f"Numeric length missing in {declared_type}"
            parsed_length = int(m.group(1))
            assert parsed_length >= 128, f"Numeric length too short: {parsed_length} in {declared_type}"

        return {"tables": tables, "version": version, "declared_type": declared_type, "parsed_length": parsed_length}
    finally:
        conn.close()

def _check_subprocess_boundary(td_path: pathlib.Path, run_id: str):
    env = {}
    for k in ["SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "LOCALAPPDATA"]:
        if k in os.environ:
            env[k] = os.environ[k]
    env.update(_ZERO_COST_ENV)
    env["PYTHONPATH"] = f"{td_path.as_posix()}{os.pathsep}{_repo_root.as_posix()}"
    env["BOUNDARY_RUN_ID"] = run_id
    env["BOUNDARY_GUARD_DIR"] = td_path.as_posix()
    env["EXPECTED_CHILD_CWD"] = td_path.as_posix()

    for marker in ["blocker-loaded", "service-network-attempt", "forbidden-import", "internal-socketpair-used", "isolation-failure"]:
        assert not (td_path / f"{marker}-{run_id}").exists()

    test_script = td_path / "test_boundary.py"
    test_script.write_text(r"""
import socket
import urllib.request
try:
    socket.socket().connect(('127.0.0.1', 6379))
    print("FAIL: 127.0.0.1:6379 succeeded")
except RuntimeError as e:
    pass
try:
    socket.socket().connect_ex(('127.0.0.1', 8123))
    print("FAIL: 127.0.0.1:8123 succeeded")
except RuntimeError as e:
    pass
try:
    socket.create_connection(('8.8.8.8', 53), timeout=1)
    print("FAIL: 8.8.8.8:53 succeeded")
except RuntimeError as e:
    pass
try:
    socket.socket(socket.AF_INET6, socket.SOCK_STREAM).connect(('::1', 6379))
    print("FAIL: ::1:6379 succeeded")
except RuntimeError as e:
    pass
if hasattr(socket, 'AF_UNIX'):
    try:
        socket.socket(socket.AF_UNIX, socket.SOCK_STREAM).connect('/tmp/dummy.sock')
        print("FAIL: AF_UNIX succeeded")
    except RuntimeError as e:
        pass
print("BOUNDARY OK")
""", encoding="utf-8")

    cmd = [sys.executable, test_script.as_posix()]
    result = subprocess.run(cmd, cwd=td_path.as_posix(), env=env, capture_output=True, text=True, timeout=10)

    assert result.returncode == 0
    assert "FAIL:" not in result.stdout
    assert "BOUNDARY OK" in result.stdout

    assert (td_path / f"blocker-loaded-{run_id}").exists()
    assert not (td_path / f"forbidden-import-{run_id}").exists()
    assert not (td_path / f"isolation-failure-{run_id}").exists()

    attempt_marker = td_path / f"service-network-attempt-{run_id}"
    assert attempt_marker.exists()

    content = attempt_marker.read_text(encoding="utf-8")
    assert "connect:('127.0.0.1', 6379)" in content
    assert "connect_ex:('127.0.0.1', 8123)" in content
    assert "create_connection:('8.8.8.8', 53)" in content
    assert "connect:('::1', 6379)" in content
    if hasattr(socket, 'AF_UNIX'):
        assert "connect:'/tmp/dummy.sock'" in content or "connect:/tmp/dummy.sock" in content


def test_fresh_clone_migration_reproducibility():
    initial_fp = _get_db_fingerprint(_repo_db_path)

    head = _get_head_from_alembic_script()
    assert head == "0012_v7_audit_log_sqlite_pk"

    temps = []
    tables_run1 = None

    temp_prefix = "reframe-alembic-r2-"
    temp_parent = pathlib.Path(tempfile.gettempdir())
    existing_dirs = {p for p in temp_parent.glob(f"{temp_prefix}*") if p.is_dir()}

    try:
        for i in range(2):
            td = tempfile.TemporaryDirectory(prefix=temp_prefix)
            temps.append(td)

            td_path = pathlib.Path(td.name).resolve()
            assert _repo_root not in td_path.parents and _repo_root != td_path

            db_path = td_path / "fresh.db"

            _install_network_blocker(td_path)

            if i == 0:
                _check_subprocess_boundary(td_path, "boundary-negative")
                print("Boundary API/address matrix result: PASSED")

            # Enforce brand-new DB
            assert not db_path.exists(), f"DB {db_path} already exists before first upgrade!"

            run_id_first = f"db{i+1}-first"
            res = _run_alembic_upgrade(td_path, db_path, run_id_first)

            if res.returncode != 0:
                pytest.fail(f"{run_id_first} upgrade failed! exit code {res.returncode}\nstdout:\n{res.stdout}\nstderr:\n{res.stderr}")
            print(f"{run_id_first} exit code: {res.returncode}")

            assert not (td_path / f"service-network-attempt-{run_id_first}").exists()
            if (td_path / f"internal-socketpair-used-{run_id_first}").exists():
                print(f"internal asyncio socketpair IPC was permitted in {run_id_first}")

            state = _get_sqlite_schema_state(db_path)
            print(f"DB version: {state['version']}")
            print(f"Declared version_num type: {state['declared_type']} (parsed length {state['parsed_length']})")

            assert state["version"] == head
            assert "users" in state["tables"]
            assert "auth_operations" in state["tables"]

            sorted_tables = sorted(list(state["tables"]))
            print(f"Sorted table-name set: {sorted_tables}")

            if i == 0:
                tables_run1 = sorted_tables
            else:
                tables_run2 = sorted_tables
                assert tables_run1 == tables_run2

            # Enforce DB exists before idempotent upgrade and has head
            assert db_path.exists()
            assert _get_sqlite_schema_state(db_path)["version"] == head

            run_id_idemp = f"db{i+1}-idempotent"
            res2 = _run_alembic_upgrade(td_path, db_path, run_id_idemp)
            if res2.returncode != 0:
                pytest.fail(f"{run_id_idemp} upgrade failed! exit code {res2.returncode}\nstdout:\n{res2.stdout}\nstderr:\n{res2.stderr}")
            print(f"{run_id_idemp} exit code: {res2.returncode}")

            assert not (td_path / f"service-network-attempt-{run_id_idemp}").exists()
            if (td_path / f"internal-socketpair-used-{run_id_idemp}").exists():
                print(f"internal asyncio socketpair IPC was permitted in {run_id_idemp}")

            state_after_second = _get_sqlite_schema_state(db_path)
            assert state_after_second["version"] == head
            assert sorted(list(state_after_second["tables"])) == sorted_tables

    finally:
        cleanup_errors = []
        for td in temps:
            try:
                td.cleanup()
            except Exception as e:
                cleanup_errors.append(f"Failed to cleanup temp dir {td.name}: {e}")

        final_fp = _get_db_fingerprint(_repo_db_path)
        if initial_fp != final_fp:
            cleanup_errors.append(f"Repository DB fingerprint changed! Before: {initial_fp}, After: {final_fp}")

        remaining_dirs = {p for p in temp_parent.glob(f"{temp_prefix}*") if p.is_dir()}
        if existing_dirs != remaining_dirs:
            cleanup_errors.append(f"Temporary directories leaked! Before: {existing_dirs}, After: {remaining_dirs}")

        if cleanup_errors:
            pytest.fail("Cleanup errors:\n" + "\n".join(cleanup_errors))
