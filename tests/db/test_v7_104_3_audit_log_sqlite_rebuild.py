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


def snapshot_schema(engine, table_name="audit_log"):
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
        "idxs": [(idx["name"], idx["column_names"], idx["unique"], str(idx.get("dialect_options", {}).get("sqlite_where", ""))) for idx in idxs],
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

def snapshot_rows(engine, table_name="audit_log"):
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM {table_name} ORDER BY id")).fetchall()
        return [tuple(r) for r in rows]

def get_current_revision(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def setup_historical_0011(engine, sync_url):
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    return None


def check_fk(engine):
    with engine.connect() as conn:
        res = conn.execute(text("PRAGMA foreign_key_check('audit_log')")).fetchall()
        return res


def test_a_historical_upgrade_with_populated_rows(isolated_db):
    engine, sync_url = isolated_db
    setup_historical_0011(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (id, actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES 
            (7, 'USER', 'u1', 'C', 'RES', 's1', NULL, 'ah', '{}', '2026-01-01'), 
            (42, 'SYS', 'u2', 'U', 'RES', 's2', 'bh', 'ah2', '{}', '2026-01-02')
        """))
        
    pre_snap = snapshot_schema(engine)
    assert get_id_type(pre_snap) == "BIGINT"
    pre_rows = snapshot_rows(engine)
    assert len(pre_rows) == 2
    
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    post_snap = snapshot_schema(engine)
    assert get_id_type(post_snap) == "INTEGER"
    
    pre_snap_stripped = {**pre_snap}
    pre_snap_stripped["columns"] = [(c[0], "INTEGER" if c[0] == "id" else c[1], c[2], c[3]) for c in pre_snap["columns"]]
    
    post_snap_stripped = {**post_snap}
    
    def normalize_ddl(master_list, is_pre):
        return [(t, n, s.replace("id BIGINT NOT NULL", "id INTEGER NOT NULL").replace('"', '') if is_pre and s else s.replace('"', '') if s else s) for t, n, s in master_list]
        
    pre_snap_stripped["master"] = normalize_ddl(pre_snap_stripped["master"], True)
    post_snap_stripped["master"] = normalize_ddl(post_snap_stripped["master"], False)
    
    assert pre_snap_stripped == post_snap_stripped
    
    post_rows = snapshot_rows(engine)
    assert post_rows == pre_rows
    
    assert get_current_revision(engine) == "0012_v7_audit_log_sqlite_pk"
    assert check_fk(engine) == []


def test_b_implicit_id_continuation(isolated_db):
    engine, sync_url = isolated_db
    setup_historical_0011(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (id, actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES 
            (7, 'USER', 'u1', 'C', 'RES', 's1', NULL, 'ah', '{}', '2026-01-01'), 
            (42, 'SYS', 'u2', 'U', 'RES', 's2', 'bh', 'ah2', '{}', '2026-01-02')
        """))
        
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES 
            ('USER', 'u3', 'C', 'RES', 's3', NULL, 'ah', '{}', '2026-01-03'), 
            ('SYS', 'u4', 'U', 'RES', 's4', 'bh', 'ah2', '{}', '2026-01-04')
        """))
        
    rows = snapshot_rows(engine)
    ids = [r[0] for r in rows]
    assert ids == [7, 42, 43, 44]


def test_c_idempotent_head_execution(isolated_db):
    engine, sync_url = isolated_db
    setup_historical_0011(engine, sync_url)
    
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    snap1 = snapshot_schema(engine)
    rows1 = snapshot_rows(engine)
    
    command.upgrade(cfg, "head")
    
    snap2 = snapshot_schema(engine)
    rows2 = snapshot_rows(engine)
    
    assert snap1 == snap2
    assert rows1 == rows2


def test_d_already_correct_integer_noop(isolated_db):
    engine, sync_url = isolated_db
    setup_historical_0011(engine, sync_url)
    
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    snap1 = snapshot_schema(engine)
    rows1 = snapshot_rows(engine)
    
    command.stamp(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    assert get_current_revision(engine) == "0011_v7_analysis_run_events_sqlite_pk"
    
    command.upgrade(cfg, "head")
    
    snap2 = snapshot_schema(engine)
    rows2 = snapshot_rows(engine)
    
    assert snap1 == snap2
    assert rows1 == rows2
    assert get_current_revision(engine) == "0012_v7_audit_log_sqlite_pk"


def test_f_empty_historical_table(isolated_db):
    engine, sync_url = isolated_db
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    snap = snapshot_schema(engine)
    assert get_id_type(snap) == "INTEGER"
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES ('USER', 'u3', 'C', 'RES', 's3', NULL, 'ah', '{}', '2026-01-03')
        """))
        
    rows = snapshot_rows(engine)
    assert len(rows) == 1
    assert rows[0][0] == 1


