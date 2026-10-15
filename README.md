# MetricsHub & Sentry CRM

A standalone CRM for **Sentry Software** and **MetricsHub** deals. It tracks the accounts, people and opportunities that come through observability platforms (BMC Helix, Datadog, Splunk, Grafana…) and through direct sales.

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 |
| API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic |
| Web app | React 19, TypeScript, Vite, Mantine |
| Auth | Email and password, plus single sign-on through OpenID Connect (Microsoft Entra ID, Google, Okta, Keycloak) |
| Deployment | Docker Compose: Postgres, API, nginx, nightly `pg_dump` backups |
| Quote PDFs | Jinja2 HTML template rendered by WeasyPrint |

## What's in phase 1

- **Accounts:**
  - Account types: prospect, customer, platform partner (BMC, Datadog, Splunk, Grafana, Dynatrace, New Relic, ServiceNow and Elastic come pre-loaded), reseller, MSP and system integrator.
  - Supports parent accounts and owners.
- **Contacts:**
  - Roles: customer contact, platform account manager, partner contact, technical, economic buyer, champion.
  - Lifecycle: lead → qualified → customer, or disqualified.
  - Also stored: source, brand interest, and marketing consent with a timestamp.
  - Email addresses are unique regardless of case.
- **Opportunities:**
  - Fields: title, account, brand (MetricsHub or Sentry), owner, deal type, lead source, referring platform and that platform's account manager, route to market (Direct, BMC MarketZone, Marketplace, Reseller), and contract start, period and end.
  - **Products and pricing:** choose products from the catalog and enter quantities. Unit prices come from the selected price book, and you can override them. Each line can have its own discount and term.
  - **Pricing formula:** the estimated deal value is calculated live in the browser and recalculated on the server.
    - Recurring line = quantity × unit price per month × term in months × (1 − discount %)
    - One-time line = quantity × unit price × (1 − discount %)
    - TCV = sum of all lines. ARR = recurring value per year.
- **Pipelines:**
  - **New Business:** New (10%) → Discovery (20%) → Demo (30%) → PoC / Trial (50%) → Proposal / Follow-up (60%) → Negotiation (80%) → Won / Lost.
  - **Renewals:** Upcoming renewal → Renewal pending → Renewed / Churned.
  - The Kanban board supports drag and drop. Marking a deal Lost requires a reason, and stage history is recorded.
- **Products & price books:** a starter catalog for both brands.
  - "MetricsHub Direct USD" contains MetricsHub Enterprise at $15/host/month.
  - "Sentry via BMC (USD)" contains the FY27 BMC list prices for the BHOM and BHCO bundles. These are **internal**: check them before quoting.
  - Admins can edit prices and add price books in other currencies.
- **Activities:** notes, tasks with due dates, calls, meetings and logged emails on any account, contact or opportunity.
- **Import and export:**
  - Import an Excel or CSV file through a 3-step wizard: upload, map columns (mapping is auto-suggested), then review the results.
  - Duplicate records are either updated or skipped. Contacts are matched by email; accounts by domain, then name.
  - Contacts are linked to accounts automatically using the email domain. Free-mail domains such as gmail.com are ignored.
  - Contacts, accounts and opportunities can be exported to Excel or CSV.
- **Dashboard:**
  - Open and weighted pipeline. Totals are never added up across currencies.
  - Won this quarter, 12-month win rate, and pipeline by stage and by referring platform.
  - Deals closing in the next 30 days and your open tasks.
- **Users and roles:** admin, sales and read-only. An audit log records every change.

## Quotes (phase 2, part 1)

- **Quote templates** (*Quote templates* in the menu, editable by admins), one per brand:
  - Logo upload, header and accent colours, and company details.
  - Intro, payment terms, terms & conditions, footer, plus discount-column and signature-block switches.
  - Live preview with sample data, a PDF preview, and a *Reset* button that restores the defaults.
  - Placeholders such as `{customer}`, `{contact}`, `{owner}` and `{valid_until}`, and simple formatting (blank line = paragraph, `- ` = bullet, `**bold**`).
