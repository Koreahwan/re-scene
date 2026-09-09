"""phase1_rating_and_author_cutoff

Revision ID: 0019_phase1_rating_and_author_cutoff
Revises: 0018_phase1_content_inspection_and_status
Create Date: 2026-09-08 02:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0019_phase1_rating_and_author_cutoff'
down_revision = '0018_phase1_content_inspection_and_status'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    # 1. Add rating and author_cutoff_ms to post_versions if not present
    if 'post_versions' in tables:
        pv_cols = [c['name'] for c in insp.get_columns('post_versions')]
        if 'rating' not in pv_cols:
            op.add_column(
                'post_versions',
                sa.Column('rating', sa.Integer(), nullable=True)
            )
        if 'author_cutoff_ms' not in pv_cols:
            op.add_column(
                'post_versions',
                sa.Column('author_cutoff_ms', sa.BigInteger(), nullable=True)
            )

    # 2. Add author_cutoff_ms to comments if not present
    if 'comments' in tables:
        c_cols = [c['name'] for c in insp.get_columns('comments')]
        if 'author_cutoff_ms' not in c_cols:
            op.add_column(
                'comments',
                sa.Column('author_cutoff_ms', sa.BigInteger(), nullable=True)
            )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'comments' in tables:
        c_cols = [c['name'] for c in insp.get_columns('comments')]
        if 'author_cutoff_ms' in c_cols:
            op.drop_column('comments', 'author_cutoff_ms')

    if 'post_versions' in tables:
        pv_cols = [c['name'] for c in insp.get_columns('post_versions')]
        if 'author_cutoff_ms' in pv_cols:
            op.drop_column('post_versions', 'author_cutoff_ms')
        if 'rating' in pv_cols:
            op.drop_column('post_versions', 'rating')
