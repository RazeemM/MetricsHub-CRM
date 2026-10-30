import datetime as dt
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.pricing import compute_totals, line_total, months_between


def test_recurring_line():
    # 100 hosts x $15/month x 12 months x (1 - 10%) = 16,200
    assert line_total(100, "15", 10, 12, "recurring") == Decimal("16200.00")


def test_one_time_line_ignores_term():
    assert line_total(3, "1500", 0, 36, "one_time") == Decimal("4500.00")


def test_deal_total_line_is_not_multiplied_by_term():
    assert line_total(1, "120000", 0, 36, "recurring", "deal_total") == Decimal("120000.00")
    t = compute_totals([SimpleNamespace(quantity=Decimal(1), unit_price=Decimal(120000), discount_pct=Decimal(0),
                                        term_months=None, billing_type="recurring", unit="deal_total")], 24)
    assert (t.tcv, t.arr) == (Decimal("120000.00"), Decimal("60000.00"))


def test_fixed_total_is_the_line_value():
    # an imported quote line: list price and discount for reference, worth its total charge
    assert line_total(984, "31.24", "94.22", 12, "recurring", None, "10668") == Decimal("10668.00")


def test_rounding_half_up():
    assert line_total(1, "0.125", 0, 1, "recurring") == Decimal("0.13")


def test_invalid_discount():
    with pytest.raises(ValueError):
        line_total(1, 1, 120, 12, "recurring")


def test_totals_with_mixed_terms():
    lines = [
        SimpleNamespace(quantity=Decimal(100), unit_price=Decimal(15), discount_pct=Decimal(0), term_months=None,
                        billing_type="recurring"),
        SimpleNamespace(quantity=Decimal(50), unit_price=Decimal(10), discount_pct=Decimal(0), term_months=6,
                        billing_type="recurring"),
        SimpleNamespace(quantity=Decimal(2), unit_price=Decimal(1000), discount_pct=Decimal(0), term_months=None,
                        billing_type="one_time"),
    ]
    t = compute_totals(lines, default_term=36)
    assert lines[0].line_total == Decimal("54000.00")  # 100*15*36
    assert lines[1].line_total == Decimal("3000.00")  # 50*10*6
    assert t.tcv == Decimal("59000.00")
    assert t.arr == Decimal("24000.00")  # 18000 + 6000
    assert t.one_time == Decimal("2000.00")


@pytest.mark.parametrize("start,end,months", [
    (dt.date(2026, 1, 1), dt.date(2026, 12, 31), 12),
    (dt.date(2026, 3, 15), dt.date(2027, 3, 14), 12),
    (dt.date(2026, 1, 31), dt.date(2029, 1, 30), 36),
    (dt.date(2026, 1, 1), dt.date(2026, 1, 31), 1),
])
def test_months_between(start, end, months):
    assert months_between(start, end) == months
