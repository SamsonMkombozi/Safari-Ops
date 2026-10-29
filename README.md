# Safari-Ops

The operations console for safari and tour companies. One Django application provides:

- an **admin panel** (`/dashboard/`) for owners, admins and managers: quotations, bookings, payments, invoices, leads, commissions, operations, catalog, analytics and settings;
- a **partner agent portal** (`/agent/`) where agents book packages for their clients and track their own leads and earnings;
- a **client quotation page** (`/q/<token>/`) where clients view and accept a quote;
- a **REST API** (`/api/v1/`) for external websites and integrations.

Safari-Ops replaces the admin and agent panels of the legacy PHP app (`/var/www/html/safari-zangu`). The business rules (pricing, pipeline, commissions, payments) were ported from that app. Its data can be imported, including user passwords.

| | |
|---|---|
| Live demo | http://196.250.208.206:8600/ (also listed on the TechX site: http://196.250.208.206/products/safariops) |
| Demo logins | `demo.owner`, `demo.admin`, `demo.manager` (admin panel) · `agent.amina`, `agent.joseph`, `agent.grace` (agent portal). Password for all: `Safari@2026!` |
| Stack | Python 3.12 (3.10+ works), Django 5.2, Django REST Framework, SimpleJWT, MySQL 8, Gunicorn, WhiteNoise |
| Deployment guide | [DEPLOY.md](DEPLOY.md) |

---

## Contents

