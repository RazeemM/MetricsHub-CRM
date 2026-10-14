import datetime as dt
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..crud import apply_changes, audit, get_or_404, paginate
from ..db import get_db
from ..models import Account, Contact, Opportunity, Pipeline, PriceBook, PriceBookEntry, Product, Stage, StageHistory, User
from ..pricing import compute_totals
from ..schemas import (
    OpportunityCreate,
    OpportunityOut,
    OpportunityUpdate,
    Page,
    PricePreviewIn,
    PricePreviewOut,
    StageMove,
)
from ..security import get_current_user, require_writer
from ..services import (
    brand_exists,
    change_stage,
    default_pipeline,
    default_price_book,
    on_won,
    recompute,
    set_line_items,
    sync_contract_dates,
    validate_stage,
)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

LOAD = (
    selectinload(Opportunity.account), selectinload(Opportunity.brand), selectinload(Opportunity.owner),
    selectinload(Opportunity.stage), selectinload(Opportunity.referring_platform),
    selectinload(Opportunity.reseller), selectinload(Opportunity.partner_contact),
    selectinload(Opportunity.primary_contact), selectinload(Opportunity.line_items),
)
SORTS = {"title": Opportunity.title, "amount": Opportunity.amount_tcv, "close": Opportunity.expected_close_date,
         "created_at": Opportunity.created_at, "updated_at": Opportunity.updated_at}


def _load(db: Session, opp_id: int) -> Opportunity:
    opp = db.scalar(select(Opportunity).options(*LOAD).where(Opportunity.id == opp_id))
    if not opp:
        raise HTTPException(404, "Opportunity not found")
    return opp


def build_query(q=None, pipeline_id=None, stage_id=None, brand_id=None, owner_id=None, account_id=None,
                referring_platform_id=None, status=None, lead_source=None):
    stmt = select(Opportunity).options(*LOAD).join(Stage, Opportunity.stage_id == Stage.id)
    if q:
        term = f"%{q.strip()}%"
        stmt = stmt.join(Account, Opportunity.account_id == Account.id).where(
            or_(Opportunity.title.ilike(term), Account.name.ilike(term)))
    for col, val in ((Opportunity.pipeline_id, pipeline_id), (Opportunity.stage_id, stage_id),
                     (Opportunity.brand_id, brand_id), (Opportunity.owner_id, owner_id),
                     (Opportunity.account_id, account_id),
                     (Opportunity.referring_platform_id, referring_platform_id),
                     (Opportunity.lead_source, lead_source)):
        if val:
            stmt = stmt.where(col == val)
    if status in ("open", "won", "lost"):
        stmt = stmt.where(Stage.kind == status)
    return stmt


