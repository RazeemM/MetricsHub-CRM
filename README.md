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
  - **Pipeline views** save the board's filters under a name: owners (or *only my deals*, which follows whoever opens the view), brands, referring platforms, deal type, route to market, lead source, expected close (relative periods such as *This quarter* stay current, or between two dates), value range, hiding the Won and Lost columns, and the card order. A view is private, or shared with every user; only its owner and administrators can change it. *All deals*, *My deals* and *Closing this quarter* are always there. Changes show as removable chips, with **Save view**, **Save as new view** and **Reset**. The board reopens on the last view used. API: `/api/views`.
  - Click a column header to sort the Opportunities, Accounts, Contacts and Insights tables; click again to reverse. Numbers and dates sort largest or latest first. The (i) icons next to metrics and column headers explain how each figure is calculated.
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
  - It goes through the CRM's own mail system: either Microsoft 365, from the signed-in user's own mailbox (it then appears in their Outlook *Sent Items*), or the SMTP server, from `CRM_MAIL_FROM` with replies going to the user. See [Sending email](#sending-email-smtp-or-microsoft-365).
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

## Marketing: campaigns, newsletters, audiences and lists

The **Marketing** section of the menu holds the *Overview*, *Campaigns & newsletters*, *Audiences*, *Lists*, *Email templates* and (for admins) *Website forms*. Bulk email goes through the CRM's own mail system.

- **Overview:** how many contacts can be emailed or have consent, and over 30 days, 90 days or 12 months the emails delivered, open, click and unsubscribe rates, and the recent campaigns.
- **Audiences:** saved filters on contacts that stay up to date. A campaign sent to an audience goes to whoever matches when sending starts.
  - Rules: lifecycle, contact role, account type, country (the contact's or its account's), lead source, owner, brand, marketing consent, subscribed to a list, added in the last N days.
  - Licence rules use the account's licences: *has an active licence*, *lapsed* (had some, none active), *never had one*, *holds an active licence for* a product, *a licence renews within N days*.
  - The editor shows how many contacts match as you change the rules. *Save as a list* freezes today's matches into a static list, for example an event's invitees.
- **On the Contacts page:** the *View* picker shows all contacts, a list's members or an audience's matches.
  - Tick contacts and choose *Add to list* to add them to an existing list or a new one.
  - With filters set, *Save as audience* turns them into an audience.

- **Email templates:** reusable HTML designs per brand, started from a *Newsletter*, *Announcement* or *Blank* starter, or pasted/loaded from a designer's .html file, with a live desktop/mobile preview.
  - Merge fields: `{first_name}`, `{last_name}`, `{full_name}`, `{company}`, `{job_title}`, `{country}`, `{owner}`, `{email}`, `{postal_address}`, `{unsubscribe_url}`. A fallback is written `{first_name|there}`. Merged values are HTML-escaped.
- **Mailing lists:** a *contact list* (leads in a region, event attendees...) or *newsletter subscribers*.
  - Fill a list by filter (lifecycle, role, account type, country, brand, consent), from contacts, or by CSV import (`email`, optional `first_name`, `last_name`, `company`). Unknown addresses become new leads.
  - When importing, tick *they agreed to receive marketing email* only if they really did: it is recorded on each contact.
- **Campaigns:** pick a template (its content is copied into the campaign and can be adjusted), one or more lists and/or audiences, the from name and reply-to address.
  - **Send test** sends to up to 5 addresses with sample values.
  - **Send now** or **Schedule**. The recipients are fixed at that moment, and sending runs in the background at `CRM_BULK_RATE_PER_MINUTE`. It survives restarts and can be paused, resumed or cancelled. If the SMTP server cannot be reached, the campaign pauses with the error and nothing is lost.
  - The report shows sent, opened, clicked, unsubscribed, failed and skipped (with the reason) per recipient. Opens are approximate because mail apps block or pre-load images; clicks are reliable.
  - Each contact's page shows their lists and the campaigns they received.
- **Who is never emailed:**
  - contacts without an address, or with the same address twice (each address gets one copy)
  - contacts who unsubscribed from all marketing email
  - list members marked unsubscribed
  - for newsletters, and for campaigns with *Only contacts with marketing consent*: contacts without consent. Newsletter subscribers count as consenting.
- **Unsubscribe:** every email carries an unsubscribe link and the `List-Unsubscribe` / one-click headers that Gmail and Outlook show as an *Unsubscribe* button. A template without `{unsubscribe_url}` gets a footer added automatically.
  - The link opens a confirmation page, because mail scanners follow links. Confirming unsubscribes the contact from all marketing email and every list, and is noted on their timeline.
- **Tracking links** are signed, so they cannot be used to redirect people to other sites. Tracking can be turned off per campaign.

## Website tracking

**Marketing → Website tracking** (administrators) gives each website a tracking code, like Freshworks' CRM tracking code:

```html
<script src="https://crm.metricshub.com/api/public/t/<key>.js" async></script>
```

1. **Add the code** before `</head>` on every page, or once in the site's template or tag manager. **Send this to a developer** opens an email with the instructions.
2. **Add the domains** it runs on. Subdomains are included. Data from any other site is refused.

What it records:
- **Page views**, including route changes in single-page apps, with the page title. Addresses are stored without their query string.
- **Where each visit came from:**
  - The campaign parameters (`utm_source`, `utm_medium`, `utm_campaign`) when present.
  - Otherwise the referring site: *organic* for search engines, *social* for social networks, *referral* for other sites, *direct* when there is none.
  - Ad click ids mark paid search (Google, Bing).
  - *Track other URL parameters* also keeps `utm_term`, `utm_content` and the click ids.
- **Forms with an email field:**
  - Submitting one creates or completes the contact: name, company (matched to an account by email domain or name), phone, job title, country, LinkedIn, and a consent checkbox.
  - Other fields, passwords and hidden fields are never sent. Add `data-mhcrm-ignore` to a form to skip it.
  - Earlier anonymous visits from that browser join the contact, and the timeline gets a note saying where the contact first came from.
- **Your own calls:**
  ```html
  <script>
    window.mhcrm = window.mhcrm || []
    mhcrm.push(['identify', { email: 'jane@example.com', first_name: 'Jane', company: 'Example Corp' }])
    mhcrm.push(['track', 'Downloaded datasheet', { product: 'Hardware Sentry' }])
  </script>
  ```

Where it shows:
- **On the contact:** a *Website activity* card with the original and latest source, first and last visit, visits, page views, most viewed pages and a timeline of pages, events and forms. The source is also kept in the contact's data, as `web.original` and `web.latest`.
- **On the tracking page:** visitors, identified visitors, page views, sessions, custom events, top pages, sources, events, and recently seen contacts.
- **Check website integration:** looks for the code on each domain's home page and shows the last page view received.

Privacy:
- The code sets two first-party cookies: a visitor id for 13 months and a session id for 30 minutes.
- IP addresses are not stored.
- Browsers sending *Do Not Track* or *Global Privacy Control* are ignored. This setting is on by default.
- **Wait for the visitor's consent** records nothing and sets no cookie until the site's cookie banner calls `mhcrm.push(['consent', true])`. `false` forgets the visitor. Turn this on for visitors in the EU.
- Visits older than `CRM_TRACKING_RETENTION_DAYS` (395 by default) are deleted, along with anonymous visitors, by the scheduled job.

Endpoints:
- `GET /api/public/t/<key>.js` serves the script.
- `POST /api/public/t/<key>/collect` receives what it sends, rate-limited per address.
- `/api/tracking/sites` manages the sites.
- `/api/contacts/<id>/web` returns a contact's activity.

## Website forms (phase 4)

The websites' Contact, Quote request, Trial, Download, Partner and Newsletter forms post straight into the CRM. Admins set them up under **Website forms** in the menu. Each form has:

- a **key**, which gives its address: `https://crm.metricshub.com/api/public/forms/<key>`
- a **secret**, sent with every submission (see *Security* below). **Rotate** it from the form's page; the old one stops working at once.
- a **lead source** (Website contact form, Quote request, Trial, Download, Partner sign-up, Newsletter sign-up), a **brand**, and an **owner** for new contacts
- a **field mapping**: website field → contact field. Fields named `email`, `first_name`, `last_name`, `name`, `company`, `phone`, `job_title`, `country`, `message` work without a mapping.
- an optional **mailing list**, a **thank-you page** for plain HTML posts, and whether to **notify the owner**

**What a submission does**

1. Finds the contact by email, or creates it as a lead with the form's lead source, brand and owner. An existing contact keeps its values: only empty fields are filled.
2. Attaches the contact to the account with the same email domain (or exactly the company name typed), if there is one. Free-mail domains are ignored and no account is created; the company name is then kept on the contact.
3. Adds the person to the form's list:
   - **Contact list:** at once. Someone who unsubscribed from that list is not added back.
   - **Newsletter:** double opt-in. The person is added as *pending* and receives a confirmation email through the campaign mail server (`CRM_BULK_MAIL_BACKEND`). Only when they click the link and confirm on the page are they subscribed, with marketing consent recorded on the contact and on their timeline. Pending members never receive campaigns. The link is signed, valid for 7 days, and stops working if they unsubscribe afterwards. The email's subject and HTML can be customised per form (`{first_name}`, `{list_name}`, `{brand}`, `{confirm_url}`, `{postal_address}`).
   - If a website field is mapped to **Marketing consent** (a "Send me the newsletter" checkbox), people join the list only when they tick it. On a form without a newsletter list, ticking it records consent directly.
4. Logs every submitted field on the contact's timeline, and notifies the contact's owner (else the administrators) in the bell.

Every submission is listed on the form's **Submissions** tab with its status: accepted, pending opt-in, confirmed, spam or error. The **Test** tab processes a submission as if the website had sent it.

**Security**

- **Signed by the website server (HMAC), recommended.** The website's backend (WordPress, Next.js…) forwards the form fields and signs them, so the secret never reaches visitors: `X-CRM-Timestamp: <unix seconds>` and `X-CRM-Signature: sha256=<hex HMAC-SHA256(secret, timestamp + "." + raw body)>`. Requests more than 5 minutes old are refused.
- **Posted from the browser (token).** The secret is sent as the `X-CRM-Form-Token` header or a hidden `_token` field. It is visible in the page, so list the **allowed websites** (origins such as `https://www.metricshub.com`): browsers on other sites are refused.
- **Spam:** a hidden **honeypot** field (default `website`) that people never fill. Submissions with it filled, or with more than 3 links, get the usual answer but create nothing (status *spam*).
- **Rate limits:** submissions per hour per visitor and per form (default 20), plus 30 requests per 10 minutes per visitor across all forms, which also stops secret guessing. The visitor's address is read from `X-Forwarded-For`: set `CRM_PROXY_HOPS` to the number of proxies in front of the API (1 = the web container's nginx; 2 with Caddy or a load balancer in front).
- **Answers** are JSON: `{"ok": true, "status": "accepted"}` (or `"pending_confirmation"`), errors `{"ok": false, "detail": "..."}` with 401, 403, 404, 413, 422 or 429. A plain HTML form post is redirected to the thank-you page instead.

