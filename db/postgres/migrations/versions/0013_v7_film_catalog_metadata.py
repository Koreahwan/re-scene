"""v7 film catalog metadata

Revision ID: 0013_v7_film_catalog_metadata
Revises: 0012_v7_audit_log_sqlite_pk
Create Date: 2026-09-06 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0013_v7_film_catalog_metadata'
down_revision = '0012_v7_audit_log_sqlite_pk'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'film_catalog' not in tables:
        op.create_table(
            'film_catalog',
            sa.Column('movie_id', sa.String(length=64), nullable=False),
            sa.Column('source_qid', sa.String(length=32), nullable=False),
            sa.Column('title_en', sa.String(length=255), nullable=False),
            sa.Column('title_ko', sa.String(length=255), nullable=True),
            sa.Column('year', sa.Integer(), nullable=False),
            sa.Column('description_en', sa.Text(), nullable=True),
            sa.Column('description_ko', sa.Text(), nullable=True),
            sa.Column('runtime_minutes', sa.Integer(), nullable=True),
            sa.Column('directors', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('cast_members', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('genres', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('countries', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('languages', sa.JSON(), nullable=False, server_default='[]'),
            sa.Column('core_demo_supported', sa.Boolean(), nullable=False, server_default='false'),
            sa.Column('poster_local_path', sa.String(length=255), nullable=True),
            sa.Column('poster_source_filename', sa.String(length=255), nullable=True),
            sa.Column('poster_sha256', sa.String(length=64), nullable=True),
            sa.Column('poster_license', sa.String(length=128), nullable=True),
            sa.Column('source_revision', sa.BigInteger(), nullable=False),
            sa.Column('source_url', sa.String(length=255), nullable=False),
            sa.Column('fetched_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
            sa.PrimaryKeyConstraint('movie_id'),
            sa.UniqueConstraint('source_qid')
        )
        op.create_index('ix_film_catalog_movie_id', 'film_catalog', ['movie_id'], unique=False)
        op.create_index('ix_film_catalog_source_qid', 'film_catalog', ['source_qid'], unique=True)
        op.create_index('ix_film_catalog_title_en', 'film_catalog', ['title_en'], unique=False)
        op.create_index('ix_film_catalog_year', 'film_catalog', ['year'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'film_catalog' in tables:
        op.drop_index('ix_film_catalog_year', table_name='film_catalog')
        op.drop_index('ix_film_catalog_title_en', table_name='film_catalog')
        op.drop_index('ix_film_catalog_source_qid', table_name='film_catalog')
        op.drop_index('ix_film_catalog_movie_id', table_name='film_catalog')
        op.drop_table('film_catalog')