@pytest.mark.parametrize("scenario", [
    "unexpected_index", "unexpected_column", "missing_column", "missing_action_column",
    "missing_idx_actor", "missing_idx_subject", "missing_idx_created",
    "index_wrong_col", "unique_index", "partial_index",
    "malformed_actor_type", "malformed_actor_id", "malformed_action", 
    "malformed_subject_type", "malformed_subject_id",
    "malformed_before_hash", "malformed_after_hash", 
    "malformed_safe_metadata", "malformed_created_at",
    "wrong_pk", "unexpected_fk", "unique_constraint", "check_constraint",
    "trigger", "required_column_nullable", "required_column_nullable_action",
    "before_hash_not_nullable", "after_hash_not_nullable", "non_id_default", "id_default"
])
def test_gh_fail_closed(isolated_db, scenario):
    engine, sync_url = isolated_db
    setup_historical_0011(engine, sync_url)
    
    with engine.begin() as conn:
        bhash = "'sentinel_b'" if scenario in ("before_hash_not_nullable", "malformed_before_hash") else "NULL"
        ahash = "'sentinel_a'" if scenario in ("after_hash_not_nullable", "malformed_after_hash") else "'ah'"
        conn.execute(text(f"""
            INSERT INTO audit_log (id, actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES (7, 'USER', 'u1', 'C', 'RES', 's1', {bhash}, {ahash}, '{{}}', '2026-01-01')
        """))
        
        if scenario == "unexpected_index":
            conn.execute(text("CREATE INDEX ix_audit_log_extra ON audit_log (action)"))
        elif scenario == "unexpected_column":
            conn.execute(text("ALTER TABLE audit_log ADD COLUMN unexpected_probe_column INTEGER"))
        elif scenario in ("missing_column", "missing_action_column"):
            conn.execute(text("DROP INDEX ix_audit_log_actor_id"))
            conn.execute(text("DROP INDEX ix_audit_log_subject_id"))
            conn.execute(text("DROP INDEX ix_audit_log_created_at"))
            conn.execute(text("ALTER TABLE audit_log RENAME TO audit_log_old"))
            conn.execute(text("""
                CREATE TABLE audit_log (
                    id BIGINT NOT NULL,
                    actor_type VARCHAR(32) NOT NULL,
                    actor_id VARCHAR(64) NOT NULL,
                    subject_type VARCHAR(64) NOT NULL,
                    subject_id VARCHAR(64) NOT NULL,
                    before_hash VARCHAR(64) NULL,
                    after_hash VARCHAR(64) NULL,
                    safe_metadata JSON NOT NULL,
                    created_at DATETIME NOT NULL,
                    PRIMARY KEY (id)
                )
            """))
            conn.execute(text("INSERT INTO audit_log SELECT id, actor_type, actor_id, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at FROM audit_log_old"))
            conn.execute(text("CREATE INDEX ix_audit_log_actor_id ON audit_log (actor_id)"))
            conn.execute(text("CREATE INDEX ix_audit_log_subject_id ON audit_log (subject_id)"))
            conn.execute(text("CREATE INDEX ix_audit_log_created_at ON audit_log (created_at)"))
            conn.execute(text("DROP TABLE audit_log_old"))
        elif scenario == "missing_idx_actor":
            conn.execute(text("DROP INDEX ix_audit_log_actor_id"))
        elif scenario == "missing_idx_subject":
            conn.execute(text("DROP INDEX ix_audit_log_subject_id"))
        elif scenario == "missing_idx_created":
            conn.execute(text("DROP INDEX ix_audit_log_created_at"))
        elif scenario == "index_wrong_col":
            conn.execute(text("DROP INDEX ix_audit_log_actor_id"))
            conn.execute(text("CREATE INDEX ix_audit_log_actor_id ON audit_log (action)"))
        elif scenario == "unique_index":
            conn.execute(text("DROP INDEX ix_audit_log_actor_id"))
            conn.execute(text("CREATE UNIQUE INDEX ix_audit_log_actor_id ON audit_log (actor_id)"))
        elif scenario == "partial_index":
            conn.execute(text("DROP INDEX ix_audit_log_actor_id"))
            conn.execute(text("CREATE INDEX ix_audit_log_actor_id ON audit_log (actor_id) WHERE action='C'"))
        elif scenario == "trigger":
            conn.execute(text("CREATE TRIGGER mock_trigger AFTER INSERT ON audit_log BEGIN SELECT 1; END;"))
            
        elif scenario.startswith("malformed_") or scenario in [
            "wrong_pk", "unexpected_fk", "unique_constraint", "check_constraint",
            "required_column_nullable", "required_column_nullable_action",
            "before_hash_not_nullable", "after_hash_not_nullable",
            "non_id_default", "id_default"
        ]:
            # Table reconstruction for type tests
            conn.execute(text("DROP INDEX ix_audit_log_actor_id"))
            conn.execute(text("DROP INDEX ix_audit_log_subject_id"))
            conn.execute(text("DROP INDEX ix_audit_log_created_at"))
            conn.execute(text("ALTER TABLE audit_log RENAME TO audit_log_old"))
            
            # Default definition
            defs = {
                "id": "BIGINT NOT NULL",
                "actor_type": "VARCHAR(32) NOT NULL",
                "actor_id": "VARCHAR(64) NOT NULL",
                "action": "VARCHAR(64) NOT NULL",
                "subject_type": "VARCHAR(64) NOT NULL",
                "subject_id": "VARCHAR(64) NOT NULL",
                "before_hash": "VARCHAR(64) NULL",
                "after_hash": "VARCHAR(64) NULL",
                "safe_metadata": "JSON NOT NULL",
                "created_at": "DATETIME NOT NULL"
            }
            pk_def = "PRIMARY KEY (id)"
            extras = ""
            
            # Inject malformation
            if scenario == "malformed_actor_type": defs["actor_type"] = "TEXT NOT NULL"
            if scenario == "malformed_actor_id": defs["actor_id"] = "INTEGER NOT NULL"
            if scenario == "malformed_action": defs["action"] = "VARCHAR(255) NOT NULL"
            if scenario == "malformed_subject_type": defs["subject_type"] = "TEXT NOT NULL"
            if scenario == "malformed_subject_id": defs["subject_id"] = "INTEGER NOT NULL"
            if scenario == "malformed_before_hash": defs["before_hash"] = "INTEGER NULL"
            if scenario == "malformed_after_hash": defs["after_hash"] = "INTEGER NULL"
            if scenario == "malformed_safe_metadata": defs["safe_metadata"] = "TEXT NOT NULL"
            if scenario == "malformed_created_at": defs["created_at"] = "TEXT NOT NULL"
            if scenario == "wrong_pk": pk_def = "PRIMARY KEY (id, actor_id)"
            if scenario == "unexpected_fk":
                conn.execute(text("CREATE TABLE dummy_fk_target (id VARCHAR(64) PRIMARY KEY)"))
                conn.execute(text("INSERT INTO dummy_fk_target (id) VALUES ('u1')"))
                extras = ", FOREIGN KEY (actor_id) REFERENCES dummy_fk_target (id)"
            if scenario == "unique_constraint": extras = ", UNIQUE (actor_id)"
            if scenario == "check_constraint": extras = ", CHECK (id > 0)"
            if scenario in ("required_column_nullable", "required_column_nullable_actor"): defs["actor_type"] = "VARCHAR(32) NULL"
            if scenario == "required_column_nullable_action": defs["action"] = "VARCHAR(64) NULL"
            if scenario == "before_hash_not_nullable": defs["before_hash"] = "VARCHAR(64) NOT NULL"
            if scenario == "after_hash_not_nullable": defs["after_hash"] = "VARCHAR(64) NOT NULL"
            if scenario == "non_id_default": defs["action"] = "VARCHAR(64) NOT NULL DEFAULT 'C'"
            if scenario == "id_default": defs["id"] = "BIGINT NOT NULL DEFAULT 0"
            
            conn.execute(text(f"""
                CREATE TABLE audit_log (
                    id {defs['id']},
                    actor_type {defs['actor_type']},
                    actor_id {defs['actor_id']},
                    action {defs['action']},
                    subject_type {defs['subject_type']},
                    subject_id {defs['subject_id']},
                    before_hash {defs['before_hash']},
                    after_hash {defs['after_hash']},
                    safe_metadata {defs['safe_metadata']},
                    created_at {defs['created_at']},
                    {pk_def}{extras}
                )
            """))
            conn.execute(text("INSERT INTO audit_log SELECT * FROM audit_log_old"))
            conn.execute(text("CREATE INDEX ix_audit_log_actor_id ON audit_log (actor_id)"))
            conn.execute(text("CREATE INDEX ix_audit_log_subject_id ON audit_log (subject_id)"))
            conn.execute(text("CREATE INDEX ix_audit_log_created_at ON audit_log (created_at)"))
            conn.execute(text("DROP TABLE audit_log_old"))
            
    pre_snap = snapshot_schema(engine)
    pre_rows = snapshot_rows(engine)
    
    cfg = get_alembic_config(sync_url)
    with pytest.raises(RuntimeError):
        command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
        
    assert get_current_revision(engine) == "0011_v7_analysis_run_events_sqlite_pk"
    
    post_snap = snapshot_schema(engine)
    post_rows = snapshot_rows(engine)
    
    assert pre_snap == post_snap
    assert pre_rows == post_rows


