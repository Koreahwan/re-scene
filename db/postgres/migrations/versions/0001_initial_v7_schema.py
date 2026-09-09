"""initial_v7_schema

Revision ID: 0001_initial_v7_schema
Revises: 
Create Date: 2026-08-19 15:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0001_initial_v7_schema'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('email_normalized', sa.String(255), unique=True, index=True, nullable=False),
        sa.Column('status', sa.String(32), default='ACTIVE', nullable=False),
        sa.Column('role', sa.String(32), default='USER', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 2. profiles
    op.create_table(
        'profiles',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('display_name', sa.String(100), nullable=False),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('locale', sa.String(10), default='en', nullable=False),
        sa.Column('fan_depth', sa.String(32), default='REGULAR', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 3. watch_progress
    op.create_table(
        'watch_progress',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('work_id', sa.String(64), nullable=False),
        sa.Column('edition_id', sa.String(64), nullable=False),
        sa.Column('state', sa.String(32), default='NOT_STARTED', nullable=False),
        sa.Column('progress_ms', sa.Integer(), default=0, nullable=False),
        sa.Column('season', sa.Integer(), nullable=True),
        sa.Column('episode', sa.Integer(), nullable=True),
        sa.Column('completed_reveal_ids', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('user_id', 'work_id', 'edition_id', name='uq_watch_progress_user_work_edition')
    )

    # 4. spoiler_preferences
    op.create_table(
        'spoiler_preferences',
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('default_mode', sa.String(16), default='STRICT', nullable=False),
        sa.Column('mask_titles', sa.Boolean(), default=True, nullable=False),
        sa.Column('mask_thumbnails', sa.Boolean(), default=True, nullable=False),
        sa.Column('mask_comments', sa.Boolean(), default=True, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 5. spoiler_scopes
    op.create_table(
        'spoiler_scopes',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('work_id', sa.String(64), index=True, nullable=False),
        sa.Column('edition_id', sa.String(64), nullable=False),
        sa.Column('minimum_progress_ms', sa.Integer(), default=0, nullable=False),
        sa.Column('required_season', sa.Integer(), nullable=True),
        sa.Column('required_episode', sa.Integer(), nullable=True),
        sa.Column('required_reveal_ids', sa.JSON(), nullable=False),
        sa.Column('severity', sa.String(32), default='MEDIUM', nullable=False),
        sa.Column('safe_title', sa.String(255), nullable=True),
        sa.Column('safe_preview', sa.String(512), nullable=True),
    )

    # 6. evidence_catalog
    op.create_table(
        'evidence_catalog',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('work_id', sa.String(64), index=True, nullable=False),
        sa.Column('edition_id', sa.String(64), nullable=False),
        sa.Column('dataset_version', sa.String(32), nullable=False),
        sa.Column('evidence_type', sa.String(32), nullable=False),
        sa.Column('evidence_id', sa.String(64), index=True, nullable=False),
        sa.Column('evidence_hash', sa.String(64), nullable=False),
        sa.Column('correction_overlay_sha', sa.String(64), nullable=True),
        sa.Column('screen_start_ms', sa.Integer(), default=0, nullable=False),
        sa.Column('screen_end_ms', sa.Integer(), default=0, nullable=False),
        sa.Column('status', sa.String(32), default='ACTIVE', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('superseded_by', sa.Uuid(), nullable=True),
        sa.UniqueConstraint('work_id', 'edition_id', 'dataset_version', 'evidence_type', 'evidence_id', name='uq_evidence_catalog_ref')
    )

    # 7. analysis_runs
    op.create_table(
        'analysis_runs',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_type', sa.String(32), default='REFRAME', nullable=False),
        sa.Column('owner_user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), index=True, nullable=True),
        sa.Column('work_id', sa.String(64), nullable=False),
        sa.Column('edition_id', sa.String(64), nullable=False),
        sa.Column('reveal_id', sa.String(64), nullable=True),
        sa.Column('status', sa.String(32), default='QUEUED', index=True, nullable=False),
        sa.Column('idempotency_key', sa.String(128), index=True, nullable=True),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('config_hash', sa.String(64), nullable=False),
        sa.Column('dataset_version', sa.String(32), nullable=False),
        sa.Column('model_id', sa.String(64), nullable=False),
        sa.Column('prompt_hash', sa.String(64), nullable=False),
        sa.Column('proof_schema_version', sa.String(16), default='1.0.0', nullable=False),
        sa.Column('cost_reserved_micros', sa.BigInteger(), default=0, nullable=False),
        sa.Column('cost_actual_micros', sa.BigInteger(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), index=True, nullable=False),
        sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_code', sa.String(64), nullable=True),
        sa.Column('failure_detail_redacted', sa.Text(), nullable=True),
    )

    # 8. analysis_run_steps
    op.create_table(
        'analysis_run_steps',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('step_type', sa.String(64), nullable=False),
        sa.Column('input_hash', sa.String(64), nullable=False),
        sa.Column('output_hash', sa.String(64), nullable=True),
        sa.Column('status', sa.String(32), default='PENDING', nullable=False),
        sa.Column('attempt', sa.Integer(), default=1, nullable=False),
        sa.Column('worker_id', sa.String(64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_code', sa.String(64), nullable=True),
        sa.Column('artifact_uri', sa.String(512), nullable=True),
    )

    # 9. analysis_run_events
    op.create_table(
        'analysis_run_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('safe_payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 10. idempotency_records
    op.create_table(
        'idempotency_records',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('principal_id', sa.String(64), index=True, nullable=False),
        sa.Column('route_key', sa.String(128), nullable=False),
        sa.Column('idempotency_key', sa.String(128), nullable=False),
        sa.Column('request_hash', sa.String(64), nullable=False),
        sa.Column('response_status', sa.Integer(), nullable=False),
        sa.Column('response_body_ref', sa.Text(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('principal_id', 'route_key', 'idempotency_key', name='uq_idempotency_principal_route_key')
    )

    # 11. usage_ledger
    op.create_table(
        'usage_ledger',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), index=True, nullable=True),
        sa.Column('analysis_run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE'), index=True, nullable=True),
        sa.Column('model_call_id', sa.String(64), nullable=False),
        sa.Column('model_id', sa.String(64), nullable=False),
        sa.Column('purpose', sa.String(64), nullable=False),
        sa.Column('input_text_tokens', sa.Integer(), default=0, nullable=False),
        sa.Column('input_image_tokens', sa.Integer(), default=0, nullable=False),
        sa.Column('output_tokens', sa.Integer(), default=0, nullable=False),
        sa.Column('reasoning_tokens', sa.Integer(), default=0, nullable=False),
        sa.Column('total_tokens', sa.Integer(), default=0, nullable=False),
        sa.Column('estimated_cost_micros', sa.BigInteger(), default=0, nullable=False),
        sa.Column('pricing_version', sa.String(32), default='2026-08-gemini', nullable=False),
        sa.Column('billing_reference', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 12. budget_reservations
    op.create_table(
        'budget_reservations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('analysis_run_id', sa.Uuid(), sa.ForeignKey('analysis_runs.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('scope', sa.String(32), default='USER', nullable=False),
        sa.Column('reserved_micros', sa.BigInteger(), default=0, nullable=False),
        sa.Column('released_micros', sa.BigInteger(), default=0, nullable=False),
        sa.Column('consumed_micros', sa.BigInteger(), default=0, nullable=False),
        sa.Column('status', sa.String(32), default='ACTIVE', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 13. audit_log
    op.create_table(
        'audit_log',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('actor_type', sa.String(32), nullable=False),
        sa.Column('actor_id', sa.String(64), index=True, nullable=False),
        sa.Column('action', sa.String(64), nullable=False),
        sa.Column('subject_type', sa.String(64), nullable=False),
        sa.Column('subject_id', sa.String(64), index=True, nullable=False),
        sa.Column('before_hash', sa.String(64), nullable=True),
        sa.Column('after_hash', sa.String(64), nullable=True),
        sa.Column('safe_metadata', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), index=True, nullable=False),
    )

    # 14. outbox_events
    op.create_table(
        'outbox_events',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('aggregate_type', sa.String(64), nullable=False),
        sa.Column('aggregate_id', sa.String(64), index=True, nullable=False),
        sa.Column('event_type', sa.String(64), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(32), default='PENDING', index=True, nullable=False),
        sa.Column('attempts', sa.Integer(), default=0, nullable=False),
        sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 15. posts
    op.create_table(
        'posts',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('author_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('work_id', sa.String(64), index=True, nullable=False),
        sa.Column('edition_id', sa.String(64), nullable=False),
        sa.Column('content_type', sa.String(32), default='FAN_THEORY', nullable=False),
        sa.Column('current_version_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(32), default='DRAFT', index=True, nullable=False),
        sa.Column('spoiler_scope_id', sa.Uuid(), sa.ForeignKey('spoiler_scopes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('ai_disclosure', sa.String(32), default='HUMAN', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    )

    # 16. post_versions
    op.create_table(
        'post_versions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('post_id', sa.Uuid(), sa.ForeignKey('posts.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('version_no', sa.Integer(), default=1, nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('body_markdown', sa.Text(), nullable=False),
        sa.Column('body_sanitized_html', sa.Text(), nullable=False),
        sa.Column('change_summary', sa.String(255), nullable=True),
        sa.Column('created_by', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('post_id', 'version_no', name='uq_post_version_no')
    )

    # 17. claims
    op.create_table(
        'claims',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('post_id', sa.Uuid(), sa.ForeignKey('posts.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('current_version_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(32), default='ACTIVE', nullable=False),
    )

    # 18. claim_versions
    op.create_table(
        'claim_versions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('claim_id', sa.Uuid(), sa.ForeignKey('claims.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('classification', sa.String(32), default='STRONG_INTERPRETATION', nullable=False),
        sa.Column('confidence_label', sa.String(32), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 19. post_evidence_links
    op.create_table(
        'post_evidence_links',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('post_version_id', sa.Uuid(), sa.ForeignKey('post_versions.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('claim_version_id', sa.Uuid(), sa.ForeignKey('claim_versions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('evidence_catalog_id', sa.Uuid(), sa.ForeignKey('evidence_catalog.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('relation', sa.String(32), default='SUPPORTS', nullable=False),
        sa.Column('annotation', sa.Text(), nullable=True),
        sa.Column('display_order', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 20. comments
    op.create_table(
        'comments',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('post_id', sa.Uuid(), sa.ForeignKey('posts.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('parent_comment_id', sa.Uuid(), sa.ForeignKey('comments.id', ondelete='CASCADE'), nullable=True),
        sa.Column('author_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('comment_type', sa.String(32), default='COMMENT', nullable=False),
        sa.Column('body_markdown', sa.Text(), nullable=False),
        sa.Column('body_sanitized_html', sa.Text(), nullable=False),
        sa.Column('spoiler_scope_id', sa.Uuid(), sa.ForeignKey('spoiler_scopes.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(32), default='PUBLISHED', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 21. counterclaims
    op.create_table(
        'counterclaims',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('post_id', sa.Uuid(), sa.ForeignKey('posts.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('target_claim_id', sa.Uuid(), sa.ForeignKey('claims.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('challenged_premise', sa.Text(), nullable=False),
        sa.Column('alternative_explanation', sa.Text(), nullable=False),
        sa.Column('status', sa.String(32), default='OPEN', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 22. counterclaim_evidence_links
    op.create_table(
        'counterclaim_evidence_links',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('counterclaim_id', sa.Uuid(), sa.ForeignKey('counterclaims.id', ondelete='CASCADE'), nullable=False),
        sa.Column('evidence_catalog_id', sa.Uuid(), sa.ForeignKey('evidence_catalog.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('relation', sa.String(32), default='SUPPORTS_COUNTERCLAIM', nullable=False),
    )

    # 23. reactions
    op.create_table(
        'reactions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('subject_type', sa.String(32), index=True, nullable=False),
        sa.Column('subject_id', sa.Uuid(), index=True, nullable=False),
        sa.Column('user_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('reaction_type', sa.String(32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('subject_type', 'subject_id', 'user_id', 'reaction_type', name='uq_reactions_subject_user_type')
    )

    # 24. reports
    op.create_table(
        'reports',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('reporter_id', sa.Uuid(), sa.ForeignKey('users.id', ondelete='CASCADE'), index=True, nullable=False),
        sa.Column('subject_type', sa.String(32), nullable=False),
        sa.Column('subject_id', sa.Uuid(), index=True, nullable=False),
        sa.Column('category', sa.String(64), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(32), default='PENDING', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # 25. moderation_cases
    op.create_table(
        'moderation_cases',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('report_id', sa.Uuid(), sa.ForeignKey('reports.id', ondelete='SET NULL'), nullable=True),
        sa.Column('subject_type', sa.String(32), nullable=False),
        sa.Column('subject_id', sa.Uuid(), nullable=False),
        sa.Column('assigned_to', sa.Uuid(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('decision', sa.String(64), nullable=True),
        sa.Column('action', sa.String(64), nullable=True),
        sa.Column('reason_code', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table('moderation_cases')
    op.drop_table('reports')
    op.drop_table('reactions')
    op.drop_table('counterclaim_evidence_links')
    op.drop_table('counterclaims')
    op.drop_table('comments')
    op.drop_table('post_evidence_links')
    op.drop_table('claim_versions')
    op.drop_table('claims')
    op.drop_table('post_versions')
    op.drop_table('posts')
    op.drop_table('outbox_events')
    op.drop_table('audit_log')
    op.drop_table('budget_reservations')
    op.drop_table('usage_ledger')
    op.drop_table('idempotency_records')
    op.drop_table('analysis_run_events')
    op.drop_table('analysis_run_steps')
    op.drop_table('analysis_runs')
    op.drop_table('evidence_catalog')
    op.drop_table('spoiler_scopes')
    op.drop_table('spoiler_preferences')
    op.drop_table('watch_progress')
    op.drop_table('profiles')
    op.drop_table('users')