The form's **Website code** tab shows these snippets with the form's own address, fields and secret filled in.

**Plain HTML form** (token mode):

```html
<form action="https://crm.metricshub.com/api/public/forms/contact-us" method="post">
  <input type="hidden" name="_token" value="FORM_TOKEN">
  <input type="email" name="email" required placeholder="Email">
  <input type="text" name="name" placeholder="Name">
  <input type="text" name="company" placeholder="Company">
  <textarea name="message" placeholder="Message"></textarea>
  <label><input type="checkbox" name="newsletter" value="yes"> Send me the newsletter</label>
  <!-- honeypot: hidden from people, bots fill it -->
  <input type="text" name="website" tabindex="-1" autocomplete="off" style="position:absolute;left:-9999px" aria-hidden="true">
  <button type="submit">Send</button>
</form>
```

**JavaScript, staying on the page** (token mode; give the form `id="crm-form"`):

```html
<script>
document.querySelector('#crm-form').addEventListener('submit', async (e) => {
  e.preventDefault()
  const fields = Object.fromEntries(new FormData(e.target))
  fields._page = location.href
  const res = await fetch('https://crm.metricshub.com/api/public/forms/newsletter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CRM-Form-Token': 'FORM_TOKEN' },
    body: JSON.stringify(fields),
  })
  const r = await res.json()
  e.target.innerHTML = r.ok
    ? (r.status === 'pending_confirmation' ? 'Check your inbox to confirm.' : 'Thank you, we will be in touch.')
    : 'Sorry: ' + r.detail
})
</script>
```

