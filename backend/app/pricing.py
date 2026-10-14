"""Deal value calculation.

Recurring line:  quantity x unit price (per month) x term months x (1 - discount%)
One-time line:   quantity x unit price x (1 - discount%)

TCV  = sum of all line totals
ARR  = sum over recurring lines of (line total / term months x 12)
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


def _d(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))


def line_total(quantity, unit_price, discount_pct, term_months: int | None, billing_type: str) -> Decimal:
    qty, price, disc = _d(quantity), _d(unit_price), _d(discount_pct)
    if disc < 0 or disc > 100:
        raise ValueError("discount must be between 0 and 100")
    factor = (Decimal(100) - disc) / Decimal(100)
    total = qty * price * factor
    if billing_type == "recurring":
        total *= Decimal(term_months or 0)
    return total.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass
class Totals:
    tcv: Decimal
    arr: Decimal
    recurring: Decimal
    one_time: Decimal


def compute_totals(lines, default_term: int) -> Totals:
    """`lines` are objects with quantity, unit_price, discount_pct, term_months, billing_type.

    Sets `line_total` on each line and returns aggregated totals.
    """
    recurring = one_time = arr = Decimal(0)
    for ln in lines:
        term = ln.term_months or default_term
        ln.line_total = line_total(ln.quantity, ln.unit_price, ln.discount_pct, term, ln.billing_type)
        if ln.billing_type == "recurring":
            recurring += ln.line_total
            if term:
                arr += ln.line_total / Decimal(term) * Decimal(12)
        else:
            one_time += ln.line_total
    return Totals(
        tcv=(recurring + one_time).quantize(CENT),
        arr=arr.quantize(CENT, rounding=ROUND_HALF_UP),
        recurring=recurring.quantize(CENT),
        one_time=one_time.quantize(CENT),
    )


def months_between(start, end) -> int:
    """Whole months covered by a contract, end date inclusive.

    2026-01-01 -> 2026-12-31 = 12 months; 2026-03-15 -> 2027-03-14 = 12 months.
    """
    import datetime as _dt

    end = end + _dt.timedelta(days=1)
    months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        months -= 1
    return max(months, 0)
