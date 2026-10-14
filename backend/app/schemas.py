from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .enums import (
    AccountType,
    ActivityType,
    BillingType,
    Channel,
    ContactRole,
    DealType,
    LeadSource,
    Lifecycle,
    ProductUnit,
    RouteToMarket,
    UserRole,
)

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class Ref(ORM):
    id: int
    name: str


# ---------- Auth / users ----------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    role: UserRole = UserRole.sales
    brand_id: int | None = None
    is_active: bool = True


class UserCreate(UserBase):
    password: str | None = Field(default=None, min_length=8)  # None => SSO-only user


class UserUpdate(BaseModel):
    full_name: str | None = None
    role: UserRole | None = None
    brand_id: int | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8)


class UserOut(ORM, UserBase):
    id: int
    email: str
    last_login_at: dt.datetime | None = None


class UserRef(ORM):
    id: int
    full_name: str


# ---------- Brands ----------
class BrandOut(ORM):
    id: int
    code: str
    name: str
    quote_prefix: str
    default_currency: str
    website: str | None


# ---------- Accounts ----------
class AccountBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    account_type: AccountType = AccountType.prospect
    domain: str | None = None
    website: str | None = None
    industry: str | None = None
    country: str | None = None
    region: str | None = None
    city: str | None = None
    address: str | None = None
    phone: str | None = None
    vat_number: str | None = None
    parent_id: int | None = None
    owner_id: int | None = None
    notes: str | None = None

    @field_validator("domain")
    @classmethod
    def norm_domain(cls, v: str | None) -> str | None:
        if not v:
            return None
        v = v.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
        return v.split("/")[0] or None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(AccountBase):
    name: str | None = None  # type: ignore[assignment]
    account_type: AccountType | None = None  # type: ignore[assignment]


class AccountOut(ORM, AccountBase):
    id: int
    owner: UserRef | None = None
    created_at: dt.datetime
    updated_at: dt.datetime
    contact_count: int = 0
    open_opportunity_count: int = 0


