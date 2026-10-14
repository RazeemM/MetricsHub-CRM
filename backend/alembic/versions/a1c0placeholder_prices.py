"""placeholder prices for all products

Adds a price for every product that has none in its brand's price books (existing installs).
Fresh installs get the same prices from app/seed.py. All values are editable in Products & pricing.

Revision ID: a1c0placeholder
Revises: 3375a61d05bb
"""
from alembic import op

revision = "a1c0placeholder"
down_revision = "3375a61d05bb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.seed import PRICE_BOOKS

    conn = op.get_bind()
    for book, (_brand, _cur, _ch, _default, prices) in PRICE_BOOKS.items():
        for sku, price in prices.items():
            conn.exec_driver_sql(
                """
                INSERT INTO price_book_entries (price_book_id, product_id, unit_price)
                SELECT pb.id, p.id, %(price)s FROM price_books pb, products p
                WHERE pb.name = %(book)s AND p.sku = %(sku)s
                ON CONFLICT (price_book_id, product_id) DO NOTHING
                """,
                {"price": price, "book": book, "sku": sku},
            )


def downgrade() -> None:
    pass  # prices may have been edited since; leave them
