"""Licence insights for managers: renewals at risk, retention, resellers, credit memos, cross-sell whitespace."""
import datetime as dt

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import insights
from ..db import get_db
from ..models import User
from ..security import get_current_user

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/renewals")
def renewals_at_risk(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db),
                     _: User = Depends(get_current_user)):
    """Licences renewing within `months`, by annual value, flagged when no renewal deal, no recent activity or no
    owner."""
    return insights.renewals_at_risk(db, months)


@router.get("/retention")
def retention(year: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Net revenue retention of `year` against the year before (default: last full year)."""
    return insights.retention(db, year or dt.date.today().year - 1)


@router.get("/resellers")
def resellers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Per billing company: revenue (12 months and the 12 before), customers, renewal rate, lapses, credits."""
    return insights.resellers(db)


@router.get("/credits")
def credits(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Credit memos per quarter, customer and reseller, and licences credited and re-invoiced repeatedly."""
    return insights.credits(db)


@router.get("/whitespace")
def whitespace(min_confidence: int = Query(40, ge=10, le=100), db: Session = Depends(get_db),
               _: User = Depends(get_current_user)):
    """Customers who own a product family but not the ones usually bought with it."""
    return insights.whitespace(db, min_confidence / 100)