def test_i_downgrade_reupgrade_round_trip(isolated_db):
    engine, sync_url = isolated_db
    setup_historical_0011(engine, sync_url)
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (id, actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES (7, 'USER', 'u1', 'C', 'RES', 's1', NULL, 'ah', '{}', '2026-01-01')
        """))
        
    cfg = get_alembic_config(sync_url)
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    post_snap = snapshot_schema(engine)
    post_rows = snapshot_rows(engine)
    assert get_id_type(post_snap) == "INTEGER"
    
    command.downgrade(cfg, "0011_v7_analysis_run_events_sqlite_pk")
    
    down_snap = snapshot_schema(engine)
    down_rows = snapshot_rows(engine)
    assert get_id_type(down_snap) == "BIGINT"
    assert post_rows == down_rows
    assert get_current_revision(engine) == "0011_v7_analysis_run_events_sqlite_pk"
    
    command.upgrade(cfg, "0012_v7_audit_log_sqlite_pk")
    
    up_snap = snapshot_schema(engine)
    up_rows = snapshot_rows(engine)
    assert get_id_type(up_snap) == "INTEGER"
    assert up_rows == down_rows
    
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO audit_log (actor_type, actor_id, action, subject_type, subject_id, before_hash, after_hash, safe_metadata, created_at)
            VALUES ('USER', 'u1', 'U', 'RES', 's1', NULL, 'ah', '{}', '2026-01-02')
        """))
        
    final_rows = snapshot_rows(engine)
    assert final_rows[-1][0] == 8


