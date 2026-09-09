"""v7_usage_ledger_unique

Revision ID: 0010_v7_usage_ledger_unique
Revises: 0009_v7_auth_operations_saga
Create Date: 2026-08-31 23:15:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0010_v7_usage_ledger_unique'
down_revision: Union[str, None] = '0009_v7_auth_operations_saga'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'usage_ledger' not in tables:
        raise RuntimeError("Table 'usage_ledger' does not exist")

    # 4-4. Data preflight
    # Check for NULLs
    null_count = bind.execute(sa.text("SELECT count(*) FROM usage_ledger WHERE model_call_id IS NULL")).scalar()
    if null_count > 0:
        raise RuntimeError(f"Cannot create unique index: found {null_count} rows with NULL model_call_id")

    # Check for duplicates
    dup_count = bind.execute(sa.text(
        "SELECT count(*) FROM (SELECT model_call_id FROM usage_ledger GROUP BY model_call_id HAVING count(*) > 1) as dups"
    )).scalar()
    if dup_count > 0:
        raise RuntimeError(f"Cannot create unique index: found {dup_count} duplicate model_call_id groups")

    indexes = insp.get_indexes('usage_ledger')
    exact_index_found = False

    # 4-3. Check for conflicting objects
    # 1. Other indexes targeting only model_call_id
    for idx in indexes:
        dialect_options = idx.get('dialect_options', {})
        is_partial = any(k.endswith('_where') and v is not None for k, v in dialect_options.items())

        if idx['column_names'] == ['model_call_id']:
            if idx['name'] == 'ix_usage_ledger_model_call_id':
                if idx.get('unique', False) and not is_partial:
                    exact_index_found = True
                elif is_partial:
                    raise RuntimeError(f"Conflicting index found: index '{idx['name']}' is a partial/predicate index")
                else:
                    raise RuntimeError(f"Conflicting index found: {idx['name']} targets ['model_call_id'] but is not unique")
            else:
                raise RuntimeError(f"Conflicting index found: another index {idx['name']} targets ['model_call_id']")
        elif idx['name'] == 'ix_usage_ledger_model_call_id':
            # Same name but different columns
            raise RuntimeError(f"Conflicting index found: index 'ix_usage_ledger_model_call_id' targets different columns {idx['column_names']}")

    # Check for unique constraints on model_call_id
    try:
        constraints = insp.get_unique_constraints('usage_ledger')
        for cons in constraints:
            if cons['column_names'] == ['model_call_id']:
                raise RuntimeError(f"Conflicting constraint found: unique constraint {cons.get('name')} targets ['model_call_id']")
    except NotImplementedError:
        pass

    if exact_index_found:
        # 4-2. Exact match -> no-op
        return

    op.create_index(
        "ix_usage_ledger_model_call_id",
        "usage_ledger",
        ["model_call_id"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'usage_ledger' not in tables:
        return

    indexes = insp.get_indexes('usage_ledger')

    has_exact = False
    for idx in indexes:
        if idx['name'] == 'ix_usage_ledger_model_call_id':
            dialect_options = idx.get('dialect_options', {})
            is_partial = any(k.endswith('_where') and v is not None for k, v in dialect_options.items())
            if idx['column_names'] == ['model_call_id'] and idx.get('unique', False) and not is_partial:
                has_exact = True
            else:
                raise RuntimeError(f"Cannot downgrade: index 'ix_usage_ledger_model_call_id' exists but is not the exact unique index we created")

    if has_exact:
        op.drop_index('ix_usage_ledger_model_call_id', table_name='usage_ledger')
