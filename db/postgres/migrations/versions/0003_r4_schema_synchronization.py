"""r4_schema_synchronization

Revision ID: 0003_r4_schema_sync
Revises: 0002_add_canonical_proof_records
Create Date: 2026-08-19 20:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003_r4_schema_sync'
down_revision: Union[str, None] = '0002_add_canonical_proof_records'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add missing metadata columns to proof_records
    with op.batch_alter_table('proof_records') as batch_op:
        batch_op.add_column(sa.Column('human_review_status', sa.String(32), server_default='NOT_REVIEWED', nullable=False))
        batch_op.add_column(sa.Column('presentation_status', sa.String(32), server_default='PUBLIC', nullable=False))
        batch_op.add_column(sa.Column('trust_namespace', sa.String(32), server_default='ENGINE_INFERENCE', nullable=False))
        batch_op.add_column(sa.Column('trust_label', sa.String(64), server_default='Engine-supported interpretation', nullable=False))
        batch_op.add_column(sa.Column('generation_mode', sa.String(64), server_default='OFFLINE_CANONICAL_FIXTURE', nullable=False))
        batch_op.add_column(sa.Column('asset_sha256', sa.String(64), server_default='8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948', nullable=False))
        batch_op.add_column(sa.Column('correction_overlay_sha', sa.String(64), server_default='8bb196344ab03a29e90dd62a08a318329560582c69fafe36aac4354d40f64948', nullable=False))
        batch_op.add_column(sa.Column('evidence_bundle_hash', sa.String(64), server_default='default_evidence_bundle', nullable=False))
        batch_op.add_column(sa.Column('model_id', sa.String(64), server_default='gemini-2.5-flash', nullable=False))
        batch_op.add_column(sa.Column('prompt_hash', sa.String(64), server_default='prompt_v7_canonical', nullable=False))
        batch_op.add_column(sa.Column('retrieval_config_hash', sa.String(64), server_default='5channel_retrieval_v7', nullable=False))
        batch_op.add_column(sa.Column('proof_schema_version', sa.String(16), server_default='1.0.0', nullable=False))

    # 2. Create model_call_claims table
    op.create_table(
        'model_call_claims',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('model_call_id', sa.String(128), unique=True, index=True, nullable=False),
        sa.Column('analysis_run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('model_id', sa.String(64), nullable=False),
        sa.Column('role', sa.String(64), server_default='REASONING', nullable=False),
        sa.Column('state', sa.String(32), server_default='CLAIMED', nullable=False),
        sa.Column('estimated_cost_micros', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('actual_cost_micros', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True)
    )

    # 3. Create counterfactual_run_records table
    op.create_table(
        'counterfactual_run_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('experiment_id', sa.String(128), index=True, nullable=False),
        sa.Column('proof_id', sa.String(128), index=True, nullable=False),
        sa.Column('proof_input_hash', sa.String(64), nullable=False),
        sa.Column('experiment_type', sa.String(64), nullable=False),
        sa.Column('control_hash', sa.String(64), nullable=False),
        sa.Column('result_hash', sa.String(64), nullable=False),
        sa.Column('before_score', sa.Float(), nullable=False),
        sa.Column('after_score', sa.Float(), nullable=False),
        sa.Column('delta', sa.Float(), nullable=False),
        sa.Column('broken_obligations', sa.JSON(), nullable=False),
        sa.Column('is_robust', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)
    )


def downgrade() -> None:
    op.drop_table('counterfactual_run_records')
    op.drop_table('model_call_claims')
    with op.batch_alter_table('proof_records') as batch_op:
        batch_op.drop_column('proof_schema_version')
        batch_op.drop_column('retrieval_config_hash')
        batch_op.drop_column('prompt_hash')
        batch_op.drop_column('model_id')
        batch_op.drop_column('evidence_bundle_hash')
        batch_op.drop_column('correction_overlay_sha')
        batch_op.drop_column('asset_sha256')
        batch_op.drop_column('generation_mode')
        batch_op.drop_column('trust_label')
        batch_op.drop_column('trust_namespace')
        batch_op.drop_column('presentation_status')
        batch_op.drop_column('human_review_status')
