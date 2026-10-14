# MetricsHub & Sentry CRM

A standalone CRM for **Sentry Software** and **MetricsHub** deals. It tracks the accounts, people and opportunities that come through observability platforms (BMC Helix, Datadog, Splunk, Grafana…) and through direct sales.

| Layer | Technology |
|---|---|
| Database | PostgreSQL 16 |
| API | Python 3.13, FastAPI, SQLAlchemy 2, Alembic |
| Web app | React 19, TypeScript, Vite, Mantine |
| Auth | Email and password, plus single sign-on through OpenID Connect (Microsoft Entra ID, Google, Okta, Keycloak) |
| Deployment | Docker Compose: Postgres, API, nginx, nightly `pg_dump` backups |

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

## Coming in the next phases

2. Quote PDFs (versioned, numbered per brand, emailed from the CRM), automatic renewal opportunities 120 days before contract end, and richer reports.
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
