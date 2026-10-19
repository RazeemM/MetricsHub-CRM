from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(14, 2)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ExternalRefMixin:
    """Identity of a record in the system it was migrated from (e.g. Freshsales), for idempotent re-imports."""

    external_source: Mapped[str | None] = mapped_column(String(30))
    external_id: Mapped[str | None] = mapped_column(String(64))


class Brand(Base):
    __tablename__ = "brands"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    quote_prefix: Mapped[str] = mapped_column(String(16))
    default_currency: Mapped[str] = mapped_column(String(3), default="USD")
    website: Mapped[str | None] = mapped_column(String(255))


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="sales")
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sso_subject: Mapped[str | None] = mapped_column(String(255), unique=True)
    last_login_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    brand: Mapped[Brand | None] = relationship()


class Account(ExternalRefMixin, TimestampMixin, Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    account_type: Mapped[str] = mapped_column(String(32), default="prospect", index=True)
    domain: Mapped[str | None] = mapped_column(String(255), index=True)
    website: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(120))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(60))
    vat_number: Mapped[str | None] = mapped_column(String(60))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    owner: Mapped[User | None] = relationship()
    parent: Mapped[Account | None] = relationship(remote_side=[id])
    contacts: Mapped[list[Contact]] = relationship(back_populates="account")


class Contact(ExternalRefMixin, TimestampMixin, Base):
    __tablename__ = "contacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(60))
    mobile: Mapped[str | None] = mapped_column(String(60))
    job_title: Mapped[str | None] = mapped_column(String(160))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    role: Mapped[str] = mapped_column(String(40), default="customer_contact")
    lifecycle: Mapped[str] = mapped_column(String(20), default="lead", index=True)
    source: Mapped[str | None] = mapped_column(String(40))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    country: Mapped[str | None] = mapped_column(String(80))
    linkedin: Mapped[str | None] = mapped_column(String(255))
    consent_marketing: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    unsubscribed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    account: Mapped[Account | None] = relationship(back_populates="contacts")
    owner: Mapped[User | None] = relationship()
    brand: Mapped[Brand | None] = relationship()

    @property
    def full_name(self) -> str:
        return " ".join(p for p in (self.first_name, self.last_name) if p) or (self.email or "")


Index("uq_contacts_email_lower", func.lower(Contact.email), unique=True)
Index("uq_contacts_external", Contact.external_source, Contact.external_id, unique=True)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    sku: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str] = mapped_column(String(32), default="host")
    billing_type: Mapped[str] = mapped_column(String(16), default="recurring")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    brand: Mapped[Brand] = relationship()


class PriceBook(TimestampMixin, Base):
    __tablename__ = "price_books"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    channel: Mapped[str] = mapped_column(String(20), default="direct")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    entries: Mapped[list[PriceBookEntry]] = relationship(back_populates="price_book", cascade="all, delete-orphan")


class PriceBookEntry(Base):
    __tablename__ = "price_book_entries"
    __table_args__ = (UniqueConstraint("price_book_id", "product_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    price_book_id: Mapped[int] = mapped_column(ForeignKey("price_books.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    price_book: Mapped[PriceBook] = relationship(back_populates="entries")
    product: Mapped[Product] = relationship()


class Pipeline(Base):
    __tablename__ = "pipelines"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(20))
    stages: Mapped[list[Stage]] = relationship(order_by="Stage.position", back_populates="pipeline")


class Stage(Base):
    __tablename__ = "stages"
    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    position: Mapped[int] = mapped_column(Integer)
    probability: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="open")
    pipeline: Mapped[Pipeline] = relationship(back_populates="stages")


