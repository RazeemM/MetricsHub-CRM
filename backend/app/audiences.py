"""Dynamic audiences (segments): contacts matching saved rules, worked out again each time they are used.

A static mailing list holds the people added to it; an audience follows the data, so "customers whose licence renews
in the next 90 days" or "leads in France with marketing consent" stays current without anyone maintaining it.
"""
from __future__ import annotations

import datetime as dt
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select

from .models import Account, Contact, Entitlement, ListMember


class AudienceRules(BaseModel):
    """Every rule given must match (AND); several values in one rule mean any of them (OR)."""

    lifecycle: list[str] = Field(default_factory=list)
    role: list[str] = Field(default_factory=list)
    account_type: list[str] = Field(default_factory=list)
    country: list[str] = Field(default_factory=list)
    source: list[str] = Field(default_factory=list)
    brand_id: int | None = None
    owner_id: int | None = None
    consent_only: bool = False
    # licences of the contact's account: active (one in force), lapsed (had some, none in force), none (never had one)
    licence: Literal["active", "lapsed", "none"] | None = None
    product: str | None = Field(default=None, max_length=120)  # holds an active licence whose product name contains this
    renews_within_days: int | None = Field(default=None, ge=1, le=730)  # an active licence ends within N days
    list_ids: list[int] = Field(default_factory=list)  # subscribed to any of these lists
    created_within_days: int | None = Field(default=None, ge=1, le=3650)


def _licences(*conds):
    return exists().where(Entitlement.account_id == Contact.account_id, *conds)


def condition(rules: AudienceRules | dict, today: dt.date | None = None):
    """SQL condition on Contact for these rules (always: has an email address)."""
    r = rules if isinstance(rules, AudienceRules) else AudienceRules.model_validate(rules or {})
    today = today or dt.date.today()
    active = or_(Entitlement.end_date.is_(None), Entitlement.end_date >= today)
    conds = [Contact.email.is_not(None), Contact.email.contains("@")]
    if r.lifecycle:
        conds.append(Contact.lifecycle.in_(r.lifecycle))
    if r.role:
        conds.append(Contact.role.in_(r.role))
    if r.source:
        conds.append(Contact.source.in_(r.source))
    if r.country:
        wanted = [c.lower() for c in r.country]
        conds.append(or_(func.lower(Contact.country).in_(wanted),
                         and_(Contact.country.is_(None), Contact.account.has(func.lower(Account.country).in_(wanted)))))
    if r.account_type:
        conds.append(Contact.account.has(Account.account_type.in_(r.account_type)))
    if r.brand_id:
        conds.append(Contact.brand_id == r.brand_id)
    if r.owner_id:
        conds.append(Contact.owner_id == r.owner_id)
    if r.consent_only:
        conds.append(Contact.consent_marketing.is_(True))
    if r.licence == "active":
        conds.append(_licences(active))
    elif r.licence == "lapsed":
        conds += [_licences(), ~_licences(active)]
    elif r.licence == "none":
        conds.append(~_licences())
    if r.product:
        conds.append(_licences(active, Entitlement.product_name.ilike(f"%{r.product.strip()}%")))
    if r.renews_within_days:
        conds.append(_licences(Entitlement.end_date >= today,
                               Entitlement.end_date <= today + dt.timedelta(days=r.renews_within_days)))
    if r.list_ids:
        conds.append(exists().where(ListMember.contact_id == Contact.id, ListMember.list_id.in_(r.list_ids),
                                    ListMember.status == "subscribed"))
    if r.created_within_days:
        since = dt.datetime.now(dt.UTC) - dt.timedelta(days=r.created_within_days)
        conds.append(Contact.created_at >= since)
    return and_(*conds)


def contact_ids(db, rules: AudienceRules | dict) -> list[int]:
    return list(db.scalars(select(Contact.id).where(condition(rules)).order_by(Contact.id)))


def count(db, rules: AudienceRules | dict) -> dict:
    """How many contacts match, and how many of them can receive marketing email."""
    cond = condition(rules)
    total = db.scalar(select(func.count()).select_from(Contact).where(cond)) or 0
    reachable = db.scalar(select(func.count()).select_from(Contact).where(cond, Contact.unsubscribed.is_(False))) or 0
    consent = db.scalar(select(func.count()).select_from(Contact).where(
        cond, Contact.unsubscribed.is_(False), Contact.consent_marketing.is_(True))) or 0
    return {"matching": total, "reachable": reachable, "with_consent": consent}
