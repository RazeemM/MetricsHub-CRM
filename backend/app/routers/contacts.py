import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..crud import apply_changes, audit, get_or_404, paginate
from ..db import get_db
from ..models import Account, Contact, User
from ..schemas import ContactCreate, ContactOut, ContactUpdate, Page
from ..security import get_current_user, require_writer
from ..services import find_contact_by_email

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

SORTS = {"name": Contact.last_name, "email": Contact.email, "created_at": Contact.created_at,
         "updated_at": Contact.updated_at, "lifecycle": Contact.lifecycle}


def build_query(q=None, account_id=None, lifecycle=None, role=None, source=None, brand_id=None, owner_id=None,
                account_type=None):
    stmt = select(Contact).options(selectinload(Contact.account), selectinload(Contact.owner))
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.outerjoin(Account, Contact.account_id == Account.id).where(or_(
            Contact.email.ilike(term), Contact.first_name.ilike(term), Contact.last_name.ilike(term),
            func.concat(Contact.first_name, " ", Contact.last_name).ilike(term),
            Contact.job_title.ilike(term), Account.name.ilike(term)))
    if account_id:
        stmt = stmt.where(Contact.account_id == account_id)
    if lifecycle:
        stmt = stmt.where(Contact.lifecycle.in_(lifecycle))
    if role:
        stmt = stmt.where(Contact.role.in_(role))
    if source:
        stmt = stmt.where(Contact.source.in_(source))
    if brand_id:
        stmt = stmt.where(Contact.brand_id == brand_id)
    if owner_id:
        stmt = stmt.where(Contact.owner_id == owner_id)
    if account_type:
        stmt = stmt.where(Contact.account.has(Account.account_type.in_(account_type)))
    return stmt


@router.get("", response_model=Page[ContactOut])
def list_contacts(
    q: str | None = None,
    account_id: int | None = None,
    lifecycle: list[str] | None = Query(None),
    role: list[str] | None = Query(None),
    source: list[str] | None = Query(None),
    account_type: list[str] | None = Query(None),
    brand_id: int | None = None,
    owner_id: int | None = None,
    sort: str = "created_at",
    desc: bool = True,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    col = SORTS.get(sort, Contact.created_at)
    stmt = build_query(q, account_id, lifecycle, role, source, brand_id, owner_id, account_type)
    stmt = stmt.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last(), Contact.id)
    items, total = paginate(db, stmt, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(contact_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return get_or_404(db, Contact, contact_id)


def _check_email(db: Session, email: str | None, exclude_id: int | None = None):
    existing = find_contact_by_email(db, email)
    if existing and existing.id != exclude_id:
        raise HTTPException(409, {"message": "A contact with this email already exists", "contact_id": existing.id})


@router.post("", response_model=ContactOut, status_code=201)
def create_contact(data: ContactCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    if not (data.email or data.first_name or data.last_name):
        raise HTTPException(422, "Provide at least a name or an email")
    _check_email(db, data.email)
    c = Contact(**data.model_dump(), extra={})
    if c.email:
        c.email = c.email.lower()
    if c.consent_marketing:
        c.consent_at = dt.datetime.now(dt.UTC)
    if c.owner_id is None:
        c.owner_id = user.id
    db.add(c)
    db.flush()
    audit(db, user, "contact", c.id, "create")
    db.commit()
    db.refresh(c)
    return c


@router.patch("/{contact_id}", response_model=ContactOut)
def update_contact(contact_id: int, data: ContactUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require_writer)):
    c = get_or_404(db, Contact, contact_id)
    if data.email:
        _check_email(db, data.email, exclude_id=c.id)
        data.email = data.email.lower()
    had_consent = c.consent_marketing
    changes = apply_changes(c, data)
    if c.consent_marketing and not had_consent:
        c.consent_at = dt.datetime.now(dt.UTC)
    audit(db, user, "contact", c.id, "update", changes)
    db.commit()
    db.refresh(c)
    return c


@router.delete("/{contact_id}", status_code=204)
def delete_contact(contact_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    c = get_or_404(db, Contact, contact_id)
    audit(db, user, "contact", c.id, "delete", {"email": c.email})
    db.delete(c)
    db.commit()
