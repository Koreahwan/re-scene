"""v7 magazine work_id nullable

Revision ID: 0014_v7_magazine_work_id_nullable
Revises: 0013_v7_film_catalog_metadata
Create Date: 2026-09-07 02:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0014_v7_magazine_work_id_nullable'
down_revision = '0013_v7_film_catalog_metadata'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('posts') as batch_op:
        batch_op.alter_column('work_id', existing_type=sa.String(length=64), nullable=True)
        batch_op.alter_column('edition_id', existing_type=sa.String(length=64), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('posts') as batch_op:
        batch_op.alter_column('work_id', existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column('edition_id', existing_type=sa.String(length=64), nullable=False)
