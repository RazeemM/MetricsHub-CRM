"""quote email wording per brand

Revision ID: b7e3f0c21d44
Revises: adaa31ad6391
Create Date: 2026-10-15 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e3f0c21d44'
down_revision: Union[str, Sequence[str], None] = 'adaa31ad6391'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.quotes import DEFAULT_EMAIL_BODY, DEFAULT_EMAIL_SUBJECT

    op.add_column('quote_templates', sa.Column('email_subject', sa.String(length=255), nullable=True))
    op.add_column('quote_templates', sa.Column('email_body', sa.Text(), nullable=True))
    op.execute(sa.text("UPDATE quote_templates SET email_subject = :s, email_body = :b")
               .bindparams(s=DEFAULT_EMAIL_SUBJECT, b=DEFAULT_EMAIL_BODY))


def downgrade() -> None:
    op.drop_column('quote_templates', 'email_body')
    op.drop_column('quote_templates', 'email_subject')
