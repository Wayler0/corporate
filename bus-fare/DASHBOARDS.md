# Dashboards and server: what was built (Kim)

Work on branch **`kim`**, 13–14 Nov 2026. Covers the dashboards (Kim's part) and
the server changes they needed (PK's area, **for PK to review** before merging
into `main`). Hardware and firmware are in [`PROGRESS.md`](PROGRESS.md) and
[`WIRING.md`](WIRING.md); how to run the dashboards is in
[`dashboard/README.md`](dashboard/README.md).

---

## Who uses what

Passengers are **employees of companies** that join the scheme. They tap their
card on the terminal in a bus or matatu; the fare is charged and everyone sees
it on their own dashboard.

| Who | Dashboard | Sees and does |
|---|---|---|
| **Bus crew** (operator) | Live, Trips, Account | **Their own vehicle only.** Each tap: passenger name, paid / already paid / declined, amount. Totals, today's trips, start a new trip, switch route |
| **Company admin** (one per company) | Overview, Employees, Account | **Their own company only.** Month's travel, unpaid bill (if the company pays), register employees, edit, deactivate, reset password, statements |
| **Employee** | Wallet, Profile | **Their own card.** Balance, top-up with their payment method, history, details, payment method, password |
| **Platform** (the team) | Django admin | Creates companies and their admin's login, vehicles and crew logins, routes and fares; records company payments |

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
- Fares are set only by the platform in the Django admin; a change reaches
  every bus running that route.
- `seed_demo` creates demo companies, buses and logins.

**Bridge:** new `--token` option (or `FARE_TERMINAL_TOKEN`). The firmware is
unchanged.

**Dashboards:** one app with a login page; each role lands on its own screens.
First login with a temporary password asks for a new one.

---

## API

| Who calls | Endpoint | Does |
|---|---|---|
| Bridge (token) | `POST /api/tap/` | Decide a tap → `RES` line for the Uno |
| | `GET /api/status/` | This vehicle's trip and fare |
| | `POST /api/terminal/poll/` | Waiting lines for this vehicle; marks it online |
| Anyone | `GET /api/auth/me/` · `POST /api/auth/login/` · `POST /api/auth/logout/` · `POST /api/auth/password/` | Logins |
| Crew | `GET /api/operator/live/` · `GET /api/operator/trips/` · `POST /api/operator/trip/` · `GET /api/routes/` | Own vehicle |
| Company admin | `GET /api/company/` · `GET, POST /api/company/employees/` · `GET, PATCH /api/company/employees/<id>/` · `POST /api/company/employees/<id>/reset-password/` | Own company |
| Employee | `GET /api/me/` · `POST /api/me/topup/` · `PUT /api/me/payment-method/` | Own account |

Removed: the old open endpoints `/api/topup/`, `/api/fare/`, `/api/trip/`,
`/api/live/`, `/api/trips/` and `/api/passengers/`.

---

## Testing

- **Server:** 45 tests: the `WIRING.md` tap sequence, terminal tokens, two buses
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

### Bugs found and fixed
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
- Fares belong to the platform, because several buses share a route.
- The server uses Django 6.1 in `server/.venv` (the system Python had 5.1, which
  would have produced wrong migrations).

---

## For the team

| Who | What |
|---|---|
| **PK** | Review the server redesign on `kim` before merging. Each bus's bridge now needs `--token`. |
| **Solomon** | No firmware change needed. Offline, the Uno only knows its 4 built-in test cards, so registered employees are declined until the link is back. For company-paid cards the LCD shows "PAID" then the card's own balance. |
| **Team** | Real fares; real companies, vehicles and logins instead of the demo ones. |

## Open items

| Item | Notes |
|---|---|
| PR from `kim` to `main` | After PK's review |
| Real M-Pesa top-ups | Replaces the simulated payment in `services.top_up` |
| Update the design canvas | Still shows the first, crew-only screens |
| Offline cards on the Uno | Firmware could cache registered cards (Solomon) |
| Company statements to download | e.g. monthly CSV for finance |
| Deployment | Real server, HTTPS, `DEBUG = False`, secret key |

## Commits on `kim`

| Commit | What |
|---|---|
| `76ba53a` | Server: read-only endpoints for the dashboard |
| `e172144` | First mobile-first React dashboard |
| `796326c` | Operator dashboard: names and amounts, totals, trips |
| `6f29ca6` | Server: companies, employees, vehicles and logins |
| `2373484` | Dashboards for crew, company admins and employees |
