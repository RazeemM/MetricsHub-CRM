"""Saved views: named filters for the pipeline board, private to their owner or shared with every user."""
import datetime as dt
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import SavedView, User
from ..security import get_current_user

router = APIRouter(prefix="/api/views", tags=["views"])

ClosePreset = Literal["any", "overdue", "this_month", "next_month", "this_quarter", "next_90_days", "this_year",
                      "none", "custom"]


class PipelineFilters(BaseModel):
    """What a pipeline view stores. Close date presets are relative, so a view stays current: "this_quarter" is
    always the current quarter. "mine" means the deals of whoever opens the view."""
    model_config = {"extra": "ignore"}

    pipeline_id: int | None = None
    q: str = ""
    mine: bool = False
    owner_ids: list[int] = []
    brand_ids: list[int] = []
    platform_ids: list[int] = []
    deal_types: list[str] = []
    routes: list[str] = []
    lead_sources: list[str] = []
    close: ClosePreset = "any"
    close_from: dt.date | None = None  # with close = "custom"
    close_to: dt.date | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    hide_closed: bool = False  # hide the won and lost columns
    sort: Literal["close", "amount", "updated", "created", "title", "account"] = "close"


class ViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    shared: bool = False
    filters: PipelineFilters = Field(default_factory=PipelineFilters)


class ViewUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    shared: bool | None = None
    filters: PipelineFilters | None = None


class ViewOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    entity: str
    name: str
    shared: bool
    filters: PipelineFilters
    owner_id: int
    owner_name: str | None = None
    editable: bool = False
    updated_at: dt.datetime


def _out(v: SavedView, user: User) -> ViewOut:
    o = ViewOut.model_validate(v)
    o.owner_name = v.owner.full_name if v.owner else None
    o.editable = v.owner_id == user.id or user.role == "admin"
    return o


def _visible(db: Session, user: User, view_id: int) -> SavedView:
    v = db.get(SavedView, view_id)
    if not v or (v.owner_id != user.id and not v.shared):
        raise HTTPException(404, "View not found")
    return v


def _editable(db: Session, user: User, view_id: int) -> SavedView:
    v = _visible(db, user, view_id)
    if v.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "Only the view's owner or an administrator can change it")
    return v


def _unique_name(db: Session, user: User, entity: str, name: str, exclude_id: int | None = None) -> None:
    q = select(SavedView.id).where(SavedView.entity == entity, SavedView.owner_id == user.id,
                                   func.lower(SavedView.name) == name.strip().lower())
    if exclude_id:
        q = q.where(SavedView.id != exclude_id)
    if db.scalar(q):
        raise HTTPException(409, "You already have a view with this name")


@router.get("", response_model=list[ViewOut])
def list_views(entity: Literal["pipeline"] = Query("pipeline"), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)):
    """Your views, then the views other users shared."""
    views = db.scalars(select(SavedView).options(selectinload(SavedView.owner))
                       .where(SavedView.entity == entity, or_(SavedView.owner_id == user.id, SavedView.shared))
                       .order_by((SavedView.owner_id != user.id), func.lower(SavedView.name))).all()
    return [_out(v, user) for v in views]


@router.post("", response_model=ViewOut, status_code=201)
def create_view(data: ViewIn, entity: Literal["pipeline"] = Query("pipeline"), db: Session = Depends(get_db),
                user: User = Depends(get_current_user)):
    _unique_name(db, user, entity, data.name)
    v = SavedView(entity=entity, name=data.name.strip(), owner_id=user.id, shared=data.shared,
                  filters=data.filters.model_dump(mode="json"))
    db.add(v)
    db.commit()
    db.refresh(v)
    return _out(v, user)


@router.patch("/{view_id}", response_model=ViewOut)
def update_view(view_id: int, data: ViewUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    v = _editable(db, user, view_id)
    if data.name is not None:
        _unique_name(db, user, v.entity, data.name, v.id)
        v.name = data.name.strip()
    if data.shared is not None:
        v.shared = data.shared
    if data.filters is not None:
        v.filters = data.filters.model_dump(mode="json")
    db.commit()
    db.refresh(v)
    return _out(v, user)


@router.delete("/{view_id}", status_code=204)
def delete_view(view_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    db.delete(_editable(db, user, view_id))
    db.commit()
