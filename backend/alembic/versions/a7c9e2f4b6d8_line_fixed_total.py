"""line items: a fixed total (the total charge of an imported quote line)

Revision ID: a7c9e2f4b6d8
Revises: f3b7d9e1a2c5
"""
import sqlalchemy as sa
from alembic import op

revision = "a7c9e2f4b6d8"
down_revision = "f3b7d9e1a2c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("opportunity_line_items", sa.Column("fixed_total", sa.Numeric(14, 2)))


def downgrade() -> None:
    op.drop_column("opportunity_line_items", "fixed_total")
