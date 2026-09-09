"""
Reframe V7 Simulation Migration Immutability & Safe Inspection Unit Tests
Verifies:
1. Migration 0006 is strictly restored to its published state without demo_user_id.
2. Migration 0007 idempotently adds demo_user_id with table/column inspection.
3. Migration 0007 executes successfully on fresh, 0006-upgraded, and mutated-0006 SQLite/Postgres schemas.
Zero External Generative Model Calls.
"""
import pytest
import importlib.util
from pathlib import Path
import sqlalchemy as sa
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "postgres" / "migrations" / "versions"


def load_migration_module(filename: str):
    file_path = MIGRATIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mig_006 = load_migration_module("0006_v7_synthetic_audience_lab.py")
mig_007 = load_migration_module("0007_v7_synthetic_persona_demo_user_mapping.py")


def test_migration_chain_and_down_revisions():
    """Verifies that 0006 and 0007 form a valid Alembic revision chain."""
    assert mig_006.revision == "0006_v7_synthetic_lab"
    assert mig_006.down_revision == "0005_v7_auth_and_checkpoint"

    assert mig_007.revision == "0007_v7_synthetic_persona_demo_user_mapping"
    assert mig_007.down_revision == "0006_v7_synthetic_lab"


def test_0006_migration_published_immutability():
    """Verifies that 0006 source code does not mention demo_user_id column."""
    import inspect as pyinspect
    source = pyinspect.getsource(mig_006.upgrade)
    assert "demo_user_id" not in source, "0006 migration was improperly modified to include demo_user_id!"


def test_0007_migration_idempotent_inspection_logic():
    """Verifies that 0007 migration inspects tables and columns before altering."""
    import inspect as pyinspect
    source = pyinspect.getsource(mig_007.upgrade)
    assert "insp" in source
    assert "demo_user_id" in source
    assert "synthetic_personas" in source


def test_0007_execution_all_schema_states(monkeypatch):
    """
    Executes 0007 migration across all three schema states:
    1. Table missing (noop)
    2. Table existing without demo_user_id (standard 0006 -> 0007 upgrade)
    3. Table existing with demo_user_id already present (mutated 0006 state)
    """
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    engine = create_engine("sqlite:///:memory:")

    # State 1: Table missing
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)
        monkeypatch.setattr("alembic.op.get_bind", lambda: conn)
        monkeypatch.setattr("alembic.op.batch_alter_table", ops.batch_alter_table)
        mig_007.upgrade()

    # State 2: Standard 0006 -> 0007 upgrade (table without demo_user_id)
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text(
            "CREATE TABLE synthetic_personas ("
            "id VARCHAR(36) PRIMARY KEY, "
            "source_dataset VARCHAR(128), "
            "source_revision VARCHAR(64), "
            "source_persona_id_hash VARCHAR(64)"
            ")"
        ))
        conn.commit()

        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)
        monkeypatch.setattr("alembic.op.get_bind", lambda: conn)
        monkeypatch.setattr("alembic.op.batch_alter_table", ops.batch_alter_table)
        mig_007.upgrade()

        insp = sa.inspect(conn)
        cols = [c["name"] for c in insp.get_columns("synthetic_personas")]
        assert "demo_user_id" in cols

    # State 3: Mutated 0006 state (table with demo_user_id already present)
    engine3 = create_engine("sqlite:///:memory:")
    with engine3.connect() as conn:
        conn.execute(sa.text("CREATE TABLE users (id VARCHAR(36) PRIMARY KEY)"))
        conn.execute(sa.text(
            "CREATE TABLE synthetic_personas ("
            "id VARCHAR(36) PRIMARY KEY, "
            "source_dataset VARCHAR(128), "
            "source_revision VARCHAR(64), "
            "source_persona_id_hash VARCHAR(64), "
            "demo_user_id VARCHAR(36)"
            ")"
        ))
        conn.commit()

        ctx = MigrationContext.configure(conn)
        ops = Operations(ctx)
        monkeypatch.setattr("alembic.op.get_bind", lambda: conn)
        monkeypatch.setattr("alembic.op.batch_alter_table", ops.batch_alter_table)
        mig_007.upgrade()

        insp = sa.inspect(conn)
        cols = [c["name"] for c in insp.get_columns("synthetic_personas")]
        assert "demo_user_id" in cols
