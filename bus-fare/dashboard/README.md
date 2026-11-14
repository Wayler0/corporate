# Fare dashboard

Mobile-first React dashboard for the bus fare terminal. Four screens:

| Screen | Shows / does | Refreshes |
|---|---|---|
| **Live** (`#/`) | Running trip, money collected, terminal online/offline, every tap as it happens | every 2 s |
| **Cards** (`#/cards`) | All cards and balances, which ones cannot pay the fare | every 5 s |
| **Card** (`#/cards/E5734107`) | Balance, top-up (with a preview of the terminal's LCD), history | every 5 s |
| **Trip** (`#/trip`) | Start a new trip, switch route, change the fare | every 5 s |

## Run it

The Django server must be running first (`bus-fare/server`):

```
cd bus-fare/server
python3 manage.py migrate
python3 manage.py seed_demo
python3 manage.py runserver
```

Then, in another terminal:

```
cd bus-fare/dashboard
npm install        # first time only
npm run dev
```

Open the address Vite prints (http://localhost:5173). To use it **on a phone**, connect
the phone to the same Wi-Fi and open the "Network" address Vite prints
(e.g. `http://192.168.1.20:5173`).

Vite passes every `/api/...` call on to Django at `http://127.0.0.1:8000`, so there is no
CORS set-up. If Django runs elsewhere: `FARE_SERVER=http://192.168.1.20:8000 npm run dev`.

## "Online" / "Offline"

The terminal counts as online while the laptop bridge (`bus-fare/bridge/bridge.py`)
has polled the server in the last 8 seconds, the same timeout the Uno uses. When
it is offline the Uno keeps charging from its own memory, and those taps never reach
the server, so the dashboard warns that balances may differ.

## Server endpoints it uses

`GET /api/live/`, `GET /api/passengers/`, `GET /api/passengers/<uid>/`, `GET /api/status/`,
`GET /api/routes/`, `POST /api/topup/`, `POST /api/trip/`, `POST /api/fare/`.

## Code

- `src/api.js`: every server call
- `src/usePoll.js`: refresh on a timer; keeps the last good data if the server blips
- `src/screens/`: one file per screen
- `src/styles.css`: colours and layout (design: https://claude.ai/artifact/KfHYPqxP74hM5yBqWXuTFr)
