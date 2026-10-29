from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased, selectinload

from ..crud import apply_changes, audit, get_or_404, paginate
from ..db import get_db
from ..models import Account, Contact, Opportunity, Stage, User
from ..schemas import AccountCreate, AccountOut, AccountUpdate, Page
from ..security import get_current_user, require_writer

router = APIRouter(prefix="/api/accounts", tags=["accounts"])

SORTS = {"name": func.lower(Account.name), "created_at": Account.created_at, "updated_at": Account.updated_at,
         "country": Account.country, "account_type": Account.account_type, "domain": Account.domain,
         "contacts": select(func.count()).where(Contact.account_id == Account.id).scalar_subquery(),
         "open_deals": select(func.count()).select_from(Opportunity).join(Stage, Opportunity.stage_id == Stage.id)
         .where(Opportunity.account_id == Account.id, Stage.kind == "open").scalar_subquery()}


def _with_counts(db: Session, accounts: list[Account]) -> list[AccountOut]:
    ids = [a.id for a in accounts]
    if not ids:
        return []
    contacts = dict(db.execute(select(Contact.account_id, func.count()).where(Contact.account_id.in_(ids))
                               .group_by(Contact.account_id)).all())
    opps = dict(db.execute(select(Opportunity.account_id, func.count()).join(Stage, Opportunity.stage_id == Stage.id)
                           .where(Opportunity.account_id.in_(ids), Stage.kind == "open")
                           .group_by(Opportunity.account_id)).all())
    out = []
    for a in accounts:
        item = AccountOut.model_validate(a)
        item.contact_count = contacts.get(a.id, 0)
        item.open_opportunity_count = opps.get(a.id, 0)
        out.append(item)
    return out


def build_query(q: str | None = None, account_type: list[str] | None = None, owner_id: int | None = None,
                country: str | None = None):
    stmt = select(Account).options(selectinload(Account.owner))
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.where(or_(Account.name.ilike(term), Account.domain.ilike(term), Account.city.ilike(term)))
    if account_type:
        stmt = stmt.where(Account.account_type.in_(account_type))
    if owner_id:
        stmt = stmt.where(Account.owner_id == owner_id)
    if country:
        stmt = stmt.where(Account.country.ilike(country))
    return stmt


@router.get("", response_model=Page[AccountOut])
def list_accounts(
    q: str | None = None,
    account_type: list[str] | None = Query(None),
    owner_id: int | None = None,
    country: str | None = None,
    sort: str = "name",
    desc: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = build_query(q, account_type, owner_id, country)
    if sort == "owner":
        owner = aliased(User)
        stmt, col = stmt.outerjoin(owner, Account.owner_id == owner.id), func.lower(owner.full_name)
    else:
        col = SORTS.get(sort, SORTS["name"])
    stmt = stmt.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last(), Account.id)
    items, total = paginate(db, stmt, page, page_size)
    return Page(items=_with_counts(db, items), total=total, page=page, page_size=page_size)


@router.get("/{account_id}", response_model=AccountOut)
def get_account(account_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _with_counts(db, [get_or_404(db, Account, account_id)])[0]


@router.post("", response_model=AccountOut, status_code=201)
def create_account(data: AccountCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    acc = Account(**data.model_dump(), extra={})
    if acc.owner_id is None:
        acc.owner_id = user.id
    db.add(acc)
    db.flush()
    audit(db, user, "account", acc.id, "create")
    db.commit()
    db.refresh(acc)
    return _with_counts(db, [acc])[0]


@router.patch("/{account_id}", response_model=AccountOut)
def update_account(account_id: int, data: AccountUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require_writer)):
    acc = get_or_404(db, Account, account_id)
    if data.parent_id == account_id:
        raise HTTPException(422, "An account cannot be its own parent")
    changes = apply_changes(acc, data)
    audit(db, user, "account", acc.id, "update", changes)
    db.commit()
    db.refresh(acc)
    return _with_counts(db, [acc])[0]


@router.delete("/{account_id}", status_code=204)
def delete_account(account_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    acc = get_or_404(db, Account, account_id)
    if db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.account_id == account_id)):
        raise HTTPException(409, "This account has opportunities; delete or move them first")
    audit(db, user, "account", acc.id, "delete", {"name": acc.name})
    db.delete(acc)
    db.commit()