@router.get("", response_model=Page[OpportunityOut])
def list_opportunities(
    q: str | None = None, pipeline_id: int | None = None, stage_id: int | None = None,
    brand_id: int | None = None, owner_id: int | None = None, account_id: int | None = None,
    referring_platform_id: int | None = None, status: str | None = None, lead_source: str | None = None,
    sort: str = "updated_at", desc: bool = True,
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    col = SORTS.get(sort, Opportunity.updated_at)
    stmt = build_query(q, pipeline_id, stage_id, brand_id, owner_id, account_id, referring_platform_id, status,
                       lead_source).order_by(col.desc().nulls_last() if desc else col.asc().nulls_last(),
                                             Opportunity.id)
    items, total = paginate(db, stmt, page, page_size)
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/board")
def board(
    pipeline_id: int | None = None, brand_id: int | None = None, owner_id: int | None = None,
    referring_platform_id: int | None = None, q: str | None = None,
    db: Session = Depends(get_db), _: User = Depends(get_current_user),
):
    pipeline = db.get(Pipeline, pipeline_id) if pipeline_id else default_pipeline(db)
    if not pipeline:
        raise HTTPException(404, "Pipeline not found")
    stmt = build_query(q, pipeline.id, None, brand_id, owner_id, None, referring_platform_id).order_by(
        Opportunity.expected_close_date.asc().nulls_last(), Opportunity.id)
    opps = db.scalars(stmt).unique().all()
    columns = []
    for st in sorted(pipeline.stages, key=lambda s: s.position):
        items = [o for o in opps if o.stage_id == st.id]
        columns.append({
            "stage": {"id": st.id, "name": st.name, "probability": st.probability, "kind": st.kind},
            "count": len(items),
            "total": sum((o.amount_tcv for o in items), Decimal(0)),
            "weighted": sum((o.weighted_amount for o in items), Decimal(0)),
            "items": [OpportunityOut.model_validate(o).model_dump(
                include={"id", "title", "account", "brand", "owner", "amount_tcv", "amount_arr", "currency",
                         "expected_close_date", "referring_platform", "deal_type", "next_step",
                         "effective_probability", "contract_end"}) for o in items],
        })
    return {"pipeline": {"id": pipeline.id, "name": pipeline.name, "kind": pipeline.kind}, "columns": columns}


@router.get("/{opp_id}", response_model=OpportunityOut)
def get_opportunity(opp_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _load(db, opp_id)


def _validate_refs(db: Session, opp: Opportunity) -> None:
    get_or_404(db, Account, opp.account_id)
    brand_exists(db, opp.brand_id)
    for attr in ("referring_platform_id", "reseller_id"):
        if getattr(opp, attr) and not db.get(Account, getattr(opp, attr)):
            raise HTTPException(422, f"{attr}: account not found")
    for attr in ("partner_contact_id", "primary_contact_id"):
        if getattr(opp, attr) and not db.get(Contact, getattr(opp, attr)):
            raise HTTPException(422, f"{attr}: contact not found")
    if opp.price_book_id:
        pb = db.get(PriceBook, opp.price_book_id)
        if not pb:
            raise HTTPException(422, "Price book not found")
        opp.currency = pb.currency


@router.post("", response_model=OpportunityOut, status_code=201)
def create_opportunity(data: OpportunityCreate, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    payload = data.model_dump(exclude={"line_items"})
    opp = Opportunity(**payload)
    if not opp.stage_id:
        pipeline = db.get(Pipeline, opp.pipeline_id) if opp.pipeline_id else default_pipeline(
            db, "renewal" if opp.deal_type == "renewal" else "new_business")
        opp.pipeline_id = pipeline.id
        opp.stage_id = pipeline.stages[0].id
    stage = validate_stage(db, opp, opp.stage_id)
    opp.pipeline_id = stage.pipeline_id
    if not opp.price_book_id:
        pb = default_price_book(db, opp.brand_id)
        opp.price_book_id = pb.id if pb else None
    _validate_refs(db, opp)
    opp.currency = opp.currency or "USD"
    opp.owner_id = opp.owner_id or user.id
    sync_contract_dates(opp)
    db.add(opp)
    db.flush()
    set_line_items(db, opp, data.line_items)
    if stage.kind == "lost" and not opp.lost_reason:
        raise HTTPException(422, "A lost reason is required to close an opportunity as lost")
    if stage.kind != "open":
        opp.closed_at = dt.datetime.now(dt.UTC)
        if stage.kind == "won":
            on_won(db, opp)
    db.add(StageHistory(opportunity_id=opp.id, from_stage_id=None, to_stage_id=stage.id, changed_by_id=user.id))
    audit(db, user, "opportunity", opp.id, "create")
    db.commit()
    return _load(db, opp.id)


@router.patch("/{opp_id}", response_model=OpportunityOut)
def update_opportunity(opp_id: int, data: OpportunityUpdate, db: Session = Depends(get_db),
                       user: User = Depends(require_writer)):
    opp = _load(db, opp_id)
    changes = apply_changes(opp, data, exclude={"line_items", "stage_id", "lost_reason"})
    _validate_refs(db, opp)
    sync_contract_dates(opp)
    if data.line_items is not None:
        set_line_items(db, opp, data.line_items)
        changes["line_items"] = "replaced"
    else:
        recompute(opp)
    if "lost_reason" in data.model_fields_set and data.lost_reason:
        opp.lost_reason = data.lost_reason
    if data.stage_id and data.stage_id != opp.stage_id:
        stage = validate_stage(db, opp, data.stage_id)
        changes["stage_id"] = [opp.stage_id, stage.id]
        change_stage(db, opp, stage, user, data.lost_reason)
    audit(db, user, "opportunity", opp.id, "update", changes)
    db.commit()
    return _load(db, opp.id)


@router.post("/{opp_id}/stage", response_model=OpportunityOut)
def move_stage(opp_id: int, data: StageMove, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    opp = _load(db, opp_id)
    stage = validate_stage(db, opp, data.stage_id)
    old = opp.stage_id
    change_stage(db, opp, stage, user, data.lost_reason)
    audit(db, user, "opportunity", opp.id, "stage", {"stage_id": [old, stage.id]})
    db.commit()
    return _load(db, opp.id)


@router.delete("/{opp_id}", status_code=204)
def delete_opportunity(opp_id: int, db: Session = Depends(get_db), user: User = Depends(require_writer)):
    opp = get_or_404(db, Opportunity, opp_id)
    audit(db, user, "opportunity", opp.id, "delete", {"title": opp.title})
    db.delete(opp)
    db.commit()


@router.post("/price-preview", response_model=PricePreviewOut)
def price_preview(data: PricePreviewIn, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Compute line totals without saving (used live by the deal form)."""

    class L:  # lightweight line object for compute_totals
        pass

    lines = []
    for item in data.line_items:
        ln = L()
        product = db.get(Product, item.product_id) if item.product_id else None
        price = item.unit_price
        if price is None and product and data.price_book_id:
            entry = db.scalar(select(PriceBookEntry).where(PriceBookEntry.price_book_id == data.price_book_id,
                                                           PriceBookEntry.product_id == product.id))
            price = entry.unit_price if entry else Decimal(0)
        ln.name = item.name or (product.name if product else "")
        ln.quantity, ln.unit_price, ln.discount_pct = item.quantity, price or Decimal(0), item.discount_pct
        ln.term_months = item.term_months
        ln.billing_type = item.billing_type or (product.billing_type if product else "recurring")
        lines.append(ln)
    totals = compute_totals(lines, data.term_months)
    return PricePreviewOut(
        line_items=[{"name": ln.name, "unit_price": ln.unit_price, "line_total": ln.line_total,
                     "billing_type": ln.billing_type} for ln in lines],
        tcv=totals.tcv, arr=totals.arr, recurring=totals.recurring, one_time=totals.one_time)
