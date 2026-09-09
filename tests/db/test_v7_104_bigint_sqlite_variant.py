import pytest
from sqlalchemy import MetaData, Table, Column, String, create_engine, inspect
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.types import BigInteger, Integer
from sqlalchemy.schema import CreateTable

from src.reframe.jobs.models import AnalysisRunEvent
from src.reframe.audit.models import AuditLog


@pytest.mark.parametrize("model_class", [AnalysisRunEvent, AuditLog])
def test_a_orm_column_contract(model_class):
    col = model_class.__table__.c.id

    # 1. primary_key is True
    assert col.primary_key is True

    # 2. autoincrement is True
    assert col.autoincrement is True

    # 3. PostgreSQL dialect type compile == "BIGINT"
    pg_type = col.type.compile(dialect=postgresql.dialect())
    assert pg_type == "BIGINT"

    # 4. SQLite dialect type compile == "INTEGER"
    sqlite_type = col.type.compile(dialect=sqlite.dialect())
    assert sqlite_type == "INTEGER"

    # 5. 기본 타입이 BigInteger 계약임
    assert isinstance(col.type, BigInteger)

    # 6. SQLite dialect implementation이 Integer 계약임
    sqlite_impl = col.type.dialect_impl(sqlite.dialect())
    assert isinstance(sqlite_impl, Integer)
    assert not isinstance(sqlite_impl, BigInteger)


@pytest.mark.parametrize("model_class", [AnalysisRunEvent, AuditLog])
def test_b_isolated_probe_table_ddl(model_class):
    metadata = MetaData()
    col = model_class.__table__.c.id

    probe = Table(
        "probe_table",
        metadata,
        Column("id", col.type, primary_key=True, autoincrement=True),
        Column("payload", String)
    )

    # PostgreSQL DDL
    pg_ddl = str(CreateTable(probe).compile(dialect=postgresql.dialect())).upper()
    id_line = next((line for line in pg_ddl.splitlines() if line.strip().startswith('"ID"') or line.strip().startswith('ID')), "")

    has_serial = "BIGSERIAL" in id_line or "SERIAL8" in id_line
    has_identity = "BIGINT" in id_line and "GENERATED" in id_line and "IDENTITY" in id_line
    assert has_serial or has_identity

    # SQLite DDL
    sqlite_ddl = str(CreateTable(probe).compile(dialect=sqlite.dialect())).upper()
    assert "INTEGER" in sqlite_ddl
    assert "PRIMARY KEY" in sqlite_ddl
    assert "BIGINT" not in sqlite_ddl


@pytest.mark.parametrize("model_class", [AnalysisRunEvent, AuditLog])
def test_c_sqlite_implicit_id(model_class):
    metadata = MetaData()
    col = model_class.__table__.c.id

    probe = Table(
        "probe_table",
        metadata,
        Column("id", col.type, primary_key=True, autoincrement=True),
        Column("payload", String)
    )

    engine = create_engine("sqlite:///:memory:")
    try:
        metadata.create_all(engine)

        with engine.begin() as conn:
            conn.execute(probe.insert().values(payload="first"))
            conn.execute(probe.insert().values(payload="second"))

            res = conn.execute(probe.select().order_by(probe.c.id)).fetchall()
            ids = [row.id for row in res]

            # implicit id is [1, 2]
            assert ids == [1, 2]

        insp = inspect(engine)
        cols = insp.get_columns("probe_table")
        id_col = next(c for c in cols if c["name"] == "id")

        # SQLite declared type == INTEGER
        assert str(id_col["type"]).upper() == "INTEGER"

        # primary_key == 1
        assert id_col.get("primary_key", 0) in (1, True)
    finally:
        engine.dispose()
