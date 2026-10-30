/**
 * The in-app Help. Each topic is Markdown (see help/Markdown.tsx for what is supported):
 * links to pages are written [label](/pipeline), links to other topics [label](help:pipeline).
 * `admin` topics are listed for administrators only (others can still open them from a link).
 */
export interface HelpTopic {
  id: string
  group: string
  title: string
  summary: string
  admin?: boolean
  body: string
}

export const GROUPS = ['Getting started', 'Selling', 'Customers and licences', 'Marketing', 'Data', 'Administration', 'Best practices', 'Troubleshooting']

export const TOPICS: HelpTopic[] = [
  // ------------------------------------------------------------------ Getting started
  {
    id: 'welcome',
    group: 'Getting started',
    title: 'Welcome to the CRM',
    summary: 'What the CRM is for, how it is laid out, and what each role can do.',
    body: `
The CRM tracks the accounts, people and deals of **MetricsHub** and **Sentry Software**, including the deals that come through observability platforms (BMC Helix, Datadog, Splunk, Grafana…) and BMC MarketZone. It also holds customer licences from the MarketZone reports, and runs email campaigns, website forms and website tracking.

## Finding your way around

- **The menu** on the left: [Dashboard](/), [Pipeline](/pipeline), [Insights](/insights), [Opportunities](/opportunities), [Accounts](/accounts), [Contacts](/contacts), [Products & pricing](/products), [Quote templates](/quote-templates), **Marketing**, [Import / export](/import), and for administrators [Users](/users) and [System status](/system).
- **Search** at the top finds accounts, contacts and deals by name, email (also an earlier address) or domain. Accounts show their licences and next renewal right in the results.
- **The bell** lists your notifications: licence renewals coming up, website form submissions, and similar.
- **The moon/sun** switches between dark and light mode.
- **The (i) icons** next to figures explain how each one is calculated. Hover them.
- **Column headers** in tables sort the table; click again to reverse.

## Roles

| Role | Can |
|---|---|
| **Sales** | Create and edit accounts, contacts, deals, activities, quotes, lists, audiences and campaigns; import data. |
| **Read-only** | See everything, change nothing. Good for management and for integrations. |
| **Admin** | Everything, plus users, prices and quote templates, website forms and tracking, MarketZone imports, migrations and system status. |

Every change is recorded in an audit log.

> New here? Read [Your first day](help:first-day), then [The pipeline and its views](help:pipeline).
`,
  },
  {
    id: 'first-day',
    group: 'Getting started',
    title: 'Your first day',
    summary: 'A short checklist to get set up and productive.',
    body: `
1. **Sign in with Microsoft** (or the email and password you were given). If the CRM says your account does not exist, ask an administrator to invite you under [Users](/users).
2. **Open the [Pipeline](/pipeline)** and pick the view **My deals**: these are the opportunities you own.
3. **Check the [Dashboard](/)**: your open tasks and the deals closing in the next 30 days.
4. **Look up a customer** with the search box at the top. On the account, open the **Licences** tab to see what they own and when it renews.
5. **Log what you do.** On an account, contact or deal, add a note, call, meeting or task. The timeline is what your colleagues will rely on.
6. **Save your own pipeline view**, for example "My renewals this quarter": see [The pipeline and its views](help:pipeline).

> Tip: everything you see in a table can be sorted by clicking its column headers, and most lists can be exported to Excel from their page or from [Import / export](/import).
`,
  },

  // ------------------------------------------------------------------ Selling
  {
    id: 'accounts-contacts',
    group: 'Selling',
    title: 'Accounts and contacts',
    summary: 'Companies and people: types, roles, lifecycle, owners, and keeping them clean.',
    body: `
## Accounts

An account is a company. Its **type** says what it is to us:

- **Prospect** or **customer**.
- **Platform partner**: BMC, Datadog, Splunk, Grafana, Dynatrace, New Relic, ServiceNow, Elastic. Deals they refer point to them as the *referring platform*.
- **Reseller**, **MSP**, **system integrator**, or **other**.

An account can have a **parent** (a group and its subsidiaries) and an **owner**: the person responsible for the relationship. The account page has tabs for its licences, contacts, opportunities and activity.

## Contacts

A contact is a person, usually attached to an account. Contacts are matched to accounts by their **email domain** (free-mail domains like gmail.com are ignored).

- **Role:** customer contact, platform account manager (for example the Datadog rep who brought a deal), partner contact, technical, economic buyer, champion.
- **Lifecycle:** lead → qualified → customer, or disqualified.
- **Source:** how they reached us (website form, import, Freshsales…).
- **Marketing consent:** whether they agreed to receive marketing email, with the date. *Unsubscribed* contacts are never emailed by a campaign.
- **Previous addresses:** an earlier email (for example @bmc.com before BMC Helix). Searching for it still finds the contact.
- **Website activity:** when the website tracking code is in place, the pages they viewed and where they first came from.

Email addresses are unique: the CRM refuses a second contact with the same address, whatever the case.

## Day to day

- **Email a contact** from their page (click the address). The message goes from your own mailbox and is logged on the timeline.
- **Filter the [Contacts](/contacts) list** by lifecycle, role, source, list or audience, tick contacts and **Add to list**, or **Save as audience**.
`,
  },
  {
    id: 'opportunities',
    group: 'Selling',
    title: 'Opportunities and pricing',
    summary: 'Creating a deal, adding products, how TCV, ARR and weighted value are worked out.',
    body: `
An opportunity is a deal with one account, for one **brand** (MetricsHub or Sentry Software).

## Creating one

Use **New opportunity** (on the Pipeline or Opportunities page, or from an account). The important fields:

| Field | Why it matters |
|---|---|
| **Deal type** | New, expansion or renewal. Renewals go to the Renewals pipeline. |
| **Lead source** | Where the deal came from (platform referral, website, trial…). Used in reports. |
| **Referring platform** and its **account manager** | The partner that brought the deal (BMC, Datadog…) and their rep. |
| **Route to market** | Direct, BMC MarketZone, marketplace or reseller. |
| **Expected close** | Drives forecasts, "closing soon" lists and pipeline views. Keep it realistic. |
| **Contract start and term** | The contract end is calculated. |

## Products and value

Add lines from the catalog. The unit price comes from the **price book**; you can override it, and give each line its own discount and term.

- Recurring line = quantity × monthly unit price × term in months × (1 − discount)
- One-time line = quantity × unit price × (1 − discount)
- **TCV** (total contract value) = all lines. **ARR** = the recurring value per year.
- **Weighted** = TCV × win probability: the deal's own probability if you set one, otherwise its stage's.

Amounts in different currencies are never added together.

## From a BMC quote

When a BMC quote with Sentry products comes to you for approval, use **Paste BMC quote** (on the Pipeline or Opportunities page):

1. Open the approval email, select all of it (Ctrl+A), copy it and paste it into the box. Copying from Outlook, a browser or a PDF all work.
2. **Read quote** lists the Sentry products found in the quote, with their quantity, period, discount and total charge. The BMC products are left out. Untick a line to leave it out too.
3. Pick the customer account (or add it), check the deal type and expected close, and **Create opportunity**.

The opportunity is a Sentry Software deal through BMC MarketZone, referred by BMC, at the "Proposal / Follow-up" stage ("Renewal pending" for a renewal). Each Sentry product becomes a line with the quote's **Qty**, its **List Price** as unit price (per month), its **Recurring Discount%** as discount, and its term from the start and end dates. The dialog shows what that comes to next to the quote's **Total Charge**: they often differ, because BMC's effective price is not always list price less the recurring discount. Choose **Total charge in the quote** to make each line worth exactly what BMC charges instead. Either way the total charge, effective price and dates are kept in the line's description.

The opportunity is in the quote's currency. Add a Sentry price book in that currency (for example EUR) under Products & pricing so that the deal is linked to one. The contract runs from the earliest start date to the latest end date. The BMC sales rep named in the approvals becomes the partner contact when they are a contact in the CRM, and the approvals are kept in a note.

> Pasting the same quote twice is caught: the second time you get a link to the opportunity already created.

## Stages

**New Business:** New (10%) → Discovery (20%) → Demo (30%) → PoC / Trial (50%) → Proposal / Follow-up (60%) → Negotiation (80%) → Won / Lost. **Renewals:** Upcoming renewal → Renewal pending → Renewed / Churned.

Moving a deal records the stage history. Marking it **Lost** asks for a reason: always give one, it is how we learn.

The [Opportunities](/opportunities) list can be filtered (open, won, lost, brand, platform), sorted by any column, and exported.
`,
  },
  {
    id: 'pipeline',
    group: 'Selling',
    title: 'The pipeline and its views',
    summary: 'The Kanban board, filters, and saving views you and your team can reuse.',
    body: `
The [Pipeline](/pipeline) shows each open deal as a card in its stage. **Drag a card** to another column to change its stage. Switch between the **New Business** and **Renewals** pipelines at the top.

Each column shows its number of deals, its total value and the stage probability. Hover the total for the weighted value.

## Filters

- **Search** finds deals by title or account.
- **Filters** opens the full set:
  - *Only my deals*, which follows whoever opens the view.
  - Owners, brands, referring platforms, deal type, route to market and lead source.
  - Expected close: this month, this quarter, next 90 days, overdue, no date, or between two dates.
  - A value range, and *Hide the Won and Lost columns*.
- **Card order** sorts the cards in each column by close date, value, recently updated, newest, title or account.

Active filters show as chips under the bar. Click × on a chip to remove that filter.

## Views

A view is a named set of filters.

- **All deals**, **My deals** and **Closing this quarter** are always there.
- **Save as new view** keeps the current filters under a name. Tick *Share with everyone* to make it a team view.
- When you change the filters of a view you own, **Save view** updates it, and **Reset** goes back to what was saved.
- The **⋯** menu next to the view renames, shares or deletes it. Only the owner and administrators can change a shared view; others can still save their own copy.
- The board reopens on the last view you used.

> Relative dates stay current: a view saved as "This quarter" always shows the current quarter. Good team views: "Closing this quarter", "Datadog-referred deals", "Renewals over $50k".
`,
  },
  {
    id: 'quotes',
    group: 'Selling',
    title: 'Quotes',
    summary: 'Generating a PDF quote from a deal, versions, statuses and emailing it.',
    body: `
On an opportunity, **Generate quote** creates a PDF from the deal's lines, using the brand's [quote template](/quote-templates).

- **Numbering** is per brand and year: \`MH-Q-2026-0001\`, \`SEN-Q-2026-0001\`. Later quotes for the same deal become v2, v3…
- **A quote is frozen**: it keeps the lines, prices, customer and template as they were. Change the deal and generate a new version rather than editing what the customer already has.
- **Status:** draft, sent, accepted, rejected or expired. Only drafts can be deleted.
- **Email it** with the envelope button: the message is pre-filled for the primary contact with the PDF attached, sent from your mailbox, logged on the timeline, and the quote is marked *sent*.

> Before quoting Sentry bundles through BMC, check the price book: the BMC list prices are internal and must not appear in customer documents other than the quote itself.

Administrators edit the templates (logo, colours, company details, payment terms, terms & conditions, email wording) under [Quote templates](/quote-templates), with a live and PDF preview.
`,
  },
  {
    id: 'activities',
    group: 'Selling',
    title: 'Activities, tasks and email',
    summary: 'Notes, calls, meetings, tasks and emails on the timeline.',
    body: `
Every account, contact and opportunity has a **timeline**. Add a **note**, **task** (with a due date), **call**, **meeting** or **logged email**.

- **Tasks** you own appear on the [Dashboard](/) under *My open tasks*. Overdue ones show in red. Tick them off when done.
- **Emails written in the CRM** (from a contact's address, or a quote's envelope button) are sent from your own mailbox and logged automatically, including who they went to and the attachment names.
- The CRM also writes to timelines for you: website form submissions, contacts identified by website tracking, campaign unsubscribes, merges and address changes.

> Write notes for the colleague who will pick up the account after you: who you spoke to, what they need, what was agreed, what happens next.
`,
  },

  // ------------------------------------------------------------------ Customers and licences
  {
    id: 'licences',
    group: 'Customers and licences',
    title: 'Licences and renewals',
    summary: 'What a customer owns, renewal dates, lapsed licences and renewal notices.',
    body: `
An account's **Licences** tab shows one row per product: the current quantity (credit memos subtracted), the **renewal date**, the reseller and a status: active, renewal due, ended · awaiting next report, lapsed, or starts later.

Licences come from the quarterly **BMC MarketZone reports** (loaded by an administrator, see [MarketZone reports](help:marketzone)). They can also be added by hand, for example for direct sales.

- **Renewal date** = the end of the last period already invoiced, so a prepaid multi-year deal shows its final year.
- **Instalments** (quarterly SaaS billing, for example) are not contract ends and never trigger a notice.
- **Perpetual licences** never renew; their maintenance appears as a separate *Support* licence, which does.
- **Lapsed** means a later report covered the end date and had no renewal line. Until that report arrives, the licence shows *ended · awaiting next report*.

## Renewal notices

About 60 days before a renewal date, the CRM notifies the owner of the account's open renewal opportunity (else the account owner, else the administrators), in the bell and by email. Each renewal is notified once.

## Lapsed licences

They stay on the [Dashboard](/) until someone clicks **Resolve** and notes what happened (renewed outside MarketZone, churned…). A resolved licence can be reopened.
`,
  },
  {
    id: 'insights',
    group: 'Customers and licences',
    title: 'Insights',
    summary: 'Renewals at risk, retention (NRR/GRR), resellers, credit memos and cross-sell.',
    body: `
[Insights](/insights) turns the licence data into where to focus. Hover the (i) icons for exact definitions.

| Tab | Shows |
|---|---|
| **Renewals at risk** | Licences renewing within N months, their annual value, and what to do: no renewal deal yet, no activity in 90 days, no owner. Choose *Needs action* to see only those. |
| **Retention** | Net and gross revenue retention for a year against the one before, churned and new customers, and where revenue is kept or lost by region, product family or reseller. |
| **Resellers** | Revenue per reseller over 12 months, growth, customers, renewal rate, lapsed licences and credits. *Quiet* resellers have not invoiced in 6 months. |
| **Credit memos** | Amounts credited per quarter, per customer and reseller, and licences credited and re-billed repeatedly. |
| **Cross-sell** | Product families customers usually own together, and which customers are missing one. |

> Work the *Renewals at risk* list every week: open a renewal opportunity for each "no renewal deal" line well before the date.
`,
  },
  {
    id: 'dashboard',
    group: 'Customers and licences',
    title: 'Dashboard and reports',
    summary: 'The headline figures, charts, and getting data out.',
    body: `
The [Dashboard](/) shows, for all brands or the one you pick:

- **Open pipeline** and **weighted pipeline**, per currency.
- **Won this quarter** and the **12-month win rate** (won ÷ won or lost).
- Open pipeline **by stage** and **by referring platform**.
- **Deals closing in the next 30 days**, including overdue ones, and **your open tasks**.
- **Licences:** products, revenue by region and country, active customers per period, invoiced vs paid to Sentry, and lapsed licences to resolve. Each chart has a *Table* switch with the exact figures.

**Exports:** the Opportunities, Accounts and Contacts pages have an **Export** button (Excel or CSV) that follows your filters. Tables can be sorted before you copy them.
`,
  },

  // ------------------------------------------------------------------ Marketing
  {
    id: 'audiences-lists',
    group: 'Marketing',
    title: 'Audiences and lists',
    summary: 'Who to email: dynamic audiences, static lists and newsletter subscribers.',
    body: `
## Audiences (dynamic)

An [audience](/marketing/audiences) is a saved filter on contacts that stays up to date: a campaign sent to it goes to whoever matches when sending starts.

- **Contact rules:** lifecycle, role, account type, country, lead source, owner, brand, marketing consent, member of a list, added in the last N days.
- **Licence rules:** has an active licence, lapsed, never had one, holds a given product, renews within N days.

The editor shows how many contacts match as you go. **Save as a list** freezes today's matches, for example an event's invitees.

## Lists (static)

A [list](/email/lists) is either a **contact list** (leads in a region, event attendees…) or **newsletter subscribers**. Fill it by filter, by picking contacts, or by importing Excel/CSV (\`email\`, optionally \`first_name\`, \`last_name\`, \`company\`). Unknown addresses become new leads.

> When importing, tick *they agreed to receive marketing email* only if they really did. It is recorded on each contact and decides who newsletters can reach.
`,
  },
  {
    id: 'campaigns',
    group: 'Marketing',
    title: 'Campaigns and newsletters',
    summary: 'Templates, sending, tests, scheduling, reports, and who is never emailed.',
    body: `
1. **Design** an [email template](/email/templates): start from *Newsletter*, *Announcement* or *Blank*, or paste a designer's HTML. Preview on desktop and mobile. Merge fields: \`{first_name}\`, \`{company}\`, \`{owner}\`… with fallbacks like \`{first_name|there}\`.
2. **Create** a [campaign](/email/campaigns): pick the template (its content is copied and can be adjusted), one or more lists and/or audiences, the from name and reply-to address.
3. **Send test** to yourself (up to 5 addresses).
4. **Send now** or **Schedule**. Sending runs in the background at a steady rate, survives restarts, and can be paused, resumed or cancelled. If the mail server refuses, the campaign **pauses** with the reason and nothing is lost.
5. **Read the report:** sent, opened, clicked, unsubscribed, failed and skipped, per recipient. Opens are approximate (mail apps block or pre-load images); clicks are reliable.

## Who is never emailed

- Contacts without an address, or a duplicate address (each address gets one copy).
- Contacts who unsubscribed from all marketing email, and list members marked unsubscribed.
- For newsletters, and campaigns set to *Only contacts with marketing consent*: contacts without consent.

Every email has an unsubscribe link and the one-click *Unsubscribe* button Gmail and Outlook show. Unsubscribing is final for all marketing email and is noted on the contact's timeline.

> See [Email best practices](help:bp-email) before your first large send.
`,
  },
  {
    id: 'web-forms',
    group: 'Marketing',
    title: 'Website forms',
    summary: 'Contact, quote, trial and newsletter forms that post straight into the CRM.',
    admin: true,
    body: `
[Website forms](/web-forms) give each website form an address in the CRM. A submission:

1. Finds the contact by email or creates a lead, with the form's **lead source**, **brand** and **owner**. Only empty fields of an existing contact are filled.
2. Attaches it to the account with the same email domain (or company name).
3. Adds it to the form's **list**, with **double opt-in** for newsletters: the person must confirm by email before receiving anything.
4. Logs every field on the timeline and notifies the owner.

Each form has a **Website code** tab with ready-to-paste HTML, JavaScript and server examples, a **Test** tab, and a **Submissions** tab (accepted, pending opt-in, confirmed, spam, error).

**Security:** prefer **HMAC signing from the website's server** (the secret never reaches browsers). For browser posts, list the **allowed websites**. A hidden honeypot field and rate limits stop spam. **Rotate** the secret if it leaks.

> Website forms and [website tracking](help:website-tracking) work together: the form creates the contact, tracking adds the pages they visited before.
`,
  },
  {
    id: 'website-tracking',
    group: 'Marketing',
    title: 'Website tracking',
    summary: 'The tracking code: page views, forms, custom events, sources and consent.',
    admin: true,
    body: `
[Website tracking](/tracking) gives each website a one-line code, like Freshworks' CRM tracking code.

1. **Add the code** before \`</head>\` on every page (or once in the template or tag manager). **Send this to a developer** emails the instructions.
2. **Add your domains.** Subdomains are included; data from other sites is refused.
3. Open the website and click **Check website integration**.

## What it records

- **Page views**, including single-page-app route changes, without query strings.
- **Where each visitor came from:** utm campaign parameters, ad clicks, or the referring site (organic, social, referral, direct). Contacts get an *original* and a *latest* source.
- **Forms with an email field** create or complete the contact (name, company, phone, job title only), and earlier anonymous visits from that browser join the contact. Add \`data-mhcrm-ignore\` to a form to skip it.
- **Your own calls** after sign-ups or sign-ins:

\`\`\`html
<script>
  window.mhcrm = window.mhcrm || []
  mhcrm.push(['identify', { email: 'jane@example.com', first_name: 'Jane' }])
  mhcrm.push(['track', 'Downloaded datasheet', { product: 'Hardware Sentry' }])
</script>
\`\`\`

The contact page shows a **Website activity** card, and the tracking page shows visitors, sources, top pages and events.

## Privacy

- **Wait for the visitor's consent:** nothing is recorded until your cookie banner calls \`mhcrm.push(['consent', true])\`. Turn this on for EU visitors.
- Do Not Track and Global Privacy Control are respected.
- IP addresses are not stored, and visits are deleted after 13 months.
`,
  },

  // ------------------------------------------------------------------ Data
  {
    id: 'import-export',
    group: 'Data',
    title: 'Importing and exporting',
    summary: 'Bringing in Excel/CSV files without duplicates, and getting data out.',
    body: `
[Import / export](/import) brings accounts, contacts or opportunities in from Excel or CSV in three steps:

1. **Upload** the file.
2. **Map** its columns to CRM fields (suggested automatically, check them).
3. **Review** the result: created, updated, skipped, and the errors with their row numbers.

**Duplicates:** contacts are matched by email, accounts by domain then name. Choose whether a match is **updated** (only the mapped columns) or **skipped**. Contacts are linked to accounts by email domain.

**Exports:** accounts, contacts and opportunities to Excel or CSV, from this page or each list's **Export** button.

> Import a small sample first (10 rows), check the result, then the whole file. Keep the original file until you have checked the import.
`,
  },
  {
    id: 'marketzone',
    group: 'Data',
    title: 'BMC MarketZone reports',
    summary: 'Loading the quarterly reseller fee report to keep licences current.',
    admin: true,
    body: `
Each quarter BMC sends the *Reseller Fee Report to Sentry Software* (PDF) and a *Detail* .xlsx. Load it under [Import / export](/import) → **BMC MarketZone report**:

1. Drop the file and click **Dry run**: it lists what will be created and checks every section total of the report.
2. If everything reads correctly, click **Import licences**.

- **Prefer the Detail .xlsx**: it is exact. Some older PDF layouts cannot be read reliably.
- **Nothing half-right is saved:** if a line cannot be read or a total does not match, the import is refused. Load the .xlsx of that quarter instead.
- Loading the same report again (or both files of a quarter) changes nothing.
- Customers are matched to accounts by name, ignoring Ltd, Inc, GmbH…; new ones are created as customers, and a different billing company becomes the reseller.

> The reports are BMC-confidential: don't keep copies in shared folders.
`,
  },
  {
    id: 'migrations',
    group: 'Data',
    title: 'Freshsales migration and BMC Helix addresses',
    summary: 'One-off data moves: from Freshsales, and @bmc.com contacts moving to BMC Helix.',
    admin: true,
    body: `
## From Freshsales

Under [Import / export](/import) → **Migrate from Freshsales**: drop the Accounts, Contacts and Deals exports, click **Dry run**, check the stage mapping, unknown owners and detected platforms, invite missing owners under [Users](/users), then **Import for real**. Running it again updates rather than duplicates (each record keeps its Freshsales id). The final sync on cut-over day can use the Freshsales API: see the README.

## BMC → BMC Helix contact addresses

Under [Import / export](/import) → **BMC → BMC Helix contact addresses**, upload the reconciliation workbook and always **Dry run** first.

- Probable matches move the contact to the Helix address. If both addresses exist, the two contacts are merged and everything is kept.
- Missing contacts are created; ambiguous rows are only listed.
- The old address stays as a *previous address*, so search still finds it.
`,
  },

  // ------------------------------------------------------------------ Administration
  {
    id: 'users-sso',
    group: 'Administration',
    title: 'Users, roles and sign-in',
    summary: 'Inviting people, choosing roles, Microsoft sign-in.',
    admin: true,
    body: `
Under [Users](/users), **Invite user** with their email, name, role and main brand. Leave the password empty for people who sign in with Microsoft.

- **Roles:** *admin*, *sales*, *read-only* (see [Welcome](help:welcome)). Give admin to as few people as possible.
- **Deactivate** people who leave instead of deleting them: their deals and history stay attributed.
- **Integrations and AI agents** get their own user with the *read-only* role.

## Microsoft sign-in (SSO)

Configured on the server with \`CRM_OIDC_*\` settings (an Entra ID app registration). People whose email is in an auto-provisioned domain (metricshub.com, sentrysoftware.com) get a *sales* account on first sign-in; others must be invited. Once everyone uses Microsoft sign-in, password login can be turned off (\`CRM_PASSWORD_LOGIN_ENABLED=false\`).
`,
  },
  {
    id: 'email-setup',
    group: 'Administration',
    title: 'Setting up email',
    summary: 'Microsoft 365 or SMTP for quotes and campaigns, and fixing send errors.',
    admin: true,
    body: `
The CRM sends two kinds of email, each through its own backend, set in the server's \`.env\` file:

| Setting | For | Values |
|---|---|---|
| \`CRM_MAIL_BACKEND\` | quotes, emails written in the CRM, notifications | \`graph\` (Microsoft 365), \`smtp\`, \`log\`, \`disabled\` |
| \`CRM_BULK_MAIL_BACKEND\` | campaigns and newsletters | same; empty = same as above |

**Recommended:** Microsoft 365 for one-to-one email (it then appears in the sender's Outlook *Sent Items*), and an email service's SMTP relay (Brevo, SendGrid…) for campaigns, to protect your Microsoft 365 domain's reputation.

## Microsoft 365 (graph)

The app registration needs the Microsoft Graph **application** permission **Mail.Send** with **admin consent**, in the tenant of every sending mailbox. An Exchange application access policy should limit it to a group of CRM senders.

## Checking

[System status](/system) shows the email check, recent failures with Microsoft's or the SMTP server's exact reason, and a **Send test** button.

> \`ErrorAccessDenied\` from Microsoft 365 means the app may not send as that mailbox: check the Mail.Send application permission and admin consent, the application access policy, and that \`CRM_GRAPH_TENANT_ID\` names the mailbox's tenant.
`,
  },
  {
    id: 'pricing-admin',
    group: 'Administration',
    title: 'Products, price books and quote templates',
    summary: 'Keeping the catalog and prices right.',
    admin: true,
    body: `
- **[Products & pricing](/products):** the catalog per brand (SKU, unit, recurring or one-time) and **price books** (per currency or channel: *MetricsHub Direct USD*, *Sentry via BMC (USD)*…). Recurring products are priced per unit per month.
- Changing a price affects **new** deal lines only; existing deals and sent quotes keep their prices.
- **[Quote templates](/quote-templates):** one per brand: logo, colours, company details, introduction, payment terms, terms & conditions, footer, and the email wording. Use the PDF preview before saving, and *Reset* to restore the defaults.

> Review price books when list prices change (new fiscal year, BMC price list) and say in the price book's name which year it is.
`,
  },
  {
    id: 'monitoring',
    group: 'Administration',
    title: 'System status, monitoring and backups',
    summary: 'Health checks, statistics, MetricsHub monitoring, backups and updates.',
    admin: true,
    body: `
[System status](/system) shows the health checks (database, schema, email, background jobs, backups) with the reason when something is wrong, plus API traffic, users, email, database size and recent failures.

- **MetricsHub Enterprise** can monitor the CRM with the connector in \`monitoring/metricshub\`, using the \`CRM_MONITORING_TOKEN\`. Prometheus can read \`/api/metrics\`.
- **Backups** run every night into the server's \`backups\` folder and are kept for 14 days by default. The Backups check turns degraded after 26 hours without a new one. Copy backups off the server regularly, and test a restore now and then.
- **Updating** the CRM on the server: \`cd /opt/crm && git pull && docker compose up -d --build\`. Database changes apply automatically when the API starts.

> Alert on: overall status *failed*, backup age over 26 hours, a paused campaign, and failed emails.
`,
  },
  {
    id: 'api',
    group: 'Administration',
    title: 'API and integrations',
    summary: 'Connecting other tools and AI agents to the CRM.',
    admin: true,
    body: `
- **Reference:** [/api/docs](/api/docs) (click **Authorize** to try any call) and the machine-readable [/api/openapi.json](/api/openapi.json) for tools and AI agents.
- **Sign in:** \`POST /api/auth/login\` with \`username\` and \`password\` returns a token; send it as \`Authorization: Bearer <token>\`. Tokens last 12 hours.
- Lists are paged (\`page\`, \`page_size\` up to 500); bulk exports are under \`/api/export/…\`.

> Give each integration its own **read-only** user, so it can be switched off on its own and its actions show in the audit log.
`,
  },

  // ------------------------------------------------------------------ Best practices
  {
    id: 'bp-data',
    group: 'Best practices',
    title: 'Keeping data clean',
    summary: 'Habits that keep the CRM trustworthy.',
    body: `
- **Search before you create.** Search finds accounts by name and domain and contacts by email, including previous addresses.
- **One person = one contact, one company = one account.** Use parent accounts for groups and subsidiaries rather than duplicates.
- **Fill the account domain**: it links contacts and website form submissions to the right account automatically.
- **Set the referring platform and its account manager** on partner-sourced deals: platform reports depend on it.
- **Keep the account type current**: a prospect that buys becomes a customer.
- **Disqualify, don't delete**: a disqualified lead keeps its history and stays out of campaigns that target leads.
- **Record consent honestly**: tick marketing consent only when the person agreed. It protects deliverability and keeps us compliant.
`,
  },
  {
    id: 'bp-pipeline',
    group: 'Best practices',
    title: 'Pipeline discipline',
    summary: 'Making the forecast something people can rely on.',
    body: `
- **Every open deal has a next step and a realistic close date.** Review **Overdue** deals weekly (Pipeline → Filters → Expected close → Overdue) and either update the date or close the deal.
- **Move stages when the customer moves**, not when you hope they will. The stage drives the weighted forecast.
- **Use products, not a typed amount**, so TCV and ARR are right and quotes can be generated.
- **Close lost deals with a reason**: it is the cheapest market research we have.
- **Open renewal opportunities early**: 120 days before the contract end, or as soon as *Renewals at risk* shows "no renewal deal".
- **Share team views** ("Closing this quarter", "Datadog deals") so everyone looks at the same numbers in pipeline reviews.
- **Log activities** after every meaningful interaction: the timeline is the account's memory.
`,
  },
  {
    id: 'bp-email',
    group: 'Best practices',
    title: 'Email and privacy best practices',
    summary: 'Deliverability, consent and GDPR for campaigns, forms and tracking.',
    body: `
## Deliverability

- **Authenticate the sending domain** (SPF, DKIM, DMARC) with your email provider before the first campaign.
- **Send campaigns through an email service's SMTP relay**, not your personal Microsoft 365 mailbox.
- **Warm up**: start with your most engaged contacts and small volumes; grow over a few weeks.
- **Always send a test** and check it on a phone. Keep subject lines honest and the HTML light.
- **Watch the report**: high failure or unsubscribe rates mean the list or the content needs attention.

## Consent and GDPR

- Newsletters go only to contacts with **marketing consent**; website newsletter forms use **double opt-in**.
- Every campaign carries an **unsubscribe** link and our **postal address**.
- Don't import bought lists, and don't tick "they agreed" for people who didn't.
- For **website tracking** of EU visitors, turn on **Wait for the visitor's consent** and connect it to the cookie banner.
- Collect only what you need: tracking stores no query strings and no IP addresses, and forgets visits after 13 months.
`,
  },
  {
    id: 'bp-security',
    group: 'Best practices',
    title: 'Security',
    summary: 'Protecting customer data and access.',
    body: `
- **Sign in with Microsoft** (single sign-on with your company account and its MFA) rather than a CRM password.
- **Least privilege:** sales for sellers, read-only for viewers and integrations, admin for very few.
- **Deactivate leavers** on their last day.
- **Keep secrets out of email and chat:** form secrets, the monitoring token and API keys belong in the server's \`.env\` or a password manager. Rotate a form secret if it was exposed.
- **Confidential data:** BMC price lists and MarketZone reports are internal. Export only what you need and delete exports when done.
`,
  },

  // ------------------------------------------------------------------ Troubleshooting
  {
    id: 'faq',
    group: 'Troubleshooting',
    title: 'Common questions and problems',
    summary: 'Quick answers when something does not work as expected.',
    body: `
**I can't sign in / "account does not exist".** Ask an administrator to invite you under Users, with the email you sign in with.

**"Request failed" or a red error.** The message says why; if it names HTTP 5xx, tell an administrator: [System status](/system) shows the cause.

**A test or campaign email fails.** [System status](/system) → Email shows the server's exact reason. For Microsoft 365, see [Setting up email](help:email-setup).

**A campaign is paused.** The mail server refused it; the campaign page shows why. Fix the cause, then resume: nothing is lost.

**A contact was not emailed.** The campaign report shows *skipped* with the reason: no address, unsubscribed, or no consent for a consent-only campaign.

**Duplicate contacts or accounts.** Contacts can't share an address. For a duplicate account, keep one, move the contacts and deals to it (edit their account), then delete the empty one.

**Import errors.** The review step lists each error with its row number. Fix those rows and import again: matched records are updated, not duplicated.

**Licences look wrong after a report.** Check the account's Licences tab: *ended · awaiting next report* is normal until the next quarter's report is loaded.

**Website tracking shows nothing.** The domain must be listed (step 2), the code must be on the page, and with *Wait for consent* on, nothing is recorded until the cookie banner gives consent. Use **Check website integration**.

**The page looks outdated after an update.** Refresh with Ctrl+F5.
`,
  },
]