**From the website's server** (HMAC mode, Node.js):

```js
import crypto from 'node:crypto'

export async function sendToCrm(fields) {
  const body = JSON.stringify(fields)
  const ts = Math.floor(Date.now() / 1000).toString()
  const sig = crypto.createHmac('sha256', process.env.CRM_FORM_SECRET).update(ts + '.' + body).digest('hex')
  const res = await fetch('https://crm.metricshub.com/api/public/forms/quote-request', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CRM-Timestamp': ts, 'X-CRM-Signature': 'sha256=' + sig },
    body,
  })
  return res.json()
}
```

**Test with curl:**

```bash
# token mode
curl -i https://crm.metricshub.com/api/public/forms/contact-us -H 'Content-Type: application/json' \
  -H 'X-CRM-Form-Token: FORM_TOKEN' -d '{"email":"jane@example.com","name":"Jane Example","message":"Hello"}'

# HMAC mode
SECRET='FORM_SECRET'; BODY='{"email":"jane@example.com","name":"Jane Example"}'; TS=$(date +%s)
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | sed 's/^.* //')
curl -i https://crm.metricshub.com/api/public/forms/quote-request -H 'Content-Type: application/json' \
  -H "X-CRM-Timestamp: $TS" -H "X-CRM-Signature: sha256=$SIG" -d "$BODY"
```

