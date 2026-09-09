"""Review uniqueness, wishlist, sanitized profile photos and author spoiler marks.

Additive migration: preserves all existing posts, comments and profiles.
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_product_engagement"
down_revision = "0019_phase1_rating_and_author_cutoff"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    for table in ("post_versions", "comments"):
        if "contains_spoilers" not in {col["name"] for col in inspector.get_columns(table)}:
            op.add_column(table, sa.Column("contains_spoilers", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "film_review_slots" not in tables:
        op.create_table("film_review_slots",
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("work_id", sa.String(64), primary_key=True),
            sa.Column("post_id", sa.Uuid(), sa.ForeignKey("posts.id", ondelete="SET NULL"), nullable=True))
    if "film_wishlist" not in tables:
        op.create_table("film_wishlist",
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("work_id", sa.String(64), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    if "profile_photos" not in tables:
        op.create_table("profile_photos",
            sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("png", sa.LargeBinary(), nullable=False))


def downgrade():
    op.drop_table("profile_photos")
    op.drop_table("film_wishlist")
    op.drop_table("film_review_slots")
    op.drop_column("comments", "contains_spoilers")
    op.drop_column("post_versions", "contains_spoilers")
