import os
import uuid
import pytest
import sqlite3
import datetime
import sqlalchemy as sa
from sqlalchemy.event import listens_for
from sqlalchemy import create_engine, inspect, text

from alembic.config import Config
from alembic import command

import pathlib
_repo_root = pathlib.Path(__file__).parent.parent.parent.resolve()
_ini_path = _repo_root / "alembic.ini"
_migrations_dir = _repo_root / "db" / "postgres" / "migrations"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    sync_url = f"sqlite:///{db_path.as_posix()}"
    async_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    
    monkeypatch.setenv("DATABASE_URL", async_url)
    monkeypatch.setenv("SYNC_DATABASE_URL", sync_url)
    
    from src.reframe.shared.config import settings
    monkeypatch.setattr(settings, "DATABASE_URL", async_url)
    monkeypatch.setattr(settings, "SYNC_DATABASE_URL", sync_url)
    
    engine = create_engine(sync_url)
    
    @listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
        
    yield engine, sync_url
    
    engine.dispose()


def get_alembic_config(sync_url):
    cfg = Config(str(_ini_path))
    cfg.set_main_option("script_location", str(_migrations_dir))
    cfg.set_main_option("sqlalchemy.url", sync_url)
    return cfg


def snapshot_schema(engine, table_name="analysis_run_events"):
    insp = inspect(engine)
    cols = insp.get_columns(table_name)
    pk = insp.get_pk_constraint(table_name)
    fks = insp.get_foreign_keys(table_name)
    idxs = insp.get_indexes(table_name)
    
    
    with engine.connect() as conn:
        master_rows = conn.execute(text(f"SELECT type, name, sql FROM sqlite_master WHERE tbl_name='{table_name}' ORDER BY name")).fetchall()
        master = [(r[0], r[1], r[2]) for r in master_rows]
        
    return {
        "columns": [(c["name"], str(c["type"]).upper(), c["nullable"], str(c.get("default", ""))) for c in cols],
        "pk": pk.get("constrained_columns"),
        "fks": [(fk["referred_table"], fk["constrained_columns"], fk["referred_columns"], str(fk.get("options", {}).get("ondelete", fk.get("ondelete", ""))).upper()) for fk in fks],
        "idxs": [(idx["name"], idx["column_names"], idx["unique"], idx.get("dialect_options", {}).get("sqlite_where", "")) for idx in idxs],
        "unique_constraints": insp.get_unique_constraints(table_name),
        "check_constraints": insp.get_check_constraints(table_name),
        "master": [(t, n, s) for t, n, s in master if not n.startswith("sqlite_autoindex_")],
        "triggers": [(t, n, s) for t, n, s in master if t == "trigger" and not n.startswith("sqlite_autoindex_")]
    }

def get_id_type(schema_snap):
    for c in schema_snap["columns"]:
        if c[0] == "id":
            return c[1]
    return None

def snapshot_rows(engine, table_name="analysis_run_events"):
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT id, run_id, sequence, event_type, safe_payload, created_at FROM {table_name} ORDER BY id")).fetchall()
        return [tuple(r) for r in rows]

