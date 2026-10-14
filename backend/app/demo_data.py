"""Optional demo data so a fresh install has something to look at.

Run with:  python -m app.demo_data       (does nothing if opportunities already exist)
All company and person names are fictitious.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select

from .db import SessionLocal
from .models import Account, Brand, Contact, Opportunity, Pipeline, PriceBook, Product, Stage, User
from .schemas import LineItemIn
from .seed import seed
from .services import set_line_items, sync_contract_dates


def run() -> None:
    with SessionLocal() as db:
        seed(db)
        if db.scalar(select(func.count()).select_from(Opportunity)):
            print("Opportunities already exist, skipping demo data")
            return
        admin = db.scalar(select(User).order_by(User.id))
        mh = db.scalar(select(Brand).where(Brand.code == "METRICSHUB"))
        sen = db.scalar(select(Brand).where(Brand.code == "SENTRY"))
        plat = {a.domain: a for a in db.scalars(select(Account).where(Account.account_type == "platform_partner"))}
        prod = {p.sku: p for p in db.scalars(select(Product))}
        pb = {b.name: b for b in db.scalars(select(PriceBook))}
        nb = db.scalar(select(Pipeline).where(Pipeline.kind == "new_business"))
        stages = {s.name: s for s in db.scalars(select(Stage).where(Stage.pipeline_id == nb.id))}

        def account(name, domain, country, industry, kind="prospect"):
            a = Account(name=name, domain=domain, country=country, industry=industry, account_type=kind,
                        owner_id=admin.id, extra={})
            db.add(a)
            db.flush()
            return a

        def contact(first, last, email, acc, title, role="customer_contact", lifecycle="lead", source="direct"):
            c = Contact(first_name=first, last_name=last, email=email, account_id=acc.id, job_title=title, role=role,
                        lifecycle=lifecycle, source=source, owner_id=admin.id, extra={})
            db.add(c)
            db.flush()
            return c

        dd_am = contact("Dana", "Price", "dana.price@datadoghq.com", plat["datadoghq.com"], "Strategic Account Executive",
                        role="platform_account_manager", lifecycle="customer")
        bmc_am = contact("Luca", "Ferri", "luca.ferri@bmc.com", plat["bmc.com"], "Account Manager",
                         role="platform_account_manager", lifecycle="customer")

        a1 = account("Northwind Telecom", "northwind-telecom.example", "Canada", "Telecommunications")
        a2 = account("Fabrikam Bank", "fabrikam-bank.example", "France", "Banking")
        a3 = account("Contoso Cloud", "contoso-cloud.example", "United States", "Technology")
        a4 = account("Tailspin Government Services", "tailspin-gov.example", "United Arab Emirates", "Government")
        c1 = contact("Maya", "Chen", "maya.chen@northwind-telecom.example", a1, "Head of Infrastructure", lifecycle="qualified")
        c2 = contact("Pierre", "Martin", "pierre.martin@fabrikam-bank.example", a2, "Monitoring Lead", lifecycle="qualified")
        c3 = contact("Alex", "Rivera", "alex.rivera@contoso-cloud.example", a3, "SRE Manager", source="download")
        contact("Sara", "Haddad", "sara.haddad@tailspin-gov.example", a4, "IT Operations Director", source="website_contact")

        today = dt.date.today()
        deals = [
            ("Northwind – 6,000 servers hardware monitoring", a1, mh, "PoC / Trial", plat["datadoghq.com"], dd_am, c1,
             "marketplace", pb["MetricsHub Direct USD"], [("MH-ENT-HOST", 6000, None, 25)], 36, 45),
            ("Fabrikam – Sentry bundle for BHOM", a2, sen, "Negotiation", plat["bmc.com"], bmc_am, c2, "bmc_marketzone",
             pb["Sentry via BMC (USD)"], [("SEN-BHOM-BUNDLE", 800, None, 30)], 36, 20),
            ("Contoso – MetricsHub Enterprise trial", a3, mh, "Discovery", None, None, c3, "direct",
             pb["MetricsHub Direct USD"], [("MH-ENT-HOST", 250, None, 0), ("MH-PS-DAY", 3, "1500", 0)], 12, 75),
            ("Tailspin – storage capacity (BHCO)", a4, sen, "Demo", plat["bmc.com"], bmc_am, None, "bmc_marketzone",
             pb["Sentry via BMC (USD)"], [("SEN-BHCO-BUNDLE", 300, None, 20)], 12, 110),
        ]
        for title, acc, brand, stage, platform, am, pc, rtm, book, lines, term, close_in in deals:
            o = Opportunity(title=title, account_id=acc.id, brand_id=brand.id, owner_id=admin.id, pipeline_id=nb.id,
                            stage_id=stages[stage].id, lead_source="platform_referral" if platform else "download",
                            referring_platform_id=platform.id if platform else None,
                            partner_contact_id=am.id if am else None, primary_contact_id=pc.id if pc else None,
                            route_to_market=rtm, price_book_id=book.id, currency=book.currency, term_months=term,
                            expected_close_date=today + dt.timedelta(days=close_in),
                            contract_start=today + dt.timedelta(days=close_in + 1))
            sync_contract_dates(o)
            db.add(o)
            db.flush()
            set_line_items(db, o, [LineItemIn(product_id=prod[sku].id, quantity=Decimal(q),
                                              unit_price=Decimal(price) if price else None, discount_pct=Decimal(d))
                                   for sku, q, price, d in lines])
        db.commit()
        print("Demo data created")


if __name__ == "__main__":
    run()
