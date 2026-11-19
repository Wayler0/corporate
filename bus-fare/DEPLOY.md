# Deploying the fare system (Railway)

The server and the dashboards run as **one service** on [Railway](https://railway.com),
with a **PostgreSQL** database next to it. The ESP32 terminal talks to it over
HTTPS from any Wi-Fi with internet.

| | |
|---|---|
| Live address | **https://web-production-9ad597a4.up.railway.app** |
| Dashboards | the address above (crew, company admins, employees) |
| Platform admin | `/admin/` (companies, vehicles, routes and fares, settlements) |
| Health check | `/api/health/` → `{"ok": true}` |
| Railway project | `bus-fare` (workspace "Kimathi Emmanuel's Projects"), region Amsterdam |
| Services | `web` (this repo's `bus-fare/Dockerfile`) and `Postgres` |

Deployed 16 Nov 2026 from branch `kim`.

---

## How it fits together

```
 ESP32 terminal ──HTTPS──┐
                         ▼
 phone / laptop ──HTTPS──► Railway edge ──► web: gunicorn + Django ──► Postgres
                                             ├─ /api/...    the fare API
                                             ├─ /admin/     Django admin
                                             └─ /           built React dashboard (WhiteNoise)
```

- **One image** (`Dockerfile`): stage 1 builds the dashboard with Node; stage 2 is
  Python 3.13 with the Django server, which serves the built dashboard at `/`.
  The dashboard calls `/api/...` on the same address, so no CORS set-up is needed.
- **Start** (`server/start.sh`): apply migrations → load demo data if
  `SEED_DEMO=1` → create the platform admin if it does not exist → start gunicorn.
- **Settings** come from environment variables (`server/config/settings.py`). With
  none set it is the laptop set-up: debug on, SQLite.

## Files

| File | Does |
|---|---|
| `Dockerfile` | Builds the image (dashboard + server) |
| `.dockerignore` | Only `server/` and `dashboard/` go into the image |
| `.railwayignore` | What `railway up` does not upload (secrets, `.venv`, `node_modules`, databases) |
| `railway.json` | Railway: build with the Dockerfile, health check `/api/health/`, restart on failure |
| `server/start.sh` | Start command (migrate, seed, admin, gunicorn) |
| `server/requirements.txt` | Adds `gunicorn`, `whitenoise`, `psycopg`, `dj-database-url` |
| `.railway-secrets.env` | **Not in git.** The secrets below, on the laptop that deployed |

## Variables (Railway → bus-fare → web → Variables)

| Variable | Value | Why |
|---|---|---|
| `DJANGO_DEBUG` | `0` | Production mode. The server refuses to start without a secret key |
| `DJANGO_SECRET_KEY` | long random string | Signs logins and sessions |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Railway fills in the database address |
| `SEED_DEMO` | `1` | Load the demo routes, companies, cards, buses and logins (only adds what is missing) |
| `DEMO_PASSWORD` | random | Password of every demo login (`crew1`, `staffadmin`, `0700000001`, ...) |
| `DEMO_TERMINAL_TOKEN_BUS1` / `_BUS2` | random | Terminal tokens of KDA 001A / KDB 002B; goes in the ESP32's `secrets.h` |
| `DJANGO_SUPERUSER_USERNAME` / `_PASSWORD` | `platform` / random | Login for `/admin/` |
| `ALLOWED_HOSTS` | optional | Extra addresses, e.g. a custom domain |
| `DEMO_TOPUP` | unset (or `1` for a demo) | Top-up adds money with no payment provider, so in production it is **off** unless this is `1`. Turn it off again after a demo |
| `LOGIN_RATE` | optional, default `10/min` | Login attempts allowed per address |

Railway sets `PORT` and `RAILWAY_PUBLIC_DOMAIN` itself; the server adds that
domain to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`.

> ⚠️ **Never deploy the demo data without these secrets.** `seed_demo`'s defaults
> (`demo-pass-2026`, `demo-terminal-bus-1`) are published in this repo: anyone could
> log in as a company admin or record taps. The demo secrets only apply when the
> rows are first created; to change one later, change it in `/admin/` (passwords)
> or on the vehicle (terminal token).

To see the values: Railway dashboard → `web` → Variables, or `railway variables
--service web` in `bus-fare/`, or `.railway-secrets.env` on the laptop that deployed.

## The ESP32 terminal

In `terminal_esp32/secrets.h` (never committed):

```c
#define SERVER_URL "https://web-production-9ad597a4.up.railway.app"
#define TERMINAL_TOKEN "<DEMO_TERMINAL_TOKEN_BUS1>"
```

Any Wi-Fi with internet works (phone hotspot included). With an `https://` address
the firmware waits longer for answers (6 s for a tap, 20 s before calling the server
lost) and keeps **one encrypted connection open** for every tap and poll. Measured
16 Nov from the Redmi hotspot: a tap answered in **0.6–1.5 s** (median 1.2 s);
without reusing the connection it was 4–5 s. The certificate is not checked
(`setInsecure`): the link is encrypted but a determined attacker on the same
network could impersonate the server. Fine for a demo; pin the certificate
before real money.

Offline mode works the same as on the laptop (see `WIRING.md`, "Offline mode").

---

## First-time set-up (what was done)

From `bus-fare/`, with the Railway CLI logged in (`railway login`):

```
railway init --name bus-fare                    # new project, links this folder
railway add --database postgres                 # the database
railway add --service web --variables "DJANGO_DEBUG=0" --variables 'DATABASE_URL=${{Postgres.DATABASE_URL}}' \
  --variables "DJANGO_SECRET_KEY=..." --variables "SEED_DEMO=1" --variables "DEMO_PASSWORD=..." \
  --variables "DEMO_TERMINAL_TOKEN_BUS1=..." --variables "DEMO_TERMINAL_TOKEN_BUS2=..." \
  --variables "DJANGO_SUPERUSER_USERNAME=platform" --variables "DJANGO_SUPERUSER_PASSWORD=..."
railway domain --service web                    # public https address
railway up --service web --ci                   # upload, build, deploy
```

Make random secrets with
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`.

## Deploying a change

```
cd bus-fare
railway up --service web --ci
```

That uploads the working folder (not a git commit), builds the image and swaps it in
once `/api/health/` answers. Migrations run at start. Check afterwards:

```
curl https://web-production-9ad597a4.up.railway.app/api/health/
railway logs --service web
```

Errors are printed to the log (`DJANGO_LOG_LEVEL`, default `WARNING`).

## Checking before deploying

Run the tests against PostgreSQL too, not only SQLite: SQLite ignores row locking,
and a Postgres-only bug (locking a row across an optional join, which made **every
tap fail** with a 500 error) was found this way on 16 Nov.

```
docker run -d --name pg -e POSTGRES_PASSWORD=pw -p 5432:5432 postgres:16-alpine
cd bus-fare/server
DATABASE_URL=postgres://postgres:pw@localhost:5432/postgres .venv/bin/python manage.py test fares
.venv/bin/python manage.py test fares          # and SQLite
```

The whole image can be tried on the laptop the way Railway runs it:

```
cd bus-fare
docker build -t bus-fare .
docker run --rm -p 8000:8000 -e PORT=8000 -e DJANGO_DEBUG=0 -e DJANGO_SECRET_KEY=test \
  -e SEED_DEMO=1 -e DEMO_PASSWORD=test-pass-123 bus-fare      # SQLite inside the container
```

## Good to know

- **`railway.json` is "Config as Code", which Railway is retiring:** it keeps
  working until **1 Dec 2026**. Before then run `railway config migrate` (writes
  `.railway/railway.ts`) and `railway config migrate cutover`, or set the builder,
  health check and restart policy by hand in the service settings.
- **Costs:** Railway bills by usage (two small services). Stop or delete the project
  in the Railway dashboard when the demo is over.
- **Backups:** the Postgres data lives on a Railway volume. Railway's dashboard can
  take backups; there are none yet.
- **Top-ups are still simulated** (no M-Pesa): with `DEMO_TOPUP=1` anyone with an
  employee login can add balance. Without it, production refuses top-ups and the
  wallet says top-up is not available yet.
- The laptop set-up still works unchanged (`DASHBOARDS.md`, `dashboard/README.md`).