def get_current_revision(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def setup_historical_0010(engine, sync_url):
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0010_v7_usage_ledger_unique")
    
    run_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_runs (id, run_type, work_id, edition_id, status, input_hash, config_hash, dataset_version, model_id, prompt_hash, proof_schema_version, cost_reserved_micros, cost_actual_micros, created_at)
            VALUES (:id, 'REFRAME', 'w1', 'e1', 'QUEUED', 'ih', 'ch', 'dv', 'm1', 'ph', '1.0.0', 0, 0, '2026-01-01 00:00:00')
        """), {"id": run_id})
    return run_id


def check_fk(engine):
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA foreign_key_check('analysis_run_events')")).fetchall()
        return res


def test_a_historical_upgrade_with_populated_rows(isolated_db):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (id, run_id, sequence, event_type, safe_payload, created_at)
            VALUES (7, :run_id, 1, 'type1', '{}', '2026-01-01'), (42, :run_id, 2, 'type2', '{}', '2026-01-02')
        """), {"run_id": run_id})
        
    pre_snap = snapshot_schema(engine)
    assert get_id_type(pre_snap) == "BIGINT"
    pre_rows = snapshot_rows(engine)
    assert len(pre_rows) == 2
    
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    post_snap = snapshot_schema(engine)
    assert get_id_type(post_snap) == "INTEGER"
    
    pre_snap_stripped = {**pre_snap}
    pre_snap_stripped["columns"] = [(c[0], "INTEGER" if c[0] == "id" else c[1], c[2], c[3]) for c in pre_snap["columns"]]
    
    post_snap_stripped = {**post_snap}
    
    # Normalize DDL strings for id type difference and quotes
    def normalize_ddl(master_list, is_pre):
        return [(t, n, s.replace("id BIGINT NOT NULL", "id INTEGER NOT NULL").replace('"', '') if is_pre and s else s.replace('"', '') if s else s) for t, n, s in master_list]
        
    pre_snap_stripped["master"] = normalize_ddl(pre_snap_stripped["master"], True)
    post_snap_stripped["master"] = normalize_ddl(post_snap_stripped["master"], False)
    
    assert pre_snap_stripped == post_snap_stripped
    
    post_rows = snapshot_rows(engine)
    assert post_rows == pre_rows
    
    assert get_current_revision(engine) == "0011_v7_analysis_run_events_sqlite_pk"
    assert check_fk(engine) == []


def test_b_implicit_id_continuation(isolated_db):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (id, run_id, sequence, event_type, safe_payload, created_at)
            VALUES (7, :run_id, 1, 'type1', '{}', '2026-01-01'), (42, :run_id, 2, 'type2', '{}', '2026-01-02')
        """), {"run_id": run_id})
        
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (run_id, sequence, event_type, safe_payload, created_at)
            VALUES (:run_id, 3, 'type3', '{}', '2026-01-03'), (:run_id, 4, 'type4', '{}', '2026-01-04')
        """), {"run_id": run_id})
        
    rows = snapshot_rows(engine)
    ids = [r[0] for r in rows]
    assert ids == [7, 42, 43, 44]


def test_c_idempotent_head_execution(isolated_db):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    snap1 = snapshot_schema(engine)
    rows1 = snapshot_rows(engine)
    
    command.upgrade(cfg, "head")
    
    snap2 = snapshot_schema(engine)
    rows2 = snapshot_rows(engine)
    
    assert snap1 == snap2
    assert rows1 == rows2


def test_d_already_correct_integer_noop(isolated_db):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    snap1 = snapshot_schema(engine)
    rows1 = snapshot_rows(engine)
    
    command.stamp(cfg, "0010_v7_usage_ledger_unique")
    assert get_current_revision(engine) == "0010_v7_usage_ledger_unique"
    
    command.upgrade(cfg, "head")
    
    snap2 = snapshot_schema(engine)
    rows2 = snapshot_rows(engine)
    
    assert snap1 == snap2
    assert rows1 == rows2
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(cfg)
    assert get_current_revision(engine) == script.get_current_head()


def test_e_fk_cascade(isolated_db):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (id, run_id, sequence, event_type, safe_payload, created_at)
            VALUES (7, :run_id, 1, 'type1', '{}', '2026-01-01')
        """), {"run_id": run_id})
        
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    with engine.connect() as conn:
        fk_on = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk_on == 1
        
        conn.execute(text("DELETE FROM analysis_runs WHERE id = :run_id"), {"run_id": run_id})
        conn.commit()
        
    rows = snapshot_rows(engine)
    assert len(rows) == 0
    assert check_fk(engine) == []


def test_f_empty_historical_table(isolated_db):
    engine, sync_url = isolated_db
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0010_v7_usage_ledger_unique")
    
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    snap = snapshot_schema(engine)
    assert get_id_type(snap) == "INTEGER"
    
    run_id = uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_runs (id, run_type, work_id, edition_id, status, input_hash, config_hash, dataset_version, model_id, prompt_hash, proof_schema_version, cost_reserved_micros, cost_actual_micros, created_at)
            VALUES (:id, 'REFRAME', 'w1', 'e1', 'QUEUED', 'ih', 'ch', 'dv', 'm1', 'ph', '1.0.0', 0, 0, '2026-01-01 00:00:00')
        """), {"id": run_id})
        
        conn.execute(text("""
            INSERT INTO analysis_run_events (run_id, sequence, event_type, safe_payload, created_at)
            VALUES (:run_id, 1, 'type1', '{}', '2026-01-01')
        """), {"run_id": run_id})
        
    rows = snapshot_rows(engine)
    assert len(rows) == 1
    assert rows[0][0] == 1


