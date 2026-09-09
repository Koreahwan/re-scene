"""v7_auth_and_step_checkpoint

Revision ID: 0005_v7_auth_and_checkpoint
Revises: 0004_r4_1_final_sync
Create Date: 2026-08-21 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0005_v7_auth_and_checkpoint'
down_revision: Union[str, None] = '0004_r4_1_final_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create user_credentials table
    op.create_table(
        'user_credentials',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('password_algorithm', sa.String(length=32), server_default='argon2id', nullable=False),
        sa.Column('password_updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('failed_attempt_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id')
    )

    # 2. Add output_json column to analysis_run_steps for durable retrieval checkpoints
    with op.batch_alter_table('analysis_run_steps') as batch_op:
        batch_op.add_column(sa.Column('output_json', sa.JSON(), server_default='{}', nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('analysis_run_steps') as batch_op:
        batch_op.drop_column('output_json')

    op.drop_table('user_credentials')
