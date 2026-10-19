"""Licence insights: renewals at risk, retention (NRR), reseller scorecard, credit memos, whitespace.

Revenue "per year" spreads each invoice line over its service period (a 3-year prepaid licence counts a third in each
year), so retention compares what customers pay for each year, not when BMC happened to invoice them.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .entitlements import holdings
from .models import Account, Activity, Entitlement, Opportunity, Pipeline, Stage, User
from .product_families import family
from .regions import region_of

DIRECT = "Direct (no reseller)"
ZERO = Decimal(0)


@dataclass
class Line:
    e: Entitlement
    account: str
    region: str
    reseller: str
    owner: str | None


def load(db: Session) -> list[Line]:
    rows = db.execute(select(Entitlement, Account).join(Account, Entitlement.account_id == Account.id)).all()
    resellers = {a.id: a.name for a in db.scalars(select(Account).where(
        Account.id.in_({e.reseller_id for e, _ in rows if e.reseller_id})))}
    owners = {u.id: u.full_name for u in db.scalars(select(User))}
    # region from the report's Sold To Country on the line; the account's country only for licences added by hand
    return [Line(e, a.name, region_of(e.country or a.country, a.region), resellers.get(e.reseller_id, DIRECT),
                 owners.get(a.owner_id)) for e, a in rows]


def _date(e: Entitlement) -> dt.date | None:
    return e.document_date or e.start_date


def per_year(e: Entitlement) -> dict[int, Decimal]:
    """The line's net amount spread over its service period by days; undated or perpetual lines count in one year."""
    if e.net_amount is None:
        return {}
    start, end = e.start_date, e.end_date
    if not start or not end or end <= start:
        d = _date(e)
        return {d.year: e.net_amount} if d else {}
    days = (end - start).days + 1
    out: dict[int, Decimal] = {}
    for y in range(start.year, end.year + 1):
        a, b = max(start, dt.date(y, 1, 1)), min(end, dt.date(y, 12, 31))
        out[y] = e.net_amount * Decimal((b - a).days + 1) / Decimal(days)
    return out


