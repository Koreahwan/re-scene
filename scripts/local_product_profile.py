"""Explicit offline local profile; no inherited application credentials or .env."""
from pathlib import Path
import json
import os
import secrets
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
OWNER = "reframe-isolated-local-v1"


def clean_environment():
    return {key: os.environ[key] for key in (
        "SystemRoot", "WINDIR", "COMSPEC", "TEMP", "TMP", "PATH", "PATHEXT",
        "USERPROFILE", "LOCALAPPDATA", "APPDATA", "ProgramFiles",
    ) if key in os.environ}


def claim_database(path: Path) -> Path:
    path = path.resolve()
    if path.suffix != ".db" or path.parent == REPO_ROOT or path.parent == Path.home():
        raise ValueError("Use a dedicated local runtime directory and a .db filename")
    marker = path.with_suffix(".owner.json")
    expected = {"owner": OWNER, "database": str(path)}
    if path.exists() and not marker.exists():
        raise ValueError("Existing unowned database refused; choose a new dedicated --db path")
    if marker.exists() and json.loads(marker.read_text(encoding="utf-8")) != expected:
        raise ValueError("Database ownership marker does not match")
    if (path.parent / ".env").exists():
        raise ValueError("Local runtime directory must not contain .env")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not marker.exists():
        with marker.open("x", encoding="utf-8") as stream:
            json.dump(expected, stream)
    return path


def configure_api(path: Path):
    path = claim_database(path)
    environment = clean_environment()
    os.environ.clear()
    os.environ.update(environment)
    os.chdir(path.parent)
    key_file = path.with_suffix(".session-key")
    if not key_file.exists():
        with key_file.open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(48))
        key_file.chmod(0o600)
    os.environ.update({
        "DATABASE_URL": "sqlite+aiosqlite:///" + path.as_posix(),
        "SYNC_DATABASE_URL": "sqlite:///" + path.as_posix(),
        "ENVIRONMENT": "test", "SCHEMA_INIT_MODE": "MIGRATIONS_ONLY",
        "SECRET_KEY": key_file.read_text(encoding="utf-8"),
        "PAID_CALLS_ENABLED": "false", "SPEND_KILL_SWITCH_ACTIVE": "true",
        "EXECUTION_MODE": "OFFLINE_FIXTURE", "LIVE_AGENT_ENABLED": "false",
        "LIVE_EVAL_ENABLED": "false", "LEGACY_PAID_PATH_ENABLED": "false",
        "EMBEDDED_WORKER_ENABLED": "false", "AUTH_EMAIL_DELIVERY_MODE": "DEV_OUTBOX",
        "AUTH_DEV_OUTBOX_VIEWER_ENABLED": "true",
        "LOCAL_STORAGE_DIR": str(path.parent / "storage"),
        "SIMULATION_DATA_DIR": str(path.parent / "simulation"), "STORAGE_BACKEND": "local",
        "ENABLE_SYNTHETIC_DEMO_CONTENT": "false", "ENABLE_SYNTHETIC_MAGAZINE": "false",
        "ENABLE_AUDIENCE_LAB": "false", "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUNBUFFERED": "1",
    })
    sys.path.insert(0, str(REPO_ROOT))
    return path


def deny_outbound(event, args):
    if event == "socket.getaddrinfo" and args[0] not in (None, "localhost", "127.0.0.1", "::1"):
        raise PermissionError("LOCAL_PRODUCT_DNS_BLOCKED")
    if event == "socket.sendto":
        raise PermissionError("LOCAL_PRODUCT_DATAGRAM_BLOCKED")
    if event != "socket.connect":
        return
    # asyncio's Windows loopback socketpair is internal, not service egress.
    frame = sys._getframe(1)
    while frame:
        if frame.f_globals.get("__name__") == "socket" and frame.f_code.co_name in ("socketpair", "_fallback_socketpair"):
            return
        frame = frame.f_back
    raise PermissionError("LOCAL_PRODUCT_OUTBOUND_BLOCKED")