The form address and the confirmation link use `CRM_APP_URL`, which must be the CRM's public HTTPS address.

## BMC → BMC Helix contact addresses

Many BMC people moved from @bmc.com to a BMC Helix address. Admins upload the reconciliation workbook (`rapprochement_bmc_helix_historique.xlsx`) under *Import / export → BMC → BMC Helix contact addresses*.

Always run a **Dry run** first: it lists every change without writing anything.

| Sheet | What happens |
|---|---|
| *Correspondances* (probable match) | The contact with the @bmc.com address takes the Helix address. If both addresses exist as separate contacts, they are merged into the Helix one, keeping timeline, deals, list memberships, campaign history and form submissions. If neither exists, the contact is created. |
| *Non trouvés* | Missing contacts are created with their @bmc.com address. Nothing is deduced. |
| *Déjà Helix* | Missing contacts are created. |
| *Ambigus* | Never applied, only listed. |

- Existing contacts only get blank fields filled: name, and an account when the workbook's account exists in the CRM. BMC, BMC Software and BMC Helix map to the BMC platform account. Other account names are never created.
- The old address is kept as a *previous address*. It shows on the contact page, and searching for it finds the contact.
- The workbook's evidence (status, proof, date seen, original ID) is stored on the contact, and moves and merges are noted on its timeline.
- Untick *Move contacts to the probable Helix address* to apply only the creations. Running the same workbook again changes nothing more.

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
3. Email: one-to-one emails from a contact's page logged on the timeline, bounce handling, and .eml import of templates.

## API for integrations and AI agents

- **Interactive reference:** `https://<CRM address>/api/docs`. Click **Authorize** and sign in to try any endpoint. An alternative layout is at `/api/redoc`.
- **Machine-readable description (OpenAPI 3):** `https://<CRM address>/api/openapi.json`. Point tools and AI agents at it to discover the endpoints.
- **Authentication:** `POST /api/auth/login` with form fields `username` and `password` returns `access_token`. Send it as `Authorization: Bearer <token>`; tokens last 12 hours. Give integrations their own user with the **readonly** role.
- **Pages:** lists take `page` and `page_size` (up to 500) and return `items` and `total`.
- **Bulk exports:** `/api/export/opportunities`, `/api/export/accounts` and `/api/export/contacts`, with `?fmt=csv` or `?fmt=xlsx`.

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
uvicorn app.main:app --reload  # API reference: http://localhost:8000/api/docs

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

