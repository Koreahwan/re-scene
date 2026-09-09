import pytest
from sqlalchemy import create_engine, text
from alembic.config import Config
from alembic import command
import sqlalchemy as sa
import os
import tempfile
import uuid
from datetime import datetime, timezone

def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')

@pytest.fixture
def disposable_db_path(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = os.path.join(temp_dir, "test_usage_ledger.db")
        # Patch both os.environ and the cached settings object directly
        monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
        monkeypatch.setenv("SYNC_DATABASE_URL", f"sqlite:///{db_path}")

        try:
            from src.reframe.shared.config import settings
            monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
            monkeypatch.setattr(settings, "SYNC_DATABASE_URL", f"sqlite:///{db_path}")
        except ImportError:
            pass

        yield db_path

@pytest.fixture
def alembic_cfg(disposable_db_path):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{disposable_db_path}")
    return cfg

@pytest.fixture
def run_id():
    return str(uuid.uuid4())

def insert_base_data(conn, run_id):
    conn.execute(
        text("""
            INSERT INTO analysis_runs (
                id, run_type, work_id, edition_id, status, input_hash, config_hash, dataset_version,
                model_id, prompt_hash, proof_schema_version, cost_reserved_micros, cost_actual_micros, created_at
            )
            VALUES (
                :run_id, 'REFRAME', 'w1', 'e1', 'QUEUED', 'ih', 'ch', 'v1', 'm1', 'ph', '1.0.0', 0, 0, :created_at
            )
        """),
        {"run_id": run_id, "created_at": utc_now()}
    )

def insert_ledger_row(conn, model_call_id, cost=0.01, run_id=None, tokens=10, row_id=None):
    if row_id is None:
        row_id = str(uuid.uuid4())
    conn.execute(
        text("""
            INSERT INTO usage_ledger (
                id, analysis_run_id, model_call_id, model_id, purpose,
                input_text_tokens, input_image_tokens, output_tokens, reasoning_tokens,
                total_tokens, estimated_cost_micros, pricing_version, billing_reference, created_at
            )
            VALUES (
                :id, :run_id, :model_call_id, 'gemini-1.5-pro', 'HYPOTHESIS',
                :tokens, 0, :tokens, 0, :total_tokens, :cost, '2026-08-gemini', :billing, :created_at
            )
        """),
        {
            "id": row_id,
            "run_id": run_id,
            "model_call_id": model_call_id,
            "tokens": tokens,
            "total_tokens": tokens * 2,
            "cost": int(cost * 1_000_000),
            "billing": f"bill-{row_id}",
            "created_at": utc_now()
        }
    )

def snapshot_ledger(conn):
    res = conn.execute(text("""
        SELECT id, user_id, analysis_run_id, model_call_id, model_id, purpose,
               input_text_tokens, input_image_tokens, output_tokens, reasoning_tokens,
               total_tokens, estimated_cost_micros, pricing_version, billing_reference, created_at
        FROM usage_ledger
        ORDER BY id
    """)).fetchall()
    return [tuple(row) for row in res]

def snapshot_indexes(insp, table_name="usage_ledger"):
    indexes = insp.get_indexes(table_name)
    result = []
    for idx in indexes:
        dialect_options = idx.get('dialect_options', {})
        predicate = tuple(
            sorted(
                (k, str(v)) for k, v in dialect_options.items()
                if k.endswith('_where') and v is not None
            )
        )
        result.append((
            idx['name'],
            tuple(idx['column_names']),
            bool(idx.get('unique')),
            predicate
        ))
    return tuple(sorted(result))

def snapshot_unique_constraints(insp, table_name="usage_ledger"):
    try:
        constraints = insp.get_unique_constraints(table_name)
    except NotImplementedError:
        constraints = []
    result = []
    for cons in constraints:
        result.append((
            cons.get('name'),
            tuple(cons['column_names'])
        ))
    return tuple(sorted(result))

def test_a_clean_upgrade(alembic_cfg, disposable_db_path, run_id):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            insert_base_data(conn, run_id)
            insert_ledger_row(conn, "call_1", 0.05, run_id, tokens=10)
            insert_ledger_row(conn, "call_2", 0.10, run_id, tokens=20)
            pre_snap = snapshot_ledger(conn)

        command.upgrade(alembic_cfg, "head")

        with engine.begin() as conn:
            insp = sa.inspect(conn)
            indexes = insp.get_indexes('usage_ledger')
            idx = next((i for i in indexes if i['name'] == 'ix_usage_ledger_model_call_id'), None)
            assert idx is not None
            assert idx['column_names'] == ['model_call_id']
            assert bool(idx.get('unique')) is True

            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap
            assert len(post_snap) == 2

            from sqlalchemy.exc import IntegrityError
            with pytest.raises(IntegrityError):
                insert_ledger_row(conn, "call_1", 0.01, run_id, tokens=10)
    finally:
        engine.dispose()


def test_b_duplicate_preflight(alembic_cfg, disposable_db_path, run_id):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            insert_base_data(conn, run_id)
            insert_ledger_row(conn, "dup_call_synth", 0.02, run_id, tokens=15)
            insert_ledger_row(conn, "dup_call_synth", 0.03, run_id, tokens=25)
            pre_snap = snapshot_ledger(conn)

        with pytest.raises(RuntimeError) as exc_info:
            command.upgrade(alembic_cfg, "head")

        err_msg = str(exc_info.value)
        assert "found 1 duplicate model_call_id groups" in err_msg
        assert "dup_call_synth" not in err_msg

        with engine.begin() as conn:
            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap
            assert len(post_snap) == 2

            insp = sa.inspect(conn)
            indexes = insp.get_indexes('usage_ledger')
            idx = next((i for i in indexes if i['name'] == 'ix_usage_ledger_model_call_id'), None)
            assert idx is None
    finally:
        engine.dispose()


def test_c_existing_correct_index(alembic_cfg, disposable_db_path):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE UNIQUE INDEX ix_usage_ledger_model_call_id ON usage_ledger (model_call_id)"))

        command.upgrade(alembic_cfg, "head")

        with engine.begin() as conn:
            insp = sa.inspect(conn)
            indexes = insp.get_indexes('usage_ledger')
            idx = next((i for i in indexes if i['name'] == 'ix_usage_ledger_model_call_id'), None)
            assert idx is not None
            assert bool(idx.get('unique')) is True
            assert idx['column_names'] == ['model_call_id']
    finally:
        engine.dispose()


def test_d_conflicting_index(alembic_cfg, disposable_db_path):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE INDEX ix_usage_ledger_model_call_id ON usage_ledger (model_call_id)"))

        with pytest.raises(RuntimeError, match="is not unique"):
            command.upgrade(alembic_cfg, "head")
    finally:
        engine.dispose()


def test_e_downgrade_preservation(alembic_cfg, disposable_db_path, run_id):
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            insert_base_data(conn, run_id)
            insert_ledger_row(conn, "call_3", 0.05, run_id, tokens=55)
            pre_snap = snapshot_ledger(conn)

        command.downgrade(alembic_cfg, "0009_v7_auth_operations_saga")

        with engine.begin() as conn:
            insp = sa.inspect(conn)
            indexes = insp.get_indexes('usage_ledger')
            idx = next((i for i in indexes if i['name'] == 'ix_usage_ledger_model_call_id'), None)
            assert idx is None

            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap

        command.upgrade(alembic_cfg, "head")
        with engine.begin() as conn:
            insp = sa.inspect(conn)
            indexes = insp.get_indexes('usage_ledger')
            idx = next((i for i in indexes if i['name'] == 'ix_usage_ledger_model_call_id'), None)
            assert idx is not None
            assert bool(idx.get('unique')) is True
    finally:
        engine.dispose()


def test_f_null_preflight(alembic_cfg, disposable_db_path, run_id):
    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
            conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('0009_v7_auth_operations_saga')"))

            conn.execute(text("""
                CREATE TABLE usage_ledger (
                    id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36),
                    analysis_run_id VARCHAR(36),
                    model_call_id VARCHAR(255),
                    model_id VARCHAR(255),
                    purpose VARCHAR(255),
                    input_text_tokens INTEGER,
                    input_image_tokens INTEGER,
                    output_tokens INTEGER,
                    reasoning_tokens INTEGER,
                    total_tokens INTEGER,
                    estimated_cost_micros INTEGER,
                    pricing_version VARCHAR(255),
                    billing_reference VARCHAR(255),
                    created_at VARCHAR(255)
                )
            """))

            insert_ledger_row(conn, None, 0.05, None, tokens=10, row_id="sentinel-row-id-999")
            # The fixture sets billing_reference to 'bill-{row_id}', which will be 'bill-sentinel-row-id-999'
            pre_snap = snapshot_ledger(conn)

        with pytest.raises(RuntimeError) as exc_info:
            command.upgrade(alembic_cfg, "head")

        err_msg = str(exc_info.value)
        assert "found 1 rows with NULL model_call_id" in err_msg
        assert "sentinel-row-id-999" not in err_msg
        assert "bill-sentinel-row-id-999" not in err_msg
        assert "gemini-1.5-pro" not in err_msg

        with engine.begin() as conn:
            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap
            assert len(post_snap) == 1
    finally:
        engine.dispose()


def test_g_partial_unique_index_conflict(alembic_cfg, disposable_db_path, run_id):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            insert_base_data(conn, run_id)
            insert_ledger_row(conn, "billable-1", 0.05, run_id, tokens=10)
            pre_snap = snapshot_ledger(conn)

            conn.execute(text("CREATE UNIQUE INDEX ix_usage_ledger_model_call_id ON usage_ledger (model_call_id) WHERE model_call_id LIKE 'billable-%'"))

            insp = sa.inspect(conn)
            indexes = insp.get_indexes('usage_ledger')
            idx = next((i for i in indexes if i['name'] == 'ix_usage_ledger_model_call_id'), None)
            assert idx is not None
            assert idx['column_names'] == ['model_call_id']
            assert bool(idx.get('unique')) is True
            assert idx.get('dialect_options', {}).get('sqlite_where') is not None

        with pytest.raises(RuntimeError, match="partial/predicate index"):
            command.upgrade(alembic_cfg, "head")

        with engine.begin() as conn:
            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap
    finally:
        engine.dispose()


def test_h_exact_canonical_plus_differently_named_conflict(alembic_cfg, disposable_db_path, run_id):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            insert_base_data(conn, run_id)
            insert_ledger_row(conn, "call_h", 0.05, run_id, tokens=10)

            conn.execute(text("CREATE UNIQUE INDEX ix_usage_ledger_model_call_id ON usage_ledger (model_call_id)"))
            conn.execute(text("CREATE INDEX zz_usage_ledger_model_call_id_conflict ON usage_ledger (model_call_id)"))
            pre_snap = snapshot_ledger(conn)

            insp = sa.inspect(conn)
            pre_idx_snap = snapshot_indexes(insp)
            expected_ix = ('ix_usage_ledger_model_call_id', ('model_call_id',), True, ())
            expected_zz = ('zz_usage_ledger_model_call_id_conflict', ('model_call_id',), False, ())
            assert expected_ix in pre_idx_snap
            assert expected_zz in pre_idx_snap

        with pytest.raises(RuntimeError, match="another index zz_usage_ledger_model_call_id_conflict targets"):
            command.upgrade(alembic_cfg, "head")

        with engine.begin() as conn:
            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap

            insp = sa.inspect(conn)
            post_idx_snap = snapshot_indexes(insp)
            assert pre_idx_snap == post_idx_snap
            assert expected_ix in post_idx_snap
            assert expected_zz in post_idx_snap

            # Check alembic_version
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "0009_v7_auth_operations_saga"
    finally:
        engine.dispose()


def test_i_exact_canonical_plus_single_column_unique_constraint(alembic_cfg, disposable_db_path, run_id):
    command.upgrade(alembic_cfg, "0009_v7_auth_operations_saga")

    engine = create_engine(f"sqlite:///{disposable_db_path}")
    try:
        with engine.begin() as conn:
            insert_base_data(conn, run_id)
            insert_ledger_row(conn, "call_i", 0.05, run_id, tokens=10)

            # Recreate table with constraint
            conn.execute(text("CREATE TABLE usage_ledger_new (id VARCHAR(36) NOT NULL, user_id VARCHAR(36), analysis_run_id VARCHAR(36), model_call_id VARCHAR(255), model_id VARCHAR(255), purpose VARCHAR(255), input_text_tokens INTEGER, input_image_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, total_tokens INTEGER, estimated_cost_micros INTEGER, pricing_version VARCHAR(255), billing_reference VARCHAR(255), created_at VARCHAR(255), CONSTRAINT uq_usage_ledger_model_call_id UNIQUE (model_call_id))"))
            conn.execute(text("INSERT INTO usage_ledger_new SELECT * FROM usage_ledger"))
            conn.execute(text("DROP TABLE usage_ledger"))
            conn.execute(text("ALTER TABLE usage_ledger_new RENAME TO usage_ledger"))

            conn.execute(text("CREATE UNIQUE INDEX ix_usage_ledger_model_call_id ON usage_ledger (model_call_id)"))

            insp = sa.inspect(conn)
            pre_idx_snap = snapshot_indexes(insp)
            pre_uq_snap = snapshot_unique_constraints(insp)

            expected_ix = ('ix_usage_ledger_model_call_id', ('model_call_id',), True, ())
            expected_uq = ('uq_usage_ledger_model_call_id', ('model_call_id',))

            assert expected_ix in pre_idx_snap
            assert expected_uq in pre_uq_snap

            pre_snap = snapshot_ledger(conn)

        with pytest.raises(RuntimeError, match="Conflicting constraint found"):
            command.upgrade(alembic_cfg, "head")

        with engine.begin() as conn:
            post_snap = snapshot_ledger(conn)
            assert pre_snap == post_snap

            insp = sa.inspect(conn)
            post_idx_snap = snapshot_indexes(insp)
            post_uq_snap = snapshot_unique_constraints(insp)

            assert pre_idx_snap == post_idx_snap
            assert pre_uq_snap == post_uq_snap

            assert expected_ix in post_idx_snap
            assert expected_uq in post_uq_snap

            # Check alembic_version
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            assert version == "0009_v7_auth_operations_saga"
    finally:
        engine.dispose()
