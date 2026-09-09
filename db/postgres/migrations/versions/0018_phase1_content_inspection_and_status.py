"""phase1_content_inspection_and_status

Revision ID: 0018_phase1_content_inspection_and_status
Revises: 0017_phase1_comment_version_no
Create Date: 2026-09-07 22:45:00.000000

"""
import uuid
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0018_phase1_content_inspection_and_status'
down_revision = '0017_phase1_comment_version_no'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    # 1. Add inspection_status to post_versions if not present
    if 'post_versions' in tables:
        pv_cols = [c['name'] for c in insp.get_columns('post_versions')]
        if 'inspection_status' not in pv_cols:
            op.add_column(
                'post_versions',
                sa.Column('inspection_status', sa.String(64), server_default='UNVERIFIED_CALLS_DISABLED', nullable=False)
            )

    # 2. Add inspection_status to comments if not present
    if 'comments' in tables:
        c_cols = [c['name'] for c in insp.get_columns('comments')]
        if 'inspection_status' not in c_cols:
            op.add_column(
                'comments',
                sa.Column('inspection_status', sa.String(64), server_default='UNVERIFIED_CALLS_DISABLED', nullable=False)
            )

    # 3. Create content_inspection_records table if not present
    if 'content_inspection_records' not in tables:
        op.create_table(
            'content_inspection_records',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('content_type', sa.String(32), nullable=False),
            sa.Column('content_id', sa.Uuid(), index=True, nullable=False),
            sa.Column('version_no', sa.Integer(), nullable=False),
            sa.Column('status', sa.String(64), nullable=False),
            sa.Column('detected_cutoff_ms', sa.Integer(), nullable=True),
            sa.Column('effective_cutoff_ms', sa.Integer(), nullable=True),
            sa.Column('confidence_score', sa.Float(), nullable=True),
            sa.Column('spoiler_flags', sa.JSON(), nullable=True),
            sa.Column('paid_model_calls', sa.Integer(), default=0, nullable=False),
            sa.Column('analysis_run_id', sa.Uuid(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('content_type', 'content_id', 'version_no', name='uq_inspection_type_id_ver')
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'content_inspection_records' in tables:
        op.drop_table('content_inspection_records')

    if 'comments' in tables:
        c_cols = [c['name'] for c in insp.get_columns('comments')]
        if 'inspection_status' in c_cols:
            op.drop_column('comments', 'inspection_status')

    if 'post_versions' in tables:
        pv_cols = [c['name'] for c in insp.get_columns('post_versions')]
        if 'inspection_status' in pv_cols:
            op.drop_column('post_versions', 'inspection_status')