1. [Features](#features)
2. [Project structure](#project-structure)
3. [Running locally](#running-locally)
4. [Configuration](#configuration)
5. [Data: legacy import and demo data](#data-legacy-import-and-demo-data)
6. [Background jobs](#background-jobs)
7. [Tests](#tests)
8. [Deployment](#deployment)
9. [Changelog](#changelog)
10. [Known limitations and open items](#known-limitations-and-open-items)

---

## Features

### Admin panel (`/dashboard/`)

| Area | What it does |
|---|---|
| **Overview** | Sales, cash collected, outstanding balances, gross profit, open quotes, leads, commissions due, inbox, upcoming departures, pipeline |
| **Bookings** | List and filters, detail page, payment ledger, record payment, status changes (cancelling claws back commission), guide/driver/vehicle assignment, reset of the client's tracking password |
| **Quotations** | Itemised pricing from an itinerary (see [Pricing](#pricing)), markup, discount, internal flights, email to client, accept/decline, convert to booking |
| **Leads** | Pipeline stages; moving a lead to *booked* creates the agent's commission |
| **Requests & messages** | Custom safari requests (turn into a lead or a quotation) and contact messages (reply, turn into a lead) |
| **Invoices & payments** | Printable invoices, payments by method, refunds |
| **Commissions** | Pending → approved → paid; per-agent commission rates (admins only) |
| **Communications** | Email templates, email queue (process now, retry), booking reminders |
| **Catalog** | Packages (reprice from itinerary), itineraries, accommodations, activities, fleet, park fees, seasons, emergency contacts |
| **People & partners** | Team, suppliers (private PDF contracts), guides and drivers |
| **Analytics** | Sales & pipeline, profitability (admins only), customer experience (reviews/NPS), agent performance (admins only) |
| **Settings** | General business settings (deposit %, VAT, commission default, bank details, feature flags), currencies, users, activity log |

### Roles

| Role | Access |
|---|---|
| `owner`, `admin` | Everything, including settings, users, profitability and agent performance |
| `manager` | The admin panel without settings and margin pages; can change statuses / delete records only if enabled on their user |
| `agent` | The agent portal only; sees only their own leads, bookings, quotations and commissions (other agents' records return 404) |

### Agent portal (`/agent/`)

The dashboard shows commission paid, pending and approved, plus progress towards the monthly target. Agents can book a package directly (price preview first, then confirm), which creates the booking, the quotation, the lead and the commission. They can submit custom requests and see their own bookings, quotations and earnings.

### Client quotation page (`/q/<token>/`)

Quotation emails link here. The page is reached only through an unguessable 48-character token. It shows the itemised price, deposit, trip details and bank details, and has an **Accept quotation** button that notifies the office and moves the lead forward.

### Pricing

`apps/bookings/pricing.py` is a line-by-line port of the legacy `ItineraryQuoteBuilder`:

- **Accommodation:** two pricing models. Per-room, or per-person sharing, where adults pair into rooms and an odd adult pays the single supplement. Child rates apply in both.
- **Vehicles:** priced per vehicle-day. The daily rate, fuel and driver costs are listed separately when they're on file.
- **Park fees:** adult and child fees, resident rates for East African Community (EAC) nationals, and vehicle entry fees.
- **Activities, meals and other costs:** paid activities and meals are priced, per head or per group; optional activities are never priced; plus other per-day costs.
- **Service charge and totals:** a service charge per adult and child, then markup → discount → VAT → deposit.

The VAT rate and deposit percentage come from **Settings → General**.

### Themes

The theme picker is in the top bar, the agent navigation and the login page. Options are **Match my device**, **Light**, **Dark** (true black) and **Black & white** (monochrome). The choice is saved to the user's profile and follows them across browsers and devices.

### REST API (`/api/v1/`)

Authentication is by JWT (`/api/v1/auth/token/`), session, or an `X-API-Key` header for external sites (keys are managed in Django admin at `/django-admin/`). Endpoints:

`packages`, `itineraries`, `accommodations`, `vehicles`, `park-fees`, `activities`, `seasonal-rates`, `team`, `contact-messages`, `custom-safari-requests`, `bookings` (plus `POST bookings/<id>/record_payment/`), `payments` (read-only), `booking-reminders`, `quotations`, `leads` (plus `set_stage`), `commissions` (plus `approve` / `mark_paid`), `customers`, `agent-targets`, `email-templates`.

There are also two public endpoints: `POST bookings/track/` (booking reference plus tracking password) and `GET quotations/view/<token>/`.

---

## Project structure

```
apps/
  accounts/      custom User (roles, commission rate, permissions, theme), login with lockout, profile, password reset
  agent_portal/  partner agent portal views and forms
  api/           REST router, API-key authentication, permissions, error format
  bookings/      Quotation, Booking, Payment, BookingReminder; pricing.py; services.py (all money write paths); public quote page
  content/       team, contact messages, custom requests, email templates, reviews, email queue; mailer.py
  core/          settings store, activity log, API keys, currencies, legacy import (legacy.py), template tags (ui.py)
  crm/           Customer, Lead, Commission, AgentTarget; pipeline.py (stage changes and commission rules)
  dashboard/     admin panel views, forms, navigation, generic CRUD engine (crud.py), analytics
  operations/    suppliers, guides and drivers, booking assignments, incidents
  packages/      accommodations, vehicles, park fees, activities, seasons, itineraries, packages
config/settings/ base.py · development.py · production.py · test.py
templates/       base.html, dashboard/, agent_portal/, accounts/, public/, partials/, error pages
static/          css/ui.css (Kilima design system), js/admin.js, js/admin-layout.js
deploy/          gunicorn.conf.py, nginx.conf, safariops.service, crontab, docker/ (Dockerfile, entrypoint.sh)
tests/           automated test suite
docker-compose.server.yml   Docker deployment used on the demo server
```

All writes that touch money or the pipeline go through `apps/bookings/services.py` and `apps/crm/pipeline.py`, never straight to model fields. That includes recording payments, status changes, converting quotes, agent bookings, and stage changes and commissions. This way the side effects (payment ledger, commission creation and clawback, reminders, emails) happen the same way from every screen and from the API.

---

## Running locally

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set SECRET_KEY, DEBUG=True and the DB_* values; LEGACY_DB_* only if importing
python manage.py migrate
python manage.py import_legacy_data      # or sync_legacy_data, see below (needs LEGACY_DB_*)
python manage.py seed_demo_data          # optional demo data
python manage.py runserver 0.0.0.0:8010  # port 8000 is taken on this dev machine
```

Then open http://localhost:8010/accounts/login/. `manage.py` defaults to `config.settings.development`, which uses the console email backend.

---

## Configuration

All configuration comes from environment variables or `.env`; see [`.env.example`](.env.example) for the full list. The important ones:

| Variable | Purpose |
|---|---|
| `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS` | Standard Django settings; production refuses to start without `ALLOWED_HOSTS` |
| `SITE_URL` | Absolute base URL for links in emails sent outside a request (quotes, reminders) |
| `DB_*`, `LEGACY_DB_*` | The application database; the legacy PHP database is used only by the import commands |
| `CACHE_URL` | Shared cache for login lockouts, throttles and settings. Use `dbcache://django_cache` (run `createcachetable`) or Redis when running several workers |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL`, `ADMINS` | Outgoing mail; `ADMINS` receive reports of server errors |
| `HTTPS_ENABLED` | Default `True` (HTTPS redirect, HSTS, Secure cookies). Set `False` **only** on plain-HTTP `IP:port` demo hosts |
| `SESSION_COOKIE_NAME`, `CSRF_COOKIE_NAME` | Default `safariops_sessionid` / `safariops_csrftoken`. Keep them unique on any host that runs several apps |
| `CSRF_TRUSTED_ORIGINS`, `CORS_ALLOWED_ORIGINS` | Allowed origins for forms and for the API |

Business settings live in the database, not in `.env`. Edit them under **Settings → General**: app name, deposit %, balance days, VAT, service charge, default commission, quotation validity, maximum party size, session timeout, agent direct booking on/off, automatic payment emails, maintenance mode, contact and bank details.

---

## Data: legacy import and demo data

| Command | Use it when |
|---|---|
| `import_legacy_data [--dry-run]` | Loading an **empty** database from the legacy PHP database: users, catalog, customers, leads, commissions, custom requests, quotations, bookings (with an opening entry in the payment ledger), reminders, team, messages, email templates, settings, currencies, suppliers, staff, reviews, incidents |
| `sync_legacy_data [--dry-run] [--keep-settings] [--no-passwords]` | Topping up an **already-imported** database; safe to re-run. Brings in settings, currencies, suppliers, staff, reviews, incidents, and each user's role, commission rate, permissions and password |
| `seed_demo_data [--reset \| --purge] [--allow-production]` | Demo users, leads, quotes, bookings, payments and commissions, all created through the real services. Demo rows are tagged so `--purge` removes only them. It never overwrites business settings, and refuses to run when `DEBUG=False` unless you pass `--allow-production` |

**Passwords:** legacy users keep their PHP-app passwords. Their bcrypt `$2y$` hashes are migrated and checked by Django's bcrypt hasher, and each one is upgraded to PBKDF2 on that user's first successful login. Anyone without a migrated password uses **Forgot your password?** on the login page.

---

## Background jobs

| Command | Schedule | Job |
|---|---|---|
| `process_email_queue` | every 2 min | Sends queued emails (all outgoing mail is queued, never sent while handling a request) |
| `process_reminders` | every 15 min | Queues due booking reminders and expires stale quotations |
| `clearsessions`, `flushexpiredtokens` | nightly | Housekeeping |

On a normal server, install [`deploy/crontab`](deploy/crontab). The Docker deployment runs these jobs in the `scheduler` container instead.

---

## Tests

```bash
python manage.py test tests --settings=config.settings.test
```

The tests run on in-memory SQLite, so no MySQL is needed. The 36 tests cover:

- pricing: room models, supplements, child and resident rates, totals;
- the money flows: quote → booking → commission, payments ledger, PayPal replay, cancellation clawback, agent direct booking, settings-driven deposit;
- access control: every staff page renders, admin-only pages, agent isolation, login lockout, POST-only logout;
- themes, the public quote page, legacy password verification, password reset, maintenance mode and the party-size cap;
- regressions: bad `Host` header → 400, JavaScript files free of template leftovers, and login surviving another app's cookies on the same host.

---

## Deployment

- **Any Linux server (nginx + gunicorn + systemd):** follow [DEPLOY.md](DEPLOY.md), including its go-live checklist.
- **Docker (used on the demo server):**

  ```bash
  cd ~/safariops
  docker compose -p safariops -f docker-compose.server.yml --env-file .env.server up -d
  ```

  The stack has four containers:
  - `web`: runs migrations, creates the cache table, collects static files, then starts gunicorn on host port **8600**;
  - `scheduler`: runs the background jobs;
  - `db`: MySQL 8.4;
  - `mailpit`: catches outgoing email, with its web UI on `127.0.0.1:58625`.

  Secrets live only in `~/safariops/.env.server`, which is generated on the server and never committed.

**Auto-deploy from GitHub (demo server):** push to `main` and the server deploys it within about 2 minutes.

- `~/ops/bin/deploy` checks GitHub using a read-only deploy key and fast-forwards the checkout.
- It then runs [`deploy/server-update.sh`](deploy/server-update.sh). This rebuilds the image fully only when `requirements.txt`, the Dockerfile or the entrypoint change; otherwise it layers the new code onto `safariops-web:base` in seconds.
- It health-checks the login page and rolls back automatically if that check fails.
- Results appear in the TechX admin under Safari-Ops → **Deploys**.

Server-side setup and safety rules are in `~/ops/README.md` on the server.

**Demo server notes (196.250.208.206):**

- **Build locally:** the server's Debian package mirror is very slow. Build the image locally and stream it over:
  `docker save safariops-web | gzip -1 | ssh <server> 'gunzip | docker load'`, then run `up -d --no-build`.
- **Code-only updates:** rsync the source, then build a thin layer on the existing image (`FROM safariops-web:latest` + `COPY config/ apps/ templates/`) and recreate `web` and `scheduler`.
- **Reseed demo data:**
  `docker compose -p safariops -f docker-compose.server.yml --env-file .env.server exec web python manage.py seed_demo_data --reset --allow-production`

---

## Changelog

What changed in turning the initial scaffold into a production-ready MVP, grouped by phase.

### 1. Admin panel and agent portal ported from the PHP system

- **Business logic ported:** the legacy pricing engine, `PipelineSync` (lead stages and commissions), payment recording, status changes with commission clawback, quote → booking conversion, agent direct booking and the reminder scheduler. All live in `services.py` / `pipeline.py`.
- **New models:**
  - `Payment`, a ledger alongside `Booking.amount_paid`;
  - `Supplier`, `StaffMember`, `BookingAssignment` and `Incident` (the new `operations` app);
  - `Review` and `EmailQueue`;
  - `SiteSetting` and `CurrencyRate`;
  - user commission rate, monthly target, permission flags and theme;
  - park-fee vehicle fee, booking country/rooms/supplier cost, quotation markup/lead/custom-request links.
- **Admin panel:** about 45 pages with full actions (see [Features](#features)). Catalog, people and config pages use a generic CRUD engine (`dashboard/crud.py`).
- **Agent portal:** dashboard, leads, direct booking, custom requests, bookings, quotations, commissions.
- **Operations:** management commands for the email queue and reminders; a demo-data seeder that uses the real services.

### 2. Bugs fixed in the original scaffold

- `STATICFILES_STORAGE` was silently ignored (removed in Django 5.1); replaced with `STORAGES`.
- JWT refresh-token blacklisting was configured but its app wasn't installed, so rotated tokens were never revoked.
- Creating a booking or quotation through the API always failed (the reference was never generated).
- Agents could create their own commission records through the API; creating, approving and paying are now staff-only.
- The API's lead-stage change had a duplicate copy of the commission logic and was open to agents; it now uses the shared pipeline and is staff-only.
- Logout worked over GET, so a link on any site could sign users out; it is now POST-only.
- Analytics crashed on MySQL without timezone tables; months are now grouped in Python.
- Quotation totals were held as floats, which broke the commission calculation.

### 3. New visual design ("Kilima")

- `static/css/ui.css` replaced the copied PHP stylesheet. It uses a night-emerald sidebar, sunset-coral accents and a warm sand background, with rounded cards, tinted stat cards and pill badges.
- Redesigned page layouts: the admin sidebar and top bar, an agent portal with a hero header and floating pill navigation, a split-screen login with a savanna illustration, and a welcome banner on the overview.
- Mobile layout: the sidebar slides in, and the grids reflow.

### 4. Rebrand, themes and production hardening

- **Rebrand:** the app is now **Safari-Ops**, set through the `app_name` setting and used in emails too. The logo image and brand mark were removed; the favicon is a plain letter tile.
- **Themes:** the four-mode theme system described above, saved to the user's profile on the server. It previously lived only in one browser and conflicted with the profile setting.
- **Legacy data alignment:**
  - added the `luxury` accommodation level (27 lodges and 2 packages failed validation without it), quotation status `negotiating` and reminder type `win_back`;
  - added the remaining legacy columns: airport pickup, trip extension, rooms, first-response times, vehicle maintenance and insurance costs.
- **Legacy import:**
  - the importer now carries user commission rates, permissions, themes and passwords; the commission → lead link; quotation ownership and pipeline links; and existing client quote links;
  - added payment-ledger opening entries, plus import of settings, currencies, suppliers, staff, reviews and incidents;
  - added the new idempotent `sync_legacy_data` command;
  - this restored the real settings (40% deposit, 20-day balance window, bank account) that the demo seeder had overwritten.
- **Settings now enforced:** session timeout, maximum party size and maintenance mode were editable but had no effect before.
- **New pages and flows:** the client quotation page with an accept button (quote emails used to link to raw JSON), email-based password reset, and styled 400/403/404/500 and CSRF error pages.
- **Security:** supplier contracts moved out of the public media folder; they are PDF-only with a size limit and download through a staff-only view.
- **Production configuration:**
  - bcrypt hasher for migrated passwords, a configurable shared cache, `CSRF_TRUSTED_ORIGINS`, error emails to `ADMINS`, and SMTP over SSL;
  - `check --deploy` passes with no issues;
  - verified under gunicorn: HTTP redirects to HTTPS, HSTS is set, and the cookies are Secure.
- **Critical JavaScript fix:** `admin-layout.js` contained leftover PHP template lines, so none of its code ever ran. That broke the mobile menu, the collapsible navigation, the notification bell, the confirmation dialogs (destructive forms submitted with no confirmation) and the theme picker. All are now verified in a real browser, and a regression test guards against it.
- **Smaller fixes:**
  - a forged `Host` header caused a 500 error (and an error email) instead of a 400;
  - the incidents list showed status where severity should be;
  - analytics month boundaries shifted by the timezone offset;
  - two lists paginated without a fixed order.
- **Deployment kit:** `.env.example`, `DEPLOY.md`, gunicorn, nginx (which keeps `/media/private/` unreachable), a systemd unit, a crontab and nightly backups; also an automated test suite.

### 5. Deployment to the demo server

- Docker packaging: `deploy/docker/Dockerfile`, `entrypoint.sh` (the scheduler waits for migrations) and `docker-compose.server.yml`. `HTTPS_ENABLED` can be switched off for plain-HTTP demo hosts; `cryptography` was added (PyMySQL needs it for MySQL 8 logins) and the unused `mysql-connector-python` removed.
- Deployed to `~/safariops` on port 8600 with the real catalogue plus demo data. Real staff accounts and bank details were deliberately **not** copied to the public plain-HTTP server.
- Added to the TechX main site:
  - the public product listing, through TechX's own `product_save()`;
  - 3 public and 2 admin-only demo logins, with encrypted passwords, through `credential_save()`;
  - the admin server inventory and the catalogue seed file.

  The live TechX storage and data files were backed up first.
- **Login fix (403 "Session expired"):** browsers share cookies across every port of an IP, so other apps' `csrftoken` / `sessionid` cookies blocked Safari-Ops logins. Safari-Ops now uses app-specific cookie names, with a regression test.

---

## Known limitations and open items

- **The demo server runs plain HTTP** (like the other demos there). Real use needs a domain with HTTPS: then set `HTTPS_ENABLED=True` and load real data with `sync_legacy_data`.
- **Demo-server firewall:** the UFW rule for port 8600 was not added (it needs sudo). The site is reachable because Docker-published ports bypass UFW; for consistency with the other apps, run `sudo ufw allow 8600/tcp comment "Safari-Ops web"`.
- **Test accounts from the PHP app are active with admin or owner rights:** `qa_manualtest`, `qa_a11y_test` and `qa_sec_agent`. Deactivate them before go-live.
- **Email:** on the demo server, outgoing email goes to Mailpit and is not delivered. Set real `EMAIL_*` values for live use; password reset depends on them.
- **Not ported from the PHP admin:** Poster Maker, Image Gallery, Operations Calendar and Room Availability.
- **Simpler than the PHP version:**
  - itinerary days are edited as JSON, not with the visual editor;
  - invoices print to PDF from the browser instead of being generated as files;
  - PayPal payments are recorded manually, without checking them against PayPal.
- **Import not tested on real transactions:** the legacy database has no bookings, payments or leads, so those parts of `import_legacy_data` have never run against real data.
- **Unchanged on purpose:** booking references keep the legacy `SZV` prefix so existing tracking keeps working, and the bank account name still reads "Safari Zangu Ventures Ltd" because it's a legal bank detail.
