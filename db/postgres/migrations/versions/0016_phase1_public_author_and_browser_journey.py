"""phase1_public_author_and_browser_journey

Revision ID: 0016_phase1_public_author_and_browser_journey
Revises: 0015_v7_posts_scope_conditional_check
Create Date: 2026-09-07 16:30:00.000000

"""
import uuid
from datetime import datetime, timezone
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0016_phase1_public_author_and_browser_journey'
down_revision = '0015_v7_posts_scope_conditional_check'
branch_labels = None
depends_on = None

PUBLIC_AUTHOR_UUID = uuid.UUID('00000000-0000-4000-8000-000000000002')


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    # 1. browser_watch_progress
    if 'browser_watch_progress' not in tables:
        op.create_table(
            'browser_watch_progress',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('session_id', sa.String(64), index=True, nullable=False),
            sa.Column('work_id', sa.String(64), index=True, nullable=False),
            sa.Column('edition_id', sa.String(64), nullable=False),
            sa.Column('state', sa.String(32), default='NOT_STARTED', nullable=False),
            sa.Column('progress_ms', sa.Integer(), default=0, nullable=False),
            sa.Column('completed_reveal_ids', sa.JSON(), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('session_id', 'work_id', 'edition_id', name='uq_browser_watch_progress_session_work_edition')
        )

    # 2. browser_content_unlocks
    if 'browser_content_unlocks' not in tables:
        op.create_table(
            'browser_content_unlocks',
            sa.Column('id', sa.Uuid(), primary_key=True, default=uuid.uuid4),
            sa.Column('session_id', sa.String(64), index=True, nullable=False),
            sa.Column('content_type', sa.String(32), nullable=False),
            sa.Column('content_id', sa.Uuid(), index=True, nullable=False),
            sa.Column('version_no', sa.Integer(), default=1, nullable=False),
            sa.Column('unlocked_at', sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint('session_id', 'content_type', 'content_id', 'version_no', name='uq_browser_content_unlocks')
        )

    # 3. Seed Public Author user and profile if not present
    now = datetime.now(timezone.utc)
    users_table = sa.table(
        'users',
        sa.column('id', sa.Uuid()),
        sa.column('email_normalized', sa.String()),
        sa.column('handle', sa.String()),
        sa.column('handle_normalized', sa.String()),
        sa.column('status', sa.String()),
        sa.column('role', sa.String()),
        sa.column('account_origin', sa.String()),
        sa.column('auth_version', sa.Integer()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )
    profiles_table = sa.table(
        'profiles',
        sa.column('user_id', sa.Uuid()),
        sa.column('display_name', sa.String()),
        sa.column('bio', sa.Text()),
        sa.column('locale', sa.String()),
        sa.column('fan_depth', sa.String()),
        sa.column('created_at', sa.DateTime(timezone=True)),
        sa.column('updated_at', sa.DateTime(timezone=True)),
    )

    existing_user = bind.execute(
        sa.select(users_table.c.id).where(users_table.c.id == PUBLIC_AUTHOR_UUID)
    ).fetchone()

    if not existing_user:
        op.bulk_insert(
            users_table,
            [
                {
                    'id': PUBLIC_AUTHOR_UUID,
                    'email_normalized': 'public-author@reframe.local',
                    'handle': 'public_audience',
                    'handle_normalized': 'public_audience',
                    'status': 'ACTIVE',
                    'role': 'PUBLIC_AUTHOR',
                    'account_origin': 'SYSTEM',
                    'auth_version': 1,
                    'created_at': now,
                    'updated_at': now,
                }
            ]
        )
        op.bulk_insert(
            profiles_table,
            [
                {
                    'user_id': PUBLIC_AUTHOR_UUID,
                    'display_name': 'Public Audience',
                    'bio': 'Official public audience contributor for Reframe.',
                    'locale': 'en',
                    'fan_depth': 'CASUAL',
                    'created_at': now,
                    'updated_at': now,
                }
            ]
        )


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    tables = insp.get_table_names()

    if 'browser_content_unlocks' in tables:
        op.drop_table('browser_content_unlocks')
    if 'browser_watch_progress' in tables:
        op.drop_table('browser_watch_progress')

    profiles_table = sa.table('profiles', sa.column('user_id', sa.Uuid()))
    users_table = sa.table('users', sa.column('id', sa.Uuid()))
    bind.execute(profiles_table.delete().where(profiles_table.c.user_id == PUBLIC_AUTHOR_UUID))
    bind.execute(users_table.delete().where(users_table.c.id == PUBLIC_AUTHOR_UUID))
