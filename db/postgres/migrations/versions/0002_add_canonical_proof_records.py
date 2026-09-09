"""add_canonical_proof_records

Revision ID: 0002_add_canonical_proof_records
Revises: 0001_initial_v7_schema
Create Date: 2026-08-19 18:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002_add_canonical_proof_records'
down_revision: Union[str, None] = '0001_initial_v7_schema'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'proof_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('proof_id', sa.String(128), unique=True, index=True, nullable=False),
        sa.Column('work_id', sa.String(64), index=True, nullable=False),
        sa.Column('edition_id', sa.String(64), nullable=False),
        sa.Column('dataset_version', sa.String(32), default='v3', nullable=False),
        sa.Column('reveal_id', sa.String(128), index=True, nullable=False),
        sa.Column('proof_type', sa.String(64), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('blind_explanation', sa.Text(), nullable=False),
        sa.Column('reveal_explanation', sa.Text(), nullable=False),
        sa.Column('evidence_chain', sa.JSON(), nullable=False),
        sa.Column('observed_premises', sa.JSON(), nullable=False),
        sa.Column('alternative_explanations', sa.JSON(), nullable=False),
        sa.Column('counterfactual_results', sa.JSON(), nullable=False),
        sa.Column('proof_strength', sa.Float(), default=0.9, nullable=False),
        sa.Column('fan_impact', sa.Float(), default=0.85, nullable=False),
        sa.Column('cache_key', sa.String(255), index=True, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)
    )


def downgrade() -> None:
    op.drop_table('proof_records')
