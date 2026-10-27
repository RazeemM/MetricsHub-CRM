"""users: roles are known values (an SSO setting could store "Read-only")

Revision ID: a1c3e5f7b9d2
Revises: 307b37b515a0
"""
from alembic import op

revision = "a1c3e5f7b9d2"
down_revision = "307b37b515a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE users SET role = CASE lower(regexp_replace(role, '[^A-Za-z]', '', 'g'))
            WHEN 'admin' THEN 'admin' WHEN 'sales' THEN 'sales' ELSE 'readonly' END
        WHERE role NOT IN ('admin', 'sales', 'readonly')
    """)


def downgrade() -> None:
    pass
