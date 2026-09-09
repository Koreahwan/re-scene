import os
import sys
import json
import pathlib
import hashlib
import tempfile
import subprocess

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
    "TEST_POSTGRES_URL": "",
    "RUN_DISPOSABLE_POSTGRES_TESTS": "false",
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

def test_alembic_target_metadata_registration():
    initial_fp = _get_db_fingerprint(_repo_db_path)

    td = tempfile.TemporaryDirectory(prefix="reframe-v7-008-metadata-")
    owned_path = pathlib.Path(td.name).resolve()

    try:
        env = {}
        for k in ["SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "LOCALAPPDATA"]:
            if k in os.environ:
                env[k] = os.environ[k]

        env.update(_ZERO_COST_ENV)
        env["PYTHONPATH"] = _repo_root.as_posix()

        db_path = owned_path / "fresh.db"
        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        env["SYNC_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"

        test_script = owned_path / "metadata_child.py"
        test_script.write_text(r"""
import sys
import os
import socket
import json
import pathlib

socket_attempts = 0

def _blocked(*args, **kwargs):
    global socket_attempts
    socket_attempts += 1
    raise RuntimeError("Socket attempts are blocked in this child.")

socket.socket.connect = _blocked
socket.socket.connect_ex = _blocked
socket.create_connection = _blocked

import db.postgres.migrations.env as env_module

target_metadata = env_module.target_metadata
from src.reframe.shared.database import Base
import sqlalchemy

forbidden = [
    "src.reframe.agents.runtime",
    "src.reframe.agents.adk_gateway",
    "google.genai",
    "google.adk"
]

found = [m for m in forbidden if m in sys.modules]

tables = list(target_metadata.tables.keys())

col = target_metadata.tables["analysis_runs"].c.get("cost_actual_micros")
if col is not None:
    cost_actual_info = {
        "exists": True,
        "type": type(col.type).__name__,
        "nullable": col.nullable,
        "default": col.default.arg if col.default else None,
        "server_default": str(col.server_default.arg) if col.server_default else None
    }
else:
    cost_actual_info = {"exists": False}

data = {
    "tables": tables,
    "metadata_is_base": target_metadata is Base.metadata,
    "cwd": os.getcwd(),
    "socket_attempts": socket_attempts,
    "forbidden_found": found,
    "cost_actual_info": cost_actual_info
}

analysis_table = target_metadata.tables.get("analysis_runs")
if analysis_table is not None:
    proof_col = analysis_table.c.get("proof_ids")
    if proof_col is not None:
        first_default = proof_col.default.arg(None) if (proof_col.default and proof_col.default.is_callable) else None
        second_default = proof_col.default.arg(None) if (proof_col.default and proof_col.default.is_callable) else None

        proof_ids_info = {
            "exists": True,
            "type": type(proof_col.type).__name__,
            "is_sqlalchemy_json": isinstance(proof_col.type, sqlalchemy.JSON),
            "nullable": proof_col.nullable,
            "has_default": proof_col.default is not None,
            "is_callable_default": proof_col.default.is_callable if proof_col.default else False,
            "first_default": first_default,
            "second_default": second_default,
            "first_is_not_second": first_default is not second_default if first_default is not None else False,
            "has_server_default": proof_col.server_default is not None,
            "server_default": str(proof_col.server_default.arg).strip() if proof_col.server_default else None
        }
    else:
        proof_ids_info = {"exists": False}
else:
    proof_ids_info = {"exists": False}

data["proof_ids_info"] = proof_ids_info

step_table = target_metadata.tables.get("analysis_run_steps")
if step_table is not None:
    model_call_col = step_table.c.get("model_call_ids")
    if model_call_col is not None:
        first_default = model_call_col.default.arg(None) if (model_call_col.default and model_call_col.default.is_callable) else None
        second_default = model_call_col.default.arg(None) if (model_call_col.default and model_call_col.default.is_callable) else None

        model_call_ids_info = {
            "exists": True,
            "type": type(model_call_col.type).__name__,
            "is_sqlalchemy_json": isinstance(model_call_col.type, sqlalchemy.JSON),
            "nullable": model_call_col.nullable,
            "has_default": model_call_col.default is not None,
            "is_callable_default": model_call_col.default.is_callable if model_call_col.default else False,
            "first_default": first_default,
            "second_default": second_default,
            "first_is_not_second": first_default is not second_default if first_default is not None else False,
            "has_server_default": model_call_col.server_default is not None,
            "server_default": str(model_call_col.server_default.arg).strip() if model_call_col.server_default else None
        }
    else:
        model_call_ids_info = {"exists": False}
else:
    model_call_ids_info = {"exists": False}

data["model_call_ids_info"] = model_call_ids_info

counter_table = target_metadata.tables.get("counterfactual_run_records")
if counter_table is not None:
    exp_constraints = [
        c for c in counter_table.constraints
        if isinstance(c, sqlalchemy.UniqueConstraint) and [col.name for col in c.columns] == ["experiment_id"]
    ]
    exp_indexes = [
        i for i in counter_table.indexes
        if [col.name for col in i.columns] == ["experiment_id"]
    ]
    experiment_col = counter_table.c.get("experiment_id")

    counterfactual_info = {
        "exists": True,
        "constraint_count": len(exp_constraints),
        "constraint_name": exp_constraints[0].name if exp_constraints else None,
        "constraint_columns": [col.name for col in exp_constraints[0].columns] if exp_constraints else None,
        "index_count": len(exp_indexes),
        "index_name": exp_indexes[0].name if exp_indexes else None,
        "index_unique": exp_indexes[0].unique if exp_indexes else None,
        "col_type": type(experiment_col.type).__name__ if experiment_col is not None else None,
        "col_length": getattr(experiment_col.type, "length", None) if experiment_col is not None else None,
        "col_nullable": experiment_col.nullable if experiment_col is not None else None
    }
else:
    counterfactual_info = {"exists": False}

data["counterfactual_info"] = counterfactual_info

users_table = target_metadata.tables.get("users")
if users_table is not None:
    users_constraints = [
        c for c in users_table.constraints
        if isinstance(c, sqlalchemy.UniqueConstraint) and [col.name for col in c.columns] == ["handle_normalized"]
    ]
    users_indexes = [
        i for i in users_table.indexes
        if [col.name for col in i.columns] == ["handle_normalized"]
    ]
    handle_col = users_table.c.get("handle_normalized")

    users_handle_info = {
        "exists": True,
        "constraint_count": len(users_constraints),
        "constraint_name": users_constraints[0].name if users_constraints else None,
        "constraint_columns": [col.name for col in users_constraints[0].columns] if users_constraints else None,
        "index_count": len(users_indexes),
        "index_name": users_indexes[0].name if users_indexes else None,
        "index_unique": users_indexes[0].unique if users_indexes else None,
        "col_type": type(handle_col.type).__name__ if handle_col is not None else None,
        "col_length": getattr(handle_col.type, "length", None) if handle_col is not None else None,
        "col_nullable": handle_col.nullable if handle_col is not None else None,
        "col_unique": getattr(handle_col, "unique", None) if handle_col is not None else None
    }
else:
    users_handle_info = {"exists": False}

data["users_handle_info"] = users_handle_info

personas_table = target_metadata.tables.get("synthetic_personas")
if personas_table is not None:
    source_col = personas_table.c.get("source_persona_id_hash")
    demo_col = personas_table.c.get("demo_user_id")

    source_constraints = [
        c for c in personas_table.constraints
        if isinstance(c, sqlalchemy.UniqueConstraint) and [col.name for col in c.columns] == ["source_persona_id_hash"]
    ]
    source_indexes = [
        i for i in personas_table.indexes
        if [col.name for col in i.columns] == ["source_persona_id_hash"]
    ]

    demo_constraints = [
        c for c in personas_table.constraints
        if isinstance(c, sqlalchemy.UniqueConstraint) and [col.name for col in c.columns] == ["demo_user_id"]
    ]
    demo_indexes = [
        i for i in personas_table.indexes
        if [col.name for col in i.columns] == ["demo_user_id"]
    ]

    demo_fks = [
        fk for c in personas_table.columns for fk in c.foreign_keys if c.name == "demo_user_id"
    ]

    persona_info = {
        "exists": True,
        "source_constraint_count": len(source_constraints),
        "source_constraint_name": source_constraints[0].name if source_constraints else None,
        "source_constraint_columns": [col.name for col in source_constraints[0].columns] if source_constraints else None,
        "source_index_count": len(source_indexes),
        "source_index_name": source_indexes[0].name if source_indexes else None,
        "source_index_unique": source_indexes[0].unique if source_indexes else None,
        "source_col_type": type(source_col.type).__name__ if source_col is not None else None,
        "source_col_length": getattr(source_col.type, "length", None) if source_col is not None else None,
        "source_col_nullable": source_col.nullable if source_col is not None else None,
        "source_col_unique": getattr(source_col, "unique", None) if source_col is not None else None,

        "demo_constraint_count": len(demo_constraints),
        "demo_constraint_name": demo_constraints[0].name if demo_constraints else None,
        "demo_constraint_columns": [col.name for col in demo_constraints[0].columns] if demo_constraints else None,
        "demo_index_count": len(demo_indexes),
        "demo_index_name": demo_indexes[0].name if demo_indexes else None,
        "demo_index_unique": demo_indexes[0].unique if demo_indexes else None,
        "demo_col_type": type(demo_col.type).__name__ if demo_col is not None else None,
        "demo_col_nullable": demo_col.nullable if demo_col is not None else None,
        "demo_col_unique": getattr(demo_col, "unique", None) if demo_col is not None else None,
        "demo_fk_count": len(demo_fks),
        "demo_fk_target": demo_fks[0].target_fullname if demo_fks else None,
        "demo_fk_ondelete": demo_fks[0].ondelete if demo_fks else None
    }
else:
    persona_info = {"exists": False}

data["persona_info"] = persona_info

provenance_table = target_metadata.tables.get("synthetic_content_provenance")
if provenance_table is not None:
    prov_constraints = [
        c for c in provenance_table.constraints
        if isinstance(c, sqlalchemy.UniqueConstraint) and [col.name for col in c.columns] == ["stable_content_key"]
    ]

    run_indexes = [i for i in provenance_table.indexes if [col.name for col in i.columns] == ["simulation_run_id"]]
    persona_indexes = [i for i in provenance_table.indexes if [col.name for col in i.columns] == ["persona_id"]]
    subject_indexes = [i for i in provenance_table.indexes if [col.name for col in i.columns] == ["subject_type", "subject_id"]]
    key_indexes = [i for i in provenance_table.indexes if [col.name for col in i.columns] == ["stable_content_key"]]

    run_col = provenance_table.c.get("simulation_run_id")
    persona_col = provenance_table.c.get("persona_id")
    type_col = provenance_table.c.get("subject_type")
    id_col = provenance_table.c.get("subject_id")
    key_col = provenance_table.c.get("stable_content_key")

    run_fks = [fk for c in provenance_table.columns for fk in c.foreign_keys if c.name == "simulation_run_id"]
    persona_fks = [fk for c in provenance_table.columns for fk in c.foreign_keys if c.name == "persona_id"]

    provenance_info = {
        "exists": True,
        "constraint_count": len(prov_constraints),
        "constraint_name": prov_constraints[0].name if prov_constraints else None,
        "constraint_columns": [col.name for col in prov_constraints[0].columns] if prov_constraints else None,

        "run_index_count": len(run_indexes),
        "run_index_name": run_indexes[0].name if run_indexes else None,
        "run_index_unique": run_indexes[0].unique if run_indexes else None,

        "persona_index_count": len(persona_indexes),
        "persona_index_name": persona_indexes[0].name if persona_indexes else None,
        "persona_index_unique": persona_indexes[0].unique if persona_indexes else None,

        "subject_index_count": len(subject_indexes),
        "subject_index_name": subject_indexes[0].name if subject_indexes else None,
        "subject_index_unique": subject_indexes[0].unique if subject_indexes else None,

        "key_index_count": len(key_indexes),
        "key_index_name": key_indexes[0].name if key_indexes else None,
        "key_index_unique": key_indexes[0].unique if key_indexes else None,

        "run_col_type": type(run_col.type).__name__ if run_col is not None else None,
        "run_col_nullable": run_col.nullable if run_col is not None else None,
        "run_fk_count": len(run_fks),
        "run_fk_target": run_fks[0].target_fullname if run_fks else None,
        "run_fk_ondelete": run_fks[0].ondelete if run_fks else None,

        "persona_col_type": type(persona_col.type).__name__ if persona_col is not None else None,
        "persona_col_nullable": persona_col.nullable if persona_col is not None else None,
        "persona_fk_count": len(persona_fks),
        "persona_fk_target": persona_fks[0].target_fullname if persona_fks else None,
        "persona_fk_ondelete": persona_fks[0].ondelete if persona_fks else None,

        "type_col_type": type(type_col.type).__name__ if type_col is not None else None,
        "type_col_length": getattr(type_col.type, "length", None) if type_col is not None else None,
        "type_col_nullable": type_col.nullable if type_col is not None else None,

        "id_col_type": type(id_col.type).__name__ if id_col is not None else None,
        "id_col_nullable": id_col.nullable if id_col is not None else None,

        "key_col_type": type(key_col.type).__name__ if key_col is not None else None,
        "key_col_length": getattr(key_col.type, "length", None) if key_col is not None else None,
        "key_col_nullable": key_col.nullable if key_col is not None else None,
        "key_col_unique": getattr(key_col, "unique", None) if key_col is not None else None,
    }
else:
    provenance_info = {"exists": False}

data["provenance_info"] = provenance_info

ledger_table = target_metadata.tables.get("usage_ledger")
if ledger_table is not None:
    model_call_col = ledger_table.c.get("model_call_id")
    
    call_indexes = [i for i in ledger_table.indexes if [col.name for col in i.columns] == ["model_call_id"]]
    
    ledger_info = {
        "exists": True,
        "call_col_type": type(model_call_col.type).__name__ if model_call_col is not None else None,
        "call_col_length": getattr(model_call_col.type, "length", None) if model_call_col is not None else None,
        "call_col_nullable": model_call_col.nullable if model_call_col is not None else None,
        
        "call_index_count": len(call_indexes),
        "call_index_name": call_indexes[0].name if call_indexes else None,
        "call_index_columns": [col.name for col in call_indexes[0].columns] if call_indexes else None,
        "call_index_unique": call_indexes[0].unique if call_indexes else None,
    }
else:
    ledger_info = {"exists": False}

data["ledger_info"] = ledger_info


print(json.dumps(data))
""", encoding="utf-8")

        cmd = [sys.executable, test_script.as_posix()]
        result = subprocess.run(cmd, cwd=owned_path.as_posix(), env=env, capture_output=True, text=True, timeout=10)

        assert result.returncode == 0, f"Child process failed: {result.stderr}\n\nSTDOUT:\n{result.stdout}"

        lines = result.stdout.strip().splitlines()
        json_line = lines[-1]

        data = json.loads(json_line)

        assert data["metadata_is_base"] is True
        assert "synthetic_personas" in data["tables"]
        assert "synthetic_content_provenance" in data["tables"]
        assert data["tables"].count("synthetic_personas") == 1
        assert data["tables"].count("synthetic_content_provenance") == 1
        assert len(data["forbidden_found"]) == 0
        assert data["socket_attempts"] == 0
        assert pathlib.Path(data["cwd"]).resolve() == owned_path

        assert data["cost_actual_info"]["exists"] is True
        assert data["cost_actual_info"]["type"] == "BigInteger"
        assert data["cost_actual_info"]["nullable"] is False
        assert data["cost_actual_info"]["default"] == 0
        assert data["cost_actual_info"]["server_default"] is None

        assert data["proof_ids_info"]["exists"] is True
        assert data["proof_ids_info"]["is_sqlalchemy_json"] is True
        assert data["proof_ids_info"]["nullable"] is True
        assert data["proof_ids_info"]["has_default"] is True
        assert data["proof_ids_info"]["is_callable_default"] is True
        assert data["proof_ids_info"]["first_default"] == []
        assert data["proof_ids_info"]["second_default"] == []
        assert data["proof_ids_info"]["first_is_not_second"] is True
        assert data["proof_ids_info"]["has_server_default"] is True
        assert data["proof_ids_info"]["server_default"] == "[]"

        assert data["model_call_ids_info"]["exists"] is True
        assert data["model_call_ids_info"]["is_sqlalchemy_json"] is True
        assert data["model_call_ids_info"]["nullable"] is True
        assert data["model_call_ids_info"]["has_default"] is True
        assert data["model_call_ids_info"]["is_callable_default"] is True
        assert data["model_call_ids_info"]["first_default"] == []
        assert data["model_call_ids_info"]["second_default"] == []
        assert data["model_call_ids_info"]["first_is_not_second"] is True
        assert data["model_call_ids_info"]["has_server_default"] is True
        assert data["model_call_ids_info"]["server_default"] == "[]"

        assert data["counterfactual_info"]["exists"] is True
        assert data["counterfactual_info"]["constraint_count"] == 1
        assert data["counterfactual_info"]["constraint_name"] == "uq_counterfactual_experiment_id"
        assert data["counterfactual_info"]["constraint_columns"] == ["experiment_id"]
        assert data["counterfactual_info"]["index_count"] == 1
        assert data["counterfactual_info"]["index_name"] == "ix_counterfactual_run_records_experiment_id"
        assert data["counterfactual_info"]["index_unique"] is False
        assert data["counterfactual_info"]["col_type"] == "String"
        assert data["counterfactual_info"]["col_length"] == 128
        assert data["counterfactual_info"]["col_nullable"] is False

        assert data["users_handle_info"]["exists"] is True
        assert data["users_handle_info"]["constraint_count"] == 1
        assert data["users_handle_info"]["constraint_name"] == "uq_users_handle_normalized"
        assert data["users_handle_info"]["constraint_columns"] == ["handle_normalized"]
        assert data["users_handle_info"]["index_count"] == 1
        assert data["users_handle_info"]["index_name"] == "ix_users_handle_normalized"
        assert data["users_handle_info"]["index_unique"] is False
        assert data["users_handle_info"]["col_type"] == "String"
        assert data["users_handle_info"]["col_length"] == 64
        assert data["users_handle_info"]["col_nullable"] is True
        assert data["users_handle_info"]["col_unique"] is not True

        assert data["persona_info"]["exists"] is True
        assert data["persona_info"]["source_constraint_count"] == 1
        assert data["persona_info"]["source_constraint_name"] == "uq_synthetic_persona_hash"
        assert data["persona_info"]["source_constraint_columns"] == ["source_persona_id_hash"]
        assert data["persona_info"]["source_index_count"] == 1
        assert data["persona_info"]["source_index_name"] == "ix_synthetic_personas_hash"
        assert data["persona_info"]["source_index_unique"] is False
        assert data["persona_info"]["source_col_type"] == "String"
        assert data["persona_info"]["source_col_length"] == 64
        assert data["persona_info"]["source_col_nullable"] is False
        assert data["persona_info"]["source_col_unique"] is not True

        assert data["persona_info"]["demo_constraint_count"] == 1
        assert data["persona_info"]["demo_constraint_name"] == "uq_synthetic_persona_demo_user_id"
        assert data["persona_info"]["demo_constraint_columns"] == ["demo_user_id"]
        assert data["persona_info"]["demo_index_count"] == 1
        assert data["persona_info"]["demo_index_name"] == "ix_synthetic_personas_demo_user_id"
        assert data["persona_info"]["demo_index_unique"] is False
        assert data["persona_info"]["demo_col_type"] == "Uuid"
        assert data["persona_info"]["demo_col_nullable"] is True
        assert data["persona_info"]["demo_col_unique"] is not True
        assert data["persona_info"]["demo_fk_count"] == 1
        assert data["persona_info"]["demo_fk_target"] == "users.id"
        assert data["persona_info"]["demo_fk_ondelete"] == "SET NULL"

        assert data["provenance_info"]["exists"] is True
        assert data["provenance_info"]["constraint_count"] == 1
        assert data["provenance_info"]["constraint_name"] == "uq_synthetic_content_stable_key"
        assert data["provenance_info"]["constraint_columns"] == ["stable_content_key"]

        assert data["provenance_info"]["run_index_count"] == 1
        assert data["provenance_info"]["run_index_name"] == "ix_synthetic_provenance_run_id"
        assert data["provenance_info"]["run_index_unique"] is False
        assert data["provenance_info"]["persona_index_count"] == 1
        assert data["provenance_info"]["persona_index_name"] == "ix_synthetic_provenance_persona_id"
        assert data["provenance_info"]["persona_index_unique"] is False
        assert data["provenance_info"]["subject_index_count"] == 1
        assert data["provenance_info"]["subject_index_name"] == "ix_synthetic_provenance_subject"
        assert data["provenance_info"]["subject_index_unique"] is False
        assert data["provenance_info"]["key_index_count"] == 1
        assert data["provenance_info"]["key_index_name"] == "ix_synthetic_provenance_key"
        assert data["provenance_info"]["key_index_unique"] is False

        assert data["provenance_info"]["run_col_type"] == "Uuid"
        assert data["provenance_info"]["run_col_nullable"] is True
        assert data["provenance_info"]["run_fk_count"] == 1
        assert data["provenance_info"]["run_fk_target"] == "analysis_runs.id"
        assert data["provenance_info"]["run_fk_ondelete"] == "SET NULL"

        assert data["provenance_info"]["persona_col_type"] == "Uuid"
        assert data["provenance_info"]["persona_col_nullable"] is False
        assert data["provenance_info"]["persona_fk_count"] == 1
        assert data["provenance_info"]["persona_fk_target"] == "synthetic_personas.id"
        assert data["provenance_info"]["persona_fk_ondelete"] == "CASCADE"

        assert data["provenance_info"]["type_col_type"] == "String"
        assert data["provenance_info"]["type_col_length"] == 32
        assert data["provenance_info"]["type_col_nullable"] is False

        assert data["provenance_info"]["id_col_type"] == "Uuid"
        assert data["provenance_info"]["id_col_nullable"] is False

        assert data["provenance_info"]["key_col_type"] == "String"
        assert data["provenance_info"]["key_col_length"] == 128
        assert data["provenance_info"]["key_col_nullable"] is False
        assert data["provenance_info"]["key_col_unique"] is not True

        assert data["ledger_info"]["exists"] is True
        assert data["ledger_info"]["call_col_type"] == "String"
        assert data["ledger_info"]["call_col_length"] == 64
        assert data["ledger_info"]["call_col_nullable"] is False
        assert data["ledger_info"]["call_index_count"] == 1
        assert data["ledger_info"]["call_index_name"] == "ix_usage_ledger_model_call_id"
        assert data["ledger_info"]["call_index_columns"] == ["model_call_id"]
        assert data["ledger_info"]["call_index_unique"] is True

    finally:
        td.cleanup()

        final_fp = _get_db_fingerprint(_repo_db_path)
        assert initial_fp == final_fp, "Repository DB was modified!"

        assert not owned_path.exists(), "Temp dir leaked!"


def test_isolated_alembic_check_diagnostic():
    initial_fp = _get_db_fingerprint(_repo_db_path)

    td = tempfile.TemporaryDirectory(prefix="reframe-v7-008-check-")
    owned_path = pathlib.Path(td.name).resolve()

    try:
        env = {}
        for k in ["SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "PATHEXT", "TEMP", "TMP", "LOCALAPPDATA"]:
            if k in os.environ:
                env[k] = os.environ[k]

        env.update(_ZERO_COST_ENV)
        env["PYTHONPATH"] = _repo_root.as_posix()

        db_path = owned_path / "diagnostic.db"
        assert not db_path.exists(), "DB should not exist before upgrade"

        env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path.as_posix()}"
        env["SYNC_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"

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

        temp_ini_path = owned_path / "alembic.ini"
        temp_ini_path.write_text(temp_ini_text, encoding="utf-8")

        # Upgrade head
        cmd_upgrade = [
            sys.executable, "-m", "alembic",
            "-c", temp_ini_path.as_posix(),
            "upgrade", "head"
        ]
        res_up = subprocess.run(cmd_upgrade, cwd=owned_path.as_posix(), env=env, capture_output=True, text=True, timeout=60)
        assert res_up.returncode == 0, f"Upgrade head failed: {res_up.stderr}"

        # Alembic check
        cmd_check = [
            sys.executable, "-m", "alembic",
            "-c", temp_ini_path.as_posix(),
            "check"
        ]
        res_check = subprocess.run(cmd_check, cwd=owned_path.as_posix(), env=env, capture_output=True, text=True, timeout=60)

        stdout_and_err = res_check.stdout + "\n" + res_check.stderr

        if res_check.returncode == 0:
            assert "New upgrade operations detected" not in stdout_and_err, "Zero exit but operations detected"
            state = "CLEAN"
        else:
            assert "New upgrade operations detected:" in stdout_and_err, "Non-zero exit but no upgrade operations detected"
            forbidden_errors = [
                "Traceback",
                "OperationalError",
                "connection refused",
                "no such file or directory",
                "No module named",
                "Can't locate revision",
                "failed to load"
            ]
            for err in forbidden_errors:
                assert err not in stdout_and_err, f"Forbidden error found: {err}"

            assert "alembic.autogenerate" in stdout_and_err or "modify_" in stdout_and_err or "remove_" in stdout_and_err or "add_" in stdout_and_err, "No actual autogenerate comparison evidence"
            state = "EXPECTED_DRIFT"

        print(f"=== ALEMBIC CHECK RESULT: {state} (code {res_check.returncode}) ===")
        print("=== ALEMBIC CHECK DIFF ===")
        print(stdout_and_err)

        removal_lines = [
            line for line in stdout_and_err.splitlines()
            if "remove_table" in line or "Detected removed table" in line
        ]

        print("=== DETECTED TABLE-REMOVAL LINES ===")
        for line in removal_lines:
            print(line)

        for table in ["synthetic_personas", "synthetic_content_provenance"]:
            for line in removal_lines:
                assert table not in line, f"Table {table} proposed for complete removal: {line}"

        cost_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if "cost_actual_micros" in line
        ]
        assert cost_drift_lines == [], f"cost_actual_micros drift detected: {cost_drift_lines}"

        proof_ids_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if "proof_ids" in line
        ]
        assert proof_ids_drift_lines == [], f"proof_ids drift detected: {proof_ids_drift_lines}"

        model_call_ids_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if "model_call_ids" in line
        ]
        assert model_call_ids_drift_lines == [], f"model_call_ids drift detected: {model_call_ids_drift_lines}"

        counterfactual_constraint_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if (
                "uq_counterfactual_experiment_id" in line
                or (
                    "counterfactual_run_records" in line
                    and "experiment_id" in line
                    and (
                        "remove_constraint" in line
                        or "Detected removed unique constraint" in line
                    )
                )
            )
        ]
        assert counterfactual_constraint_drift_lines == [], f"counterfactual unique constraint drift detected: {counterfactual_constraint_drift_lines}"

        users_handle_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if (
                "uq_users_handle_normalized" in line
                or "ix_users_handle_normalized" in line
                or (
                    "users" in line
                    and "handle_normalized" in line
                    and any(
                        token in line
                        for token in (
                            "remove_constraint",
                            "remove_index",
                            "add_index",
                            "Detected removed unique constraint",
                            "Detected removed index",
                            "Detected added index",
                            "Detected changed index",
                        )
                    )
                )
            )
        ]
        assert users_handle_drift_lines == [], f"users.handle_normalized drift detected: {users_handle_drift_lines}"

        persona_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if (
                any(
                    name in line
                    for name in (
                        "uq_synthetic_persona_hash",
                        "ix_synthetic_personas_hash",
                        "uq_synthetic_persona_demo_user_id",
                        "ix_synthetic_personas_demo_user_id",
                    )
                )
                or (
                    "synthetic_personas" in line
                    and (
                        "source_persona_id_hash" in line
                        or "demo_user_id" in line
                    )
                    and any(
                        token in line
                        for token in (
                            "remove_constraint",
                            "remove_index",
                            "add_index",
                            "Detected removed unique constraint",
                            "Detected removed index",
                            "Detected added index",
                            "Detected changed index",
                        )
                    )
                )
            )
        ]
        assert persona_drift_lines == [], f"synthetic_personas drift detected: {persona_drift_lines}"

        provenance_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if (
                any(
                    name in line
                    for name in (
                        "uq_synthetic_content_stable_key",
                        "ix_synthetic_provenance_run_id",
                        "ix_synthetic_provenance_persona_id",
                        "ix_synthetic_provenance_subject",
                        "ix_synthetic_provenance_key",
                        "ix_synthetic_content_provenance_simulation_run_id",
                        "ix_synthetic_content_provenance_persona_id",
                        "ix_synthetic_content_provenance_subject_type",
                        "ix_synthetic_content_provenance_subject_id",
                        "ix_synthetic_content_provenance_stable_content_key",
                    )
                )
                or (
                    "synthetic_content_provenance" in line
                    and any(
                        col_name in line
                        for col_name in (
                            "simulation_run_id",
                            "persona_id",
                            "subject_type",
                            "subject_id",
                            "stable_content_key",
                        )
                    )
                    and any(
                        token in line
                        for token in (
                            "remove_constraint",
                            "add_constraint",
                            "create_unique_constraint",
                            "remove_index",
                            "add_index",
                            "create_index",
                            "Detected removed unique constraint",
                            "Detected removed index",
                            "Detected added index",
                            "Detected changed index",
                            "index replacement",
                        )
                    )
                )
            )
        ]
        assert provenance_drift_lines == [], f"synthetic_content_provenance drift detected: {provenance_drift_lines}"

        ledger_drift_lines = [
            line
            for line in stdout_and_err.splitlines()
            if (
                "ix_usage_ledger_model_call_id" in line
                or (
                    "usage_ledger" in line
                    and "model_call_id" in line
                    and any(
                        token in line
                        for token in (
                            "remove_index",
                            "add_index",
                            "create_index",
                            "Detected removed index",
                            "Detected added index",
                            "Detected changed index",
                            "index replacement",
                        )
                    )
                )
            )
        ]
        assert ledger_drift_lines == [], f"usage_ledger drift detected: {ledger_drift_lines}"

    finally:
        td.cleanup()

        final_fp = _get_db_fingerprint(_repo_db_path)
        assert initial_fp == final_fp, "Repository DB was modified!"

        assert not owned_path.exists(), "Temp dir leaked!"
