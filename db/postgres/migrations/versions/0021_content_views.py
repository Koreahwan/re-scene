"""Anonymous page-view events for lifetime and rolling seven-day rankings."""
from alembic import op
import sqlalchemy as sa

revision = "0021_content_views"
down_revision = "0020_product_engagement"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("content_views",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("content_id", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("viewed_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_content_views_lookup", "content_views", ["kind", "content_id", "viewed_at"])


def downgrade():
    op.drop_table("content_views")
