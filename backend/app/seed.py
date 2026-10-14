"""Idempotent reference data: brands, pipelines, platform partners, starter catalog, first admin.

Run with:  python -m app.seed
Prices are starting points only. Review them in Settings > Products before quoting.
"""
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal
from .models import Account, Brand, Pipeline, PriceBook, PriceBookEntry, Product, Stage, User
from .security import hash_password

BRANDS = [
    {"code": "METRICSHUB", "name": "MetricsHub", "quote_prefix": "MH", "default_currency": "USD",
     "website": "https://metricshub.com"},
    {"code": "SENTRY", "name": "Sentry Software", "quote_prefix": "SEN", "default_currency": "USD",
     "website": "https://www.sentrysoftware.com"},
]

PIPELINES = {
    ("New Business", "new_business"): [
        ("New", 10, "open"), ("Discovery", 20, "open"), ("Demo", 30, "open"), ("PoC / Trial", 50, "open"),
        ("Proposal / Follow-up", 60, "open"), ("Negotiation", 80, "open"), ("Won", 100, "won"),
        ("Lost", 0, "lost"),
    ],
    ("Renewals", "renewal"): [
        ("Upcoming renewal", 70, "open"), ("Renewal pending", 90, "open"), ("Renewed", 100, "won"),
        ("Churned", 0, "lost"),
    ],
}

PLATFORMS = [
    ("BMC Software (BMC Helix)", "bmc.com"), ("Datadog", "datadoghq.com"), ("Splunk", "splunk.com"),
    ("Grafana Labs", "grafana.com"), ("Dynatrace", "dynatrace.com"), ("New Relic", "newrelic.com"),
    ("ServiceNow", "servicenow.com"), ("Elastic", "elastic.co"),
]

# (brand, sku, name, unit, billing, description)
PRODUCTS = [
    ("METRICSHUB", "MH-ENT-HOST", "MetricsHub Enterprise", "host", "recurring",
     "MetricsHub Enterprise subscription per monitored host per month (290+ connectors, embedded OTel Collector, "
     "24/7 support)."),
    ("METRICSHUB", "MH-PREMIER-SUP", "MetricsHub Premier Support", "license", "recurring",
     "Premier support add-on."),
    ("METRICSHUB", "MH-PS-DAY", "MetricsHub Professional Services (day)", "service_day", "one_time",
     "Deployment, PoC or training services, per day."),
    ("SENTRY", "SEN-BHOM-BUNDLE", "Sentry Bundle for BMC Helix Operations Management", "resource_unit", "recurring",
     "All Sentry KMs, Monitoring Studio X and MetricsHub for BHOM, per resource unit per month."),
    ("SENTRY", "SEN-BHCO-BUNDLE", "Sentry Bundle for BMC Helix Continuous Optimization", "resource_unit",
     "recurring", "Storage All-in-One ETL and views for BHCO, per resource unit per month."),
    ("SENTRY", "SEN-HW-KM", "Hardware Sentry KM", "physical_system", "recurring",
     "Hardware monitoring for BMC Helix Operations Management, per physical system."),
    ("SENTRY", "SEN-SA-KM", "Storage Analyzer KM", "front_end_ports_5", "recurring",
     "Storage monitoring for BHOM, per 5 active front-end ports."),
    ("SENTRY", "SEN-MSX", "Monitoring Studio X", "host", "recurring", "No-code custom monitoring for PATROL."),
    ("SENTRY", "SEN-STORAGE-ETL", "Storage All-in-One ETL", "front_end_ports_5", "recurring",
     "Storage capacity ETL for BHCO, per 5 active front-end ports."),
    ("SENTRY", "SEN-BACKUP-KM", "Backup & High-Availability KMs", "physical_system", "recurring",
     "NetBackup, Spectrum Protect, NetWorker, Veritas Cluster... per managed system."),
    ("SENTRY", "SEN-PS-DAY", "Sentry Professional Services (day)", "service_day", "one_time",
     "Services per day."),
]

# Price book name -> (brand, currency, channel, default, {sku: monthly price})
PRICE_BOOKS = {
    "MetricsHub Direct USD": ("METRICSHUB", "USD", "direct", True, {"MH-ENT-HOST": "15.00"}),
    "MetricsHub Direct EUR": ("METRICSHUB", "EUR", "direct", False, {}),
    # Internal FY27 BMC SaaS list prices (verify before use, never show BMC list in customer material)
    "Sentry via BMC (USD)": ("SENTRY", "USD", "bmc", True,
                             {"SEN-BHOM-BUNDLE": "76.35", "SEN-BHCO-BUNDLE": "90.55"}),
}


def seed(db: Session) -> None:
    settings = get_settings()
    brands = {}
    for b in BRANDS:
        obj = db.scalar(select(Brand).where(Brand.code == b["code"]))
        if not obj:
            obj = Brand(**b)
            db.add(obj)
            db.flush()
        brands[b["code"]] = obj

    for (name, kind), stages in PIPELINES.items():
        if not db.scalar(select(Pipeline).where(Pipeline.name == name)):
            p = Pipeline(name=name, kind=kind)
            db.add(p)
            db.flush()
            for pos, (sname, prob, skind) in enumerate(stages):
                db.add(Stage(pipeline_id=p.id, name=sname, position=pos, probability=prob, kind=skind))

    for name, domain in PLATFORMS:
        if not db.scalar(select(Account).where(Account.domain == domain)):
            db.add(Account(name=name, domain=domain, website=f"https://www.{domain}",
                           account_type="platform_partner", extra={}))

    products = {}
    for brand, sku, name, unit, billing, desc in PRODUCTS:
        p = db.scalar(select(Product).where(Product.sku == sku))
        if not p:
            p = Product(brand_id=brands[brand].id, sku=sku, name=name, unit=unit, billing_type=billing,
                        description=desc)
            db.add(p)
            db.flush()
        products[sku] = p

    for name, (brand, cur, channel, default, prices) in PRICE_BOOKS.items():
        if not db.scalar(select(PriceBook).where(PriceBook.name == name)):
            pb = PriceBook(name=name, brand_id=brands[brand].id, currency=cur, channel=channel, is_default=default)
            db.add(pb)
            db.flush()
            for sku, price in prices.items():
                db.add(PriceBookEntry(price_book_id=pb.id, product_id=products[sku].id, unit_price=Decimal(price)))

    if not db.scalar(select(User).limit(1)):
        db.add(User(email=settings.admin_email.lower(), full_name=settings.admin_name,
                    password_hash=hash_password(settings.admin_password), role="admin"))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
    print("Seed complete")
