import dataclasses
import datetime as dt
import logging
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from .. import entitlements as ent
from ..crud import audit, get_or_404
from ..db import get_db
from ..models import Account, Entitlement, Notification, User
from ..mzd_report import ReportError, parse
from ..security import get_current_user, require_admin, require_writer

router = APIRouter(prefix="/api", tags=["licences"])
log = logging.getLogger("crm.licences")
MAX_PDF = 20_000_000


class HoldingOut(BaseModel):
    account_id: int
    account_name: str
    product_name: str
    license_type: str
    quantity: Decimal
    period_start: dt.date | None
    period_end: dt.date | None
    renewal_date: dt.date | None
    status: str
    installments: bool
    days_to_renewal: int | None
    reseller: str | None
    latest_line_id: int
    resolved: bool
    resolution: str | None
    resolved_by: str | None
    resolved_at: dt.datetime | None


class LineOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    product_name: str
    quantity: Decimal
    license_type: str
    start_date: dt.date | None
    end_date: dt.date | None
    net_amount: Decimal | None
    currency: str
    source: str
    source_ref: str | None
    document_date: dt.date | None
    report_name: str | None


class AccountLicences(BaseModel):
    holdings: list[HoldingOut]
    lines: list[LineOut]


class EntitlementIn(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    quantity: Decimal
    license_type: str = Field(default="term", pattern="^(term|support|saas|perpetual|other)$")
    start_date: dt.date | None = None
    end_date: dt.date | None = None

    @model_validator(mode="after")
    def end_needed(self):
        if self.end_date is None and self.license_type != "perpetual":
            raise ValueError("an end / renewal date is needed (only perpetual licences have none)")
        return self


class ResolveIn(BaseModel):
    note: str = Field(min_length=1, max_length=2000)


def _h(h: ent.Holding) -> HoldingOut:
    return HoldingOut(**{f.name: getattr(h, f.name) for f in dataclasses.fields(h) if f.name != "lines"})


@router.get("/accounts/{account_id}/licences", response_model=AccountLicences)
def account_licences(account_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    get_or_404(db, Account, account_id)
    lines = db.scalars(select(Entitlement).where(Entitlement.account_id == account_id)
                       .order_by(Entitlement.end_date.desc().nulls_last(), Entitlement.product_name))
    return AccountLicences(holdings=[_h(h) for h in ent.holdings(db, [account_id])], lines=list(lines))


@router.post("/accounts/{account_id}/licences", response_model=LineOut, status_code=201)
def add_licence(account_id: int, data: EntitlementIn, db: Session = Depends(get_db),
                user: User = Depends(require_writer)):
    """Record a licence by hand (a direct sale, or a correction to a report)."""
    from ..models import Brand

    get_or_404(db, Account, account_id)
    brand = db.scalar(select(Brand).where(Brand.code == "SENTRY"))
    e = Entitlement(account_id=account_id, brand_id=brand.id, source="manual", **data.model_dump())
    db.add(e)
    db.flush()
    audit(db, user, "entitlement", e.id, "create", {"product": e.product_name, "quantity": str(e.quantity)})
    db.commit()
    return e


@router.delete("/licences/{line_id}", status_code=204)
def delete_licence(line_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    e = get_or_404(db, Entitlement, line_id)
    audit(db, user, "entitlement", e.id, "delete", {"product": e.product_name, "account_id": e.account_id,
                                                    "source_ref": e.source_ref})
    db.delete(e)
    db.commit()


@router.get("/licences/lapsed", response_model=list[HoldingOut])
def lapsed_licences(include_resolved: bool = False, db: Session = Depends(get_db),
                    _: User = Depends(get_current_user)):
    return [_h(h) for h in ent.lapsed(db, include_resolved)]


@router.get("/licences/renewals", response_model=list[HoldingOut])
def upcoming_renewals(days: int = 90, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_h(h) for h in ent.holdings(db) if h.status in ("renewal_due", "active")
            and h.days_to_renewal is not None and h.days_to_renewal <= days]


@router.post("/licences/{line_id}/resolve", response_model=HoldingOut)
def resolve_lapse(line_id: int, data: ResolveIn, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    """Take a lapsed licence off the dashboard (renewed outside the report, churned, duplicate...)."""
    e = get_or_404(db, Entitlement, line_id)
    e.lapse_resolved_at, e.lapse_resolved_by_id, e.lapse_resolution = dt.datetime.now(dt.UTC), user.id, data.note
    audit(db, user, "entitlement", e.id, "resolve_lapse", {"note": data.note})
    db.commit()
    h = next(h for h in ent.holdings(db, [e.account_id]) if line_id in h.lines)
    return _h(h)


@router.post("/licences/{line_id}/reopen", response_model=HoldingOut)
def reopen_lapse(line_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    e = get_or_404(db, Entitlement, line_id)
    e.lapse_resolved_at = e.lapse_resolved_by_id = e.lapse_resolution = None
    audit(db, user, "entitlement", e.id, "reopen_lapse")
    db.commit()
    return _h(next(h for h in ent.holdings(db, [e.account_id]) if line_id in h.lines))


@router.post("/licences/import/bmc-mzd")
def import_mzd(file: UploadFile = File(...), commit: bool = Form(False), db: Session = Depends(get_db),
               user: User = Depends(require_admin)):
    """Import a BMC MarketZone quarterly reseller fee report (PDF or Detail .xlsx). Dry run unless commit=true.

    A report with problems (lines that could not be read, totals that do not add up) is never saved: the dry run
    lists the problems, and the Detail .xlsx of the same quarter can be imported instead."""
    raw = file.file.read(MAX_PDF + 1)
    if len(raw) > MAX_PDF:
        raise HTTPException(413, "File too large (max 20 MB)")
    try:
        report = parse(raw, file.filename or "")
    except ReportError as exc:
        raise HTTPException(422, str(exc)) from None
    except Exception:  # noqa: BLE001 - a malformed file must never become a 500
        log.exception("Could not read report %s", file.filename)
        raise HTTPException(422, "Could not read this file. Is it a MarketZone report (PDF or Detail .xlsx)?") from None
    if commit and not report.reliable:
        raise HTTPException(422, f"Not imported: {len(report.warnings)} problem(s) reading this report. Run a dry run "
                                 "to see them, or import the Detail .xlsx of the same quarter instead.")
    try:
        res = ent.import_report(db, report, file.filename or "MarketZone report", dry_run=not commit)
    except DBAPIError:
        db.rollback()
        log.exception("Report import failed for %s", file.filename)
        raise HTTPException(422, "Some values in this report could not be saved. Nothing was imported.") from None
    if commit:
        audit(db, user, "entitlement_import", 0, "bmc_mzd", {"file": file.filename, "created": res.created,
                                                             "already_imported": res.already_imported})
        db.commit()
    return dataclasses.asdict(res)


@router.post("/licences/notify-renewals")
def run_notices(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    """Run the renewal check now (it also runs daily on its own)."""
    return {"accounts_notified": ent.send_renewal_notices(db)}


# ---------------- notifications ----------------
class NotificationOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    read_at: dt.datetime | None
    created_at: dt.datetime


@router.get("/notifications")
def my_notifications(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    items = db.scalars(select(Notification).where(Notification.user_id == user.id)
                       .order_by(Notification.created_at.desc()).limit(50))
    unread = db.scalar(select(func.count()).select_from(Notification)
                       .where(Notification.user_id == user.id, Notification.read_at.is_(None)))
    return {"unread": unread, "items": [NotificationOut.model_validate(n) for n in items]}


@router.post("/notifications/read", status_code=204)
def mark_read(ids: list[int] | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Mark the given notifications (or all of them) as read."""
    stmt = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if ids:
        stmt = stmt.where(Notification.id.in_(ids))
    db.execute(stmt.values(read_at=dt.datetime.now(dt.UTC)))
    db.commit()
