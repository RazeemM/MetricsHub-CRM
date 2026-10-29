"""website tracking: sites carrying the tracking code, their visitors and events

Revision ID: f3b7d9e1a2c5
Revises: e8a4c6f2b1d7
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f3b7d9e1a2c5"
down_revision = "e8a4c6f2b1d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tracking_sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("domains", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("brand_id", sa.Integer(), sa.ForeignKey("brands.id", ondelete="SET NULL")),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("lead_source", sa.String(40), nullable=False, server_default="website_contact"),
        sa.Column("track_utm", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("track_params", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("capture_forms", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("require_consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("respect_dnt", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_hit_at", sa.DateTime(timezone=True)),
        sa.Column("last_hit_url", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "web_visitors",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("tracking_sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("vid", sa.String(40), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_views", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_touch", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("last_touch", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("user_agent", sa.String(255)),
        sa.UniqueConstraint("site_id", "vid"),
    )
    op.create_index("ix_web_visitors_contact_id", "web_visitors", ["contact_id"])
    op.create_index("ix_web_visitors_last_seen", "web_visitors", ["last_seen"])
    op.create_table(
        "web_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("site_id", sa.Integer(), sa.ForeignKey("tracking_sites.id", ondelete="CASCADE"), nullable=False),
        sa.Column("visitor_id", sa.Integer(), sa.ForeignKey("web_visitors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("contact_id", sa.Integer(), sa.ForeignKey("contacts.id", ondelete="SET NULL")),
        sa.Column("session", sa.String(40)),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(255)),
        sa.Column("url", sa.String(1000)),
        sa.Column("referrer", sa.String(1000)),
        sa.Column("props", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_web_events_visitor_id", "web_events", ["visitor_id"])
    op.create_index("ix_web_events_contact", "web_events", ["contact_id", "created_at"])
    op.create_index("ix_web_events_site_time", "web_events", ["site_id", "created_at"])


def downgrade() -> None:
    op.drop_table("web_events")
    op.drop_table("web_visitors")
    op.drop_table("tracking_sites")
