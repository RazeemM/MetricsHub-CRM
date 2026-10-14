from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..crud import apply_changes, get_or_404, paginate
from ..db import get_db
from ..models import Account, Activity, Contact, Opportunity, User
from ..schemas import ActivityCreate, ActivityOut, ActivityUpdate, Page
from ..security import get_current_user, require_writer

router = APIRouter(prefix="/api/activities", tags=["activities"])


@router.get("", response_model=Page[ActivityOut])
def list_activities(
    account_id: int | None = None, contact_id: int | None = None, opportunity_id: int | None = None,
    owner_id: int | None = None, type: str | None = None, open_tasks: bool = False,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    stmt = select(Activity).options(selectinload(Activity.owner))
    if account_id:
        # include activities logged on the account's contacts and opportunities
        stmt = stmt.where(
            (Activity.account_id == account_id)
            | Activity.contact_id.in_(select(Contact.id).where(Contact.account_id == account_id))
            | Activity.opportunity_id.in_(select(Opportunity.id).where(Opportunity.account_id == account_id)))
    if contact_id:
        stmt = stmt.where(Activity.contact_id == contact_id)
    if opportunity_id:
        stmt = stmt.where(Activity.opportunity_id == opportunity_id)
    if owner_id:
        stmt = stmt.where(Activity.owner_id == owner_id)
    if type:
        stmt = stmt.where(Activity.type == type)
    if open_tasks:
        stmt = stmt.where(Activity.type == "task", Activity.completed_at.is_(None)).order_by(
            Activity.due_at.asc().nulls_last())
    stmt = stmt.order_by(Activity.created_at.desc())
    items, total = paginate(db, stmt, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ActivityOut, status_code=201)
def create_activity(data: ActivityCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    if not (data.account_id or data.contact_id or data.opportunity_id):
        raise HTTPException(422, "Link the activity to an account, contact or opportunity")
    for model, val in ((Account, data.account_id), (Contact, data.contact_id), (Opportunity, data.opportunity_id)):
        if val:
            get_or_404(db, model, val)
    act = Activity(**data.model_dump(), created_by_id=user.id)
    act.owner_id = act.owner_id or user.id
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


@router.patch("/{activity_id}", response_model=ActivityOut)
def update_activity(activity_id: int, data: ActivityUpdate, db: Session = Depends(get_db),
                    _: User = Depends(require_writer)):
    act = get_or_404(db, Activity, activity_id)
    apply_changes(act, data)
    db.commit()
    db.refresh(act)
    return act


@router.delete("/{activity_id}", status_code=204)
def delete_activity(activity_id: int, db: Session = Depends(get_db), _: User = Depends(require_writer)):
    db.delete(get_or_404(db, Activity, activity_id))
    db.commit()
