"""v7_synthetic_audience_lab

Revision ID: 0006_v7_synthetic_lab
Revises: 0005_v7_auth_and_checkpoint
Create Date: 2026-08-21 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0006_v7_synthetic_lab'
down_revision: Union[str, None] = '0005_v7_auth_and_checkpoint'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add account_origin to users
    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('account_origin', sa.String(length=32), server_default='HUMAN', nullable=False))

    # 2. Create synthetic_personas table
    op.create_table(
        'synthetic_personas',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('source_dataset', sa.String(length=128), nullable=False),
        sa.Column('source_revision', sa.String(length=64), nullable=False),
        sa.Column('source_persona_id_hash', sa.String(length=64), nullable=False),
        sa.Column('locale', sa.String(length=16), server_default='en_US', nullable=False),
        sa.Column('display_alias', sa.String(length=64), nullable=False),
        sa.Column('demographic_context', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('fan_traits', sa.JSON(), server_default='{}', nullable=False),
        sa.Column('sampling_weight', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('is_repro_sample', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_persona_id_hash', name='uq_synthetic_persona_hash')
    )
    op.create_index('ix_synthetic_personas_hash', 'synthetic_personas', ['source_persona_id_hash'])

    # 3. Create synthetic_content_provenance table
    op.create_table(
        'synthetic_content_provenance',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('simulation_run_id', sa.Uuid(), nullable=True),
        sa.Column('persona_id', sa.Uuid(), nullable=False),
        sa.Column('subject_type', sa.String(length=32), nullable=False),
        sa.Column('subject_id', sa.Uuid(), nullable=False),
        sa.Column('content_origin', sa.String(length=32), server_default='SYNTHETIC_DEMO', nullable=False),
        sa.Column('generator_mode', sa.String(length=64), server_default='DETERMINISTIC_TEMPLATE_V1', nullable=False),
        sa.Column('content_version', sa.String(length=32), server_default='v1.0', nullable=False),
        sa.Column('stable_content_key', sa.String(length=128), nullable=False),
        sa.Column('source_dataset', sa.String(length=128), server_default='nvidia/Nemotron-Personas-USA', nullable=False),
        sa.Column('source_revision', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['simulation_run_id'], ['analysis_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['persona_id'], ['synthetic_personas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('stable_content_key', name='uq_synthetic_content_stable_key')
    )
    op.create_index('ix_synthetic_provenance_run_id', 'synthetic_content_provenance', ['simulation_run_id'])
    op.create_index('ix_synthetic_provenance_persona_id', 'synthetic_content_provenance', ['persona_id'])
    op.create_index('ix_synthetic_provenance_subject', 'synthetic_content_provenance', ['subject_type', 'subject_id'])
    op.create_index('ix_synthetic_provenance_key', 'synthetic_content_provenance', ['stable_content_key'])


def downgrade() -> None:
    op.drop_table('synthetic_content_provenance')
    op.drop_table('synthetic_personas')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('account_origin')
