# Tap-to-pay bus fares

A contactless fare system for Kenyan buses and corporate shuttles, inspired by
German tap-to-pay ticketing. An employee taps a card at the door; the terminal
in the vehicle says **PAID**, **ALREADY PAID** or **DECLINED** in about a second,
and the fare comes off the card (or is billed to their company).

**Live demo:** https://9two5.nextup.co.ke

```
 card ──tap──► ESP32 terminal ──HTTPS──► Django server ──► PostgreSQL
               RC522 reader               │  (KENET)  
               16×2 LCD, LED, piezo       └─► dashboards: crew, company admin, employee
               offline: decides by itself,
               syncs payments later
```

## What it does

- **Tap to pay:** a fixed fare per route, each card pays once per trip.
- **Two kinds of billing:** employees pay from their own card balance, or the
  company pays and settles the bill later (with an optional credit limit).
- **Keeps working offline:** the terminal keeps a copy of every card and
  decides taps by itself when the Wi-Fi or server is down. It sends those
  payments to the server when it is back. Sending them twice is harmless.
- **Lost cards:** the employee blocks the card from their phone. Every terminal
  refuses it straight away; only the company admin can unblock or replace it.
- **Dashboards (one web app):**
  - **Crew:** live taps, money collected, start a trip or switch route.
  - **Company admin:** employees, cards, statements, the unpaid bill.
  - **Employee:** balance, history, top-up, block a lost card.

## Repository

Everything lives in [`bus-fare/`](bus-fare):

| Folder | What |
|---|---|
| `terminal_esp32/` | **The terminal firmware** (ESP32: Wi-Fi, RC522, I2C LCD, RGB LED, piezo, offline mode) |
| `server/` | Django + Django REST Framework fare server (taps, trips, cards, companies, logins) |
| `dashboard/` | React + Vite dashboards, served by the server in production |
| `tools/` | `set_wifi.py` (Wi-Fi, server and token over the USB cable), `fake_server.py` |
| `terminal_mvp/`, `bridge/` | Older Arduino Uno version (USB link via a laptop bridge), kept as a backup |
| `stage1_…` – `stage5_…`, `check_…` | Build steps and hardware checks from the prototype |

## Run it on a laptop

```bash
# Server (Python 3.13)
cd bus-fare/server
python -m venv ../.venv && ../.venv/bin/pip install -r requirements.txt
../.venv/bin/python manage.py migrate
../.venv/bin/python manage.py seed_demo        # demo routes, cards, buses and logins
../.venv/bin/python manage.py runserver 0.0.0.0:8000

# Dashboards (another terminal)
cd bus-fare/dashboard
npm install && npm run dev                     # http://localhost:5173

# Tests
cd bus-fare/server && ../.venv/bin/python manage.py test fares
```

`seed_demo` prints the demo logins (crew, company admin, employees). To flash the
terminal, follow [`WIRING.md`](bus-fare/WIRING.md). Set its Wi-Fi, server and
token over USB with `tools/set_wifi.py`.

## Documentation

| Doc | About |
|---|---|
| [`PROGRESS.md`](bus-fare/PROGRESS.md) | What is built and tested, and what is next |
| [`WIRING.md`](bus-fare/WIRING.md) | Parts, wiring, flashing and hardware tests (Uno and ESP32) |
| [`DASHBOARDS.md`](bus-fare/DASHBOARDS.md) | Server data model, API, roles and dashboards |
| [`DEPLOY.md`](bus-fare/DEPLOY.md) | Deployment (KENET now, Railway before) and its settings |

## Known limits (prototype)

This is a competition prototype, not a payment system yet.

- **Cards can be copied.** The terminal trusts the card's ID number, which any
  NFC phone can read. Real use needs cards with built-in encryption (e.g. MIFARE
  DESFire EV2/EV3) and a reader that supports them.
- **Top-up is simulated:** no M-Pesa yet. It is switched off in production unless
  `DEMO_TOPUP=1` is set.
- **Offline risks:** every terminal receives the full card list. A card can ride
  several buses offline before the payments sync (the fare it can't cover is lost).
- **Trips end only when the crew starts a new one:** there is no automatic end yet.
- **The terminal doesn't check the server's HTTPS certificate yet** (`setInsecure`).
- **Hardware is a prototype:** breadboard wiring and no enclosure. It still needs
  a 12/24 V vehicle power supply.

## Team

- **Hardware and terminal firmware:** Solomon
- **Fare server:** PK
- **Dashboards and deployment:** Kim