@pytest.mark.parametrize("scenario", ["unexpected_index", "unexpected_column", "malformed_sequence_type", "malformed_run_id_type", "malformed_event_type", "malformed_event_type_len", "malformed_safe_payload", "malformed_created_at"])
def test_gh_fail_closed(isolated_db, scenario):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (id, run_id, sequence, event_type, safe_payload, created_at)
            VALUES (7, :run_id, 1, 'type1', '{}', '2026-01-01')
        """), {"run_id": run_id})
        
        if scenario == "unexpected_index":
            conn.execute(text("CREATE INDEX ix_analysis_run_events_sequence_unexpected ON analysis_run_events (sequence)"))
        elif scenario == "unexpected_column":
            conn.execute(text("ALTER TABLE analysis_run_events ADD COLUMN unexpected_probe_column INTEGER"))
        elif scenario == "malformed_sequence_type":
            # Recreate table with wrong type to test preflight
            conn.execute(text("DROP INDEX ix_analysis_run_events_run_id"))
            conn.execute(text("ALTER TABLE analysis_run_events RENAME TO analysis_run_events_old"))
            conn.execute(text("""
                CREATE TABLE analysis_run_events (
                    id BIGINT NOT NULL,
                    run_id CHAR(32) NOT NULL,
                    sequence VARCHAR(99) NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    safe_payload JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO analysis_run_events SELECT * FROM analysis_run_events_old"))
            conn.execute(text("CREATE INDEX ix_analysis_run_events_run_id ON analysis_run_events (run_id)"))
            conn.execute(text("DROP TABLE analysis_run_events_old"))
        elif scenario == "malformed_run_id_type":
            conn.execute(text("DROP INDEX ix_analysis_run_events_run_id"))
            conn.execute(text("ALTER TABLE analysis_run_events RENAME TO analysis_run_events_old"))
            conn.execute(text("""
                CREATE TABLE analysis_run_events (
                    id BIGINT NOT NULL,
                    run_id VARCHAR(255) NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    safe_payload JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO analysis_run_events SELECT * FROM analysis_run_events_old"))
            conn.execute(text("CREATE INDEX ix_analysis_run_events_run_id ON analysis_run_events (run_id)"))
            conn.execute(text("DROP TABLE analysis_run_events_old"))
        elif scenario == "malformed_event_type":
            conn.execute(text("DROP INDEX ix_analysis_run_events_run_id"))
            conn.execute(text("ALTER TABLE analysis_run_events RENAME TO analysis_run_events_old"))
            conn.execute(text("""
                CREATE TABLE analysis_run_events (
                    id BIGINT NOT NULL,
                    run_id CHAR(32) NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    safe_payload JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO analysis_run_events SELECT * FROM analysis_run_events_old"))
            conn.execute(text("CREATE INDEX ix_analysis_run_events_run_id ON analysis_run_events (run_id)"))
            conn.execute(text("DROP TABLE analysis_run_events_old"))
        elif scenario == "malformed_event_type_len":
            conn.execute(text("DROP INDEX ix_analysis_run_events_run_id"))
            conn.execute(text("ALTER TABLE analysis_run_events RENAME TO analysis_run_events_old"))
            conn.execute(text("""
                CREATE TABLE analysis_run_events (
                    id BIGINT NOT NULL,
                    run_id CHAR(32) NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type VARCHAR(255) NOT NULL,
                    safe_payload JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO analysis_run_events SELECT * FROM analysis_run_events_old"))
            conn.execute(text("CREATE INDEX ix_analysis_run_events_run_id ON analysis_run_events (run_id)"))
            conn.execute(text("DROP TABLE analysis_run_events_old"))
        elif scenario == "malformed_safe_payload":
            conn.execute(text("DROP INDEX ix_analysis_run_events_run_id"))
            conn.execute(text("ALTER TABLE analysis_run_events RENAME TO analysis_run_events_old"))
            conn.execute(text("""
                CREATE TABLE analysis_run_events (
                    id BIGINT NOT NULL,
                    run_id CHAR(32) NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    safe_payload TEXT NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO analysis_run_events SELECT * FROM analysis_run_events_old"))
            conn.execute(text("CREATE INDEX ix_analysis_run_events_run_id ON analysis_run_events (run_id)"))
            conn.execute(text("DROP TABLE analysis_run_events_old"))
        elif scenario == "malformed_created_at":
            conn.execute(text("DROP INDEX ix_analysis_run_events_run_id"))
            conn.execute(text("ALTER TABLE analysis_run_events RENAME TO analysis_run_events_old"))
            conn.execute(text("""
                CREATE TABLE analysis_run_events (
                    id BIGINT NOT NULL,
                    run_id CHAR(32) NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type VARCHAR(64) NOT NULL,
                    safe_payload JSON NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (id),
                    FOREIGN KEY(run_id) REFERENCES analysis_runs (id) ON DELETE CASCADE
                )
            """))
            conn.execute(text("INSERT INTO analysis_run_events SELECT * FROM analysis_run_events_old"))
            conn.execute(text("CREATE INDEX ix_analysis_run_events_run_id ON analysis_run_events (run_id)"))
            conn.execute(text("DROP TABLE analysis_run_events_old"))
            
    pre_snap = snapshot_schema(engine)
    pre_rows = snapshot_rows(engine)
    
    cfg = get_alembic_config(sync_url)
    with pytest.raises(RuntimeError):
        command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
        
    assert get_current_revision(engine) == "0010_v7_usage_ledger_unique"
    
    post_snap = snapshot_schema(engine)
    post_rows = snapshot_rows(engine)
    
    assert pre_snap == post_snap
    assert pre_rows == post_rows


def test_i_downgrade_reupgrade_round_trip(isolated_db):
    engine, sync_url = isolated_db
    run_id = setup_historical_0010(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (id, run_id, sequence, event_type, safe_payload, created_at)
            VALUES (7, :run_id, 1, 'type1', '{}', '2026-01-01')
        """), {"run_id": run_id})
        
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    post_snap = snapshot_schema(engine)
    post_rows = snapshot_rows(engine)
    assert get_id_type(post_snap) == "INTEGER"
    
    command.downgrade(cfg, "0010_v7_usage_ledger_unique")
    
    down_snap = snapshot_schema(engine)
    down_rows = snapshot_rows(engine)
    assert get_id_type(down_snap) == "BIGINT"
    assert post_rows == down_rows
    assert get_current_revision(engine) == "0010_v7_usage_ledger_unique"
    
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    up_snap = snapshot_schema(engine)
    up_rows = snapshot_rows(engine)
    assert get_id_type(up_snap) == "INTEGER"
    assert up_rows == down_rows
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO analysis_run_events (run_id, sequence, event_type, safe_payload, created_at)
            VALUES (:run_id, 2, 'type2', '{}', '2026-01-02')
        """), {"run_id": run_id})
        
    final_rows = snapshot_rows(engine)
    assert final_rows[-1][0] == 8


def test_j_no_metadata_drift_at_head(isolated_db):
    engine, sync_url = isolated_db
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "head")
    
    # command.check(cfg) raises AutogenerateDiffsDetected if drift exists.
    # We expect a completely clean schema state now.
    command.check(cfg)


class MockPostgresInspector:
    def __init__(self, cols, pks, fks, idxs, unique, checks):
        self.cols = cols
        self.pks = pks
        self.fks = fks
        self.idxs = idxs
        self.unique = unique
        self.checks = checks
        
    def get_table_names(self):
        return ["analysis_run_events", "analysis_runs"]
        
    def get_columns(self, table_name):
        return self.cols
        
    def get_pk_constraint(self, table_name):
        return self.pks
        
    def get_foreign_keys(self, table_name):
        return self.fks
        
    def get_indexes(self, table_name):
        return self.idxs
        
    def get_unique_constraints(self, table_name):
        return self.unique
        
    def get_check_constraints(self, table_name):
        return self.checks


def _mock_pg_schema(id_autoincrement=False, id_identity=None, run_id_type="UUID", sequence_type="INTEGER", event_type_type="VARCHAR(64)", safe_payload_type="JSON", created_at_type="TIMESTAMP WITH TIME ZONE"):
    
    evt_type_obj = sa.String(length=64)
    if event_type_type == "TEXT":
        evt_type_obj = sa.Text()
    elif event_type_type == "VARCHAR(255)":
        evt_type_obj = sa.String(length=255)
        
    created_at_obj = sa.dialects.postgresql.TIMESTAMP(timezone=True)
    if created_at_type == "TIMESTAMP WITHOUT TIME ZONE":
        created_at_obj = sa.dialects.postgresql.TIMESTAMP(timezone=False)
    elif created_at_type == "DATETIME":
        created_at_obj = sa.DateTime(timezone=False)
    
    return [
        {"name": "id", "type": sa.BigInteger(), "nullable": False, "autoincrement": id_autoincrement, "identity": id_identity},
        {"name": "run_id", "type": sa.String() if run_id_type != "UUID" else sa.dialects.postgresql.UUID(), "nullable": False},
        {"name": "sequence", "type": sa.String() if sequence_type != "INTEGER" else sa.Integer(), "nullable": False},
        {"name": "event_type", "type": evt_type_obj, "nullable": False},
        {"name": "safe_payload", "type": sa.String() if safe_payload_type != "JSON" else sa.JSON(), "nullable": False},
        {"name": "created_at", "type": created_at_obj, "nullable": False}
    ]

def _mock_pg_pks():
    return {"constrained_columns": ["id"]}

def _mock_pg_fks():
    return [{"referred_table": "analysis_runs", "constrained_columns": ["run_id"], "referred_columns": ["id"], "options": {"ondelete": "CASCADE"}}]

def _mock_pg_idxs():
    return [{"name": "ix_analysis_run_events_run_id", "column_names": ["run_id"], "unique": False}]


@pytest.fixture
def mock_pg_bind(monkeypatch):
    from unittest.mock import MagicMock
    import importlib.util
    import sys
    
    # Load the migration module directly
    spec = importlib.util.spec_from_file_location("migration_0011", str(_migrations_dir / "versions" / "0011_v7_analysis_run_events_sqlite_pk.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migration_0011"] = mod
    spec.loader.exec_module(mod)
    
    def _create_bind(schema_cols, sequence_owned=True, has_triggers=False):
        bind = MagicMock()
        bind.dialect.name = "postgresql"
        
        executed_sqls = []
        bind.executed_sqls = executed_sqls
        
        def mock_execute(stmt):
            res = MagicMock()
            sql = str(stmt).upper()
            executed_sqls.append(sql)
            if "PG_GET_SERIAL_SEQUENCE" in sql:
                res.scalar.return_value = "public.analysis_run_events_id_seq" if sequence_owned else None
            elif "INFORMATION_SCHEMA.TRIGGERS" in sql:
                res.fetchall.return_value = [("some_trigger",)] if has_triggers else []
            return res
            
        bind.execute.side_effect = mock_execute
        
        insp = MockPostgresInspector(schema_cols, _mock_pg_pks(), _mock_pg_fks(), _mock_pg_idxs(), [], [])
        monkeypatch.setattr(mod.sa, "inspect", lambda b: insp)
        monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
        monkeypatch.setattr(mod.op, "batch_alter_table", MagicMock())
        monkeypatch.setattr(mod.op, "execute", MagicMock())
        monkeypatch.setattr(mod.op, "create_table", MagicMock())
        monkeypatch.setattr(mod.op, "drop_table", MagicMock())
        monkeypatch.setattr(mod.op, "create_index", MagicMock())
        monkeypatch.setattr(mod.op, "drop_index", MagicMock())
        monkeypatch.setattr(mod.op, "alter_column", MagicMock())
        
        return mod, bind
        
    return _create_bind

def _assert_no_ddl(mod, bind):
    mod.op.batch_alter_table.assert_not_called()
    mod.op.execute.assert_not_called()
    mod.op.create_table.assert_not_called()
    mod.op.drop_table.assert_not_called()
    mod.op.create_index.assert_not_called()
    mod.op.drop_index.assert_not_called()
    mod.op.alter_column.assert_not_called()
    for sql in bind.executed_sqls:
        assert sql.startswith("SELECT"), f"Unexpected non-SELECT query: {sql}"

def test_mock_pg_autoincrement_no_identity_no_seq_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_autoincrement=True), sequence_owned=False)
    with pytest.raises(RuntimeError, match="plain BIGINT without identity/sequence"):
        mod.upgrade()

def test_mock_pg_autoincrement_no_identity_owned_seq_accepted(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_autoincrement=True), sequence_owned=True)
    mod.upgrade()
    assert any("PG_GET_SERIAL_SEQUENCE" in sql for sql in bind.executed_sqls)
    mod.downgrade()
    _assert_no_ddl(mod, bind)

def test_mock_pg_valid_identity_always_true(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity={"always": True}), sequence_owned=False)
    mod.upgrade()
    mod.downgrade()
    _assert_no_ddl(mod, bind)

def test_mock_pg_valid_identity_always_false(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity={"always": False}), sequence_owned=False)
    mod.upgrade()
    mod.downgrade()
    _assert_no_ddl(mod, bind)

def test_mock_pg_malformed_identity(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity={"always": "yes"}), sequence_owned=False)
    with pytest.raises(RuntimeError, match="Malformed identity metadata"):
        mod.upgrade()
        
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity={}), sequence_owned=False)
    with pytest.raises(RuntimeError, match="Malformed identity metadata"):
        mod.upgrade()
        
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity="always"), sequence_owned=False)
    with pytest.raises(RuntimeError, match="Malformed identity metadata"):
        mod.upgrade()

