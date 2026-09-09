"""v7_auth_operations_saga

Revision ID: 0009_v7_auth_operations_saga
Revises: 0008_v7_auth_version_and_user_handle
Create Date: 2026-08-23 03:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = '0009_v7_auth_operations_saga'
down_revision: Union[str, None] = '0008_v7_auth_version_and_user_handle'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'auth_operations' not in tables:
        op.create_table(
            'auth_operations',
            sa.Column('id', sa.Uuid(), nullable=False),
            sa.Column('idempotency_key', sa.String(length=128), nullable=False),
            sa.Column('operation_type', sa.String(length=32), nullable=False),
            sa.Column('email_hash', sa.String(length=64), nullable=False),
            sa.Column('ticket_hash', sa.String(length=64), nullable=False),
            sa.Column('status', sa.String(length=32), server_default='STARTED', nullable=False),
            sa.Column('user_id', sa.Uuid(), nullable=True),
            sa.Column('result_json', sa.JSON(), nullable=True),
            sa.Column('failure_code', sa.String(length=64), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index('ix_auth_operations_idempotency_key', 'auth_operations', ['idempotency_key'], unique=True)
        op.create_index('ix_auth_operations_email_hash', 'auth_operations', ['email_hash'])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'auth_operations' in tables:
        op.drop_index('ix_auth_operations_email_hash', table_name='auth_operations')
        op.drop_index('ix_auth_operations_idempotency_key', table_name='auth_operations')
        op.drop_table('auth_operations')