class Opportunity(ExternalRefMixin, TimestampMixin, Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="RESTRICT"), index=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id"))
    stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id"), index=True)
    deal_type: Mapped[str] = mapped_column(String(20), default="new")
    lead_source: Mapped[str | None] = mapped_column(String(40))
    referring_platform_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    partner_contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    primary_contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    route_to_market: Mapped[str] = mapped_column(String(20), default="direct")
    reseller_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    price_book_id: Mapped[int | None] = mapped_column(ForeignKey("price_books.id", ondelete="SET NULL"))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    expected_close_date: Mapped[dt.date | None] = mapped_column(Date)
    contract_start: Mapped[dt.date | None] = mapped_column(Date)
    contract_end: Mapped[dt.date | None] = mapped_column(Date)
    term_months: Mapped[int] = mapped_column(Integer, default=12)
    probability: Mapped[int | None] = mapped_column(Integer)  # override of stage probability
    amount_tcv: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    amount_arr: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    lost_reason: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    next_step: Mapped[str | None] = mapped_column(String(255))
    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    renewed_from_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"))

    account: Mapped[Account] = relationship(foreign_keys=[account_id])
    referring_platform: Mapped[Account | None] = relationship(foreign_keys=[referring_platform_id])
    reseller: Mapped[Account | None] = relationship(foreign_keys=[reseller_id])
    partner_contact: Mapped[Contact | None] = relationship(foreign_keys=[partner_contact_id])
    primary_contact: Mapped[Contact | None] = relationship(foreign_keys=[primary_contact_id])
    brand: Mapped[Brand] = relationship()
    owner: Mapped[User | None] = relationship()
    stage: Mapped[Stage] = relationship()
    pipeline: Mapped[Pipeline] = relationship()
    line_items: Mapped[list[LineItem]] = relationship(
        back_populates="opportunity", cascade="all, delete-orphan", order_by="LineItem.position"
    )

    @property
    def effective_probability(self) -> int:
        if self.stage is not None and self.stage.kind != "open":
            return self.stage.probability
        return self.probability if self.probability is not None else (self.stage.probability if self.stage else 0)

    @property
    def weighted_amount(self) -> Decimal:
        return (Decimal(self.amount_tcv or 0) * Decimal(self.effective_probability) / Decimal(100)).quantize(
            Decimal("0.01")
        )


class LineItem(Base):
    __tablename__ = "opportunity_line_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"))
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(32))
    billing_type: Mapped[str] = mapped_column(String(16), default="recurring")
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    unit_price: Mapped[Decimal] = mapped_column(Money)
    discount_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    term_months: Mapped[int | None] = mapped_column(Integer)  # null => opportunity term
    line_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))

    opportunity: Mapped[Opportunity] = relationship(back_populates="line_items")
    product: Mapped[Product | None] = relationship()


class StageHistory(Base):
    __tablename__ = "opportunity_stage_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    from_stage_id: Mapped[int | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"))
    to_stage_id: Mapped[int] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"))
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Activity(TimestampMixin, Base):
    __tablename__ = "activities"
    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(16))
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    due_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    owner: Mapped[User | None] = relationship(foreign_keys=[owner_id])


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    entity: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    total: Mapped[int] = mapped_column(Integer, default=0)
    created: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    entity: Mapped[str] = mapped_column(String(40), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    action: Mapped[str] = mapped_column(String(20))
    changes: Mapped[dict] = mapped_column(JSONB, default=dict)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuoteTemplate(TimestampMixin, Base):
    """Per-brand, admin-editable layout and wording for quotes."""

    __tablename__ = "quote_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id", ondelete="CASCADE"), unique=True)
    company_name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(Text)
    vat_number: Mapped[str | None] = mapped_column(String(60))
    registration: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(60))
    website: Mapped[str | None] = mapped_column(String(200))
    logo_data_uri: Mapped[str | None] = mapped_column(Text)
    logo_height: Mapped[int] = mapped_column(Integer, default=36)
    header_show_name: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    header_bg: Mapped[str] = mapped_column(String(9), default="#141A22")
    header_text_color: Mapped[str] = mapped_column(String(9), default="#FFFFFF")
    accent_color: Mapped[str] = mapped_column(String(9), default="#7C5CFF")
    title: Mapped[str] = mapped_column(String(80), default="Quotation")
    intro_text: Mapped[str | None] = mapped_column(Text)
    terms_text: Mapped[str | None] = mapped_column(Text)
    payment_terms: Mapped[str | None] = mapped_column(String(255))
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    footer_text: Mapped[str | None] = mapped_column(Text)
    show_discount: Mapped[bool] = mapped_column(Boolean, default=True)
    show_signature: Mapped[bool] = mapped_column(Boolean, default=True)
    email_subject: Mapped[str | None] = mapped_column(String(255))
    email_body: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[Brand] = relationship()