## Sending email (SMTP or Microsoft 365)

The CRM sends two kinds of email, each through a backend you choose in `.env`:

| Setting | Used for | Values |
|---|---|---|
| `CRM_MAIL_BACKEND` | quotes and notifications | `smtp`, `graph` (Microsoft 365), `log` (keep, don't send), `disabled` |
| `CRM_BULK_MAIL_BACKEND` | campaigns and newsletters | same values; empty = same as `CRM_MAIL_BACKEND` |

A common setup: quotes through Microsoft 365 from each user's own mailbox (`graph`), campaigns through an email service's SMTP relay (`smtp`), which is built for bulk sending and keeps your Microsoft 365 domain's reputation separate.

**SMTP settings** (restart the API after changing them, then use *Send test* on a campaign):

```
CRM_SMTP_HOST=smtp-relay.brevo.com       # Microsoft 365: smtp.office365.com  ·  SendGrid: smtp.sendgrid.net
CRM_SMTP_PORT=587
CRM_SMTP_SECURITY=starttls               # starttls (587) · ssl (465) · none (local relay only)
CRM_SMTP_USERNAME=...
CRM_SMTP_PASSWORD=...
CRM_MAIL_FROM=news@metricshub.com         # SMTP always sends from this address; it must be verified with the provider
CRM_MAIL_FROM_NAME=MetricsHub
CRM_BULK_RATE_PER_MINUTE=120             # stay under the provider's limit (Microsoft 365 SMTP: 30 per minute)
CRM_MARKETING_POSTAL_ADDRESS=MetricsHub S.A.S., [street], [city], France
```

Before the first campaign:

- **Authenticate your domain** with the provider: SPF, DKIM and DMARC DNS records. Without them, campaigns land in spam.
- **Microsoft 365 SMTP** (`smtp.office365.com`) needs SMTP AUTH enabled for the sending mailbox and is limited to about 10,000 recipients a day. That is fine for quotes, not for large newsletters.
- **Postal address:** anti-spam laws (CAN-SPAM, and good practice under GDPR) expect your postal address in every marketing email. Set `CRM_MARKETING_POSTAL_ADDRESS`; the starters print it through `{postal_address}`.
- **Public links:** open and click tracking and the unsubscribe page use `CRM_APP_URL`, so it must be the public HTTPS address people can reach.

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

## Monitoring: health, statistics and MetricsHub

**Admin → System status** (`/system`) shows the CRM's health and usage, refreshed every 30 seconds:

- **Health checks**, each *ok*, *degraded* or *failed*, with the reason:
  - **Database**: reachable, and its response time.
  - **Database schema**: migrations up to date.
  - **Email**: settings complete, sends that failed in the last hour (for example Microsoft 365's `ErrorAccessDenied`), and paused campaigns.
  - **Background jobs**: campaign sending ran in the last 5 minutes. Not checked when `CRM_RUN_SCHEDULER=false`.
  - **Backups**: the last nightly dump is under 26 hours old (degraded) or 50 hours (failed), not empty, and the backup disk has space left.
- **Statistics**:
  - API requests, errors and average response time.
  - Users signed in, records per object, and website form submissions.
  - Emails sent and failed, the campaign queue and the last failures.
  - Database size and connections, the largest tables, backups, recent sign-ins and imports.
- A **Send test** button that checks email from the same page.

Request and email counters are kept in memory and start again from zero when the API restarts.

### Endpoints

| Endpoint | Access | Use |
|---|---|---|
| `GET /api/health` | open | Liveness: the API answers (`{"status":"ok","service":"metricshub-crm"}`). |
| `GET /api/health/ready` | open | Readiness: **503** when a check *failed*, 200 otherwise. Statuses only, no details. Used by the Docker healthcheck. |
| `GET /api/monitoring/status` | token or admin | Everything on the System status page, as JSON. Read by the MetricsHub connector. |
| `GET /api/metrics` | token or admin | The same figures in Prometheus text format (`crm_up`, `crm_check_status`, `crm_http_requests_total`, `crm_email_messages_total`, `crm_backup_age_seconds`…). |

Give monitoring tools a token rather than a user account. Set it in `.env`, then run `docker compose up -d api`:

```
CRM_MONITORING_TOKEN=<output of: openssl rand -hex 32>
```

Send the token as `Authorization: Bearer <token>`. Tools that only do Basic authentication can send it as the password, with any username. Without a token, only signed-in administrators can read these endpoints.

```bash
curl -fsS -H "Authorization: Bearer $TOKEN" https://crm.metricshub.com/api/monitoring/status
```

The `api` and `web` containers have Docker healthchecks (`docker compose ps` shows *healthy* or *unhealthy*). The backup folder is mounted read-only into the API so it can check the backups.

### MetricsHub Enterprise connector

[`monitoring/metricshub/connectors/MetricsHubCRM/MetricsHubCRM.yaml`](monitoring/metricshub/connectors/MetricsHubCRM/MetricsHubCRM.yaml) reads `/api/monitoring/status` over HTTPS once per collect and reports three monitors:

| Monitor | Metrics |
|---|---|
| `crm` (MetricsHub CRM) | `crm.status` (ok / degraded / failed), `crm.uptime`, `http.server.requests`, `http.server.errors{error.type}`, `http.server.request.time`, `crm.records{crm.object}`, `crm.users`, `crm.users.active{crm.period}`, `crm.email.messages{crm.email.purpose,state}`, `crm.campaign.recipients{state}`, `crm.campaigns{state}`, `crm.form.submissions{state}`, `crm.backup.age`, `crm.backup.size`, `crm.backup.files`, `crm.backup.disk.usage{state="free"}`, `crm.backup.disk.limit` |
| `crm_check`, one per health check | `crm.check.status` (ok / degraded / failed); the check's message is its status information |
| `crm_database` | `db.server.size`, `db.server.connections`, `db.server.connections.limit` |

To use it:

1. Copy the `MetricsHubCRM` folder into a folder for custom connectors on the MetricsHub agent, for example `/opt/metricshub/connectors-custom/`. Then set `patchDirectory: /opt/metricshub/connectors-custom` at the top of `metricshub.yaml`.
2. Add the CRM as a resource. [`monitoring/metricshub/metricshub-crm.yaml`](monitoring/metricshub/metricshub-crm.yaml) is a ready-made example. The HTTP password is the monitoring token; encrypt it with `metricshub-encrypt`.
3. Restart MetricsHub. The metrics then reach your backend over OTLP with the rest of your infrastructure (BMC Helix, Datadog, Grafana, Prometheus…).

To check it from the command line:

```bash
metricshub crm.metricshub.com --type linux --https --http-port 443 -u metricshub -p <token> -pd /opt/metricshub/connectors-custom -c +MetricsHubCRM
```

Suggested alerts:
- `crm.status` or `crm.check.status` is *failed*: page someone. *Degraded*: open a ticket; the message says why.
- `crm.backup.age` is over 26 h.
- `crm.campaigns{state="paused"}` is over 0.
- The rate of `crm.email.messages{state="failed"}` is above 0.

MetricsHub's own HTTP and Linux monitoring of the VM (CPU, memory, file systems) and its PostgreSQL connector complement this connector.

## Project layout

```
backend/
  app/models.py        data model (accounts, contacts, products, price books, pipelines, opportunities…)
  app/pricing.py       deal value calculation
  app/services.py      business rules (contract dates, stage changes, account matching)
  app/webforms.py      website form submissions: checks, contact upsert, double opt-in
  app/monitoring.py    health checks and statistics (System status page, /api/monitoring/status, /api/metrics)
  app/routers/         REST API (auth, sso, accounts, contacts, products, opportunities, activities, imports, dashboard)
  alembic/             database migrations
  tests/               pytest suite (pricing, API, import/export, SSO)
monitoring/metricshub/ MetricsHub Enterprise connector and example resource configuration
frontend/src/
  pages/               Dashboard, Pipeline, Opportunities, Accounts, Contacts, Products, Import, Users
  components/          layout, forms, line-item editor, activity timeline
```
