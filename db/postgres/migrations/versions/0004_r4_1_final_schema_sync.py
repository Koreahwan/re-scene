"""r4_1_final_schema_sync

Revision ID: 0004_r4_1_final_sync
Revises: 0003_r4_schema_sync
Create Date: 2026-08-20 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0004_r4_1_final_sync'
down_revision: Union[str, None] = '0003_r4_schema_sync'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add before_state and after_state to counterfactual_run_records
    with op.batch_alter_table('counterfactual_run_records') as batch_op:
        batch_op.add_column(sa.Column('before_state', sa.JSON(), server_default='{}', nullable=True))
        batch_op.add_column(sa.Column('after_state', sa.JSON(), server_default='{}', nullable=True))
        batch_op.create_unique_constraint('uq_counterfactual_experiment_id', ['experiment_id'])

    # 2. Add any missing JSON columns to analysis_runs
    with op.batch_alter_table('analysis_runs') as batch_op:
        batch_op.add_column(sa.Column('proof_ids', sa.JSON(), server_default='[]', nullable=True))
        batch_op.add_column(sa.Column('config_json', sa.JSON(), server_default='{}', nullable=True))
        batch_op.add_column(sa.Column('result_json', sa.JSON(), server_default='{}', nullable=True))

    # 3. Add model_call_ids to analysis_run_steps
    with op.batch_alter_table('analysis_run_steps') as batch_op:
        batch_op.add_column(sa.Column('model_call_ids', sa.JSON(), server_default='[]', nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('analysis_run_steps') as batch_op:
        batch_op.drop_column('model_call_ids')

    with op.batch_alter_table('analysis_runs') as batch_op:
        batch_op.drop_column('result_json')
        batch_op.drop_column('config_json')
        batch_op.drop_column('proof_ids')

    with op.batch_alter_table('counterfactual_run_records') as batch_op:
        batch_op.drop_constraint('uq_counterfactual_experiment_id', type_='unique')
        batch_op.drop_column('after_state')
        batch_op.drop_column('before_state')