class Quote(Base):
    """An immutable snapshot of an opportunity's pricing, rendered to PDF."""

    __tablename__ = "quotes"
    __table_args__ = (UniqueConstraint("number", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    opportunity_id: Mapped[int] = mapped_column(ForeignKey("opportunities.id", ondelete="CASCADE"), index=True)
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    number: Mapped[str] = mapped_column(String(40), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft, sent, accepted, rejected, expired
    issue_date: Mapped[dt.date] = mapped_column(Date)
    valid_until: Mapped[dt.date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    term_months: Mapped[int] = mapped_column(Integer)
    contract_start: Mapped[dt.date | None] = mapped_column(Date)
    contract_end: Mapped[dt.date | None] = mapped_column(Date)
    customer: Mapped[dict] = mapped_column(JSONB, default=dict)
    lines: Mapped[list] = mapped_column(JSONB, default=list)
    amount_tcv: Mapped[Decimal] = mapped_column(Money)
    amount_arr: Mapped[Decimal] = mapped_column(Money)
    amount_recurring: Mapped[Decimal] = mapped_column(Money)
    amount_one_time: Mapped[Decimal] = mapped_column(Money)
    template: Mapped[dict] = mapped_column(JSONB, default=dict)  # snapshot so later template edits don't alter it
    notes: Mapped[str | None] = mapped_column(Text)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[User | None] = relationship()


class Entitlement(TimestampMixin, Base):
    """One licence line a customer owns (e.g. one line of a BMC MarketZone fee report).

    A customer's holding of a product is the set of its lines for that product: see entitlements.holdings()."""

    __tablename__ = "entitlements"
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    reseller_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))
    brand_id: Mapped[int] = mapped_column(ForeignKey("brands.id"))
    product_name: Mapped[str] = mapped_column(String(255))  # as named in the report: the entitled product
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    license_type: Mapped[str] = mapped_column(String(16), default="term")  # term, support, saas, perpetual
    start_date: Mapped[dt.date | None] = mapped_column(Date)
    end_date: Mapped[dt.date | None] = mapped_column(Date, index=True)  # none for a perpetual licence
    net_amount: Mapped[Decimal | None] = mapped_column(Money)  # invoiced to the customer (BMC: USD Total Net)
    fee_amount: Mapped[Decimal | None] = mapped_column(Money)  # due to Sentry (BMC: Fee)
    country: Mapped[str | None] = mapped_column(String(80))  # where it is sold (BMC: Sold To Country)
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    source: Mapped[str] = mapped_column(String(40), default="manual")  # bmc_mzd, manual
    source_ref: Mapped[str | None] = mapped_column(String(80))  # invoice / credit memo number
    document_date: Mapped[dt.date | None] = mapped_column(Date)  # invoice date: tells how far a report reaches
    report_name: Mapped[str | None] = mapped_column(String(255))
    line_key: Mapped[str | None] = mapped_column(String(400), unique=True)  # makes report imports idempotent
    renewal_notified_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    lapse_resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    lapse_resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    lapse_resolution: Mapped[str | None] = mapped_column(Text)

    account: Mapped[Account] = relationship(foreign_keys=[account_id])
    reseller: Mapped[Account | None] = relationship(foreign_keys=[reseller_id])
    lapse_resolved_by: Mapped[User | None] = relationship()


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))  # renewal_due, ...
    title: Mapped[str] = mapped_column(String(255))
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(255))  # path in the web app
    read_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MailingList(TimestampMixin, Base):
    """A list of contacts to email: a static list (leads, an event's attendees...) or newsletter subscribers."""

    __tablename__ = "mailing_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(16), default="list")  # list, newsletter
    description: Mapped[str | None] = mapped_column(Text)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"))
    brand: Mapped[Brand | None] = relationship()


class ListMember(Base):
    __tablename__ = "mailing_list_members"
    __table_args__ = (UniqueConstraint("list_id", "contact_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("mailing_lists.id", ondelete="CASCADE"), index=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default="subscribed")  # subscribed, unsubscribed, pending
    # pending = signed up on a web form, waiting for the double opt-in confirmation
    source: Mapped[str | None] = mapped_column(String(40))  # manual, filter, import, web form...
    added_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    unsubscribed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    contact: Mapped[Contact] = relationship()


class EmailTemplate(TimestampMixin, Base):
    """Reusable HTML email with merge fields ({first_name}, {company}...), used by campaigns and newsletters."""

    __tablename__ = "email_templates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"))
    subject: Mapped[str] = mapped_column(String(255))
    preheader: Mapped[str | None] = mapped_column(String(255))  # preview text shown by mail clients
    body_html: Mapped[str] = mapped_column(Text)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    brand: Mapped[Brand | None] = relationship()