def _r(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"))


# ---------------------------------------------------------------- 4. renewals at risk
def renewals_at_risk(db: Session, months: int = 6, today: dt.date | None = None) -> list[dict]:
    """Licences renewing in the next `months`, most valuable first, with what is missing to secure them."""
    today = today or dt.date.today()
    horizon = today + dt.timedelta(days=round(months * 30.44))
    lines = {ln.e.id: ln for ln in load(db)}
    open_renewal = set(db.scalars(
        select(Opportunity.account_id).join(Stage, Opportunity.stage_id == Stage.id)
        .join(Pipeline, Opportunity.pipeline_id == Pipeline.id)
        .where(Stage.kind == "open", Pipeline.kind == "renewal")))
    recent = today - dt.timedelta(days=90)
    last_activity = dict(db.execute(select(Activity.account_id, func.max(Activity.created_at))
                                    .where(Activity.account_id.is_not(None)).group_by(Activity.account_id)).all())
    # activities logged on a contact or opportunity count for its account too
    for acc_id, at in db.execute(
            select(Opportunity.account_id, func.max(Activity.created_at))
            .join(Activity, Activity.opportunity_id == Opportunity.id).group_by(Opportunity.account_id)).all():
        if at and (acc_id not in last_activity or at > last_activity[acc_id]):
            last_activity[acc_id] = at
    out = []
    for h in holdings(db, today=today):
        if h.status not in ("active", "renewal_due") or h.installments or not h.renewal_date:
            continue
        if h.renewal_date > horizon:
            continue
        # annual value: the paid period ending on the renewal date, scaled to 12 months
        period = [lines[i].e for i in h.lines if lines[i].e.end_date == h.renewal_date and lines[i].e.net_amount]
        net = sum((e.net_amount for e in period), ZERO)
        days = max(((e.end_date - e.start_date).days + 1 for e in period if e.start_date), default=365)
        annual = net * Decimal(365) / Decimal(max(days, 1))
        acc_line = lines[h.latest_line_id]
        act = last_activity.get(h.account_id)
        flags = []
        if h.account_id not in open_renewal:
            flags.append("no renewal deal")
        if not act or act.date() < recent:
            flags.append("no activity in 90 days")
        if not acc_line.owner:
            flags.append("no owner")
        out.append({"account_id": h.account_id, "account": h.account_name, "product": h.product_name,
                    "license_type": h.license_type, "quantity": h.quantity, "renewal_date": h.renewal_date,
                    "days": (h.renewal_date - today).days, "annual_value": _r(annual), "region": acc_line.region,
                    "reseller": h.reseller or DIRECT, "owner": acc_line.owner,
                    "last_activity": act.date() if act else None, "flags": flags})
    return sorted(out, key=lambda r: -r["annual_value"])


# ---------------------------------------------------------------- 5. retention
def retention(db: Session, year: int) -> dict:
    """Net revenue retention: what last year's customers pay for `year`, against what they paid for `year - 1`."""
    lines = load(db)
    rev: dict[int, dict[int, Decimal]] = {year - 1: defaultdict(Decimal), year: defaultdict(Decimal)}
    acc_info: dict[int, tuple[str, str, str]] = {}
    by_dim: dict[str, dict[tuple[str, int], dict[int, Decimal]]] = {"region": defaultdict(lambda: defaultdict(Decimal)),
                                                                     "product": defaultdict(lambda: defaultdict(Decimal)),
                                                                     "reseller": defaultdict(lambda: defaultdict(Decimal))}
    for ln in lines:
        acc_info[ln.e.account_id] = (ln.account, ln.region, ln.reseller)
        for y, v in per_year(ln.e).items():
            if y in rev:
                rev[y][ln.e.account_id] += v
                by_dim["region"][(ln.region, ln.e.account_id)][y] += v
                by_dim["product"][(family(ln.e.product_name), ln.e.account_id)][y] += v
                by_dim["reseller"][(ln.reseller, ln.e.account_id)][y] += v

    def classify(before: Decimal, after: Decimal) -> str:
        if after <= 0:
            return "churned"
        if after < before * Decimal("0.95"):
            return "contracted"
        if after > before * Decimal("1.05"):
            return "expanded"
        return "retained"

    prev, cur = rev[year - 1], rev[year]
    base = {a: v for a, v in prev.items() if v > 0}
    movement = {k: {"customers": 0, "before": ZERO, "after": ZERO} for k in ("retained", "expanded", "contracted",
                                                                              "churned")}
    customers = []
    for a, before in base.items():
        after = max(cur.get(a, ZERO), ZERO)
        kind = classify(before, after)
        m = movement[kind]
        m["customers"] += 1
        m["before"] += before
        m["after"] += after
        name, region, reseller = acc_info[a]
        customers.append({"account_id": a, "account": name, "region": region, "reseller": reseller,
                          "before": _r(before), "after": _r(after), "change": _r(after - before), "status": kind})
    new = {a: v for a, v in cur.items() if v > 0 and a not in base}
    start = sum(base.values(), ZERO)
    kept = sum((max(cur.get(a, ZERO), ZERO) for a in base), ZERO)

    def breakdown(dim: str) -> list[dict]:
        acc: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"before": ZERO, "after": ZERO, "churned": ZERO})
        for (name, _a), ys in by_dim[dim].items():
            before, after = ys.get(year - 1, ZERO), max(ys.get(year, ZERO), ZERO)
            if before > 0:
                acc[name]["before"] += before
                acc[name]["after"] += after
                if after <= 0:
                    acc[name]["churned"] += before
        return sorted(({"name": n, "before": _r(v["before"]), "after": _r(v["after"]),
                        "nrr": round(float(100 * v["after"] / v["before"]), 1) if v["before"] else None,
                        "churned": _r(v["churned"])} for n, v in acc.items()), key=lambda r: -r["before"])

    first = min((d for ln in lines if ln.e.source == "bmc_mzd" and (d := _date(ln.e))), default=None)
    return {
        "year": year, "previous_year": year - 1, "partial_year": year >= dt.date.today().year,
        # the reports do not reach back to the start of the base year: its revenue, and so NRR, are not complete
        "data_from": first, "incomplete_base": bool(first and first > dt.date(year - 1, 1, 31)),
        "start_revenue": _r(start), "retained_revenue": _r(kept),
        "nrr": round(float(100 * kept / start), 1) if start else None,
        "grr": round(float(100 * sum((min(max(cur.get(a, ZERO), ZERO), v) for a, v in base.items()), ZERO) / start),
                     1) if start else None,
        "movement": [{"kind": k, "customers": v["customers"], "before": _r(v["before"]), "after": _r(v["after"])}
                     for k, v in movement.items()],
        "new_customers": len(new), "new_revenue": _r(sum(new.values(), ZERO)),
        "by_region": breakdown("region"), "by_product": breakdown("product"), "by_reseller": breakdown("reseller"),
        "customers": sorted(customers, key=lambda c: c["change"]),
    }


