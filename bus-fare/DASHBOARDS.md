# Dashboards and server: what was built (Kim)

Work on branch **`kim`**, 13–16 Nov 2026. Covers the dashboards (Kim's part) and
the server changes they needed (PK's area, **for PK to review** before merging
into `main`). Hardware and firmware are in [`PROGRESS.md`](PROGRESS.md) and
[`WIRING.md`](WIRING.md); how to run the dashboards is in
[`dashboard/README.md`](dashboard/README.md); the live deployment on Railway in
[`DEPLOY.md`](DEPLOY.md).

**Live:** https://web-production-9ad597a4.up.railway.app (logins and secrets: see `DEPLOY.md`).

---

## Who uses what

Passengers are **employees of companies** that join the scheme. They tap their
card on the terminal in a bus or matatu; the fare is charged and everyone sees
it on their own dashboard.

| Who | Dashboard | Sees and does |
|---|---|---|
| **Bus crew** (operator) | Live, Trips, Account | **Their own vehicle only.** Each tap: passenger name, paid / already paid / declined, amount. Totals, today's trips, start a new trip, switch route |
| **SACCO admin** (one per SACCO) | Overview, Fleet, Account | **Their own SACCO only.** Corporate fares and riders today and this month, routes at the agreed fares, corporate clients riding; each bus live (terminal online, route, today's takings) and its reserved seats, which they can set |
| **Company admin** (one per company) | Overview, Employees, Account | **Their own company only.** Month's travel, unpaid bill (if the company pays), register employees, edit, deactivate, reset password, block or unblock a lost card, give a new card, statements |
| **Employee** | Wallet, Profile | **Their own card.** Balance, top-up with their payment method, history, details, payment method, password, **block their own lost card** |
| **Platform** (the team) | Django admin | Creates SACCOs it has agreements with, their routes and agreed fares, their vehicles and crew logins, companies and their admin's login; records company payments |

### Billing: chosen per company

- **Employees pay:** each fare comes off the employee's card balance. They top up
  with M-Pesa, Airtel Money or a bank card.
- **Company pays:** taps go on the company's bill and are settled later. The
  platform records each payment (settlement). An optional **credit limit**
  declines taps once the bill would pass it.

### Employee details

Name, staff number (unique within the company), phone (also their login, stored
as `+2547…`), department, card ID, payment method and account (mobile money
number, or the last 4 digits of a bank card).

---

## How it was built, step by step

### 1. Understanding the project
Read the firmware, the serial protocol, the Django server and the bridge.
Server tests (24) passed; bridge tests needed `pyserial` installed.

### 2. First design (13 Nov)
A phone-sized design canvas with four screens: Live, Cards, Card top-up, Trip.
Kim asked for a **smaller top section** on the Live screen: the dark header
became one line (route · fare, trip, Online pill) and the three totals one strip.

### 3. First React dashboard
Vite + React app in `bus-fare/dashboard/`, plus read-only server endpoints for
live taps and cards. Vite passes `/api` calls on to Django, so there is no CORS
set-up. Branch renamed to `kim`; commits are authored by Kim only.

### 4. Correction: the dashboard is for the bus crew
The first version was built like an admin console (card IDs, balances,
top-ups). Kim explained it is for **operators**, who should see only **name and
amount**, totals and trips. Reworked: card screens and top-ups removed; the
server stopped sending card IDs and balances to the crew; trip history with
totals added.

### 5. Full system (14 Nov)
Kim set the requirements: fares come off the employee's card, employees get
their own dashboard, each company has its own admin, the company-pays option,
and **several buses at once with each crew seeing only their vehicle**.

**Server**
- New tables: `Company`, `Vehicle`, `Profile` (login role), `Settlement`; new
  employee fields on `Passenger`; `Trip`, `Transaction` and `TerminalMessage` now
  belong to a vehicle. Migration `0003_companies_vehicles_logins`; all new
  fields are optional, so existing data stays valid.
- **Each vehicle runs its own trips.** Its bridge proves which bus it is with
  `Authorization: Terminal <token>`. Messages (new trip, fare) go to that vehicle
  only. A wrong or missing token is refused.
- **Logins with roles** (Django sessions): operator, company admin, employee.
  Each endpoint checks the role and only returns that person's own data.
- Tap rules, in order: unknown **or deactivated** card → already paid this trip →
  not enough balance (or company over its credit limit) → paid.
- Fares are the ones agreed with each SACCO (see section 7), entered by the
  platform in the Django admin; a change reaches every bus running that route.
- `seed_demo` creates demo companies, buses and logins.

**Bridge:** new `--token` option (or `FARE_TERMINAL_TOKEN`). The firmware is
unchanged.

**Dashboards:** one app with a login page; each role lands on its own screens.
First login with a temporary password asks for a new one.

### 6. Lost cards, offline mode, deployment (16 Nov)

Context: the system is for **corporates**: their employees get **priority boarding**
(no queueing at the stage), paid by card.

**Lost cards.** An employee blocks their own card from Profile ("Block my card"): it
is declined on every bus at once, and their login keeps working. Only the company
admin can unblock it or give a new card (the card may have been copied meanwhile);
a new card ID clears the block. Taps on a blocked card are recorded as **BLOCKED**
("LOST CARD" badge) without a fare and without showing the balance, so attempts are
visible to the employee and the company. The terminal shows "Card blocked /
Reported lost". Migration `0004_card_blocked`.

**Offline mode** (with Solomon's firmware). The terminal now downloads every active
card (`GET /api/terminal/cards/`) and keeps it in flash, so every employee works
offline, blocked cards included. Payments taken offline wait in a queue in flash and
are sent with `POST /api/terminal/sync/` as soon as the server answers, before
anything else. Each carries the terminal's own number, so a resend is never charged
twice; each is dated when the card was tapped; trips started offline are created on
the server. Before this, offline payments were never recorded and were wiped by the
next online tap. Migration `0005_offline_sync`.

**Deployment** on Railway with PostgreSQL ([`DEPLOY.md`](DEPLOY.md)). Settings now come
from environment variables; the server serves the built dashboard; `seed_demo`
takes its password and terminal tokens from secrets; `GET /api/health/`.

---

### 7. SACCOs, fares per route, SACCO dashboard (20 Nov)

The team decided: every SACCO has its own fare system, the fares are fixed by our
agreement with it (no peak or rain hikes), and the card is charged by the vehicle
and route it is tapped on. We only work with SACCOs we have agreements with.

- **New table `Sacco`** (name, NTSA licence). Each **route** and each **vehicle**
  belongs to a SACCO. Route names are unique within a SACCO, so two SACCOs can both
  run "Marimanti-Chuka", each at its own fare. Migration `0007_saccos`.
- **A vehicle runs only its own SACCO's routes.** The crew's route list shows only
  those; starting a trip on another SACCO's route is refused. A vehicle with no
  running trip carries on with its last route, or starts on its SACCO's first one.
- **Moving a vehicle to another SACCO** (Django admin) ends its running trip and
  starts one on the new SACCO's route; the terminal is told the new fare.
- **SACCO dashboard** (login role *SACCO admin*, created by the platform in the
  Django admin; demo login `saccoadmin`). **Overview:** corporate fares and riders
  this month and today, each route with its agreed fare and this month's trips,
  and the corporate clients riding (riders, trips, money). **Fleet:** each bus with
  its terminal online or offline, the route it is running, today's takings, and its
  reserved seats for corporate card holders, which the SACCO sets per bus (the
  crew sees the same counter). A SACCO admin never sees another SACCO's buses, and
  looking at the fleet never starts a trip.
- **Dashboards** show the SACCO: on the crew's header and Trips screen, and on each
  line of the employee's and the company's statements.
- `seed_demo` puts the demo routes and buses in **Demo Sacco**, and gives existing
  routes and vehicles without a SACCO to it (so Railway's data carries over).
- The firmware is unchanged: it reads the fare from the server as before.
- Fixed on the way: editing a route's fare in the admin saved only the fare, so a
  name change made at the same time was lost.

## API

| Who calls | Endpoint | Does |
|---|---|---|
| Bridge (token) | `POST /api/tap/` | Decide a tap → `RES` line for the Uno |
| | `GET /api/status/` | This vehicle's trip and fare |
| | `POST /api/terminal/poll/` | Waiting lines for this vehicle; marks it online |
| | `GET /api/terminal/cards/` | Every active card for offline mode (plain text) |
| | `POST /api/terminal/sync/` | Payments taken offline, trips started offline |
| Anyone (no login) | `GET /api/health/` | Health check (Railway) |
| Anyone | `GET /api/auth/me/` · `POST /api/auth/login/` · `POST /api/auth/logout/` · `POST /api/auth/password/` | Logins |
| Crew | `GET /api/operator/live/` · `GET /api/operator/trips/` · `POST /api/operator/trip/` · `GET /api/routes/` | Own vehicle |
| SACCO admin | `GET /api/sacco/` · `GET /api/sacco/vehicles/` · `POST /api/sacco/vehicles/<id>/reserved/` | Own SACCO |
| Company admin | `GET /api/company/` · `GET, POST /api/company/employees/` · `GET, PATCH /api/company/employees/<id>/` · `POST /api/company/employees/<id>/reset-password/` | Own company |
| Employee | `GET /api/me/` · `POST /api/me/topup/` · `PUT /api/me/payment-method/` · `POST /api/me/card/block/` | Own account |

Removed: the old open endpoints `/api/topup/`, `/api/fare/`, `/api/trip/`,
`/api/live/`, `/api/trips/` and `/api/passengers/`.

---

## Testing

- **Server:** 71 tests (16 Nov), passing on **both SQLite and PostgreSQL**. Since
  14 Nov: lost cards (10) and offline mode (16). The 14 Nov set (45): the `WIRING.md` tap sequence, terminal tokens, two buses
  at once, company pays and credit limit, crew sees only their own bus, logins
  (phone typed any way), registering employees and duplicates, deactivation,
  password reset, top-ups and payment methods, each role blocked from the
  others' pages.
- **Bridge:** 11 tests, including that every call carries the token.
- **End to end:** the real bridge against the real server with a simulated Uno
  on a virtual serial port: fare sent at start-up, PAID / REPEAT / LOW answered,
  company-paid card works, a wrong token gets nothing.
- **Browser:** every dashboard driven at phone size (390 × 844): crew, both
  company admins, registering an employee, that employee's first login,
  password change and top-up. No browser errors.

- **16 Nov on hardware:** a lost card blocked through the employee API was refused
  by the real ESP32 ("BLOCKED") and worked again after the admin unblocked it.
  Offline: payments taken with the server stopped reached the server when it came
  back, dated correctly, with matching balances. On Railway: taps from the ESP32 over
  the phone hotspot answered in a median 1.2 s.

### Bugs found and fixed
- **Every tap failed on PostgreSQL (16 Nov):** the tap locked the passenger row
  across the optional join to their company, which PostgreSQL refuses (SQLite
  ignores locks, so the tests never saw it). Found by running the production image
  against Postgres before deploying; now only the passenger row is locked.
- **Django tried to shrink every table's id (16 Nov):** the app did not say which id
  type to use. Set to match the existing migrations.
- **CSRF:** every save from a logged-in dashboard failed, because the dev proxy
  kept the browser's address as Origin. The proxy now sets Origin to the server
  (also fixes phones on the Wi-Fi).
- **Screen readers:** form hints were read as part of each field's name. Hints
  are now linked as descriptions.
- **Top-up form** kept the amount after a successful top-up, inviting a double
  payment. It now clears.
- **Live screen** highlighting of new taps did not work in development (React
  renders twice); fixed.
- **Slow tests:** real password hashing is slow on purpose; tests use a fast one.

---

## Decisions

- One React app for all roles (shared login, styles and code).
- Session logins for people; secret tokens for bus terminals.
- Top-ups are **simulated** until a payment provider (M-Pesa) is connected.
- Settlements are recorded by the platform, not by the company.
- Each SACCO has its own routes and agreed fares, constant at every hour. A card is
  charged the fare of the route the vehicle it taps on is running (20 Nov).
- The server uses Django 6.1 in `server/.venv` (the system Python had 5.1, which
  would have produced wrong migrations).

---

## For the team

| Who | What |
|---|---|
| **PK** | Review the server redesign on `kim` before merging. Each bus's bridge now needs `--token`. |
| **Solomon** | The ESP32 firmware now caches every card and queues offline payments (16 Nov). The Uno (`terminal_mvp`) still only knows its 4 built-in cards offline. |
| **Team** | Real fares; real companies, vehicles and logins instead of the demo ones. |

## Open items

| Item | Notes |
|---|---|
| PR from `kim` to `main` | After PK's review |
| Real M-Pesa top-ups | Replaces the simulated payment in `services.top_up` |
| Update the design canvas | Still shows the first, crew-only screens |
| Company statements to download | e.g. monthly CSV for finance |
| Mark offline payments on the dashboards | The server stores `Transaction.offline`; not shown yet |
| Priority boarding | Seat quota per departure, door check BOARD / QUEUE |
| Railway config before 1 Dec 2026 | `railway.json` is being retired (`DEPLOY.md`) |

## Commits on `kim`

| Commit | What |
|---|---|
| `76ba53a` | Server: read-only endpoints for the dashboard |
| `e172144` | First mobile-first React dashboard |
| `796326c` | Operator dashboard: names and amounts, totals, trips |
| `6f29ca6` | Server: companies, employees, vehicles and logins |
| `2373484` | Dashboards for crew, company admins and employees |
| `526e209` | Lost cards: employees block their own card; only the admin unblocks |
| `3a68175` | Offline mode: every card on the terminal, offline payments sent to the server |
