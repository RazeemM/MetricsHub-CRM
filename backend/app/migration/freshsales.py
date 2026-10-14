"""Migration from Freshsales (Freshworks CRM).

Two sources produce the same normalized records:
  * export files (CSV/XLSX from Freshsales > Admin settings > Data management > Export)
  * the Freshsales REST API (for a final delta sync on cut-over day)

`load()` writes them idempotently: every migrated row keeps external_source="freshsales" and the Freshsales id,
so running the migration again updates records instead of duplicating them. Run with dry_run=True first.

CLI:
  python -m app.migration.freshsales files contacts.csv accounts.xlsx deals.csv [--commit]
  CRM_FRESHSALES_DOMAIN=acme CRM_FRESHSALES_API_KEY=... python -m app.migration.freshsales api [--commit]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Account, Brand, Contact, LineItem, Opportunity, Pipeline, PriceBook, Stage, StageHistory, User
from ..pricing import compute_totals
from ..services import email_domain

SOURCE = "freshsales"

# ---------------------------------------------------------------- column synonyms (export files)
COLS = {
    "account": {
        "ext_id": ["id", "account id", "sales account id"],
        "name": ["name", "account name", "sales account name", "company", "company name"],
        "website": ["website", "domain", "web"],
        "phone": ["phone", "phone number", "work"],
        "address": ["address", "street"],
        "city": ["city"],
        "state": ["state", "region"],
        "country": ["country"],
        "industry": ["industry type", "industry"],
        "owner": ["sales owner", "owner", "account owner"],
        "notes": ["description", "notes"],
    },
    "contact": {
        "ext_id": ["id", "contact id"],
        "first_name": ["first name", "firstname"],
        "last_name": ["last name", "lastname"],
        "full_name": ["name", "full name", "display name"],
        "email": ["emails", "email", "email address", "primary email"],
        "phone": ["work", "work number", "phone", "work phone"],
        "mobile": ["mobile", "mobile number"],
        "job_title": ["job title", "title", "designation"],
        "account_ext_id": ["account id", "sales account id"],
        "account_name": ["accounts", "account", "sales accounts", "sales account", "company", "company name"],
        "owner": ["sales owner", "owner", "contact owner"],
        "lifecycle": ["lifecycle stage", "lifecycle"],
        "status": ["status", "contact status"],
        "lead_source": ["source", "lead source"],
        "country": ["country"],
        "city": ["city"],
        "linkedin": ["linkedin", "linkedin url"],
        "notes": ["description", "notes"],
    },
    "deal": {
        "ext_id": ["id", "deal id"],
        "name": ["name", "deal name", "title"],
        "amount": ["deal value", "amount", "value", "deal amount"],
        "currency": ["currency", "deal currency"],
        "stage": ["deal stage", "stage"],
        "pipeline": ["deal pipeline", "pipeline"],
        "probability": ["probability", "probability (%)", "win probability"],
        "expected_close": ["expected close date", "expected close", "close date"],
        "closed_date": ["closed date", "closed on", "won/lost date"],
        "account_ext_id": ["account id", "sales account id"],
        "account_name": ["account", "sales account", "account name", "company"],
        "owner": ["sales owner", "owner", "deal owner"],
        "lost_reason": ["lost reason", "deal reason", "reason"],
        "deal_type": ["deal type", "type"],
        "source": ["source", "lead source", "deal source", "campaign"],
        "contacts": ["contacts", "contact", "related contacts"],
        "products": ["products", "deal products"],
        "notes": ["description", "notes"],
    },
}


def _norm(h) -> str:
    return re.sub(r"[\s_\-]+", " ", str(h or "").strip().lower())


def detect_entity(headers: list[str]) -> str:
    h = {_norm(x) for x in headers}
    if h & {"deal stage", "deal value", "deal pipeline", "expected close date"}:
        return "deal"
    if h & {"first name", "last name", "emails", "lifecycle stage", "job title"}:
        return "contact"
    return "account"


def map_row(entity: str, row: dict) -> dict:
    lookup = {_norm(k): (str(v).strip() if v is not None else "") for k, v in row.items()}
    out = {}
    for fld, names in COLS[entity].items():
        out[fld] = next((lookup[n] for n in names if lookup.get(n)), "")
    return out


# ---------------------------------------------------------------- normalized data
@dataclass
class Dataset:
    accounts: list[dict] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)
    deals: list[dict] = field(default_factory=list)


def from_tables(tables: list[tuple[str, list[str], list[dict]]]) -> Dataset:
    """tables: (filename, headers, rows). Entity is detected from the headers or the file name."""
    ds = Dataset()
    for name, headers, rows in tables:
        n = name.lower()
        entity = ("deal" if "deal" in n else "contact" if "contact" in n else "account" if "account" in n
                  else detect_entity(headers))
        target = {"account": ds.accounts, "contact": ds.contacts, "deal": ds.deals}[entity]
        target.extend(map_row(entity, r) for r in rows)
    return ds


# ---------------------------------------------------------------- API client
class FreshsalesClient:
    """Minimal read-only client. Key comes from the environment / server config, never from the UI."""

    def __init__(self, domain: str, api_key: str, per_page: int = 100):
        import httpx

        domain = domain.strip().removeprefix("https://").split("/")[0]
        if "." not in domain:
            domain = f"{domain}.myfreshworks.com"
        self.base = f"https://{domain}/crm/sales/api"
        self.http = httpx.Client(timeout=30, headers={"Authorization": f"Token token={api_key}",
                                                      "Content-Type": "application/json"})
        self.per_page = per_page

    def get(self, path: str, **params) -> dict:
        for attempt in range(6):
            r = self.http.get(f"{self.base}/{path.lstrip('/')}", params=params)
            if r.status_code == 429:  # 1000 requests/hour: wait as instructed
                time.sleep(min(int(r.headers.get("Retry-After", 60)), 900))
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError("Freshsales rate limit: too many retries")

    def selector(self, name: str) -> dict[int, dict]:
        data = self.get(f"selector/{name}")
        items = next((v for v in data.values() if isinstance(v, list)), [])
        return {i["id"]: i for i in items if "id" in i}

    def view_id(self, entity: str) -> int:
        data = self.get(f"{entity}/filters")
        views = data.get("filters", [])
        for v in views:
            if v.get("name", "").lower().startswith("all"):
                return v["id"]
        if not views:
            raise RuntimeError(f"No views returned for {entity}")
        return views[0]["id"]

    def iter_view(self, entity: str, key: str, include: str | None = None):
        vid = self.view_id(entity)
        page = 1
        while True:
            params = {"page": page, "per_page": self.per_page, "sort": "created_at", "sort_type": "asc"}
            if include:
                params["include"] = include
            data = self.get(f"{entity}/view/{vid}", **params)
            yield from data.get(key, [])
            meta = data.get("meta", {})
            total_pages = meta.get("total_pages") or (
                -(-meta.get("total", 0) // self.per_page) if meta.get("total") is not None else None)
            if not data.get(key) or (total_pages is not None and page >= total_pages):
                break
            page += 1


def from_api(client: FreshsalesClient, log=print) -> Dataset:
    owners = client.selector("owners")
    owner_email = {i: (o.get("email") or o.get("display_name") or "") for i, o in owners.items()}
    stages = client.selector("deal_stages")
    pipelines = client.selector("deal_pipelines")
    for pid in pipelines:  # stages of every pipeline, not only the default
        try:
            stages.update(client.selector(f"deal_pipelines/{pid}/deal_stages"))
        except Exception:  # noqa: BLE001 - older accounts: default pipeline only
            pass
    currencies = client.selector("currencies")
    lead_sources = client.selector("lead_sources")
    lifecycle = client.selector("lifecycle_stages")
    industries = client.selector("industry_types")
    reasons = client.selector("deal_reasons")
    types = client.selector("deal_types")

    def name(table, i, key="name"):
        return (table.get(i) or {}).get(key, "") if i else ""

    ds = Dataset()
    log("Fetching accounts…")
    for a in client.iter_view("sales_accounts", "sales_accounts"):
        ds.accounts.append({
            "ext_id": str(a["id"]), "name": a.get("name") or "", "website": a.get("website") or "",
            "phone": a.get("phone") or "", "address": a.get("address") or "", "city": a.get("city") or "",
            "state": a.get("state") or "", "country": a.get("country") or "",
            "industry": name(industries, a.get("industry_type_id")), "owner": owner_email.get(a.get("owner_id"), ""),
            "notes": "",
        })
    log(f"  {len(ds.accounts)} accounts")
    log("Fetching contacts…")
    for c in client.iter_view("contacts", "contacts", include="sales_accounts"):
        accts = c.get("sales_accounts") or []
        primary = next((s for s in accts if s.get("is_primary")), accts[0] if accts else None)
        ds.contacts.append({
            "ext_id": str(c["id"]), "first_name": c.get("first_name") or "", "last_name": c.get("last_name") or "",
            "full_name": "", "email": c.get("email") or "", "phone": c.get("work_number") or "",
            "mobile": c.get("mobile_number") or "", "job_title": c.get("job_title") or "",
            "account_ext_id": str(primary["id"]) if primary else "", "account_name": primary.get("name", "") if primary else "",
            "owner": owner_email.get(c.get("owner_id"), ""), "lifecycle": name(lifecycle, c.get("lifecycle_stage_id")),
            "status": "", "lead_source": name(lead_sources, c.get("lead_source_id")), "country": c.get("country") or "",
            "city": c.get("city") or "", "linkedin": c.get("linkedin") or "", "notes": "",
        })
    log(f"  {len(ds.contacts)} contacts")
    log("Fetching deals…")
    for d in client.iter_view("deals", "deals", include="sales_account,contacts"):
        ds.deals.append({
            "ext_id": str(d["id"]), "name": d.get("name") or "", "amount": str(d.get("amount") or ""),
            "currency": name(currencies, d.get("currency_id"), "currency_code"),
            "stage": name(stages, d.get("deal_stage_id")), "pipeline": name(pipelines, d.get("deal_pipeline_id")),
            "probability": str(d.get("probability") or ""), "expected_close": d.get("expected_close") or "",
            "closed_date": d.get("closed_date") or "", "account_ext_id": str(d.get("sales_account_id") or ""),
            "account_name": "", "owner": owner_email.get(d.get("owner_id"), ""),
            "lost_reason": name(reasons, d.get("deal_reason_id")), "deal_type": name(types, d.get("deal_type_id")),
            "source": name(lead_sources, d.get("lead_source_id")),
            "contacts": ",".join(str(i) for i in d.get("contact_ids") or []), "products": "", "notes": "",
        })
    log(f"  {len(ds.deals)} deals")
    return ds


# ---------------------------------------------------------------- value mapping
def map_lifecycle(lifecycle: str, status: str) -> str:
    s = f"{lifecycle} {status}".lower()
    if "unqualif" in s or "disqualif" in s or "junk" in s:
        return "disqualified"
    if "customer" in s or "won" in s:
        return "customer"
    if "qualified" in s or "sql" in s or "mql" in s or "opportunit" in s:
        return "qualified"
    return "lead"


def map_source(src: str) -> str | None:
    s = src.lower()
    if not s:
        return None
    for keys, val in ((("download",), "download"), (("trial",), "trial"),
                      (("quote",), "quote_request"),
                      (("web", "form", "contact us", "inbound", "organic", "seo"), "website_contact"),
                      (("bmc", "datadog", "splunk", "grafana", "dynatrace", "new relic", "partner", "referr"),
                       "platform_referral"),
                      (("marketplace",), "marketplace"), (("event", "trade", "webinar", "conference"), "event"),
                      (("import", "list"), "import"), (("direct", "outbound", "cold", "email", "phone"), "direct")):
        if any(k in s for k in keys):
            return val
    return "other"


PLATFORM_KEYWORDS = {"bmc": "bmc.com", "helix": "bmc.com", "datadog": "datadoghq.com", "splunk": "splunk.com",
                     "grafana": "grafana.com", "dynatrace": "dynatrace.com", "new relic": "newrelic.com",
                     "servicenow": "servicenow.com", "elastic": "elastic.co"}


def detect_platform(*texts: str) -> str | None:
    s = " ".join(texts).lower()
    return next((dom for kw, dom in PLATFORM_KEYWORDS.items() if kw in s), None)


def detect_brand(default: str, *texts: str) -> str:
    s = " ".join(texts).lower()
    if any(k in s for k in ("sentry", "bhom", "bhco", "helix", "patrol", "km ", "storage analyzer", "monitoring studio")):
        return "SENTRY"
    if "metricshub" in s or "metrics hub" in s:
        return "METRICSHUB"
    return default


STAGE_RULES_NEW = [("won", "Won"), ("lost", "Lost"), ("negotiat", "Negotiation"), ("proposal", "Proposal / Follow-up"),
                   ("quote", "Proposal / Follow-up"), ("follow", "Proposal / Follow-up"), ("poc", "PoC / Trial"),
                   ("trial", "PoC / Trial"), ("pilot", "PoC / Trial"), ("proof", "PoC / Trial"), ("demo", "Demo"),
                   ("discover", "Discovery"), ("qualif", "Discovery"), ("meeting", "Discovery"), ("new", "New"),
                   ("lead", "New"), ("prospect", "New"), ("open", "New"), ("contact", "New")]
STAGE_RULES_RENEWAL = [("won", "Renewed"), ("renewed", "Renewed"), ("lost", "Churned"), ("churn", "Churned"),
                       ("pending", "Renewal pending"), ("negotiat", "Renewal pending"), ("proposal", "Renewal pending"),
                       ("quote", "Renewal pending")]


def map_stage(stage: str, pipeline: str, overrides: dict[str, str]) -> tuple[str, str, bool]:
    """Return (pipeline kind, CRM stage name, matched?)."""
    if stage in overrides:
        target = overrides[stage]
        kind = "renewal" if target in ("Upcoming renewal", "Renewal pending", "Renewed", "Churned") else "new_business"
        return kind, target, True
    s = stage.lower()
    if "renew" in pipeline.lower() or "renew" in s:
        for kw, target in STAGE_RULES_RENEWAL:
            if kw in s:
                return "renewal", target, True
        return "renewal", "Upcoming renewal", "renew" in s
    for kw, target in STAGE_RULES_NEW:
        if kw in s:
            return "new_business", target, True
    return "new_business", "New", False


def _dec(v: str) -> Decimal | None:
    v = re.sub(r"[^\d.,\-]", "", v or "")
    if not v:
        return None
    if v.count(",") and v.count("."):
        v = v.replace(",", "")
    elif v.count(",") == 1 and len(v.split(",")[1]) != 3:
        v = v.replace(",", ".")
    else:
        v = v.replace(",", "")
    try:
        return Decimal(v)
    except InvalidOperation:
        return None


def _date(v: str) -> dt.date | None:
    v = (v or "").strip()
    if not v:
        return None
    v = v.split("T")[0].split(" ")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def _domain(site: str) -> str | None:
    site = (site or "").strip().lower()
    if not site:
        return None
    site = re.sub(r"^https?://", "", site).removeprefix("www.")
    return site.split("/")[0] or None


# ---------------------------------------------------------------- loader
@dataclass
class Report:
    dry_run: bool
    counts: dict = field(default_factory=lambda: {e: Counter() for e in ("accounts", "contacts", "deals")})
    unmapped_stages: Counter = field(default_factory=Counter)
    stage_mapping: dict = field(default_factory=dict)
    unmatched_owners: Counter = field(default_factory=Counter)
    brands: Counter = field(default_factory=Counter)
    platforms: Counter = field(default_factory=Counter)
    totals_by_currency: Counter = field(default_factory=Counter)
    warnings: list = field(default_factory=list)

    def warn(self, msg: str):
        if len(self.warnings) < 300:
            self.warnings.append(msg)

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "counts": {k: dict(v) for k, v in self.counts.items()},
            "stage_mapping": self.stage_mapping,
            "unmapped_stages": dict(self.unmapped_stages),
            "unmatched_owners": dict(self.unmatched_owners),
            "brands": dict(self.brands),
            "referring_platforms": dict(self.platforms),
            "open_pipeline_by_currency": {k: str(v) for k, v in self.totals_by_currency.items()},
            "warnings": self.warnings,
        }


def load(db: Session, ds: Dataset, *, dry_run: bool = True, default_brand: str = "METRICSHUB",
         default_currency: str = "USD", stage_overrides: dict[str, str] | None = None) -> Report:
    """Write the dataset. With dry_run the whole transaction is rolled back and only the report is returned."""
    rep = Report(dry_run=dry_run)
    overrides = stage_overrides or {}
    users = list(db.scalars(select(User)))
    by_email = {u.email.lower(): u for u in users}
    by_name = {u.full_name.lower(): u for u in users}

    def owner(raw: str) -> int | None:
        if not raw:
            return None
        u = by_email.get(raw.lower()) or by_name.get(raw.lower())
        if not u:
            rep.unmatched_owners[raw] += 1
            return None
        return u.id

    brands = {b.code: b for b in db.scalars(select(Brand))}
    if default_brand not in brands:
        raise ValueError(f"Unknown brand {default_brand}")
    platforms = {a.domain: a for a in db.scalars(select(Account).where(Account.account_type == "platform_partner"))}
    pipelines = {p.kind: p for p in db.scalars(select(Pipeline))}
    stages = {(s.pipeline_id, s.name): s for s in db.scalars(select(Stage))}
    books = list(db.scalars(select(PriceBook).where(PriceBook.active.is_(True))))

    acc_by_ext: dict[str, Account] = {}
    acc_by_name: dict[str, Account] = {}
    for a in db.scalars(select(Account)):
        if a.external_source == SOURCE and a.external_id:
            acc_by_ext[a.external_id] = a
        acc_by_name.setdefault(a.name.lower(), a)

    def account_for(ext_id: str, name: str, create: bool = True) -> Account | None:
        if ext_id and ext_id in acc_by_ext:
            return acc_by_ext[ext_id]
        if name and name.lower() in acc_by_name:
            return acc_by_name[name.lower()]
        if not (create and name):
            return None
        a = Account(name=name, account_type="prospect", extra={}, external_source=SOURCE if ext_id else None,
                    external_id=ext_id or None)
        db.add(a)
        db.flush()
        rep.counts["accounts"]["created (from contact/deal)"] += 1
        acc_by_name[name.lower()] = a
        if ext_id:
            acc_by_ext[ext_id] = a
        return a

    # ---- accounts
    for r in ds.accounts:
        if not r["name"]:
            rep.counts["accounts"]["skipped (no name)"] += 1
            continue
        a = acc_by_ext.get(r["ext_id"]) if r["ext_id"] else None
        created = False
        if not a:
            a = acc_by_name.get(r["name"].lower())
            if a and a.external_id and r["ext_id"] and a.external_id != r["ext_id"]:
                a = None  # same name, different Freshsales record: keep both
        if not a:
            a = Account(name=r["name"], account_type="prospect", extra={})
            db.add(a)
            created = True
        a.external_source, a.external_id = (SOURCE, r["ext_id"] or a.external_id) if r["ext_id"] else (
            a.external_source, a.external_id)
        a.domain = a.domain or _domain(r["website"])
        for f_crm, f_src in (("website", "website"), ("phone", "phone"), ("address", "address"), ("city", "city"),
                             ("region", "state"), ("country", "country"), ("industry", "industry"), ("notes", "notes")):
            if r.get(f_src):
                setattr(a, f_crm, r[f_src])
        if (oid := owner(r["owner"])) is not None:
            a.owner_id = oid
        db.flush()
        if r["ext_id"]:
            acc_by_ext[r["ext_id"]] = a
        acc_by_name.setdefault(a.name.lower(), a)
        rep.counts["accounts"]["created" if created else "updated"] += 1

    # ---- contacts
    ct_by_ext = {c.external_id: c for c in db.scalars(select(Contact).where(Contact.external_source == SOURCE))}
    def load_contact(r: dict) -> str:
        email = (r["email"] or "").split(",")[0].split(";")[0].strip().lower() or None
        first, last = r["first_name"], r["last_name"]
        if r.get("full_name") and not (first or last):
            parts = r["full_name"].split(None, 1)
            first, last = parts[0], parts[1] if len(parts) > 1 else ""
        if not (email or first or last):
            return "skipped (no name or email)"
        c = ct_by_ext.get(r["ext_id"]) if r["ext_id"] else None
        if not c and email:
            c = db.scalar(select(Contact).where(func.lower(Contact.email) == email))
        created = c is None
        if created:
            c = Contact(extra={}, role="customer_contact")
            db.add(c)
        if r["ext_id"]:
            c.external_source, c.external_id = SOURCE, r["ext_id"]
        c.first_name = first or c.first_name
        c.last_name = last or c.last_name
        c.email = email or c.email
        for f in ("phone", "mobile", "job_title", "country", "linkedin", "notes"):
            if r.get(f):
                setattr(c, f, r[f])
        c.lifecycle = map_lifecycle(r["lifecycle"], r["status"])
        c.source = map_source(r["lead_source"]) or c.source or "import"
        acc = account_for(r["account_ext_id"], r["account_name"].split(",")[0].strip()) \
            if (r["account_ext_id"] or r["account_name"]) else None
        if not acc and email and (dom := email_domain(email)):
            acc = next((a for a in acc_by_name.values() if a.domain == dom), None)
        if acc:
            c.account_id = acc.id
            if acc.account_type == "platform_partner":
                c.role = "platform_account_manager"
        if (oid := owner(r["owner"])) is not None:
            c.owner_id = oid
        db.flush()
        if r["ext_id"]:
            ct_by_ext[r["ext_id"]] = c
        return "created" if created else "updated"

    for r in ds.contacts:
        try:
            with db.begin_nested():
                result = load_contact(r)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the migration
            result = "failed"
            rep.warn(f"Contact {r.get('email') or r.get('first_name')}: {type(exc).__name__}: {str(exc)[:120]}")
        rep.counts["contacts"][result] += 1

    # ---- deals
    deal_by_ext = {o.external_id: o for o in db.scalars(select(Opportunity).where(Opportunity.external_source == SOURCE))}
    now = dt.datetime.now(dt.UTC)
    def load_deal(r: dict) -> str:
        if not r["name"]:
            return "skipped (no name)"
        acc = account_for(r["account_ext_id"], r["account_name"])
        if not acc:
            rep.warn(f"Deal '{r['name']}' has no account")
            return "skipped (no account)"
        kind, stage_name, matched = map_stage(r["stage"], r["pipeline"], overrides)
        rep.stage_mapping[r["stage"] or "(empty)"] = stage_name
        if not matched:
            rep.unmapped_stages[r["stage"] or "(empty)"] += 1
        pipeline = pipelines[kind]
        stage = stages[(pipeline.id, stage_name)]
        brand = brands[detect_brand(default_brand, r["pipeline"], r["name"], r["products"])]
        rep.brands[brand.name] += 1
        plat_domain = detect_platform(r["source"], r["deal_type"], r["name"], r["pipeline"])
        platform = platforms.get(plat_domain) if plat_domain else None
        if platform:
            rep.platforms[platform.name] += 1
        currency = (r["currency"] or default_currency).upper()[:3]
        amount = _dec(r["amount"]) or Decimal(0)

        o = deal_by_ext.get(r["ext_id"]) if r["ext_id"] else None
        created = o is None
        if created:
            o = Opportunity(title=r["name"], account_id=acc.id, brand_id=brand.id, pipeline_id=pipeline.id,
                            stage_id=stage.id, term_months=12, external_source=SOURCE if r["ext_id"] else None,
                            external_id=r["ext_id"] or None)
            db.add(o)
        old_stage = o.stage_id
        o.title, o.account_id, o.brand_id = r["name"], acc.id, brand.id
        o.pipeline_id, o.stage_id = pipeline.id, stage.id
        o.deal_type = "renewal" if kind == "renewal" else ("expansion" if "expan" in r["deal_type"].lower()
                                                           or "upsell" in r["deal_type"].lower() else "new")
        o.lead_source = "platform_referral" if platform else map_source(r["source"])
        o.referring_platform_id = platform.id if platform else o.referring_platform_id
        o.route_to_market = "bmc_marketzone" if plat_domain == "bmc.com" else o.route_to_market or "direct"
        o.currency = currency
        o.price_book_id = next((b.id for b in books if b.brand_id == brand.id and b.currency == currency), None)
        o.expected_close_date = _date(r["expected_close"]) or o.expected_close_date
        if (p := _dec(r["probability"])) is not None and stage.kind == "open":
            o.probability = max(0, min(100, int(p)))
        if stage.kind == "lost":
            o.lost_reason = r["lost_reason"] or o.lost_reason or "Imported from Freshsales"
        if stage.kind != "open":
            closed = _date(r["closed_date"]) or o.expected_close_date
            o.closed_at = dt.datetime.combine(closed, dt.time(12), tzinfo=dt.UTC) if closed else now
        else:
            o.closed_at = None
        o.description = "\n".join(x for x in (r["notes"], f"Imported from Freshsales (id {r['ext_id']})"
                                              if r["ext_id"] else "Imported from Freshsales") if x)
        if (oid := owner(r["owner"])) is not None:
            o.owner_id = oid
        # contacts: Freshsales ids (API) or names/emails (exports)
        primary = None
        for token in [t.strip() for t in re.split(r"[,;]", r["contacts"]) if t.strip()]:
            primary = ct_by_ext.get(token) or db.scalar(select(Contact).where(
                (func.lower(Contact.email) == token.lower())
                | (func.lower(func.concat(Contact.first_name, " ", Contact.last_name)) == token.lower())))
            if primary:
                break
        if primary:
            o.primary_contact_id = primary.id
        db.flush()
        # Freshsales deals carry a value, not product lines: keep it as one editable "imported value" line
        if created or all(li.name.startswith("Imported deal value") for li in o.line_items):
            o.line_items.clear()
            if amount:
                o.line_items.append(LineItem(position=0, name="Imported deal value (Freshsales)", billing_type="one_time",
                                             quantity=Decimal(1), unit_price=amount, discount_pct=Decimal(0)))
            totals = compute_totals(o.line_items, o.term_months)
            o.amount_tcv, o.amount_arr = totals.tcv, totals.arr
        if created or old_stage != stage.id:
            db.add(StageHistory(opportunity_id=o.id, from_stage_id=None if created else old_stage, to_stage_id=stage.id))
        if stage.kind == "open":
            rep.totals_by_currency[currency] += o.amount_tcv
        if stage.kind == "won" and acc.account_type == "prospect":
            acc.account_type = "customer"
        db.flush()
        if r["ext_id"]:
            deal_by_ext[r["ext_id"]] = o
        return "created" if created else "updated"

    for r in ds.deals:
        try:
            with db.begin_nested():
                result = load_deal(r)
        except Exception as exc:  # noqa: BLE001
            result = "failed"
            rep.warn(f"Deal {r.get('name')}: {type(exc).__name__}: {str(exc)[:120]}")
        rep.counts["deals"][result] += 1

    if dry_run:
        db.rollback()
    else:
        db.commit()
    return rep


# ---------------------------------------------------------------- CLI
def _read_file(path: Path) -> tuple[str, list[str], list[dict]]:
    import io

    from fastapi import UploadFile

    from ..routers.imports import read_table

    with path.open("rb") as fh:
        headers, rows = read_table(UploadFile(file=io.BytesIO(fh.read()), filename=path.name))
    return path.name, headers, rows


def main(argv=None) -> int:
    from ..db import SessionLocal

    ap = argparse.ArgumentParser(description="Migrate data from Freshsales")
    sub = ap.add_subparsers(dest="mode", required=True)
    f = sub.add_parser("files", help="Load Freshsales export files (CSV/XLSX)")
    f.add_argument("paths", nargs="+", type=Path)
    a = sub.add_parser("api", help="Pull directly from the Freshsales API (CRM_FRESHSALES_DOMAIN / _API_KEY)")
    a.add_argument("--save", type=Path, help="Also save the fetched data as JSON for audit")
    for p in (f, a):
        p.add_argument("--commit", action="store_true", help="Write to the database (default: dry run)")
        p.add_argument("--default-brand", default="METRICSHUB", choices=["METRICSHUB", "SENTRY"])
        p.add_argument("--default-currency", default="USD")
        p.add_argument("--stage-map", type=Path, help='JSON file {"Freshsales stage": "CRM stage"}')
    args = ap.parse_args(argv)

    if args.mode == "files":
        ds = from_tables([_read_file(p) for p in args.paths])
    else:
        domain, key = os.environ.get("CRM_FRESHSALES_DOMAIN"), os.environ.get("CRM_FRESHSALES_API_KEY")
        if not (domain and key):
            print("Set CRM_FRESHSALES_DOMAIN and CRM_FRESHSALES_API_KEY", file=sys.stderr)
            return 2
        ds = from_api(FreshsalesClient(domain, key))
        if args.save:
            args.save.write_text(json.dumps(ds.__dict__, indent=1))
    overrides = json.loads(args.stage_map.read_text()) if args.stage_map else {}
    with SessionLocal() as db:
        rep = load(db, ds, dry_run=not args.commit, default_brand=args.default_brand,
                   default_currency=args.default_currency, stage_overrides=overrides)
    print(json.dumps(rep.as_dict(), indent=2, default=str))
    if not args.commit:
        print("\nDRY RUN: nothing was written. Re-run with --commit to apply.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