# ---------------------------------------------------------------- 6. reseller scorecard
def resellers(db: Session, today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    year_ago = today - dt.timedelta(days=365)
    lines = load(db)
    held = {(h.account_id, h.product_name.lower()): h for h in holdings(db, today=today)}
    stats: dict[str, dict] = defaultdict(lambda: {"revenue_12m": ZERO, "revenue_prev_12m": ZERO, "customers": set(),
                                                   "invoices": set(), "invoice_net": defaultdict(Decimal),
                                                   "last_invoice": None, "due": 0, "renewed": 0, "lapsed": 0,
                                                   "credits": ZERO})
    periods: dict[tuple[int, str], list[Entitlement]] = defaultdict(list)
    reseller_of: dict[tuple[int, str], str] = {}
    for ln in lines:
        e, s = ln.e, stats[ln.reseller]
        d = _date(e)
        if e.net_amount is not None and d:
            if d >= year_ago:
                s["revenue_12m"] += e.net_amount
            elif d >= year_ago - dt.timedelta(days=365):
                s["revenue_prev_12m"] += e.net_amount
            if e.net_amount < 0:
                s["credits"] += -e.net_amount
            if e.source_ref:
                s["invoices"].add(e.source_ref)
                s["invoice_net"][e.source_ref] += e.net_amount
            s["last_invoice"] = max(filter(None, [s["last_invoice"], d]))
        key = (e.account_id, e.product_name.lower())
        periods[key].append(e)
        reseller_of[key] = ln.reseller
        h = held.get(key)
        if h and h.status in ("active", "renewal_due", "awaiting_report", "upcoming"):
            s["customers"].add(e.account_id)
    # renewal rate: paid periods that ended in the last 12 months and were followed by another paid period
    for key, es in periods.items():
        paid: dict[tuple, Decimal] = defaultdict(Decimal)
        for e in es:
            if e.end_date and e.license_type != "perpetual":
                paid[(e.start_date, e.end_date)] += e.quantity
        ends = sorted(p for p, q in paid.items() if q > 0)
        s = stats[reseller_of[key]]
        for start, end in ends:
            if year_ago <= end < today:
                s["due"] += 1
                if any(p[0] and p[0] > start and p[1] > end for p in ends):
                    s["renewed"] += 1
        h = held.get(key)
        if h and h.status == "lapsed" and not h.resolved:
            s["lapsed"] += 1
    out = []
    for name, s in stats.items():
        sizes = [v for v in s["invoice_net"].values() if v > 0]
        out.append({
            "reseller": name, "revenue_12m": _r(s["revenue_12m"]), "revenue_prev_12m": _r(s["revenue_prev_12m"]),
            # growth on a tiny base means nothing: under 10% of this year's revenue counts as new business
            "growth": round(float(100 * (s["revenue_12m"] - s["revenue_prev_12m"]) / s["revenue_prev_12m"]), 1)
            if s["revenue_prev_12m"] > 0 and s["revenue_prev_12m"] >= s["revenue_12m"] / 10 else None,
            "new": s["revenue_12m"] > 0 and s["revenue_prev_12m"] < s["revenue_12m"] / 10,
            "active_customers": len(s["customers"]), "invoices": len(s["invoices"]),
            "avg_invoice": _r(sum(sizes, ZERO) / len(sizes)) if sizes else ZERO,
            "renewals_due": s["due"], "renewed": s["renewed"],
            "renewal_rate": round(100 * s["renewed"] / s["due"], 1) if s["due"] else None,
            "lapsed": s["lapsed"], "credits": _r(s["credits"]), "last_invoice": s["last_invoice"],
            "quiet": bool(s["last_invoice"] and (today - s["last_invoice"]).days > 180),
        })
    return sorted(out, key=lambda r: -r["revenue_12m"])


# ---------------------------------------------------------------- 3. credit memos
def credits(db: Session) -> dict:
    """Credit memo lines (negative amounts): per quarter, per customer and reseller, and re-billed licences."""
    lines = load(db)
    q: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"invoiced": ZERO, "credited": ZERO})
    by_customer: dict[tuple[int, str], dict] = {}
    by_reseller: dict[str, Decimal] = defaultdict(Decimal)
    rebilled: dict[tuple[int, str], dict] = defaultdict(lambda: {"credits": 0, "credited": ZERO, "invoices": 0})
    out_lines = []
    for ln in lines:
        e, d = ln.e, _date(ln.e)
        if e.net_amount is None or not d:
            continue
        quarter = f"{d.year} Q{(d.month - 1) // 3 + 1}"
        key = (e.account_id, e.product_name)
        if e.net_amount < 0:
            amt = -e.net_amount
            q[quarter]["credited"] += amt
            c = by_customer.setdefault(e.account_id, {"account_id": e.account_id, "account": ln.account,
                                                      "region": ln.region, "credited": ZERO, "credit_lines": 0})
            c["credited"] += amt
            c["credit_lines"] += 1
            by_reseller[ln.reseller] += amt
            rebilled[key]["credits"] += 1
            rebilled[key]["credited"] += amt
            out_lines.append({"date": d, "document": e.source_ref, "account_id": e.account_id, "account": ln.account,
                              "product": e.product_name, "quantity": e.quantity, "amount": _r(amt),
                              "reseller": ln.reseller, "report": (e.report_name or "").replace("\\", "/")
                              .rsplit("/", 1)[-1]})
        else:
            q[quarter]["invoiced"] += e.net_amount
            rebilled[key]["invoices"] += 1
    quarters = [{"quarter": k, "invoiced": _r(v["invoiced"]), "credited": _r(v["credited"]),
                 "share": round(float(100 * v["credited"] / v["invoiced"]), 1) if v["invoiced"] else None}
                for k, v in sorted(q.items())]
    names = {ln.e.account_id: ln.account for ln in lines}
    repeat = sorted(({"account_id": a, "account": names[a], "product": p, "credit_lines": v["credits"],
                      "invoice_lines": v["invoices"], "credited": _r(v["credited"])}
                     for (a, p), v in rebilled.items() if v["credits"] >= 2 or (v["credits"] and v["invoices"] >= 3)),
                    key=lambda r: (-r["credit_lines"], -r["credited"]))
    total_inv = sum((v["invoiced"] for v in q.values()), ZERO)
    total_cr = sum((v["credited"] for v in q.values()), ZERO)
    return {"quarters": quarters, "total_invoiced": _r(total_inv), "total_credited": _r(total_cr),
            "share": round(float(100 * total_cr / total_inv), 1) if total_inv else None,
            "by_customer": sorted(by_customer.values(), key=lambda c: -c["credited"]),
            "by_reseller": sorted(({"reseller": r, "credited": _r(v)} for r, v in by_reseller.items()),
                                  key=lambda r: -r["credited"]),
            "rebilled": repeat, "lines": sorted(out_lines, key=lambda r: r["date"], reverse=True)}


