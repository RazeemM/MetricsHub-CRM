import datetime as dt
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AuditLog, User


def paginate(db: Session, stmt, page: int, page_size: int) -> tuple[list, int]:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return list(items), total


def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {obj_id} not found")
    return obj


def _jsonable(v: Any) -> Any:
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def apply_changes(obj, data: BaseModel | dict, exclude: set[str] | None = None) -> dict:
    """Apply explicitly-set fields to an ORM object; return {field: [old, new]} for auditing."""
    values = data.model_dump(exclude_unset=True) if isinstance(data, BaseModel) else data
    changes = {}
    for key, value in values.items():
        if exclude and key in exclude:
            continue
        old = getattr(obj, key)
        if old != value:
            setattr(obj, key, value)
            changes[key] = [_jsonable(old), _jsonable(value)]
    return changes


def audit(db: Session, user: User | None, entity: str, entity_id: int, action: str, changes: dict | None = None):
    db.add(AuditLog(user_id=user.id if user else None, entity=entity, entity_id=entity_id,
                    action=action, changes=changes or {}))
