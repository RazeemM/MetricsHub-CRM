from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from ..crud import apply_changes, audit, get_or_404
from ..db import get_db
from ..models import LineItem, PriceBook, PriceBookEntry, Product, User
from ..schemas import (
    PriceBookCreate,
    PriceBookOut,
    PriceBookUpdate,
    PriceOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
)
from ..security import get_current_user, require_admin
from ..services import brand_exists

router = APIRouter(prefix="/api", tags=["catalog"])


def _product_out(db: Session, products: list[Product]) -> list[ProductOut]:
    ids = [p.id for p in products]
    rows = db.execute(
        select(PriceBookEntry.product_id, PriceBook.id, PriceBook.name, PriceBook.currency, PriceBookEntry.unit_price)
        .join(PriceBook).where(PriceBookEntry.product_id.in_(ids), PriceBook.active.is_(True))
        .order_by(PriceBook.is_default.desc(), PriceBook.name)
    ).all() if ids else []
    prices: dict[int, list[PriceOut]] = {}
    for pid, pbid, pbname, cur, price in rows:
        prices.setdefault(pid, []).append(PriceOut(price_book_id=pbid, price_book=pbname, currency=cur,
                                                   unit_price=price))
    out = []
    for p in products:
        item = ProductOut.model_validate(p)
        item.prices = prices.get(p.id, [])
        out.append(item)
    return out


@router.get("/products", response_model=list[ProductOut])
def list_products(brand_id: int | None = None, active: bool | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(Product).order_by(Product.brand_id, Product.name)
    if brand_id:
        stmt = stmt.where(Product.brand_id == brand_id)
    if active is not None:
        stmt = stmt.where(Product.active.is_(active))
    return _product_out(db, list(db.scalars(stmt)))


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(data: ProductCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    brand_exists(db, data.brand_id)
    if db.scalar(select(Product).where(func.lower(Product.sku) == data.sku.lower())):
        raise HTTPException(409, "SKU already exists")
    p = Product(**data.model_dump())
    db.add(p)
    db.flush()
    audit(db, user, "product", p.id, "create")
    db.commit()
    return _product_out(db, [p])[0]


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db),
                   user: User = Depends(require_admin)):
    p = get_or_404(db, Product, product_id)
    if data.sku and db.scalar(select(Product).where(func.lower(Product.sku) == data.sku.lower(),
                                                    Product.id != product_id)):
        raise HTTPException(409, "SKU already exists")
    audit(db, user, "product", p.id, "update", apply_changes(p, data))
    db.commit()
    return _product_out(db, [p])[0]


@router.delete("/products/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    p = get_or_404(db, Product, product_id)
    if db.scalar(select(func.count()).select_from(LineItem).where(LineItem.product_id == product_id)):
        raise HTTPException(409, "Product is used in opportunities; deactivate it instead")
    audit(db, user, "product", p.id, "delete", {"sku": p.sku})
    db.delete(p)
    db.commit()


# ---------- Price books ----------
def _load_pb(db: Session, pb_id: int) -> PriceBook:
    pb = db.scalar(select(PriceBook).options(selectinload(PriceBook.entries)).where(PriceBook.id == pb_id))
    if not pb:
        raise HTTPException(404, "Price book not found")
    return pb


def _set_entries(db: Session, pb: PriceBook, entries) -> None:
    seen = set()
    pb.entries.clear()
    db.flush()
    for e in entries:
        if e.product_id in seen:
            raise HTTPException(422, f"Product {e.product_id} listed twice")
        seen.add(e.product_id)
        get_or_404(db, Product, e.product_id)
        pb.entries.append(PriceBookEntry(product_id=e.product_id, unit_price=e.unit_price))


def _ensure_single_default(db: Session, pb: PriceBook) -> None:
    if pb.is_default:
        db.execute(update(PriceBook).where(PriceBook.id != pb.id, PriceBook.brand_id == pb.brand_id)
                   .values(is_default=False))


@router.get("/price-books", response_model=list[PriceBookOut])
def list_price_books(brand_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    stmt = select(PriceBook).options(selectinload(PriceBook.entries)).order_by(PriceBook.name)
    if brand_id:
        stmt = stmt.where(PriceBook.brand_id == brand_id)
    return db.scalars(stmt).all()


@router.post("/price-books", response_model=PriceBookOut, status_code=201)
def create_price_book(data: PriceBookCreate, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    if db.scalar(select(PriceBook).where(PriceBook.name == data.name)):
        raise HTTPException(409, "A price book with this name exists")
    pb = PriceBook(**data.model_dump(exclude={"entries"}))
    pb.currency = pb.currency.upper()
    db.add(pb)
    db.flush()
    _set_entries(db, pb, data.entries)
    _ensure_single_default(db, pb)
    audit(db, user, "price_book", pb.id, "create")
    db.commit()
    return _load_pb(db, pb.id)


@router.patch("/price-books/{pb_id}", response_model=PriceBookOut)
def update_price_book(pb_id: int, data: PriceBookUpdate, db: Session = Depends(get_db),
                      user: User = Depends(require_admin)):
    pb = _load_pb(db, pb_id)
    changes = apply_changes(pb, data, exclude={"entries"})
    if data.entries is not None:
        _set_entries(db, pb, data.entries)
        changes["entries"] = "replaced"
    _ensure_single_default(db, pb)
    audit(db, user, "price_book", pb.id, "update", changes)
    db.commit()
    return _load_pb(db, pb.id)
