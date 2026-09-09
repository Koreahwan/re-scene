"""Durable comment-only moderation queue and bounded budget. Additive, no content rewrites."""
from alembic import op
import sqlalchemy as sa

revision = '0022_comment_moderation'
down_revision = '0021_content_views'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('comment_moderation_budgets', sa.Column('bucket', sa.String(32), primary_key=True),
        sa.Column('liability_micros', sa.Integer(), nullable=False))
    op.create_table('comment_moderation_jobs', sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('comment_id', sa.Uuid(), nullable=False), sa.Column('version_no', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(32), nullable=False), sa.Column('reserved_micros', sa.Integer(), nullable=False),
        sa.Column('actual_micros', sa.Integer(), nullable=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('comment_id', 'version_no', name='uq_comment_moderation_version'))
    op.create_index('ix_comment_moderation_jobs_comment_id', 'comment_moderation_jobs', ['comment_id'])
    op.create_index('ix_comment_moderation_jobs_status', 'comment_moderation_jobs', ['status'])


def downgrade():
    # Budget liabilities cannot safely be erased by an ordinary downgrade.
    raise RuntimeError('Preserve moderation budget history; downgrade requires an explicit archival plan.')
