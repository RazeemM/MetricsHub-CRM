# MetricsHub & Sentry CRM: developer's guide

This guide is for developers who run, deploy, configure or extend the CRM. The [README](../README.md) describes what
the CRM does for its users; the in-app **Help** pages (`frontend/src/help/topics.ts`) are the user documentation.

- [1. Architecture](#1-architecture)
- [2. Modules](#2-modules)
- [3. Deployment prerequisites](#3-deployment-prerequisites)
- [4. Deployment procedure](#4-deployment-procedure)
- [5. Initial configuration](#5-initial-configuration)
- [6. Local development](#6-local-development)
- [7. Making an enhancement](#7-making-an-enhancement)
- [8. Conventions and pitfalls](#8-conventions-and-pitfalls)

---

## 1. Architecture

One web application for two brands (MetricsHub and Sentry Software): a React single-page app, a FastAPI REST API and a
PostgreSQL database, shipped as four Docker containers.

```mermaid
flowchart LR
    U[Browser] -->|HTTPS| P[TLS reverse proxy<br/>Caddy / Traefik / IIS / load balancer]
    W[Website forms<br/>tracking code] -->|HTTPS| P
    M[MetricsHub / Prometheus] -->|/api/monitoring/status<br/>/api/metrics| P
    P -->|HTTP :8080| WEB[web container<br/>nginx + built React app]
    WEB -->|/api/* proxy| API[api container<br/>FastAPI + uvicorn<br/>+ background scheduler]
    API --> DB[(db container<br/>PostgreSQL 16)]
    BK[backup container<br/>nightly pg_dump] --> DB
    BK --> F[./backups]
    API -. read-only .-> F
    API -->|OpenID Connect| ENTRA[Microsoft Entra ID]
    API -->|Graph sendMail / SMTP| MAIL[Microsoft 365 / SMTP relay]
```

| Container | Image | Role |
|---|---|---|
| `web` | `frontend/Dockerfile`: Node 22 builds the app, nginx 1.27 serves it | Serves the static app on port 80 (published as `WEB_PORT`, default 8080) and forwards `/api/*` to the API (`frontend/nginx.conf`). Every other path returns `index.html` (client-side routing). |
| `api` | `backend/Dockerfile`: Python 3.13, WeasyPrint libraries and fonts | Runs `alembic upgrade head`, then uvicorn on port 8000. Also runs the background jobs (renewals, campaigns) unless `CRM_RUN_SCHEDULER=false`. |
| `db` | `postgres:16-alpine` | The only state, in the `pgdata` volume. |
| `backup` | `postgres:16-alpine` | `pg_dump -Fc` once a day into `./backups`, keeping `BACKUP_RETENTION_DAYS` days. |

**Request path.** The browser only ever talks to one origin. nginx serves the app and proxies `/api/`, so there is no
CORS in normal use. The API documentation also lives under `/api` (`/api/docs`, `/api/redoc`, `/api/openapi.json`) so it
is reachable through nginx.

**Authentication.** `POST /api/auth/login` (password) or the OpenID Connect flow (`/api/auth/sso/login` →
identity provider → `/api/auth/sso/callback`) issues the CRM's own JWT, signed with `CRM_SECRET_KEY` and valid
12 hours. The app keeps it in `localStorage` (`crm_token`) and sends it as `Authorization: Bearer`. Three roles:
`admin`, `sales` (read and write) and `readonly` (enforced by `require_admin` / `require_writer` in
`backend/app/security.py`).

**Startup** (`backend/app/main.py`, `lifespan`): refuses to start in production with a weak `CRM_SECRET_KEY`, seeds
the reference data (`backend/app/seed.py`: brands, pipelines and stages, platforms, products, price books, the first
administrator) and starts the scheduler.

**Background jobs** (`backend/app/jobs.py`). Inside the API process, guarded by PostgreSQL advisory locks so only one
worker runs each job:

| Job | Every | Does |
|---|---|---|
| `renewals` | 6 hours | Prunes old website events, closes lapsed licences that were renewed, opens renewal opportunities 60 days ahead, sends renewal notices. |
| `campaigns` | 30 seconds | Sends the next batch of queued campaign email, within `CRM_BULK_RATE_PER_MINUTE`. |

To run them from cron instead: `CRM_RUN_SCHEDULER=false` and `python -m app.jobs renewals|campaigns`.

### Technology

| Layer | Stack |
|---|---|
| API | Python 3.12+ (3.13 in Docker), FastAPI, pydantic v2 and pydantic-settings, SQLAlchemy 2, Alembic, psycopg 3 |
| Documents | WeasyPrint + Jinja2 (quote PDFs), pdfplumber (BMC report PDFs), openpyxl (Excel import/export) |
| Auth | PyJWT (CRM tokens, OIDC ID token verification), bcrypt |
| Outbound HTTP | httpx (Microsoft Graph, OIDC discovery, Freshsales API) |
| Web app | React 19, TypeScript, Vite, Mantine 7, TanStack Query 5, React Router 6 |
| Database | PostgreSQL 16 (JSONB, advisory locks; not portable to SQLite) |

---

## 2. Modules

### Repository layout

```
.env.example               every setting, documented; copy to .env
docker-compose.yml         production stack (db, api, web, backup)
backend/
  Dockerfile, requirements.txt, requirements-dev.txt, alembic.ini
  alembic/versions/        database migrations (one file per schema change)
  app/                     the API (see below)
  tests/                   pytest suite, fixtures/ for sample input files
frontend/
  Dockerfile, nginx.conf, vite.config.ts, package.json
  src/                     the web app (see below)
monitoring/metricshub/     MetricsHub Enterprise connector and example configuration
docs/                      this guide
```

### Backend (`backend/app`)

**Core**

| File | Responsibility |
|---|---|
| `main.py` | Builds the FastAPI app: lifespan (checks, seed, scheduler), CORS and public-form middleware, request statistics, registers every router. |
| `config.py` | `Settings`: every `CRM_*` environment variable with its default and comment. The single source for configuration. |
| `db.py` | SQLAlchemy engine, `SessionLocal`, declarative `Base`, the `get_db` dependency. |
| `models.py` | All tables (accounts, contacts, products, price books, pipelines, opportunities, line items, quotes, licences, campaigns, forms, tracking, settings…). |
| `schemas.py` | Shared pydantic request/response models (`…In`, `…Out`). Router-specific ones live in their router. |
| `enums.py` | Allowed values (roles, account types, lead sources, routes to market, units…). |
| `security.py` | Password hashing, JWT, `get_current_user`, `require_writer`, `require_admin`. |
| `crud.py` | Generic helpers: `get_or_404`, `apply_changes`, `audit` (writes the audit log). |
| `services.py` | Business rules shared by several routers: default pipeline and price book, contract dates, line items, stage validation, `on_won`. |
| `seed.py` | Reference data created on every start if missing; `demo_data.py` adds fictitious sample records for development. |
| `jobs.py` | Scheduler and the job functions. |
| `monitoring.py` | Health checks and counters (System status, `/api/health/ready`, `/api/monitoring/status`, `/api/metrics`). |

**Domain modules** (logic kept out of the routers so jobs and tests can call it)

| File | Area |
|---|---|
| `pricing.py` | Deal value: recurring (qty × monthly price × term × (1 − discount)), one-time, deal-total and fixed-total lines; TCV and ARR. |
| `quotes.py`, `templates/quote.html` | Quote numbering, data and PDF rendering. |
| `mail.py` | Outgoing email: SMTP, Microsoft Graph (application or delegated), log backend; the sender setting; MIME building. |
| `campaigns.py`, `audiences.py`, `email_starters.py` | Email campaigns, audience rules, starter templates. |
| `webforms.py` | Website form submissions: validation, spam checks, contact upsert, double opt-in. |
| `tracking.py`, `assets/tracker.js` | Website tracking code, visitors and events, retention. |
| `mzd_report.py` | Reader for BMC MarketZone reseller fee reports (Detail .xlsx and PDF), with total cross-checks. |
| `entitlements.py` | Licences: report import, holdings per product, renewal notices, lapsed licences. |
| `renewal_deals.py` | Renewal opportunities opened from licences before they renew. |
| `product_families.py`, `regions.py` | Product family names across product renames; countries to regions. |
| `insights.py` | Analytics behind the Insights page. |
| `bmc_quote.py` | Reader for BMC quote approval emails (Sentry lines). |
| `migration/freshsales.py`, `migration/bmc_helix.py` | One-off data migrations (Freshsales, BMC → BMC Helix contacts). |

**Routers** (`backend/app/routers`, all under `/api`)

| Router | Endpoints for |
|---|---|
| `core.py` | Login, current user, users, brands, pipelines |
| `sso.py` | OpenID Connect sign-in |
| `accounts.py`, `contacts.py` | Accounts and contacts |
| `products.py` | Products and price books |
| `opportunities.py` | Opportunities, line items, stage changes, price preview |
| `bmc_quotes.py` | "Paste BMC quote" import |
| `quotes.py` | Quotes, PDFs, quote templates, emailing quotes |
| `activities.py` | Notes, calls, meetings, tasks |
| `dashboard.py`, `insights.py`, `views.py` | Dashboard, Insights, saved views |
| `imports.py` | Excel/CSV import and export, Freshsales and BMC Helix migrations |
| `entitlements.py` | Licences, MarketZone import, lapsed licences, renewal opportunities, notifications |
| `email.py`, `compose.py`, `mail_connect.py` | Mail settings and tests, templates, campaigns, writing an email, Microsoft 365 connection and sender |
| `marketing.py` | Mailing lists and audiences |
| `webforms.py`, `public.py`, `tracking.py` | Website forms (admin and public endpoints), tracking |
| `monitoring.py` | Health and monitoring endpoints |

### Frontend (`frontend/src`)

| Path | Responsibility |
|---|---|
| `main.tsx`, `App.tsx` | Providers (Mantine, TanStack Query, auth) and the route table. |
| `api.ts` | `api<T>(path, {method, body, form})`: adds the token, turns API errors into readable messages. |
| `auth.tsx` | Signed-in user, roles (`isAdmin`, `canWrite`), login and logout. |
| `hooks.ts` | Shared queries (`useBrands`, `usePipelines`, `useProducts`…) and `useApiMutation`, which shows success and error notifications and invalidates query keys. |
| `types.ts`, `labels.ts` | API types, display labels and formatters (`money2`, `fmtDate`…). |
| `pages/` | One file per screen (Dashboard, PipelineBoard, Opportunities, OpportunityEdit, Accounts, Import, SystemStatus…). |
| `components/` | Reusable parts: `Layout` (navigation), `LineItemsEditor`, `Licences`, `Quotes`, `ComposeEmail`, `Microsoft365`, `ui.tsx` and `common.tsx` (small shared widgets). |
| `help/topics.ts` | The in-app Help pages, in Markdown. |

### Data model (main tables)

```mermaid
erDiagram
    accounts ||--o{ contacts : has
    accounts ||--o{ opportunities : has
    accounts ||--o{ entitlements : "owns licences"
    brands ||--o{ opportunities : ""
    pipelines ||--o{ stages : ""
    stages ||--o{ opportunities : "is at"
    opportunities ||--o{ opportunity_line_items : ""
    opportunities ||--o{ quotes : ""
    products ||--o{ price_book_entries : ""
    price_books ||--o{ price_book_entries : ""
    opportunities ||--o{ activities : ""
    entitlements }o--o| opportunities : "renewal_opportunity_id"
    users ||--o{ opportunities : owns
```

Other tables: `audit_log`, `opportunity_stage_history`, `quote_templates`, `notifications`, `mailing_lists`,
`mailing_list_members`, `audiences`, `email_templates`, `campaigns`, `campaign_recipients`, `web_forms`, `web_form_submissions`,
`tracking_sites`, `web_visitors`, `web_events`, `saved_views`, `app_settings`, `mail_connections`, `import_jobs`.

---

## 3. Deployment prerequisites

**Server**

- A Linux VM (any distribution with Docker), 2 vCPU, 4 GB RAM and 20 GB disk are enough for the CRM; add space for
  `./backups`.
- Docker Engine 24+ with the Compose plugin (`docker compose version`).
- Git, and read access to `https://github.com/RazeemM/MetricsHub-CRM`.
- Outbound HTTPS from the VM to `login.microsoftonline.com` and `graph.microsoft.com` (SSO, Microsoft 365 email), and
  to your SMTP relay if used. Behind a proxy, set `HTTPS_PROXY` for the `api` container.

**Network**

- A DNS name (for example `crm.internal.sentrysoftware.net`) and a TLS certificate.
- A TLS reverse proxy in front of the `web` container: Caddy, Traefik, nginx, IIS/ARR or a load balancer. It forwards
  to `http://<vm>:8080` and must pass `X-Forwarded-For` and `X-Forwarded-Proto`. Each proxy that adds to
  `X-Forwarded-For` counts in `CRM_PROXY_HOPS`.
- Upload size: allow at least 25 MB request bodies (report imports, attachments).

**Microsoft Entra ID / Microsoft 365** (when used)

- An app registration with a client secret, and the redirect URIs below registered under the **Web** platform.
- For email with `graph_delegated`: delegated Graph permissions Mail.Send.Shared, offline_access, openid, profile, and
  Exchange **Send As** on the sender mailbox for each user who sends. For `graph`: the application permission Mail.Send
  with admin consent, restricted by an application access policy.

---

## 4. Deployment procedure

### First installation

```bash
git clone https://github.com/RazeemM/MetricsHub-CRM.git /opt/crm
cd /opt/crm
cp .env.example .env
nano .env                   # see "Initial configuration" below; at least the four required values
docker compose up -d --build
docker compose ps           # api and web should become "healthy" within a minute
docker compose logs -f api  # migrations, then "Uvicorn running on http://0.0.0.0:8000"
```

Then point the reverse proxy at port 8080, open `https://<CRM address>` and sign in with `CRM_ADMIN_EMAIL` /
`CRM_ADMIN_PASSWORD`.

### Updating

```bash
cd /opt/crm
git pull
docker compose up -d --build
```

Migrations run automatically when the API container starts. Check with `docker compose logs --tail 50 api`; a failed
migration stops the API from starting and the log shows the error.

| To | Run |
|---|---|
| Apply a changed `.env` | `docker compose up -d api` (recreates the container with the new values; `restart` does not reread `.env`) |
| Restart the API only | `docker compose restart api` |
| Restart everything | `docker compose restart` |
| See the API log | `docker compose logs -f --tail 100 api` |
| Open a database shell | `docker compose exec db psql -U crm crm` |
| Run a job by hand | `docker compose exec api python -m app.jobs renewals` |

### Rolling back

Code: `git checkout <previous commit> && docker compose up -d --build`. A migration is not undone by that: restore the
backup taken before the update, or run `docker compose exec api alembic downgrade <revision>` when the migration has a
working `downgrade()`.

### Backups and restore

`./backups/crm-YYYYMMDD-HHMM.dump` is written daily. Copy the folder off the VM (it is the only copy otherwise).

```bash
docker compose exec -T db pg_restore -U crm -d crm --clean < backups/crm-YYYYMMDD-HHMM.dump
docker compose restart api
```

Take one by hand before a risky update:

```bash
docker compose exec -T db pg_dump -U crm -d crm -Fc > backups/crm-before-update.dump
```

### Monitoring the deployment

- `GET /api/health` (liveness) and `GET /api/health/ready` (503 when a check failed) are open; the Docker healthchecks
  use them.
- `GET /api/monitoring/status` (JSON) and `GET /api/metrics` (Prometheus) need `CRM_MONITORING_TOKEN` or an
  administrator. The MetricsHub connector in `monitoring/metricshub` reads the first.
- **System status** in the app shows the same checks: database, schema, email, background jobs, backups.

---

## 5. Initial configuration

All settings are environment variables prefixed `CRM_`, read by `backend/app/config.py`, set in `.env` (documented in
`.env.example`). After changing `.env`: `docker compose up -d api`.

### Required

| Variable | Value |
|---|---|
| `POSTGRES_PASSWORD` | Database password (used by `db`, `api` and `backup`). |
| `CRM_SECRET_KEY` | Long random string: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Signs sessions and encrypts stored Microsoft 365 tokens: changing it signs everyone out and requires reconnecting Microsoft 365. |
| `CRM_APP_URL` | Public address, no trailing slash, e.g. `https://crm.internal.sentrysoftware.net`. Used for SSO and OAuth redirect URIs, links in emails and notifications. |
| `CRM_ADMIN_EMAIL`, `CRM_ADMIN_NAME`, `CRM_ADMIN_PASSWORD` | First administrator, created only when there is no user yet. |

### Single sign-on (Microsoft Entra ID)

1. App registration, **Web** redirect URI `https://<CRM address>/api/auth/sso/callback`, a client secret, the optional
   claim `email` in the ID token.
2. In `.env`:
   ```
   CRM_OIDC_ISSUER=https://login.microsoftonline.com/<tenant id>/v2.0
   CRM_OIDC_CLIENT_ID=<application id>
   CRM_OIDC_CLIENT_SECRET=<secret>
   CRM_OIDC_AUTO_PROVISION_DOMAINS=metricshub.com,sentrysoftware.com
   ```
3. Once everyone signs in with Microsoft: `CRM_PASSWORD_LOGIN_ENABLED=false`.

Two tenants: register the app as multitenant and use `https://login.microsoftonline.com/organizations/v2.0`.

### Email

| Setting | Values |
|---|---|
| `CRM_MAIL_BACKEND` | Quotes, emails written in the CRM, notifications: `graph_delegated`, `graph`, `smtp`, `log`, `disabled`. |
| `CRM_BULK_MAIL_BACKEND` | Campaigns; empty = same as above. An SMTP relay (Brevo, SendGrid…) protects the Microsoft 365 domain's reputation. |
| `CRM_MAIL_FROM`, `CRM_MAIL_FROM_NAME` | Default sender. Administrators can override it in **System status → Email**. |
| `CRM_GRAPH_TENANT_ID`, `CRM_GRAPH_CLIENT_ID`, `CRM_GRAPH_CLIENT_SECRET` | Only when the mail app registration or tenant differs from SSO. Tenant per domain: `metricshub.com=<id>,sentrysoftware.com=<id>`. |
| `CRM_SMTP_*` | Host, port, security (`starttls`, `ssl`, `none`), credentials. |

`graph_delegated` (each user sends with their own Microsoft 365 sign-in, as the shared mailbox):

1. Register `https://<CRM address>/api/mail/microsoft/callback` as a **Web** redirect URI on the same app registration
   as `CRM_GRAPH_CLIENT_ID` (or the SSO app when it is empty). Without it Microsoft answers *AADSTS900971: No reply
   address provided*.
2. Add the delegated permissions above; give Exchange **Send As** on the sender mailbox to the users who send.
3. Each user clicks **Connect Microsoft 365** once (in an email dialog or System status). An administrator ticks
   **Send automatic emails with my sign-in** for campaigns and notices.
4. Check with **System status → Send test**.

### Other settings

| Variable | Default | Purpose |
|---|---|---|
| `WEB_PORT` | 8080 | Port of the `web` container on the VM. |
| `BACKUP_RETENTION_DAYS` | 14 | Days of nightly dumps kept. |
| `CRM_CORS_ORIGINS` | | Only for API calls from another origin. |
| `CRM_PROXY_HOPS` | 1 | Proxies adding to `X-Forwarded-For` (nginx = 1; add one per TLS proxy). Used for form rate limits. |
| `CRM_RENEWAL_NOTICE_DAYS` | 60 | Licence renewal notices. |
| `CRM_RENEWAL_OPPORTUNITY_DAYS` | 60 | Renewal opportunities opened from licences (0 = off). |
| `CRM_RUN_SCHEDULER` | true | false = run `python -m app.jobs …` from cron. |
| `CRM_MONITORING_TOKEN` | | Token for `/api/monitoring/status` and `/api/metrics` (`openssl rand -hex 32`). |
| `CRM_TRACKING_RETENTION_DAYS` | 395 | Website tracking data kept. |
| `CRM_MARKETING_POSTAL_ADDRESS` | | Printed in campaign footers (anti-spam laws). |
| `CRM_FRESHSALES_DOMAIN`, `CRM_FRESHSALES_API_KEY` | | Only for the Freshsales API sync. |

### In the application, after the first sign-in

1. **Users**: invite colleagues (or rely on SSO auto-provisioning) and set roles.
2. **Products & pricing**: check products and price books per brand and currency (for example a Sentry price book in
   EUR for EUR quotes).
3. **Quote templates**: logo, wording, terms per brand.
4. **System status → Email**: sender, Microsoft 365 connection, **Send test**.
5. **Import / export**: import accounts and contacts, load the BMC MarketZone reports (Detail .xlsx preferred), preview
   renewal opportunities.
6. **Website forms / Website tracking**: create the forms and copy the embed code to the websites.

---

## 6. Local development

Prerequisites: Python 3.12+, Node 20+, PostgreSQL 16 (local or `docker compose up -d db`).

```bash
# Database: a "crm" user, a development database and a test database
createuser -s crm && createdb -O crm crm && createdb -O crm crm_test

# API (http://localhost:8000/api/docs)
cd backend
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
alembic upgrade head
python -m app.demo_data                           # optional fictitious data
uvicorn app.main:app --reload

# Web app (http://localhost:5173, proxies /api to :8000)
cd ../frontend
npm install
npm run dev
```

Sign in with `admin@example.com` / `admin123`. Without `.env`, the defaults in `config.py` apply: the database
`postgresql+psycopg://crm:crm@localhost:5432/crm` and `CRM_MAIL_BACKEND=disabled`. Use `CRM_MAIL_BACKEND=log` to test
email without sending anything.

**Tests**

```bash
cd backend
pytest                        # whole suite, about 20 seconds
pytest tests/test_licences.py -k lapsed
```

- They use the `crm_test` database (`tests/conftest.py`), recreated from the models at the start of each run.
- The `client` fixture is session-scoped: one database for the whole run, signed in as the administrator. Give the
  records you create unique names so tests do not depend on their order.
- External services are faked: `mail.transport` takes an `httpx.MockTransport` (Microsoft Graph and Entra), and
  `mail.smtp_factory` a fake SMTP connection.
- Quote PDF tests need WeasyPrint's GTK/Pango libraries; on Windows without them, `test_quotes.py` fails on
  `libgobject`. They pass in the Docker image.
- Real customer files (reports, quotes) must never be committed: test with invented names.

**Frontend checks**: `npm run build` type-checks (`tsc -b`) and builds; run it before committing.

---

## 7. Making an enhancement

### Workflow

1. **Branch**: `git checkout -b feature/<name>` from `main`.
2. **Backend**: model change and migration, domain logic, router, tests.
3. **Frontend**: types, page or component, help text.
4. **Check**: `pytest`, `npm run build`, then try it in the browser with both servers running.
5. **Commit** with a message saying what changed for users and why; open a pull request into `main`.
6. **Deploy**: merge, then `git pull && docker compose up -d --build` on the VM.

### Worked example: a "Customer success manager" on accounts

**1. Model** (`backend/app/models.py`, class `Account`):

```python
csm_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
```

**2. Migration**: one file per change in `backend/alembic/versions/`. Generate a draft against an up-to-date
database, then read and tidy it (autogenerate also picks up unrelated differences):

```bash
cd backend
alembic upgrade head
alembic revision --autogenerate -m "accounts: customer success manager"
```

Or write it by hand, following the existing files: a short docstring, `revision`, `down_revision` (the previous head,
see `alembic heads`), `upgrade()` and `downgrade()`:

```python
def upgrade() -> None:
    op.add_column("accounts", sa.Column("csm_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")))


def downgrade() -> None:
    op.drop_column("accounts", "csm_id")
```

Keep migrations additive when possible (new nullable columns, new tables), so the previous version keeps working
during a rollback. A migration that rewrites data needs a tested `downgrade()` or a backup plan.

**3. Schemas** (`backend/app/schemas.py`): add `csm_id: int | None = None` to the account input and output models.
Validation (allowed values, lengths, ranges) belongs here, with pydantic `Field`.

**4. Logic and endpoint** (`backend/app/routers/accounts.py`): check the user exists, save, write the audit log:

```python
if data.csm_id is not None and not db.get(User, data.csm_id):
    raise HTTPException(422, "Customer success manager not found")
...
audit(db, user, "account", acc.id, "update", changes)
db.commit()
```

Rules used by more than one router go in `services.py` or a domain module, not in the router.

**5. Tests** (`backend/tests/test_api.py` or a new `test_<feature>.py`):

```python
def test_account_customer_success_manager(client):
    me = client.get("/api/auth/me").json()
    acc = client.post("/api/accounts", json={"name": "CSM Test Co", "csm_id": me["id"]}).json()
    assert acc["csm_id"] == me["id"]
    assert client.post("/api/accounts", json={"name": "CSM Bad Co", "csm_id": 999999}).status_code == 422
```

**6. Frontend**:
- `src/types.ts`: add `csm_id: number | null` to `Account`.
- The account form (`src/components/forms.tsx`): a `UserPicker` (from `components/common.tsx`) bound to `csm_id`;
  `src/pages/AccountDetail.tsx`: show the name (`useUsers()` from `hooks.ts`).
- Saving goes through `useApiMutation`, with `invalidate: [['accounts'], ['account', id]]` so lists refresh.

**7. Help**: describe the field in the matching topic of `src/help/topics.ts` (and in `.env.example` and this guide
when adding a setting).

### Recipes

| To add | Where |
|---|---|
| A setting | A field in `Settings` (`config.py`) with a comment, read with `get_settings().<name>`; document it in `.env.example`. |
| An endpoint | A router function with a pydantic input model, `Depends(get_db)` and the right role dependency. A new router file must be imported and added to the `for r in (...)` list in `main.py`. |
| A background task | A function in a domain module, called from `jobs.run_renewals` (daily-ish) or a new `_loop` in `scheduler()`. It must be idempotent and safe to run twice. |
| A page | A file in `src/pages/`, a `<Route>` in `App.tsx`, an entry in `components/Layout.tsx` (admin-only entries check `isAdmin`). |
| An import from an external system | Mark imported records with `external_source` and `external_id` (unique index), so re-imports update instead of duplicating. Offer a dry run first. |
| A monitoring check | `monitoring.py`: a check returns `ok`, `degraded` or `failed` with a reason; it then appears on System status, `/api/monitoring/status` and `/api/metrics`. |
| A licence report format | `mzd_report.py`: map the new column headers in `field_for`; every report must still cross-check its totals. |

### Before merging

- [ ] `pytest` passes (apart from the known PDF tests without GTK on Windows).
- [ ] `npm run build` passes.
- [ ] A new table or column has a migration, tested with `alembic upgrade head` on a copy of real data when it touches
      existing rows.
- [ ] New settings are in `config.py` and `.env.example`; user-visible changes are in the help topics.
- [ ] No secrets, customer data or real reports in the commit.

---

## 8. Conventions and pitfalls

- **Errors for users**: raise `HTTPException(422, "<sentence the user can act on>")`. Reverse proxies (IIS/ARR, nginx
  error pages) often replace 5xx bodies, so expected failures (a mail server refusing, a bad file) use 422, not 500.
  `mail.http_error()` does this for email.
- **Audit**: every create, update and delete through the API calls `audit(...)`.
- **Idempotency**: imports and jobs can run again without duplicating (`external_source`/`external_id`, report
  `line_key`, `renewal_opportunity_id`, notices marked as sent).
- **Money**: `Decimal` in Python and `Numeric(14, 2)` in the database, never floats; amounts are rounded half-up to the
  cent (`pricing.py`).
- **Dates**: `datetime.date` for business dates; timestamps are timezone-aware UTC (`DateTime(timezone=True)`).
- **Query keys** (frontend): mutations invalidate the keys of the lists they change (`['opportunities']`, `['board']`,
  `['accounts']`…); otherwise the screen shows stale data.
- **Two brands**: most records carry a `brand_id` (MetricsHub or Sentry Software); filter and price by brand.
- **PostgreSQL only**: JSONB columns and advisory locks are used; tests need PostgreSQL too.
- **Secrets**: only in `.env` on the server. `CRM_SECRET_KEY` also encrypts stored Microsoft 365 refresh tokens.
- **Local Windows setups**: when the local PostgreSQL does not restart with the machine, start it again before running
  the API or tests (`pg_ctl -D <data folder> start`).
