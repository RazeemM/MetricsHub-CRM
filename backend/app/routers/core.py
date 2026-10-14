"""Auth, users, brands, pipelines and global search."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..crud import apply_changes, audit, get_or_404
from ..db import get_db
from ..models import Account, Brand, Contact, Opportunity, Pipeline, User
from ..schemas import BrandOut, PipelineOut, Token, UserCreate, UserOut, UserUpdate
from ..security import create_access_token, get_current_user, hash_password, require_admin, verify_password

router = APIRouter(prefix="/api")


@router.post("/auth/login", response_model=Token, tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(func.lower(User.email) == form.username.strip().lower()))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Incorrect email or password")
    return Token(access_token=create_access_token(user.id))


@router.get("/auth/me", response_model=UserOut, tags=["auth"])
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut], tags=["users"])
def list_users(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(User).order_by(User.full_name)).all()


@router.post("/users", response_model=UserOut, status_code=201, tags=["users"])
def create_user(data: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    if db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(409, "A user with this email already exists")
    user = User(**data.model_dump(exclude={"password"}), password_hash=hash_password(data.password))
    user.email = user.email.lower()
    db.add(user)
    db.flush()
    audit(db, admin, "user", user.id, "create")
    db.commit()
    return user


@router.patch("/users/{user_id}", response_model=UserOut, tags=["users"])
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = get_or_404(db, User, user_id)
    if data.password:
        user.password_hash = hash_password(data.password)
    changes = apply_changes(user, data, exclude={"password"})
    audit(db, admin, "user", user.id, "update", changes)
    db.commit()
    return user


@router.get("/brands", response_model=list[BrandOut], tags=["reference"])
def list_brands(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Brand).order_by(Brand.id)).all()


@router.get("/pipelines", response_model=list[PipelineOut], tags=["reference"])
def list_pipelines(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Pipeline).options(selectinload(Pipeline.stages)).order_by(Pipeline.id)).all()


@router.get("/search", tags=["search"])
def search(q: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    term = f"%{q.strip()}%"
    if len(q.strip()) < 2:
        return {"accounts": [], "contacts": [], "opportunities": []}
    accounts = db.scalars(select(Account).where(or_(Account.name.ilike(term), Account.domain.ilike(term))).limit(8))
    contacts = db.scalars(select(Contact).where(or_(
        Contact.email.ilike(term), Contact.first_name.ilike(term), Contact.last_name.ilike(term),
        func.concat(Contact.first_name, " ", Contact.last_name).ilike(term))).limit(8))
    opps = db.scalars(select(Opportunity).where(Opportunity.title.ilike(term)).limit(8))
    return {
        "accounts": [{"id": a.id, "name": a.name, "type": a.account_type} for a in accounts],
        "contacts": [{"id": c.id, "name": c.full_name, "email": c.email} for c in contacts],
        "opportunities": [{"id": o.id, "name": o.title} for o in opps],
    }