def test_j_cleanliness_and_metadata_drift(isolated_db):
    engine, sync_url = isolated_db
    cfg = get_alembic_config(sync_url)
    
    # 1. At historical 0011:
    setup_historical_0011(engine, sync_url)
    insp_0011 = inspect(engine)
    audit_cols_0011 = {c["name"]: c for c in insp_0011.get_columns("audit_log")}
    events_cols_0011 = {c["name"]: c for c in insp_0011.get_columns("analysis_run_events")}
    
    assert str(audit_cols_0011["id"]["type"]).upper() == "BIGINT"
    assert str(events_cols_0011["id"]["type"]).upper() == "INTEGER"
    
    # 2. Upgrade to 0012/head:
    command.upgrade(cfg, "head")
    
    insp_0012 = inspect(engine)
    audit_cols_0012 = {c["name"]: c for c in insp_0012.get_columns("audit_log")}
    events_cols_0012 = {c["name"]: c for c in insp_0012.get_columns("analysis_run_events")}
    
    assert str(audit_cols_0012["id"]["type"]).upper() == "INTEGER"
    assert str(events_cols_0012["id"]["type"]).upper() == "INTEGER"
    
    # Clean check without AutogenerateDiffsDetected
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
        return ["audit_log"]
        
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


def _mock_pg_schema(id_autoincrement=False, id_identity=None, actor_type_type="VARCHAR(32)", actor_id_type="VARCHAR(64)", safe_metadata_type="JSON", created_at_type="TIMESTAMP WITH TIME ZONE"):
    
    act_type_obj = sa.String(length=32)
    if actor_type_type == "TEXT":
        act_type_obj = sa.Text()
        
    act_id_obj = sa.String(length=64)
    if actor_id_type == "TEXT":
        act_id_obj = sa.Text()
        
    created_at_obj = sa.dialects.postgresql.TIMESTAMP(timezone=True)
    if created_at_type == "TIMESTAMP WITHOUT TIME ZONE":
        created_at_obj = sa.dialects.postgresql.TIMESTAMP(timezone=False)
    elif created_at_type == "DATETIME":
        created_at_obj = sa.DateTime(timezone=False)
    
    return [
        {"name": "id", "type": sa.BigInteger(), "nullable": False, "autoincrement": id_autoincrement, "identity": id_identity},
        {"name": "actor_type", "type": act_type_obj, "nullable": False},
        {"name": "actor_id", "type": act_id_obj, "nullable": False},
        {"name": "action", "type": sa.String(length=64), "nullable": False},
        {"name": "subject_type", "type": sa.String(length=64), "nullable": False},
        {"name": "subject_id", "type": sa.String(length=64), "nullable": False},
        {"name": "before_hash", "type": sa.String(length=64), "nullable": True},
        {"name": "after_hash", "type": sa.String(length=64), "nullable": True},
        {"name": "safe_metadata", "type": sa.String() if safe_metadata_type != "JSON" else sa.JSON(), "nullable": False},
        {"name": "created_at", "type": created_at_obj, "nullable": False}
    ]