class Campaign(TimestampMixin, Base):
    """A bulk email (campaign or newsletter issue). Its content is copied from a template and frozen once sent."""

    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="campaign")  # campaign, newsletter
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"))
    template_id: Mapped[int | None] = mapped_column(ForeignKey("email_templates.id", ondelete="SET NULL"))
    subject: Mapped[str] = mapped_column(String(255), default="")
    preheader: Mapped[str | None] = mapped_column(String(255))
    body_html: Mapped[str] = mapped_column(Text, default="")
    from_name: Mapped[str | None] = mapped_column(String(120))
    reply_to: Mapped[str | None] = mapped_column(String(255))
    list_ids: Mapped[list] = mapped_column(JSONB, default=list)
    require_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    track_opens: Mapped[bool] = mapped_column(Boolean, default=True)
    track_clicks: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    # draft, scheduled, sending, paused, sent, cancelled
    scheduled_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))  # why sending paused
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_by: Mapped[User | None] = relationship()


class CampaignRecipient(Base):
    __tablename__ = "campaign_recipients"
    __table_args__ = (UniqueConstraint("campaign_id", "contact_id"),
                      Index("ix_campaign_recipients_status", "campaign_id", "status"))
    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    email: Mapped[str] = mapped_column(String(255))
    token: Mapped[str] = mapped_column(String(64), unique=True)  # identifies the recipient in links and the pixel
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued, sent, failed, skipped
    reason: Mapped[str | None] = mapped_column(String(255))  # why skipped / failed
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    open_count: Mapped[int] = mapped_column(Integer, default=0)
    clicked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    click_count: Mapped[int] = mapped_column(Integer, default=0)
    unsubscribed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    contact: Mapped[Contact | None] = relationship()


class WebForm(TimestampMixin, Base):
    """A website form (Contact, Quote request, Trial, Newsletter...) that posts submissions to the CRM."""

    __tablename__ = "web_forms"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)  # in the URL: /api/public/forms/{key}
    name: Mapped[str] = mapped_column(String(160))
    brand_id: Mapped[int | None] = mapped_column(ForeignKey("brands.id", ondelete="SET NULL"))
    lead_source: Mapped[str] = mapped_column(String(40), default="website_contact")
    field_map: Mapped[dict] = mapped_column(JSONB, default=dict)  # website field -> contact field
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    list_id: Mapped[int | None] = mapped_column(ForeignKey("mailing_lists.id", ondelete="SET NULL"))
    auth_mode: Mapped[str] = mapped_column(String(10), default="hmac")  # hmac (server to server), token (browser)
    secret: Mapped[str] = mapped_column(String(80))
    allowed_origins: Mapped[list] = mapped_column(JSONB, default=list)  # e.g. ["https://www.metricshub.com"]
    honeypot_field: Mapped[str | None] = mapped_column(String(64), default="website")
    redirect_url: Mapped[str | None] = mapped_column(String(500))  # thank-you page after a plain HTML post
    confirm_redirect_url: Mapped[str | None] = mapped_column(String(500))  # after the double opt-in confirmation
    confirm_subject: Mapped[str | None] = mapped_column(String(255))
    confirm_body_html: Mapped[str | None] = mapped_column(Text)
    notify_owner: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_hour: Mapped[int] = mapped_column(Integer, default=20)  # accepted submissions per IP address
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    brand: Mapped[Brand | None] = relationship()
    owner: Mapped[User | None] = relationship()
    mailing_list: Mapped[MailingList | None] = relationship()


class FormSubmission(Base):
    __tablename__ = "web_form_submissions"
    __table_args__ = (Index("ix_web_form_submissions_rate", "form_id", "ip", "created_at"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    form_id: Mapped[int] = mapped_column(ForeignKey("web_forms.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    status: Mapped[str] = mapped_column(String(16))  # accepted, pending (opt-in), confirmed, spam, error
    email: Mapped[str | None] = mapped_column(String(255))
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"))
    contact_created: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(String(500))  # why spam / error, or that the confirmation was sent


Index("uq_accounts_external", Account.external_source, Account.external_id, unique=True)
Index("uq_opportunities_external", Opportunity.external_source, Opportunity.external_id, unique=True)
