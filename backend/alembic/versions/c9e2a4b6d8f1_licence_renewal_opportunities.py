"""licences: the renewal opportunity opened for each licence's renewal

Revision ID: c9e2a4b6d8f1
Revises: b8d1f3a5c7e9
"""
import sqlalchemy as sa
from alembic import op

revision = "c9e2a4b6d8f1"
down_revision = "b8d1f3a5c7e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("entitlements", sa.Column("renewal_opportunity_id", sa.Integer(),
                                            sa.ForeignKey("opportunities.id", ondelete="SET NULL")))


def downgrade() -> None:
    op.drop_column("entitlements", "renewal_opportunity_id")
