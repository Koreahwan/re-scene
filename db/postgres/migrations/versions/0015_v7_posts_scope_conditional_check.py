"""v7 posts scope conditional check

Revision ID: 0015_v7_posts_scope_conditional_check
Revises: 0014_v7_magazine_work_id_nullable
Create Date: 2026-09-07 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0015_v7_posts_scope_conditional_check'
down_revision = '0014_v7_magazine_work_id_nullable'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('posts') as batch_op:
        batch_op.create_check_constraint(
            'ck_post_work_edition_scope',
            "content_type = 'MAGAZINE_ARTICLE' OR (work_id IS NOT NULL AND edition_id IS NOT NULL)"
        )


def downgrade() -> None:
    with op.batch_alter_table('posts') as batch_op:
        batch_op.drop_constraint('ck_post_work_edition_scope', type_='check')
