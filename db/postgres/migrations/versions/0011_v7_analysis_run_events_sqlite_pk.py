"""v7 analysis run events sqlite pk

Revision ID: 0011_v7_analysis_run_events_sqlite_pk
Revises: 0010_v7_usage_ledger_unique
Create Date: 2026-09-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0011_v7_analysis_run_events_sqlite_pk'
down_revision: Union[str, None] = '0010_v7_usage_ledger_unique'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def get_column_type_str(col_type):
    # Depending on dialect and SQLAlchemy version, the string representation varies slightly
    return str(col_type).upper().replace(" ", "")


def validate_sqlite_schema(bind, expected_id_type=None):
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if 'analysis_run_events' not in tables:
        raise RuntimeError("Table 'analysis_run_events' does not exist")
    if 'analysis_runs' not in tables:
        raise RuntimeError("Table 'analysis_runs' does not exist")
        
    cols = insp.get_columns("analysis_run_events")
    if len(cols) != 6:
        raise RuntimeError(f"Expected 6 columns, got {len(cols)}")
        
    expected_order = ["id", "run_id", "sequence", "event_type", "safe_payload", "created_at"]
    if [c["name"] for c in cols] != expected_order:
        raise RuntimeError(f"Column order mismatch: {[c['name'] for c in cols]}")
        
    id_col = cols[0]
    id_type = get_column_type_str(id_col["type"])
    
    if expected_id_type and id_type != expected_id_type:
        raise RuntimeError(f"Unexpected ID type: expected {expected_id_type}, got {id_type}")
    
    if id_type not in ["BIGINT", "INTEGER"]:
        raise RuntimeError(f"Unexpected ID type: {id_type}")

    if id_col.get("default") is not None and id_col.get("default") != "":
        raise RuntimeError("Column id has unexpected default")

    expected_types = {
        "run_id": "CHAR(32)",
        "sequence": "INTEGER",
        "event_type": "VARCHAR(64)",
        "safe_payload": "JSON",
        "created_at": "DATETIME"
    }
    
    for c in cols:
        name = c["name"]
        
        if c.get("nullable"):
            raise RuntimeError(f"Column {name} is nullable")
        
        if name != "id":
            if c.get("default") is not None and c.get("default") != "":
                raise RuntimeError(f"Column {name} has default")
            ctype = get_column_type_str(c["type"])
            if ctype != expected_types[name]:
                raise RuntimeError(f"Column {name} has unexpected type: {ctype} != {expected_types[name]}")
            
    pk_constraint = insp.get_pk_constraint("analysis_run_events")
    if pk_constraint.get("constrained_columns") != ["id"]:
        raise RuntimeError(f"PK mismatch: {pk_constraint.get('constrained_columns')}")
        
    fks = insp.get_foreign_keys("analysis_run_events")
    if len(fks) != 1:
        raise RuntimeError("Expected 1 FK")
    fk = fks[0]
    if fk.get("referred_table") != "analysis_runs" or fk.get("constrained_columns") != ["run_id"] or fk.get("referred_columns") != ["id"]:
        raise RuntimeError("FK mismatch")
    if str(fk.get("options", {}).get("ondelete", fk.get("ondelete", ""))).upper() != "CASCADE":
        raise RuntimeError("FK ondelete mismatch")
        
    idxs = insp.get_indexes("analysis_run_events")
    if len(idxs) != 1:
        raise RuntimeError(f"Expected 1 index, got {len(idxs)}")
    idx = idxs[0]
    if idx.get("name") != "ix_analysis_run_events_run_id" or idx.get("column_names") != ["run_id"] or idx.get("unique", False):
        raise RuntimeError("Index mismatch")
    
    dialect_options = idx.get("dialect_options", {})
    if any(k.endswith('_where') and v is not None for k, v in dialect_options.items()):
        raise RuntimeError("Index has predicate")
        
    if insp.get_unique_constraints("analysis_run_events"):
        raise RuntimeError("Unexpected unique constraint")
        
    try:
        if insp.get_check_constraints("analysis_run_events"):
            raise RuntimeError("Unexpected check constraint")
    except NotImplementedError:
        pass
        
    triggers = bind.execute(sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='analysis_run_events'")).fetchall()
    if triggers:
        raise RuntimeError("Unexpected triggers")
        
    fk_check = bind.execute(sa.text("PRAGMA foreign_key_check('analysis_run_events')")).fetchall()
    if fk_check:
        raise RuntimeError("Foreign key check failed")

    return id_type


def validate_postgresql_schema(bind):
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if 'analysis_run_events' not in tables:
        raise RuntimeError("Table 'analysis_run_events' does not exist")
    if 'analysis_runs' not in tables:
        raise RuntimeError("Table 'analysis_runs' does not exist")
        
    cols = insp.get_columns("analysis_run_events")
    if len(cols) != 6:
        raise RuntimeError(f"Expected 6 columns, got {len(cols)}")
        
    expected_order = ["id", "run_id", "sequence", "event_type", "safe_payload", "created_at"]
    if [c["name"] for c in cols] != expected_order:
        raise RuntimeError(f"Column order mismatch: {[c['name'] for c in cols]}")
        
    id_col = cols[0]
    id_type = get_column_type_str(id_col["type"])
    
    if id_type != "BIGINT":
        raise RuntimeError(f"Unexpected ID type: {id_type}")

    # Verify PostgreSQL autoincrement contract (either identity or owned sequence)
    has_identity = False
    if id_col.get("identity") is not None:
        identity = id_col["identity"]
        if not isinstance(identity, dict) or "always" not in identity or not isinstance(identity["always"], bool):
            raise RuntimeError(f"Malformed identity metadata: {identity}")
        has_identity = True
    
    has_sequence = False
    if not has_identity:
        # Check for owned sequence via pg_get_serial_sequence regardless of autoincrement
        seq_res = bind.execute(sa.text("SELECT pg_get_serial_sequence('analysis_run_events', 'id')")).scalar()
        if seq_res:
            has_sequence = True
            
    if not (has_identity or has_sequence):
        raise RuntimeError("PostgreSQL id is plain BIGINT without identity/sequence")

    expected_types = {
        "run_id": "UUID",
        "sequence": "INTEGER",
        "event_type": "VARCHAR(64)",
        "safe_payload": "JSON"
    }
    
    for c in cols:
        name = c["name"]
        
        if c.get("nullable"):
            raise RuntimeError(f"Column {name} is nullable")
        
        if name != "id":
            if c.get("default") is not None and c.get("default") != "":
                raise RuntimeError(f"Column {name} has default")
            
            if name == "created_at":
                ctype_obj = c["type"]
                # Must be DateTime or TIMESTAMP with timezone=True
                if not isinstance(ctype_obj, (sa.DateTime, getattr(sa.dialects.postgresql, "TIMESTAMP", type(None)))):
                    raise RuntimeError(f"Column {name} has unexpected type: {ctype_obj}")
                if getattr(ctype_obj, "timezone", None) is not True:
                    raise RuntimeError(f"Column {name} missing timezone=True")
            else:
                ctype = get_column_type_str(c["type"])
                if ctype != expected_types[name]:
                    raise RuntimeError(f"Column {name} has unexpected type: {ctype} != {expected_types[name]}")
            
    pk_constraint = insp.get_pk_constraint("analysis_run_events")
    if pk_constraint.get("constrained_columns") != ["id"]:
        raise RuntimeError(f"PK mismatch: {pk_constraint.get('constrained_columns')}")
        
    fks = insp.get_foreign_keys("analysis_run_events")
    if len(fks) != 1:
        raise RuntimeError("Expected 1 FK")
    fk = fks[0]
    if fk.get("referred_table") != "analysis_runs" or fk.get("constrained_columns") != ["run_id"] or fk.get("referred_columns") != ["id"]:
        raise RuntimeError("FK mismatch")
    if str(fk.get("options", {}).get("ondelete", fk.get("ondelete", ""))).upper() != "CASCADE":
        raise RuntimeError("FK ondelete mismatch")
        
    idxs = insp.get_indexes("analysis_run_events")
    if len(idxs) != 1:
        raise RuntimeError(f"Expected 1 index, got {len(idxs)}")
    idx = idxs[0]
    if idx.get("name") != "ix_analysis_run_events_run_id" or idx.get("column_names") != ["run_id"] or idx.get("unique", False):
        raise RuntimeError("Index mismatch")
    
    dialect_options = idx.get("dialect_options", {})
    if any(k.endswith('_where') and v is not None for k, v in dialect_options.items()):
        raise RuntimeError("Index has predicate")
        
    if insp.get_unique_constraints("analysis_run_events"):
        raise RuntimeError("Unexpected unique constraint")
        
    if insp.get_check_constraints("analysis_run_events"):
        raise RuntimeError("Unexpected check constraint")
        
    triggers = bind.execute(sa.text("SELECT trigger_name FROM information_schema.triggers WHERE event_object_table = 'analysis_run_events' AND trigger_schema = current_schema() AND trigger_name NOT LIKE 'RI_ConstraintTrigger%'")).fetchall()
    if triggers:
        raise RuntimeError("Unexpected triggers")


def upgrade() -> None:
    bind = op.get_bind()
    
    if bind.dialect.name == "postgresql":
        validate_postgresql_schema(bind)
        return
        
    if bind.dialect.name != "sqlite":
        raise RuntimeError(f"Unsupported dialect: {bind.dialect.name}")
        
    initial_id_type = validate_sqlite_schema(bind)
        
    if initial_id_type == "INTEGER":
        validate_sqlite_schema(bind, expected_id_type="INTEGER")
        return
        
    validate_sqlite_schema(bind, expected_id_type="BIGINT")
    
    res = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM analysis_run_events")).fetchone()
    
    with op.batch_alter_table(
        "analysis_run_events",
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
            autoincrement=True,
        )
        
    validate_sqlite_schema(bind, expected_id_type="INTEGER")
    
    res2 = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM analysis_run_events")).fetchone()
    if res != res2:
        raise RuntimeError("Data loss during rebuild")


def downgrade() -> None:
    bind = op.get_bind()
    
    if bind.dialect.name == "postgresql":
        validate_postgresql_schema(bind)
        return
        
    if bind.dialect.name != "sqlite":
        raise RuntimeError(f"Unsupported dialect: {bind.dialect.name}")
        
    initial_id_type = validate_sqlite_schema(bind)
        
    if initial_id_type == "BIGINT":
        validate_sqlite_schema(bind, expected_id_type="BIGINT")
        return
        
    validate_sqlite_schema(bind, expected_id_type="INTEGER")
        
    res = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM analysis_run_events")).fetchone()
    
    with op.batch_alter_table(
        "analysis_run_events",
        recreate="always",
    ) as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
            autoincrement=True,
        )
        
    validate_sqlite_schema(bind, expected_id_type="BIGINT")
        
    res2 = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM analysis_run_events")).fetchone()
    if res != res2:
        raise RuntimeError("Data loss during downgrade rebuild")
