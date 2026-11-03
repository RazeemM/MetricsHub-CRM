"""app settings (the email sender) and Microsoft 365 sign-ins for sending email

Revision ID: b8d1f3a5c7e9
Revises: a7c9e2f4b6d8
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8d1f3a5c7e9"
down_revision = "a7c9e2f4b6d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("value", postgresql.JSONB()),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "mail_connections",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("account", sa.String(255), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=False),
        sa.Column("scopes", sa.String(500)),
        sa.Column("connected_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(1000)),
    )


def downgrade() -> None:
    op.drop_table("mail_connections")
    op.drop_table("app_settings")
