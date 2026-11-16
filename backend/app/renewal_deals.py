"""Renewal opportunities opened from customer licences.

CRM_RENEWAL_OPPORTUNITY_DAYS (60) before a licence's renewal date, the customer gets an opportunity in the Renewals
pipeline with one line per licence that renews in that window: product, quantity, the current period and what was
invoiced for it. One opportunity per customer and brand; licences that come into the window later are added to it
while it is open. A customer that already has an open renewal opportunity of its own (entered by hand) keeps it: the
licences are listed in a note on it instead. Each licence is handled once per renewal (Entitlement.
renewal_opportunity_id on the holding's latest line), so the daily run is idempotent; the next renewal period starts
over once the renewal is imported.

Runs with the daily renewal check (jobs.run_renewals), after each MarketZone report import, and from the
Import / export page.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .entitlements import Holding, _recipients, holdings
from .models import Account, Activity, Entitlement, LineItem, Notification, Opportunity, Pipeline, Stage, StageHistory
from .pricing import months_between
from .services import default_pipeline, recompute, sync_contract_dates

SOURCE = "licence_renewal"
RENEWABLE = ("active", "renewal_due")


@dataclass
class Planned:
    account_id: int
    account: str
    brand_id: int
    action: str  # create, add (to the open opportunity opened earlier), note (on an open renewal entered by hand)
    opportunity_id: int | None
    opportunity: str | None
    renewal_date: dt.date
    licences: list[dict] = field(default_factory=list)
    value: Decimal = Decimal(0)


@dataclass
class Result:
    dry_run: bool
    days: int
    created: int = 0
    added: int = 0
    noted: int = 0
    planned: list[Planned] = field(default_factory=list)


def _period_lines(lines: list[Entitlement], h: Holding) -> list[Entitlement]:
    """The lines of the period that renews (invoice and credit memo lines of the same dates)."""
    return [e for e in lines if e.end_date == h.renewal_date and (h.period_start is None or e.start_date is None
                                                                  or e.start_date >= h.period_start)]


def _licence(h: Holding, lines: list[Entitlement]) -> dict:
    period = _period_lines(lines, h)
    nets = [e.net_amount for e in period if e.net_amount is not None]
    fees = [e.fee_amount for e in period if e.fee_amount is not None]
    term = months_between(h.period_start, h.renewal_date) if h.period_start else 12
    return {
        "product": h.product_name, "license_type": h.license_type, "quantity": h.quantity,
        "period_start": h.period_start, "period_end": h.renewal_date, "term_months": max(term, 1),
        "reseller": h.reseller, "net": sum(nets, Decimal(0)) if nets else None,
        "fee": sum(fees, Decimal(0)) if fees else None, "currency": period[0].currency if period else "USD",
        "invoices": sorted({e.source_ref for e in period if e.source_ref}),
        "from_report": any(e.source == "bmc_mzd" for e in period),
        "reseller_id": next((e.reseller_id for e in period if e.reseller_id), None),
        "latest_line_id": h.latest_line_id,
    }


def _describe(lic: dict) -> str:
    kind = {"term": "term licence", "saas": "SaaS subscription", "support": "support"}.get(lic["license_type"],
                                                                                          lic["license_type"])
    parts = [f"{lic['quantity'].normalize():,f} × {lic['product']} ({kind})"]
    if lic["period_start"]:
        parts.append(f"current period {lic['period_start']:%d %b %Y} – {lic['period_end']:%d %b %Y}")
    else:
        parts.append(f"renews {lic['period_end']:%d %b %Y}")
    if lic["net"] is not None:
        parts.append(f"invoiced {lic['currency']} {lic['net']:,.2f}"
                     + (f", Sentry fee {lic['currency']} {lic['fee']:,.2f}" if lic["fee"] is not None else ""))
    if lic["reseller"]:
        parts.append(f"via {lic['reseller']}")
    if lic["invoices"]:
        parts.append(f"invoice {', '.join(lic['invoices'][:3])}")
    return " · ".join(parts)


def _line_item(lic: dict, position: int) -> LineItem:
    """The renewal of one licence, valued at what was invoiced for the current period (BMC: USD Total Net)."""
    qty, term, net = lic["quantity"], lic["term_months"], lic["net"]
    unit = (net / qty / term).quantize(Decimal("0.01")) if net is not None and qty > 0 else Decimal(0)
    return LineItem(position=position, name=lic["product"][:200], description=_describe(lic)[:2000], unit=None,
                    billing_type="recurring", quantity=qty if qty > 0 else Decimal(1), unit_price=unit,
                    discount_pct=Decimal(0), term_months=term, fixed_total=net)


def _bmc(db: Session) -> Account | None:
    from sqlalchemy import or_
    return db.scalar(select(Account).where(Account.account_type == "platform_partner", or_(
        Account.domain == "bmc.com", Account.name.ilike("BMC%"))).order_by(Account.id))


def _open_renewal(db: Session, account_id: int, brand_id: int) -> Opportunity | None:
    return db.scalar(select(Opportunity).join(Stage, Opportunity.stage_id == Stage.id)
                     .join(Pipeline, Opportunity.pipeline_id == Pipeline.id)
                     .where(Opportunity.account_id == account_id, Opportunity.brand_id == brand_id,
                            Stage.kind == "open", Pipeline.kind == "renewal")
                     .order_by((Opportunity.external_source == SOURCE).desc(), Opportunity.expected_close_date))


def open_renewal_opportunities(db: Session, today: dt.date | None = None, dry_run: bool = False) -> Result:
    """Open (or add to) renewal opportunities for licences renewing within CRM_RENEWAL_OPPORTUNITY_DAYS."""
    today = today or dt.date.today()
    days = get_settings().renewal_opportunity_days
    res = Result(dry_run=dry_run, days=days)
    if days <= 0:
        return res
    due = [h for h in holdings(db, today=today) if h.status in RENEWABLE and not h.installments
           and h.license_type != "perpetual" and h.renewal_date and today <= h.renewal_date
           <= today + dt.timedelta(days=days)]
    if not due:
        return res
    latest = {e.id: e for e in db.scalars(select(Entitlement).where(
        Entitlement.id.in_([h.latest_line_id for h in due])))}
    due = [h for h in due if latest[h.latest_line_id].renewal_opportunity_id is None]
    lines: dict[int, Entitlement] = {e.id: e for e in db.scalars(select(Entitlement).where(
        Entitlement.id.in_([i for h in due for i in h.lines])))}
    groups: dict[tuple[int, int], list[dict]] = defaultdict(list)
    for h in due:
        groups[(h.account_id, latest[h.latest_line_id].brand_id)].append(
            _licence(h, [lines[i] for i in h.lines]))

    pipeline = default_pipeline(db, "renewal")
    first_stage = next((s for s in pipeline.stages if s.kind == "open"), pipeline.stages[0])
    platform = _bmc(db)
    now = dt.datetime.now(dt.UTC)
    for (account_id, brand_id), lics in sorted(groups.items(), key=lambda g: min(x["period_end"] for x in g[1])):
        lics.sort(key=lambda x: (x["period_end"], x["product"]))
        account = db.get(Account, account_id)
        renewal = min(x["period_end"] for x in lics)
        existing = _open_renewal(db, account_id, brand_id)
        action = "create" if not existing else ("add" if existing.external_source == SOURCE else "note")
        res.planned.append(Planned(
            account_id=account_id, account=account.name, brand_id=brand_id, action=action,
            opportunity_id=existing.id if existing else None, opportunity=existing.title if existing else None,
            renewal_date=renewal, value=sum((x["net"] or Decimal(0) for x in lics), Decimal(0)),
            licences=[{k: v for k, v in x.items() if k not in ("latest_line_id", "reseller_id")} for x in lics]))
        if dry_run:
            continue

        if action == "note":
            opp = existing
            db.add(Activity(type="note", subject=f"Licences renewing by {renewal:%d %b %Y}", owner_id=opp.owner_id,
                            account_id=account_id, opportunity_id=opp.id, completed_at=now,
                            body="These licences renew within the next "
                                 f"{days} days:\n" + "\n".join(f"- {_describe(x)}" for x in lics)))
            res.noted += 1
        elif action == "add":
            opp = existing
            pos = max((li.position for li in opp.line_items), default=-1) + 1
            for k, lic in enumerate(lics):
                opp.line_items.append(_line_item(lic, pos + k))
            opp.expected_close_date = min(opp.expected_close_date or renewal, renewal)
            recompute(opp)
            res.added += 1
        else:
            term = max(x["term_months"] for x in lics)
            via_bmc = any(x["from_report"] for x in lics)
            reseller_id = next((x["reseller_id"] for x in lics if x["reseller_id"]), None)
            opp = Opportunity(
                title=f"{account.name} - Renewal {renewal:%b %Y}"[:255], account_id=account_id, brand_id=brand_id,
                owner_id=account.owner_id, pipeline_id=pipeline.id, stage_id=first_stage.id, deal_type="renewal",
                lead_source="platform_referral" if via_bmc else "direct",
                route_to_market="bmc_marketzone" if via_bmc else ("reseller" if reseller_id else "direct"),
                referring_platform_id=platform.id if via_bmc and platform else None, reseller_id=reseller_id,
                currency=lics[0]["currency"], expected_close_date=renewal,
                contract_start=renewal + dt.timedelta(days=1), term_months=term,
                external_source=SOURCE, external_id=f"{account_id}:{brand_id}:{renewal.isoformat()}",
                description=(f"Opened automatically {days} days before the licences renew. Each line is a licence "
                             "renewing, valued at what was invoiced for its current period.\n"
                             + "\n".join(f"- {_describe(x)}" for x in lics)))
            sync_contract_dates(opp)
            db.add(opp)
            db.flush()
            for k, lic in enumerate(lics):
                opp.line_items.append(_line_item(lic, k))
            recompute(opp)
            db.add(StageHistory(opportunity_id=opp.id, from_stage_id=None, to_stage_id=first_stage.id))
            res.created += 1
        db.flush()
        res.planned[-1].opportunity_id, res.planned[-1].opportunity = opp.id, opp.title
        for lic in lics:
            latest[lic["latest_line_id"]].renewal_opportunity_id = opp.id
        verb = {"create": "Renewal opportunity opened", "add": "Licences added to the renewal opportunity",
                "note": "Licences renewing"}[action]
        for user in _recipients(db, account):
            db.add(Notification(user_id=user.id, kind="renewal_opportunity", link=f"/opportunities/{opp.id}",
                                title=f"{account.name}: {verb.lower() if action == 'note' else verb} "
                                      f"(renews {renewal:%d %b %Y})",
                                body="\n".join(f"- {_describe(x)}" for x in lics)))
    if dry_run:
        db.rollback()
    else:
        db.commit()
    return res
