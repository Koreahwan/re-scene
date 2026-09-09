"""phase1_comment_version_no

Revision ID: 0017_phase1_comment_version_no
Revises: 0016_phase1_public_author_and_browser_journey
Create Date: 2026-09-07 17:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0017_phase1_comment_version_no'
down_revision = '0016_phase1_public_author_and_browser_journey'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('comments')]
    if 'version_no' not in cols:
        op.add_column('comments', sa.Column('version_no', sa.Integer(), server_default='1', nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    cols = [c['name'] for c in insp.get_columns('comments')]
    if 'version_no' in cols:
        op.drop_column('comments', 'version_no')