# ---------- Contacts ----------
class ContactBase(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    mobile: str | None = None
    job_title: str | None = None
    account_id: int | None = None
    role: ContactRole = ContactRole.customer_contact
    lifecycle: Lifecycle = Lifecycle.lead
    source: LeadSource | None = None
    brand_id: int | None = None
    owner_id: int | None = None
    country: str | None = None
    linkedin: str | None = None
    consent_marketing: bool = False
    unsubscribed: bool = False
    notes: str | None = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(ContactBase):
    role: ContactRole | None = None  # type: ignore[assignment]
    lifecycle: Lifecycle | None = None  # type: ignore[assignment]
    consent_marketing: bool | None = None  # type: ignore[assignment]
    unsubscribed: bool | None = None  # type: ignore[assignment]


class ContactOut(ORM, ContactBase):
    id: int
    email: str | None = None
    source: str | None = None
    full_name: str = ""
    account: Ref | None = None
    owner: UserRef | None = None
    consent_at: dt.datetime | None = None
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Products / price books ----------
class ProductBase(BaseModel):
    brand_id: int
    sku: str = Field(min_length=1, max_length=64)
    name: str
    description: str | None = None
    unit: ProductUnit = ProductUnit.host
    billing_type: BillingType = BillingType.recurring
    active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    brand_id: int | None = None
    sku: str | None = None
    name: str | None = None
    description: str | None = None
    unit: ProductUnit | None = None
    billing_type: BillingType | None = None
    active: bool | None = None


class PriceOut(BaseModel):
    price_book_id: int
    price_book: str
    currency: str
    unit_price: Decimal


class ProductOut(ORM, ProductBase):
    id: int
    prices: list[PriceOut] = []


class PriceBookEntryIn(BaseModel):
    product_id: int
    unit_price: Decimal = Field(ge=0)


class PriceBookBase(BaseModel):
    name: str
    brand_id: int | None = None
    currency: str = Field(default="USD", min_length=3, max_length=3)
    channel: Channel = Channel.direct
    is_default: bool = False
    active: bool = True


class PriceBookCreate(PriceBookBase):
    entries: list[PriceBookEntryIn] = []


class PriceBookUpdate(BaseModel):
    name: str | None = None
    brand_id: int | None = None
    currency: str | None = None
    channel: Channel | None = None
    is_default: bool | None = None
    active: bool | None = None
    entries: list[PriceBookEntryIn] | None = None


class PriceBookEntryOut(ORM):
    product_id: int
    unit_price: Decimal


class PriceBookOut(ORM, PriceBookBase):
    id: int
    entries: list[PriceBookEntryOut] = []


# ---------- Pipelines ----------
class StageOut(ORM):
    id: int
    name: str
    position: int
    probability: int
    kind: str


class PipelineOut(ORM):
    id: int
    name: str
    kind: str
    stages: list[StageOut]


# ---------- Opportunities ----------
class LineItemIn(BaseModel):
    product_id: int | None = None
    name: str | None = None
    description: str | None = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal | None = Field(default=None, ge=0)  # None => price book price
    discount_pct: Decimal = Field(default=Decimal(0), ge=0, le=100)
    term_months: int | None = Field(default=None, ge=1, le=120)
    billing_type: BillingType | None = None


class LineItemOut(ORM):
    id: int
    product_id: int | None
    position: int
    name: str
    description: str | None
    unit: str | None
    billing_type: str
    quantity: Decimal
    unit_price: Decimal
    discount_pct: Decimal
    term_months: int | None
    line_total: Decimal


class OpportunityBase(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    account_id: int
    brand_id: int
    owner_id: int | None = None
    pipeline_id: int | None = None
    stage_id: int | None = None
    deal_type: DealType = DealType.new
    lead_source: LeadSource | None = None
    referring_platform_id: int | None = None
    partner_contact_id: int | None = None
    primary_contact_id: int | None = None
    route_to_market: RouteToMarket = RouteToMarket.direct
    reseller_id: int | None = None
    price_book_id: int | None = None
    currency: str | None = None
    expected_close_date: dt.date | None = None
    contract_start: dt.date | None = None
    contract_end: dt.date | None = None
    term_months: int = Field(default=12, ge=1, le=120)
    probability: int | None = Field(default=None, ge=0, le=100)
    lost_reason: str | None = None
    description: str | None = None
    next_step: str | None = None


class OpportunityCreate(OpportunityBase):
    line_items: list[LineItemIn] = []


class OpportunityUpdate(BaseModel):
    title: str | None = None
    account_id: int | None = None
    brand_id: int | None = None
    owner_id: int | None = None
    stage_id: int | None = None
    deal_type: DealType | None = None
    lead_source: LeadSource | None = None
    referring_platform_id: int | None = None
    partner_contact_id: int | None = None
    primary_contact_id: int | None = None
    route_to_market: RouteToMarket | None = None
    reseller_id: int | None = None
    price_book_id: int | None = None
    currency: str | None = None
    expected_close_date: dt.date | None = None
    contract_start: dt.date | None = None
    contract_end: dt.date | None = None
    term_months: int | None = Field(default=None, ge=1, le=120)
    probability: int | None = Field(default=None, ge=0, le=100)
    lost_reason: str | None = None
    description: str | None = None
    next_step: str | None = None
    line_items: list[LineItemIn] | None = None


class StageMove(BaseModel):
    stage_id: int
    lost_reason: str | None = None


class OpportunityOut(ORM, OpportunityBase):
    id: int
    pipeline_id: int
    stage_id: int
    currency: str
    stage: StageOut
    account: Ref
    brand: Ref
    owner: UserRef | None = None
    referring_platform: Ref | None = None
    reseller: Ref | None = None
    partner_contact: ContactOut | None = None
    primary_contact: ContactOut | None = None
    amount_tcv: Decimal
    amount_arr: Decimal
    effective_probability: int = 0
    weighted_amount: Decimal = Decimal(0)
    closed_at: dt.datetime | None = None
    renewed_from_id: int | None = None
    line_items: list[LineItemOut] = []
    created_at: dt.datetime
    updated_at: dt.datetime


class PricePreviewIn(BaseModel):
    term_months: int = Field(default=12, ge=1, le=120)
    price_book_id: int | None = None
    line_items: list[LineItemIn]


class PricePreviewOut(BaseModel):
    line_items: list[dict]
    tcv: Decimal
    arr: Decimal
    recurring: Decimal
    one_time: Decimal


# ---------- Activities ----------
class ActivityBase(BaseModel):
    type: ActivityType
    subject: str = Field(min_length=1, max_length=255)
    body: str | None = None
    due_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    owner_id: int | None = None
    account_id: int | None = None
    contact_id: int | None = None
    opportunity_id: int | None = None


class ActivityCreate(ActivityBase):
    pass


class ActivityUpdate(BaseModel):
    subject: str | None = None
    body: str | None = None
    due_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    owner_id: int | None = None


class ActivityOut(ORM, ActivityBase):
    id: int
    owner: UserRef | None = None
    created_at: dt.datetime


# ---------- Imports ----------
class ImportPreview(BaseModel):
    headers: list[str]
    sample: list[dict]
    total_rows: int
    suggested_mapping: dict[str, str | None]
    fields: list[str]


class ImportResult(ORM):
    id: int
    entity: str
    filename: str
    total: int
    created: int
    updated: int
    skipped: int
    errors: list
