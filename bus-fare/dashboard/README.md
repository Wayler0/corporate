# Fare dashboards

One mobile-first React app. Everyone logs in on the same page and lands on
their own dashboard:

| Who | Logs in with | Sees and does |
|---|---|---|
| **Bus crew** (operator) | username | **Their vehicle only.** Live taps (passenger name and amount: paid / already paid / declined), totals, trips today, start a new trip or switch route |
| **Company admin** | username | **Their company only.** This month's travel, unpaid bill (if the company pays), employees: register (name, staff number, phone, department, card, payment method), edit, deactivate, reset password, statements |
| **Employee** | phone number | **Their own card.** Balance, top-up with their payment method, history, profile, payment method, password |

The platform itself (you) works in the Django admin (http://127.0.0.1:8000/admin/):
it creates companies and their admin's login, vehicles and the crew's logins,
sets routes and fares, and records company settlements.

### Billing: two options per company

- **Employees pay:** each fare comes off the employee's card balance. They top up
  with M-Pesa, Airtel Money or a bank card. *Top-ups are simulated: no payment
  provider is connected yet, so no real money moves.*
- **Company pays:** taps are charged to the company. The admin sees the unpaid
  bill; the platform records payments as settlements. With a credit limit set,
  taps are declined once the bill would pass it.

## Run it

Live on Railway: see [`../DEPLOY.md`](../DEPLOY.md). On the laptop:

```
cd bus-fare/server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt   # first time only
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_demo          # demo companies, buses and logins
.venv/bin/python manage.py runserver
```

In another terminal:

```
cd bus-fare/dashboard
npm install        # first time only
npm run dev
```

Open http://localhost:5173. **On a phone:** same Wi-Fi, open the "Network" address
Vite prints (e.g. `http://192.168.1.20:5173`).

**Demo logins** (password `demo-pass-2026`, demo only):

| Username | Is |
|---|---|
| `crew1`, `crew2` | crew of KDA 001A / KDB 002B |
| `staffadmin` | admin of Demo Staff Ltd (employees pay) |
| `postpaidadmin` | admin of Demo Postpaid Ltd (company pays, limit KSh 5,000) |
| `0700000001` … `0700000004` | employees: White card, Blue fob, low funds, Kim |

**Each bus's laptop** runs the bridge with that vehicle's token
(Django admin → Vehicles):

```
python3 bus-fare/bridge/bridge.py --token demo-terminal-bus-1
```

Vite passes every `/api/...` call on to Django at `http://127.0.0.1:8000`
(another machine: `FARE_SERVER=http://192.168.1.20:8000 npm run dev`).

## Good to know

- **Online / Offline:** a vehicle is online while its bridge has polled in the last
  8 seconds. Offline, the Uno charges from its own memory, which only knows the 4
  built-in test cards; registered employees are declined until the link is back,
  and offline taps never reach the server.
- **Company pays:** the terminal's LCD still shows the card's own balance after
  "PAID" (the firmware has no other wording yet).
- **New employees** get a temporary password, shown once to the admin; they must
  choose their own at first login.

## Code

- `src/api.js`: every server call · `src/auth.jsx`: who is logged in
- `src/App.jsx`: picks the dashboard for the role
- `src/screens/operator`, `company`, `employee`: one folder per dashboard
- `src/usePoll.js`: refresh on a timer; keeps the last good data if the server blips
- `src/styles.css`: colours and layout