def _mock_pg_pks():
    return {"constrained_columns": ["id"]}

def _mock_pg_fks():
    return []

def _mock_pg_idxs():
    return [
        {"name": "ix_audit_log_actor_id", "column_names": ["actor_id"], "unique": False},
        {"name": "ix_audit_log_subject_id", "column_names": ["subject_id"], "unique": False},
        {"name": "ix_audit_log_created_at", "column_names": ["created_at"], "unique": False}
    ]


@pytest.fixture
def mock_pg_bind(monkeypatch):
    from unittest.mock import MagicMock
    import importlib.util
    import sys
    
    spec = importlib.util.spec_from_file_location("migration_0012", str(_migrations_dir / "versions" / "0012_v7_audit_log_sqlite_pk.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migration_0012"] = mod
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
                res.scalar.return_value = "public.audit_log_id_seq" if sequence_owned else None
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

def test_mock_pg_invalid_actor_type_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(actor_type_type="TEXT"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column actor_type has unexpected type"):
        mod.upgrade()
        
def test_mock_pg_invalid_safe_payload_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(safe_metadata_type="TEXT"), sequence_owned=True)
    with pytest.raises(RuntimeError, match="Column safe_metadata has unexpected type"):
        mod.upgrade()

@pytest.mark.parametrize("scenario", [
    # Types / lengths
    "malformed_actor_type", "malformed_actor_type_len",
    "malformed_actor_id", "malformed_actor_id_len",
    "malformed_action", "malformed_action_len",
    "malformed_subject_type", "malformed_subject_type_len",
    "malformed_subject_id", "malformed_subject_id_len",
    "malformed_before_hash", "malformed_before_hash_len",
    "malformed_after_hash", "malformed_after_hash_len",
    "malformed_safe_metadata", "malformed_created_at_tz",
    # Nullability
    "required_column_nullable", "required_column_nullable_action",
    "required_column_nullable_actor_id", "required_column_nullable_subject_type",
    "required_column_nullable_subject_id", "required_column_nullable_safe_metadata",
    "required_column_nullable_created_at",
    "before_hash_not_nullable", "after_hash_not_nullable",
    # Defaults
    "unexpected_default", "non_id_default",
    # Structure
    "wrong_pk", "unexpected_fk",
    "missing_index", "extra_index", "wrong_index_column", "unique_index", "partial_index",
    "unexpected_unique_constraint", "unexpected_check_constraint", "unexpected_trigger"
])
def test_mock_pg_structural_fail_closed(mock_pg_bind, scenario, monkeypatch):
    schema = _mock_pg_schema(id_autoincrement=True)
    pks = _mock_pg_pks()
    fks = _mock_pg_fks()
    idxs = _mock_pg_idxs()
    unique = []
    checks = []
    has_triggers = False
    
    # Types / lengths
    if scenario == "malformed_actor_type": schema[1]["type"] = sa.Text()
    elif scenario == "malformed_actor_type_len": schema[1]["type"] = sa.String(length=64)
    elif scenario == "malformed_actor_id": schema[2]["type"] = sa.Text()
    elif scenario == "malformed_actor_id_len": schema[2]["type"] = sa.String(length=32)
    elif scenario == "malformed_action": schema[3]["type"] = sa.Text()
    elif scenario == "malformed_action_len": schema[3]["type"] = sa.String(length=255)
    elif scenario == "malformed_subject_type": schema[4]["type"] = sa.Text()
    elif scenario == "malformed_subject_type_len": schema[4]["type"] = sa.String(length=32)
    elif scenario == "malformed_subject_id": schema[5]["type"] = sa.Text()
    elif scenario == "malformed_subject_id_len": schema[5]["type"] = sa.String(length=32)
    elif scenario == "malformed_before_hash": schema[6]["type"] = sa.Text()
    elif scenario == "malformed_before_hash_len": schema[6]["type"] = sa.String(length=32)
    elif scenario == "malformed_after_hash": schema[7]["type"] = sa.Text()
    elif scenario == "malformed_after_hash_len": schema[7]["type"] = sa.String(length=32)
    elif scenario == "malformed_safe_metadata": schema[8]["type"] = sa.Text()
    elif scenario == "malformed_created_at_tz": schema[9]["type"] = sa.dialects.postgresql.TIMESTAMP(timezone=False)
    
    # Nullability
    elif scenario in ("required_column_nullable", "required_column_nullable_actor_type"): schema[1]["nullable"] = True
    elif scenario == "required_column_nullable_action": schema[3]["nullable"] = True
    elif scenario == "required_column_nullable_actor_id": schema[2]["nullable"] = True
    elif scenario == "required_column_nullable_subject_type": schema[4]["nullable"] = True
    elif scenario == "required_column_nullable_subject_id": schema[5]["nullable"] = True
    elif scenario == "required_column_nullable_safe_metadata": schema[8]["nullable"] = True
    elif scenario == "required_column_nullable_created_at": schema[9]["nullable"] = True
    elif scenario == "before_hash_not_nullable": schema[6]["nullable"] = False
    elif scenario == "after_hash_not_nullable": schema[7]["nullable"] = False
    
    # Defaults
    elif scenario in ("unexpected_default", "non_id_default"): schema[3]["default"] = "C"
    
    # Structure
    elif scenario == "wrong_pk": pks["constrained_columns"] = ["id", "actor_id"]
    elif scenario == "unexpected_fk": fks.append({"referred_table": "other", "constrained_columns": ["actor_id"]})
    
    elif scenario == "missing_index": idxs.pop()
    elif scenario == "extra_index": idxs.append({"name": "ix_extra", "column_names": ["action"], "unique": False})
    elif scenario == "wrong_index_column": idxs[0]["column_names"] = ["action"]
    elif scenario == "unique_index": idxs[0]["unique"] = True
    elif scenario == "partial_index": idxs[0]["dialect_options"] = {"postgresql_where": "action='C'"}
    
    elif scenario == "unexpected_unique_constraint": unique.append({"name": "uq_act", "column_names": ["actor_id"]})
    elif scenario == "unexpected_check_constraint": checks.append({"name": "ck_id", "sqltext": "id > 0"})
    elif scenario == "unexpected_trigger": has_triggers = True
    
    from unittest.mock import MagicMock
    import importlib.util, sys
    
    spec = importlib.util.spec_from_file_location("migration_0012_mock", str(_migrations_dir / "versions" / "0012_v7_audit_log_sqlite_pk.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migration_0012_mock"] = mod
    spec.loader.exec_module(mod)
    
    bind = MagicMock()
    bind.dialect.name = "postgresql"
    bind.executed_sqls = []
    
    def mock_execute(stmt):
        res = MagicMock()
        sql = str(stmt).upper()
        if "PG_GET_SERIAL_SEQUENCE" in sql:
            res.scalar.return_value = "public.audit_log_id_seq"
        elif "INFORMATION_SCHEMA.TRIGGERS" in sql:
            res.fetchall.return_value = [("some_trigger",)] if has_triggers else []
        return res
        
    bind.execute.side_effect = mock_execute
    
    insp = MockPostgresInspector(schema, pks, fks, idxs, unique, checks)
    monkeypatch.setattr(mod.sa, "inspect", lambda b: insp)
    monkeypatch.setattr(mod.op, "get_bind", lambda: bind)
    monkeypatch.setattr(mod.op, "batch_alter_table", MagicMock())
    
    with pytest.raises(RuntimeError):
        mod.upgrade()


def test_mock_pg_check_constraints_unsupported_rejected(mock_pg_bind, monkeypatch):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity={"always": True}), sequence_owned=False)
    insp = mod.sa.inspect(bind)
    def raise_not_implemented(table_name):
        raise NotImplementedError("Check constraint inspection unsupported")
    insp.get_check_constraints = raise_not_implemented
    with pytest.raises(RuntimeError, match="Check constraint inspection unsupported"):
        mod.upgrade()


def test_mock_pg_unsupported_dialect_rejected(mock_pg_bind):
    mod, bind = mock_pg_bind(_mock_pg_schema(id_identity={"always": True}))
    bind.dialect.name = "mysql"
    with pytest.raises(RuntimeError, match="Unsupported dialect"):
        mod.upgrade()