- **Generating a quote:** use *Generate quote* on an opportunity.
  - Numbering is per brand and year (`MH-Q-2026-0001`, `SEN-Q-2026-0001`). Later quotes on the same deal become `v2`, `v3`, and so on.
  - Each quote freezes the lines, prices, customer and template as they are when it is generated, so later edits never change a quote that was already sent.
  - Status: draft, sent, accepted, rejected or expired. Only drafts can be deleted.
  - PDFs are rendered by WeasyPrint. Only embedded `data:` images may load, so rendering makes no network or file access.
- **Emailing a quote:** the envelope button on a quote opens a pre-filled message (primary contact, subject and wording from the brand's template, PDF attached).
  - It is sent through Microsoft 365 from the signed-in user's own mailbox, so it appears in their Outlook *Sent Items* and replies come back to them. See [Emailing quotes through Microsoft 365](#emailing-quotes-through-microsoft-365).
  - A draft quote is marked *sent*, the email is logged on the opportunity's activity timeline, and the send is recorded in the audit log.
  - The email subject and message are edited per brand under *Quote templates*, with the same placeholders.
- **Placeholder prices:** every catalog product now has an editable price in Products & pricing → Price books.
  - Recurring products are priced per unit per month.
  - MetricsHub Enterprise at $15/host/month and the two Sentry bundles use real list prices; everything else is a placeholder.

## Customer licences from BMC MarketZone reports

Every quarter BMC sends the *Reseller Fee Report to Sentry Software* as a PDF and, since September 2024, a *Detail* .xlsx with the same lines. An admin loads either under *Import / export → BMC MarketZone report*: **Dry run** shows what will be created, **Import licences** saves it. Loading the same report again, or both files of the same quarter, changes nothing.

- **Prefer the Detail .xlsx:** it is exact. PDFs from December 2024 onward, and June 2024, read the same lines as their .xlsx. The tighter layout of older PDFs (March 2020, March 2024, September 2024) cannot be read reliably.
- **Nothing half-right is saved:** if any line cannot be read, or a section total of the report does not match the lines read, the dry run lists the problems and the import is refused. Load the .xlsx of that quarter instead.

- **Reading the report:** each invoice or credit-memo line becomes a licence on the customer's account (the *Ordering Company*). The line records the product (as named in the report), quantity, Term/Support/SaaS/License, service period and net amount. The report's own section totals are used to check that every line was read correctly.
- **Accounts:** customers are matched to existing accounts by name, ignoring legal suffixes such as Ltd, Inc or GmbH. Customers not found are created as *customer* accounts. When the *Billing Company* is different, it is recorded as the reseller (an account of type *reseller*).
- **What a customer owns:** the account's **Licences** tab shows one row per product:
  - the quantity for the current period, with credit memos subtracted
  - the renewal date: the end of the last period already invoiced, so a prepaid multi-year deal shows its final year
  - a status: active, renewal due, ended · awaiting next report, lapsed, or starts later
  - the reseller

  Global search shows the number of products, the next renewal date and any lapsed licences next to each account. Licences can also be added by hand, for example for direct sales.
- **Renewal notices:** 60 days before a licence's renewal date (`CRM_RENEWAL_NOTICE_DAYS`), the CRM notifies the owner of the account's open renewal opportunity. If there is none, it notifies the account owner, and failing that, the administrators. The notice appears under the bell and is also emailed when email is set up. It is sent once per renewal. The check runs inside the API every few hours; to run it from cron instead, set `CRM_RUN_SCHEDULER=false` and run `docker compose exec api python -m app.jobs renewals`.
- **Instalments:** periods shorter than about 6 months, such as quarterly SaaS billing, are instalments, not contract ends, so they don't trigger renewal notices.
- **Perpetual licences** ("License" / "PERPETUAL" lines) are owned for good: they have no renewal date, never lapse and send no notice. Their maintenance appears as a separate *Support* licence of the same product, which does renew.
- **Lapsed licences:** a report licence is *lapsed* only once a later imported report covers its end date and still has no renewal line. Until then it shows as *ended · awaiting next report*, because the renewal invoice may simply be in the next quarter's report. Licences added by hand lapse on their end date. Lapsed licences stay on the dashboard until someone clicks **Resolve** and notes what happened (renewed outside MarketZone, churned...). A resolved licence can be reopened from the account.

The reports are BMC-confidential: keep them out of this repository and out of shared folders.

## Migrating from Freshsales

The migration reads accounts, contacts and deals from Freshsales and is safe to run more than once. Each migrated record stores its Freshsales id, so a second run updates records instead of duplicating them.

**1. First migration from export files.** In Freshsales, go to *Admin settings → Data management → Export* and export Accounts, Contacts and Deals with all fields. Then, as an admin, open *Import / export → Migrate from Freshsales* in the CRM:

1. Drop the files.
2. Click **Dry run**. It writes nothing and reports:
   - counts per record type
   - the Freshsales stage → CRM stage mapping
   - stages that weren't recognised
   - owners that weren't found
   - brands and referring platforms detected
   - open pipeline per currency
3. Adjust the stage mapping, invite missing owners under *Users*, and dry-run again.
4. Click **Import for real**.

The same thing works from the command line:

```bash
docker compose exec api python -m app.migration.freshsales files /data/accounts.csv /data/contacts.csv /data/deals.csv
docker compose exec api python -m app.migration.freshsales files ... --commit --stage-map stage-map.json
```

**2. Final sync on cut-over day, through the API.** Put `CRM_FRESHSALES_DOMAIN` and `CRM_FRESHSALES_API_KEY` in `.env` on the server. The key is found in Freshsales under *Profile settings → API settings*; never paste it anywhere else. Then run:

```bash
docker compose exec api python -m app.migration.freshsales api --save /tmp/freshsales.json   # dry run
docker compose exec api python -m app.migration.freshsales api --commit
```

The API sync only reads from Freshsales; it never writes there. It follows Freshsales' limit of 1,000 requests per hour and waits automatically when that limit is reached. When the sync is done, remove the API key from `.env`.

**How fields are mapped**

| Freshsales | CRM |
|---|---|
| Owners | Matched to CRM users by email or full name. Unmatched owners are listed in the report. |
| Lifecycle stage / status | Lead, qualified, customer or disqualified. |
| Lead source | Lead source. "BMC", "Datadog" and the other platform names become *Platform referral*. |
| Deal stages | Matched by keyword (won, lost, negotiation, proposal, PoC/trial, demo, discovery, new). Deals in a pipeline named "renewal" go to the Renewals pipeline. Unknown stages go to *New* and are flagged in the report. |
| Brand | Sentry Software when the deal mentions Sentry, BMC, Helix, a KM, BHOM or BHCO; otherwise the default you choose. |
| Referring platform | Detected from the deal source, type or name: BMC, Datadog, Splunk, Grafana, Dynatrace, New Relic, ServiceNow, Elastic. BMC deals get the route *BMC MarketZone*. |
| Deal value | Becomes one editable line, "Imported deal value (Freshsales)", because Freshsales deals have no product lines. Replace it with real products when you next update the deal. |

Notes, tasks and emails stay in Freshsales for now.

## Coming in the next phases

2. Automatic renewal opportunities 120 days before contract end, and richer reports.
3. Email: direct emails from Microsoft 365 logged on the timeline, a template editor with merge fields and HTML/.eml import, and campaigns with tracking and unsubscribe handling.
4. Inbound webhooks for the website Contact, Quote, Trial, Download and Partner forms, which create or update contacts automatically.

## Run it locally (development)

You need Python 3.12 or later, Node 20 or later, and PostgreSQL 16.

```bash
# 1. Database
createuser -s crm && createdb -O crm crm      # or use the docker-compose "db" service

# 2. API
cd backend
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.demo_data        # optional: fictitious sample accounts and deals
uvicorn app.main:app --reload  # http://localhost:8000/docs for the API reference

# 3. Web app
cd ../frontend
npm install
npm run dev                    # http://localhost:5173  (proxies /api to :8000)
```

The default login is `admin@example.com` / `admin123`. You can change it with the `CRM_ADMIN_*` variables before the first start.

Tests: `cd backend && createdb -O crm crm_test && pytest`

## Deploy on a Linux VM

```bash
git clone https://github.com/RazeemM/MetricsHub-CRM.git && cd MetricsHub-CRM
cp .env.example .env    # fill in passwords, CRM_SECRET_KEY, CRM_APP_URL, SSO settings
docker compose up -d --build
```

The web app listens on `WEB_PORT` (default 8080). Put your TLS reverse proxy (Caddy, Traefik, nginx or a cloud load balancer) in front of it for `https://crm.yourdomain`. Migrations run automatically when the API starts. Backups are written daily to `./backups` and kept for `BACKUP_RETENTION_DAYS` days.

Restore a backup:

```bash
docker compose exec -T db pg_restore -U crm -d crm --clean < backups/crm-YYYYMMDD-HHMM.dump
```

## Single sign-on with Microsoft Entra ID (Microsoft 365)

1. In the Entra admin center, go to **App registrations → New registration**.
   - Name: `MetricsHub CRM`
   - Supported account types: *Accounts in this organizational directory only* (or multitenant if Sentry Software and MetricsHub are separate tenants)
   - Redirect URI (Web): `https://<your CRM URL>/api/auth/sso/callback`
2. Under **Certificates & secrets**, create a client secret.
3. Under **Token configuration**, add the optional claim `email` to the ID token.
4. Put these values in `.env`:
   ```
   CRM_OIDC_ISSUER=https://login.microsoftonline.com/<Directory (tenant) ID>/v2.0
   CRM_OIDC_CLIENT_ID=<Application (client) ID>
   CRM_OIDC_CLIENT_SECRET=<secret value>
   CRM_OIDC_AUTO_PROVISION_DOMAINS=metricshub.com,sentrysoftware.com
   ```
5. Restart the API with `docker compose up -d api`. The login page now shows **Sign in with Microsoft**.
   - Users whose email is in an auto-provision domain get a *sales* account on their first sign-in. Anyone else must be invited from **Users** first.
   - Once everyone can sign in, set `CRM_PASSWORD_LOGIN_ENABLED=false`.
   - For two separate tenants (one for Sentry Software, one for MetricsHub), register the app as multitenant and use `https://login.microsoftonline.com/organizations/v2.0` as the issuer. The CRM then checks each token against the signing user's own tenant. Keep `CRM_OIDC_AUTO_PROVISION_DOMAINS` set, so only your two domains can create accounts.

The flow is the authorization code flow with PKCE. The ID token is verified against the provider's published signing keys (audience, issuer and nonce). The CRM then issues its own session token, which is passed back in the URL fragment so it never appears in server logs.

## Emailing quotes through Microsoft 365

The CRM sends with Microsoft Graph, using the same app registration as single sign-on.

1. In the app registration, go to **API permissions → Add a permission → Microsoft Graph → Application permissions** and add **Mail.Send**. Click **Grant admin consent**.
2. Limit the mailboxes the app may send from. Without this, Mail.Send allows sending as *any* mailbox in the tenant. In Exchange Online PowerShell:
   ```powershell
   New-DistributionGroup -Name "CRM senders" -Type Security -Members razeem@metricshub.com   # add every CRM user
   New-ApplicationAccessPolicy -AppId <Application (client) ID> -PolicyScopeGroupId "CRM senders" -AccessRight RestrictAccess -Description "MetricsHub CRM"
   ```
3. Put these values in `.env` and restart the API:
   ```
   CRM_MAIL_BACKEND=graph
   # Single tenant: leave empty (taken from CRM_OIDC_ISSUER).
   # Two tenants (multitenant SSO): one tenant per email domain. The app needs admin consent in both tenants.
   CRM_GRAPH_TENANT_ID=metricshub.com=<MetricsHub tenant ID>,sentrysoftware.com=<Sentry tenant ID>
   ```
   - `CRM_GRAPH_CLIENT_ID` / `CRM_GRAPH_CLIENT_SECRET` are only needed for a separate app registration.
   - `CRM_MAIL_FROM=sales@metricshub.com` sends everything from one shared mailbox instead; replies then go to the user who sent it.
   - `CRM_MAIL_BACKEND=log` keeps messages on the server without sending them (staging and demos).

## Project layout

```
backend/
  app/models.py        data model (accounts, contacts, products, price books, pipelines, opportunities…)
  app/pricing.py       deal value calculation
  app/services.py      business rules (contract dates, stage changes, account matching)
  app/routers/         REST API (auth, sso, accounts, contacts, products, opportunities, activities, imports, dashboard)
  alembic/             database migrations
  tests/               pytest suite (pricing, API, import/export, SSO)
frontend/src/
  pages/               Dashboard, Pipeline, Opportunities, Accounts, Contacts, Products, Import, Users
  components/          layout, forms, line-item editor, activity timeline
```
