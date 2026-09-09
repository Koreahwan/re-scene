"""v7_auth_version_and_user_handle

Revision ID: 0008_v7_auth_version_and_user_handle
Revises: 0007_v7_synthetic_persona_demo_user_mapping
Create Date: 2026-08-23 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision: str = '0008_v7_auth_version_and_user_handle'
down_revision: Union[str, None] = '0007_v7_synthetic_persona_demo_user_mapping'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'users' in tables:
        columns = [c['name'] for c in insp.get_columns('users')]
        with op.batch_alter_table('users') as batch_op:
            if 'auth_version' not in columns:
                batch_op.add_column(sa.Column('auth_version', sa.Integer(), server_default='1', nullable=False))
            if 'handle' not in columns:
                batch_op.add_column(sa.Column('handle', sa.String(length=64), nullable=True))
            if 'handle_normalized' not in columns:
                batch_op.add_column(sa.Column('handle_normalized', sa.String(length=64), nullable=True))
                batch_op.create_unique_constraint('uq_users_handle_normalized', ['handle_normalized'])
                batch_op.create_index('ix_users_handle_normalized', ['handle_normalized'])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'users' in tables:
        columns = [c['name'] for c in insp.get_columns('users')]
        with op.batch_alter_table('users') as batch_op:
            if 'handle_normalized' in columns:
                batch_op.drop_index('ix_users_handle_normalized')
                batch_op.drop_constraint('uq_users_handle_normalized', type_='unique')
                batch_op.drop_column('handle_normalized')
            if 'handle' in columns:
                batch_op.drop_column('handle')
            if 'auth_version' in columns:
                batch_op.drop_column('auth_version')
