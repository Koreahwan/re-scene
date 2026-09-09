"""v7 audit log sqlite pk

Revision ID: 0012_v7_audit_log_sqlite_pk
Revises: 0011_v7_analysis_run_events_sqlite_pk
Create Date: 2026-09-01 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0012_v7_audit_log_sqlite_pk'
down_revision = '0011_v7_analysis_run_events_sqlite_pk'
branch_labels = None
depends_on = None

def get_column_type_str(col_type):
    return str(col_type).upper().replace(" ", "")


def validate_sqlite_schema(bind, expected_id_type=None):
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if 'audit_log' not in tables:
        raise RuntimeError("Table 'audit_log' does not exist")
        
    cols = insp.get_columns("audit_log")
    if len(cols) != 10:
        raise RuntimeError(f"Expected 10 columns, got {len(cols)}")
        
    expected_order = [
        "id", "actor_type", "actor_id", "action", "subject_type", 
        "subject_id", "before_hash", "after_hash", "safe_metadata", "created_at"
    ]
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
        "actor_type": "VARCHAR(32)",
        "actor_id": "VARCHAR(64)",
        "action": "VARCHAR(64)",
        "subject_type": "VARCHAR(64)",
        "subject_id": "VARCHAR(64)",
        "before_hash": "VARCHAR(64)",
        "after_hash": "VARCHAR(64)",
        "safe_metadata": "JSON",
        "created_at": "DATETIME"
    }
    
    for c in cols:
        name = c["name"]
        
        if name in ["before_hash", "after_hash"]:
            if not c.get("nullable"):
                raise RuntimeError(f"Column {name} is NOT NULL but should be NULL")
        else:
            if c.get("nullable"):
                raise RuntimeError(f"Column {name} is nullable")
        
        if name != "id":
            if c.get("default") is not None and c.get("default") != "":
                raise RuntimeError(f"Column {name} has default")
            ctype = get_column_type_str(c["type"])
            if ctype != expected_types[name]:
                raise RuntimeError(f"Column {name} has unexpected type: {ctype} != {expected_types[name]}")
            
    pk_constraint = insp.get_pk_constraint("audit_log")
    if pk_constraint.get("constrained_columns") != ["id"]:
        raise RuntimeError(f"PK mismatch: {pk_constraint.get('constrained_columns')}")
        
    fks = insp.get_foreign_keys("audit_log")
    if len(fks) != 0:
        raise RuntimeError("Expected 0 FKs")
        
    idxs = insp.get_indexes("audit_log")
    if len(idxs) != 3:
        raise RuntimeError(f"Expected 3 indexes, got {len(idxs)}")
        
    expected_indexes = {
        "ix_audit_log_actor_id": ["actor_id"],
        "ix_audit_log_subject_id": ["subject_id"],
        "ix_audit_log_created_at": ["created_at"]
    }
    
    if {idx.get("name") for idx in idxs} != set(expected_indexes.keys()):
        raise RuntimeError("Unexpected index set")
    
    for idx in idxs:
        name = idx.get("name")
        if name not in expected_indexes:
            raise RuntimeError(f"Unexpected index: {name}")
        if list(idx.get("column_names")) != expected_indexes[name]:
            raise RuntimeError(f"Index {name} column mismatch")
        if idx.get("unique", False):
            raise RuntimeError(f"Index {name} is unique")
            
        dialect_options = idx.get("dialect_options", {})
        if any(k.endswith('_where') and v is not None for k, v in dialect_options.items()):
            raise RuntimeError(f"Index {name} has predicate")
            
        idx_sql = bind.execute(sa.text(f"SELECT sql FROM sqlite_master WHERE type='index' AND name='{name}'")).scalar()
        if idx_sql and " WHERE " in idx_sql.upper():
            raise RuntimeError(f"Index {name} has predicate")
        
    if insp.get_unique_constraints("audit_log"):
        raise RuntimeError("Unexpected unique constraint")
        
    try:
        if insp.get_check_constraints("audit_log"):
            raise RuntimeError("Unexpected check constraint")
    except NotImplementedError:
        raise RuntimeError("Check constraint inspection unsupported")
        
    triggers = bind.execute(sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='audit_log'")).fetchall()
    if triggers:
        raise RuntimeError("Unexpected triggers")
        
    fk_check = bind.execute(sa.text("PRAGMA foreign_key_check('audit_log')")).fetchall()
    if fk_check:
        raise RuntimeError("Foreign key check failed")

    return id_type


def validate_postgresql_schema(bind):
    insp = sa.inspect(bind)
    tables = insp.get_table_names()
    if 'audit_log' not in tables:
        raise RuntimeError("Table 'audit_log' does not exist")
        
    cols = insp.get_columns("audit_log")
    if len(cols) != 10:
        raise RuntimeError(f"Expected 10 columns, got {len(cols)}")
        
    expected_order = [
        "id", "actor_type", "actor_id", "action", "subject_type", 
        "subject_id", "before_hash", "after_hash", "safe_metadata", "created_at"
    ]
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
        seq_res = bind.execute(sa.text("SELECT pg_get_serial_sequence('audit_log', 'id')")).scalar()
        if seq_res:
            has_sequence = True
            
    if not (has_identity or has_sequence):
        raise RuntimeError("PostgreSQL id is plain BIGINT without identity/sequence")

    expected_types = {
        "actor_type": "VARCHAR(32)",
        "actor_id": "VARCHAR(64)",
        "action": "VARCHAR(64)",
        "subject_type": "VARCHAR(64)",
        "subject_id": "VARCHAR(64)",
        "before_hash": "VARCHAR(64)",
        "after_hash": "VARCHAR(64)",
        "safe_metadata": "JSON"
    }
    
    for c in cols:
        name = c["name"]
        
        if name in ["before_hash", "after_hash"]:
            if not c.get("nullable"):
                raise RuntimeError(f"Column {name} is NOT NULL but should be NULL")
        else:
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
            
    pk_constraint = insp.get_pk_constraint("audit_log")
    if pk_constraint.get("constrained_columns") != ["id"]:
        raise RuntimeError(f"PK mismatch: {pk_constraint.get('constrained_columns')}")
        
    fks = insp.get_foreign_keys("audit_log")
    if len(fks) != 0:
        raise RuntimeError("Expected 0 FK")
        
    idxs = insp.get_indexes("audit_log")
    if len(idxs) != 3:
        raise RuntimeError(f"Expected 3 indexes, got {len(idxs)}")
        
    expected_indexes = {
        "ix_audit_log_actor_id": ["actor_id"],
        "ix_audit_log_subject_id": ["subject_id"],
        "ix_audit_log_created_at": ["created_at"]
    }
    
    if {idx.get("name") for idx in idxs} != set(expected_indexes.keys()):
        raise RuntimeError("Unexpected index set")
    
    for idx in idxs:
        name = idx.get("name")
        if name not in expected_indexes:
            raise RuntimeError(f"Unexpected index: {name}")
        if list(idx.get("column_names")) != expected_indexes[name]:
            raise RuntimeError(f"Index {name} column mismatch")
        if idx.get("unique", False):
            raise RuntimeError(f"Index {name} is unique")
    
        dialect_options = idx.get("dialect_options", {})
        if any(k.endswith('_where') and v is not None for k, v in dialect_options.items()):
            raise RuntimeError(f"Index {name} has predicate")
        
    if insp.get_unique_constraints("audit_log"):
        raise RuntimeError("Unexpected unique constraint")
        
    try:
        if insp.get_check_constraints("audit_log"):
            raise RuntimeError("Unexpected check constraint")
    except NotImplementedError:
        raise RuntimeError("Check constraint inspection unsupported")
        
    triggers = bind.execute(sa.text("SELECT trigger_name FROM information_schema.triggers WHERE event_object_table = 'audit_log' AND trigger_schema = current_schema() AND trigger_name NOT LIKE 'RI_ConstraintTrigger%'")).fetchall()
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
    
    res = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM audit_log")).fetchone()
    
    with op.batch_alter_table(
        "audit_log",
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
    
    res2 = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM audit_log")).fetchone()
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
        
    res = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM audit_log")).fetchone()
    
    with op.batch_alter_table(
        "audit_log",
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
        
    res2 = bind.execute(sa.text("SELECT count(1), min(id), max(id) FROM audit_log")).fetchone()
    if res != res2:
        raise RuntimeError("Data loss during downgrade rebuild")