def test_mock_pg_plain_bigint_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_autoincrement=False), sequence_owned=False)
    with pytest.raises(RuntimeError, match="plain BIGINT without identity/sequence"):
        mod.upgrade()

def test_mock_pg_timezone_true_accepted(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(created_at_type="TIMESTAMP WITH TIME ZONE"), sequence_owned=True)
    mod.upgrade()
    mod.downgrade()
    _assert_no_ddl(mod, bind)
    
def test_mock_pg_timezone_false_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(created_at_type="TIMESTAMP WITHOUT TIME ZONE"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="missing timezone=True"):
        mod.upgrade()
        
def test_mock_pg_generic_datetime_false_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(created_at_type="DATETIME"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="missing timezone=True"):
        mod.upgrade()

def test_mock_pg_invalid_sequence_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(sequence_type="TEXT"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column sequence has unexpected type"):
        mod.upgrade()

def test_mock_pg_invalid_event_type_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(event_type_type="TEXT"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column event_type has unexpected type"):
        mod.upgrade()
        
def test_mock_pg_invalid_event_type_len_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(event_type_type="VARCHAR(255)"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column event_type has unexpected type"):
        mod.upgrade()
        
def test_mock_pg_invalid_safe_payload_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(safe_payload_type="TEXT"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column safe_payload has unexpected type"):
        mod.upgrade()

def test_mock_pg_invalid_run_id_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(run_id_type="VARCHAR"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column run_id has unexpected type"):
        mod.upgrade()