# ---------------------------------------------------------------- 8. whitespace
def whitespace(db: Session, min_confidence: float = 0.4, today: dt.date | None = None) -> dict:
    """Which customers own a product family but not the families usually bought with it."""
    lines = {ln.e.id: ln for ln in load(db)}
    owned: dict[int, set[str]] = defaultdict(set)
    info: dict[int, dict] = {}
    for h in holdings(db, today=today):
        if h.status not in ("active", "renewal_due", "awaiting_report", "upcoming", "perpetual"):
            continue
        owned[h.account_id].add(family(h.product_name))
        ln = lines[h.latest_line_id]
        info[h.account_id] = {"account": h.account_name, "region": ln.region, "owner": ln.owner,
                              "reseller": h.reseller or DIRECT}
    fam_count = Counter(f for fs in owned.values() for f in fs)
    pair = Counter((a, b) for fs in owned.values() for a in fs for b in fs if a != b)
    families = [f for f, _ in fam_count.most_common()]
    rules = []  # customers with A also have B in conf% of cases
    for (a, b), n in pair.items():
        if fam_count[a] >= 3 and n / fam_count[a] >= min_confidence:
            rules.append({"has": a, "suggest": b, "confidence": round(100 * n / fam_count[a]), "support": n})
    suggestions = []
    for acc, fs in owned.items():
        best: dict[str, dict] = {}
        for r in rules:
            if r["has"] in fs and r["suggest"] not in fs:
                cur = best.get(r["suggest"])
                if not cur or r["confidence"] > cur["confidence"]:
                    best[r["suggest"]] = {"family": r["suggest"], "because": r["has"], "confidence": r["confidence"]}
        if best:
            suggestions.append({"account_id": acc, **info[acc], "owns": sorted(fs),
                                "suggest": sorted(best.values(), key=lambda s: -s["confidence"])})
    suggestions.sort(key=lambda s: (-max(x["confidence"] for x in s["suggest"]), s["account"]))
    matrix = sorted(({"account_id": a, "account": info[a]["account"], "owns": sorted(fs)} for a, fs in owned.items()),
                    key=lambda r: (-len(r["owns"]), r["account"]))
    return {"families": [{"family": f, "customers": fam_count[f]} for f in families],
            "rules": sorted(rules, key=lambda r: (-r["confidence"], -r["support"])),
            "suggestions": suggestions, "matrix": matrix}
