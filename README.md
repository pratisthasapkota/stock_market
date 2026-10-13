# NEPSE Insight — Stock Market Dashboard

**A queue-driven crawler, a multi-label news tagger, and a live, role-gated
research dashboard for 5–10 NEPSE-listed companies.**

Crawls Nepali market news and NEPSE trading data, tags every article with the
company (or companies) it is about, computes buyer/seller behaviour indicators
from price + floorsheet data, and serves all of it through an RBAC-enforced
FastAPI backend and a real-time React dashboard.

Built for the **Full Stack Developer / Python (AI-ML) Engineer** assignment
(Omway Technologies). Design decisions and their trade-offs are written down
here rather than buried in the code — the README is part of the deliverable.

![python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square)
![fastapi](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat-square)
![react](https://img.shields.io/badge/React-18-61DAFB?style=flat-square)
![celery](https://img.shields.io/badge/Celery-5.4-37814A?style=flat-square)
![postgres](https://img.shields.io/badge/TimescaleDB-pg16-336791?style=flat-square)
![ci](https://img.shields.io/badge/CI-lint%20%2B%20tests-brightgreen?style=flat-square)

---

## Table of contents

- [TL;DR — run it in 2 minutes](#tldr--run-it-in-2-minutes)
- [Demo access](#demo-access)
- [Requirement coverage map](#requirement-coverage-map)
- [Architecture](#architecture)
- [Project layout](#project-layout)
- [Running the stack](#running-the-stack)
- [Data sources & crawling](#data-sources--crawling)
- [News categorization — approach & trade-offs](#news-categorization--approach--trade-offs)
- [Buyer/seller behaviour analysis](#buyerseller-behaviour-analysis)
- [Real-time & backend design](#real-time--backend-design)
- [Frontend dashboard](#frontend-dashboard)
- [Role-based access control](#role-based-access-control)
- [API surface](#api-surface)
- [Storage](#storage)
- [Reporting](#reporting)
- [Alerting](#alerting)
- [Next-day direction classifier (exploratory)](#next-day-direction-classifier-exploratory)
- [Configuration reference](#configuration-reference)
- [Testing & CI](#testing--ci)
- [Verification / smoke flow](#verification--smoke-flow)
- [Assumptions, limitations & next steps](#assumptions-limitations--next-steps)

---

## TL;DR — run it in 2 minutes

```bash
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---------|-----|
| Dashboard | http://localhost:5173 |
| API + Swagger UI | http://localhost:8000/docs |
| Health | http://localhost:8000/api/health |

On first boot the API creates the schema and **seeds a full month of sample
data plus the three role accounts**, so the dashboard is alive before you run a
single crawl. Prefer no Docker? See [Running the stack](#running-the-stack).

---

## Demo access

Three working accounts are created on first boot, one per role, so every
permission level can be reviewed without registering. These are the real
credentials used by the seed — copy either column:

| Role | Email | User | Password |
|------|-------|------|----------|
| **Admin** | `admin@demo.local` | `admin` | `admin123` |
| **Analyst** | `analyst@demo.local` | `analyst` | `analyst123` |
| **Viewer** | `viewer@demo.local` | `viewer` | `viewer123` |

Sign in with the email or username; the login page lists these accounts too, but it fetches them from `GET /api/auth/demo-accounts`
at runtime instead of baking them into the frontend bundle — the bundle is
public, so seeded passwords do not belong in it.

These values come from `.env.example` and can be overridden with the `DEMO_*`
environment variables. Set `DEMO_MODE=false` to skip seeding them and disable
the demo-accounts endpoint entirely — do that before exposing the app anywhere
real (see [Assumptions](#assumptions-limitations--next-steps)).

---

## Requirement coverage map

Where each item of the brief is implemented, so a reviewer can jump straight to
it.

| # | Requirement | Where |
|---|-------------|-------|
| 1 | News crawlers over 4 portals, dedup by URL, robots.txt | `backend/crawlers/crawlers/spiders/`, `services/ingest.py` |
| 1 | NEPSE OHLCV + floorsheet transactions | `crawlers/spiders/nepse_market.py`, `models.py` |
| 1 | Queue + per-portal rate limiting + scheduler | `app/tasks/celery_app.py`, `app/tasks/crawl.py` |
| 2 | Multi-label tagging with confidence | `services/categorize.py` |
| 2 | Analyst corrections + retraining log | `routers/news.py`, `models.CorrectionLog` |
| 3 | VWAP vs close, buy/sell pressure | `services/analysis.py` |
| 3 | Volume-anomaly detection (threshold + method) | `services/analysis.py` (robust z, 3.5) |
| 3 | Broker-level buy/sell from floorsheet | `services/analysis.py` |
| 3 | News vs next-day price/volume check | `services/analysis.py`, `FINDINGS.md` |
| 3 | Written findings summary | [`FINDINGS.md`](FINDINGS.md) |
| 4 | FastAPI + WebSocket push | `app/main.py`, `app/routers/ws.py` |
| 4 | Time-series-aware storage (Timescale hypertable) | `deploy/timescale-init.sql`, `app/database.py` |
| 4 | Queue for crawl + categorization | `app/tasks/` (Celery + Redis) |
| 4 | Central error handling + OpenAPI docs | `app/errors.py`, `/docs` |
| 5 | Per-company view, live-updating | `frontend/src/pages/CompanyDetail.tsx` |
| 5 | Cross-company comparison | `frontend/src/pages/Comparison.tsx` |
| 5 | Admin crawl monitor + category correction | `frontend/src/pages/Admin.tsx` |
| 5 | Responsive on desktop & tablet | `frontend/src/styles.css` |
| 6 | Server-side RBAC for all three roles | `app/deps.py`, `require_role` |
| 7 | Indicative API surface implemented | `app/routers/` |
| Bonus | Next-day direction classifier | `services/classifier.py` |
| Bonus | CI running lint + tests | `.github/workflows/ci.yml` |
| Bonus | Alert on volume-anomaly threshold | `services/alerts.py` |

---

## Architecture

```
  news portals ─┐
  NEPSE / API ──┤   HTTP (robots.txt obeyed, per-portal delay)
                ▼
      ┌───────────────────────────┐        ┌──────────────────────────┐
      │ scrapy spiders            │ JSONL  │ celery worker            │
      │ (subprocess, stateless)   ├───────▶│  crawl tasks → ingest.py │
      └───────────────────────────┘        │  (dedup + tagging)       │
                                           └───────┬──────────┬───────┘
   celery beat ──(4-hourly, staggered)──────────────┘          │ publish
   admin "trigger crawl" ───────────────────────────┐          ▼
                                                    │    ┌───────────┐
                                                    │    │   redis   │
                                                    │    │ queue +   │
                                                    │    │ pub/sub   │
                                                    ▼    └─────┬─────┘
                                           ┌──────────────┐    │ event
                                           │ timescale/pg │    ▼
                                           │  (SQLAlchemy)│  FastAPI ──WS──▶ React dashboards
                                           └──────────────┘   (REST + /ws/updates)
```

**Job flow.** Celery beat enqueues one task per portal on a staggered 4-hourly
schedule, plus a daily market run and a 6-hourly re-tag. A task runs its Scrapy
spider **in a subprocess** that writes items to JSONL and never touches the DB;
the task then reads the file and ingests it through `services/ingest.py`, the
single owner of DB writes. That split (fetch vs. persist) is what keeps spiders
stateless and lets one bad item be re-run without taking the crawler down.

**Live path.** Ingest emits an event to a Redis channel; the API listens and
fans it out to every dashboard connected to `/ws/updates`. The UI refetches on
each revision bump and shows a toast.

---

## Project layout

```
backend/
  app/
    main.py           FastAPI app + lifespan bootstrap (seed-on-empty)
    config.py         pydantic-settings; all knobs + DEMO_* accounts
    models.py         SQLAlchemy models (Company, PriceDaily, Article, …)
    deps.py           get_current_user / require_role (the RBAC gate)
    errors.py         one error envelope for every failure
    events.py         redis pub/sub listener → websocket fan-out
    security.py       password hashing + JWT
    routers/          auth, companies, news, admin, reports, ws
    services/         categorize, analysis, ingest, alerts, classifier, demo
    tasks/            celery_app (broker + beat schedule), crawl, categorize
  crawlers/           scrapy project: 4 news spiders + nepse_market
  scripts/seed_demo.py  generates the bundled sample data
  tests/test_api.py     pytest suite over the API surface
  pyproject.toml        ruff + pytest config
frontend/             React + Vite + TS dashboard (recharts)
deploy/timescale-init.sql   hypertable + index
docker-compose.yml    db · redis · api · worker · beat · web
.github/workflows/ci.yml    backend lint+pytest · frontend typecheck+build
```

---

## Running the stack

### Option A — Docker (whole stack)

```bash
cp .env.example .env
docker compose up --build
```

Brings up TimescaleDB, Redis, the API, one Celery worker, Celery beat (the
scheduler) and the nginx-served frontend. The API seeds an empty database on
first boot, so the dashboard isn't blank before any crawl has run.

The compose file has **sensible defaults for every variable**, so the `.env` copy
is optional — `docker compose up --build` works with no `.env` at all. Startup is
ordered by healthchecks (DB and Redis healthy → API → web; worker/beat wait on DB
and Redis), the backend image is built once and shared by `api`/`worker`/`beat`,
and it runs as a non-root user.

> Upgrading from an older build? The DB init only runs on an empty data volume,
> so reset it once with `docker compose down -v` before `docker compose up
> --build`.

### Option B — local, no Docker

**Backend** (Python 3.11+; developed on 3.13):

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
uvicorn app.main:app --reload     # http://localhost:8000
```

Defaults in `.env.example` target a local SQLite file and assume no Redis. With
no Redis and `INLINE_JOBS=true`, crawl and categorize jobs run in a worker
thread inside the API — so "trigger crawl" on the admin screen still works
without the whole box. With Redis present, set `INLINE_JOBS=false` and jobs go
through Celery.

**Frontend** (Node 18+):

```bash
cd frontend
npm install
npm run dev                       # http://localhost:5173, proxies /api and /ws to :8000
```

---

## Data sources & crawling

News spiders cover **merolagani.com**, **sharesansar.com**, **nepsealpha.com**
and **bizmandu.com**. Each crawls a listing page, follows article links, and
pulls headline / excerpt / body / date / source / url, stopping after a page
budget so a pagination loop can't run away. Dedup is by URL, enforced by a
unique index, so re-crawling is idempotent.

The market spider (`nepse_market`) reads the NEPSE / NepseAlpha public endpoints
for daily OHLCV per watchlist symbol, plus floorsheet rows (buyer broker, seller
broker, quantity, rate).

Politeness defaults (`crawlers/crawlers/settings.py`): `ROBOTSTXT_OBEY = True`,
a descriptive user agent, `DOWNLOAD_DELAY = 1.5`, `CONCURRENT_REQUESTS_PER_DOMAIN
= 2` and AutoThrottle. Per-portal overrides come from config, so one slow portal
doesn't throttle the others.

> **Honest caveat about live crawling.** NEPSE and the news portals change their
> markup and move JSON endpoints around, and some block datacenter IPs. Every
> selector could not be verified against the live sites from this environment,
> so the spiders are written defensively: if a listing page yields nothing the
> run records zero items and moves on, and if a market endpoint 404s the run is
> marked `error` with the reason shown in the Admin screen. The *pipeline*
> (queue, rate limiting, dedup, ingestion, tagging, live push) is exercised end
> to end by the bundled seed, so the app is fully demonstrable without depending
> on those sites being reachable on review day.

---

## News categorization — approach & trade-offs

`services/categorize.py` does **weighted keyword / alias matching**, returning a
**multi-label** result with a confidence per company.

It was chosen over embeddings or an LLM for three reasons that held up in the
time available:

1. **No external call.** Re-tagging the whole corpus whenever a company is added
   is free and instant — exactly the "adding a company is a config change"
   requirement.
2. **Nepali market news names companies literally** ("Nabil Bank", "NABIL"), so
   the obvious cases are already covered; a per-company alias list handles the
   rest.
3. **Explainable labels**, which is what makes the analyst correction workflow
   useful.

Mechanically: a company's name / symbol / aliases are matched against title and
body with title hits weighted higher, a bare-ticker match in the headline gets a
boost, and boilerplate words are de-weighted. Confidence is `1 - exp(-score)`, so
one strong headline hit clears the 0.35 threshold while a passing body mention
stays below it.

> **The trade-off, plainly:** a story that says "the bank" without naming it
> won't be tagged. That gap is what the analyst review queue exists to close.

Corrections are recorded in `correction_log` (article, from-company,
to-company, action, user) specifically so a supervised retrain can consume them
later. The next step would be embeddings over the article body compared against
company descriptions — keeping the keyword tagger as a fast path and as a sanity
check on the model.

---

## Buyer/seller behaviour analysis

All in `services/analysis.py`, surfaced by
`GET /api/companies/:id/behavior-summary`. No numpy/pandas — the numbers are
small, and staying dependency-light keeps the worker image thin.

| Indicator | Method | Interpretation |
|-----------|--------|----------------|
| **VWAP vs close** | typical price `(h+l+c)/3` weighted by volume | close ≫ VWAP ⇒ buyers won the window |
| **Pressure** `[-1,1]` | mean of (close vs VWAP) and signed-volume balance | `> +0.15` buy, `< -0.15` sell, else neutral |
| **Volume anomaly** | rolling **robust z**: `median` + `MAD` over 20 sessions, flag `|0.6745·(v−med)/MAD| > 3.5` | rare-event threshold, resistant to one block trade |
| **Broker breakdown** | floorsheet grouped by buyer/seller broker into net qty | top 10 by absolute net |
| **News vs next-day** | per day, article count vs *next* day's \|return\| & volume change, Pearson r | weak-signal check, reported as r not a verdict |

The pressure indicator is deliberately explainable — on gap-prone NEPSE data a
fancier model would want intraday prints we don't reliably have. The robust
z-score uses median/MAD rather than mean/std because a single block trade drags
the mean enough that later days stop looking unusual.

The written findings summary the brief asks for is in
[`FINDINGS.md`](FINDINGS.md) — including the patterns found and, just as
importantly, the ones that *didn't* hold.

---

## Real-time & backend design

- **API:** FastAPI with a single error envelope (`{detail, error: {code,
  message, …}}`) from `app/errors.py`, so clients have one thing to parse.
- **Docs:** OpenAPI is auto-served at `/docs` (Swagger UI).
- **Queue:** Celery on Redis. Separate `crawl` and `categorize` queues, JSON
  serialization, `Asia/Kathmandu` schedule timezone.
- **Scheduler:** Celery beat runs four staggered news crawls (minutes 7/22/37/52
  every 4h), a daily market pull at 19:30, and a 6-hourly re-tag.
- **Real-time:** `/ws/updates?token=<jwt>`; the API pushes `hello`,
  `crawl_finished`, `market_finished`, `retag_finished` and `alert_created`.
  A JWT is required on the socket, so live data is gated too.
- **Failures are never console-only:** crawl problems land in `crawl_runs.error`
  and job problems in `job_log`, both shown on the Admin screen.

---

## Frontend dashboard

React 18 + Vite + TypeScript, charts by `recharts`. Four role-aware screens
behind a login:

- **Watchlist (dashboard)** — summary stat strip (tracked / advancing /
  declining / top 30-day gain & drop), one card per company with sparkline,
  day and 30-day change, plus the latest categorized headlines showing the
  companies they were tagged to.
- **Per-company view** — price/volume chart with a running VWAP line, categorized
  news feed with inline correction for analysts, buyer/seller behaviour panel
  (pressure gauge, volume anomalies, broker table), an "experimental" next-day
  direction card, and CSV export buttons for analysts.
- **Cross-company comparison** — most volatile / most active / most in the news,
  with relative bars and the leader highlighted, plus CSV export.
- **Admin** — crawl board with trigger + retry, re-tag, watchlist add, user-role
  management, the news-correction review queue (with an "untagged only" toggle),
  and the alert list with acknowledge.

**One WebSocket keeps every screen fresh.** When a crawl finishes, connected
pages refetch and a toast reports what landed (including new alerts). The layout
collapses to a single column under 900px (tablet) and tightens further under
640px.

---

## Role-based access control

RBAC is enforced **server-side** in `deps.py` (`require_role`). The frontend
hides controls for convenience, but the API is the gate — and the test suite
asserts a viewer gets `403` on admin routes.

| Role | Permissions |
|------|-------------|
| **Viewer** | read-only: dashboards, prices, news, behaviour, comparison, direction forecast |
| **Analyst** | everything a viewer can, plus correct news categories and export CSV reports |
| **Admin** | everything, plus watchlist, crawl trigger/retry, re-tag, user roles, alerts |

Roles are ranked (`viewer < analyst < admin`), so `require_role("analyst")` also
admits admins.

---

## API surface

**Companies & market data**
```
GET   /api/companies
POST  /api/companies                         (admin)  add/update watchlist, re-tags corpus
PATCH /api/companies/:id                     (admin)
GET   /api/companies/:id/prices?range=30d
GET   /api/companies/:id/behavior-summary
GET   /api/companies/:id/direction-forecast           exploratory
GET   /api/companies/comparison
```

**News & analysis**
```
GET   /api/news?company_id=&source=&q=&untagged=&limit=
POST  /api/news/:id/recategorize             (analyst) {company_id, action: add|remove}
```

**Reports (analyst)** — CSV, same data the dashboards read
```
GET   /api/reports/news.csv?company_id=&days=
GET   /api/reports/behavior.csv?company_id=&days=
GET   /api/reports/comparison.csv
```

**Auth**
```
POST  /api/auth/login                         OAuth2 password form; username or email → bearer token
GET   /api/auth/me
GET   /api/auth/demo-accounts                 seeded logins, only while DEMO_MODE is on (404 otherwise)
POST  /api/auth/register                       (admin)
```

**Admin & real-time**
```
GET   /api/admin/crawl-runs
POST  /api/admin/crawl-runs?portal=all|merolagani|sharesansar|nepsealpha|bizmandu|market
POST  /api/admin/crawl-runs/:id/retry
POST  /api/admin/retag
GET   /api/admin/users        POST /api/admin/users/:id/role
GET   /api/admin/alerts?only_open=   POST /api/admin/alerts/check   POST /api/admin/alerts/:id/ack
WS    /ws/updates?token=<jwt>
```

Every failure returns the same envelope — `{detail, error: {code, message, …}}`
— from `app/errors.py`. Full OpenAPI is at `/docs`; the smoke flow below covers
the same ground without a Postman collection.

---

## Storage

Price rows live in `price_daily`. In Docker, `deploy/timescale-init.sql` enables
the TimescaleDB extension, and the API then converts `price_daily` into a
**hypertable** on `date` (plus a `(company_id, date DESC)` index) right after the
ORM creates the tables — see `app/database.py:ensure_timeseries()`. That
ordering matters: Postgres init scripts run *before* the app creates its tables,
so the conversion is done idempotently at startup instead (it is a no-op on
SQLite or a plain PostgreSQL without the extension). Locally the same table runs
under plain PostgreSQL or SQLite: the app is written against the SQLAlchemy
layer, and everything Timescale-specific stays behind that one guarded function.

---

## Reporting

Analysts export the three lenses as CSV (`app/routers/reports.py`): the news
stream, the per-company behaviour summary, and the cross-company comparison. The
comparison export calls the exact function the dashboard calls, so an export can
never disagree with what's on screen. The frontend downloads them as
authenticated blobs (a token can't ride along on a plain `<a href>`).

---

## Alerting

`app/services/alerts.py` turns the volume-anomaly detector into a durable
signal: one `alerts` row per `(company, day, kind)`, deduped by a unique
constraint so a re-scan can't create duplicates. Alerts are created two ways —
unattended at the end of every market crawl, and on demand from the admin "check
now" button (`POST /api/admin/alerts/check`), which also makes the demo produce
alerts right after seeding. Each new alert is published as an `alert_created`
websocket event, and the Admin screen keeps an acknowledge list. Alerts are a
**table**, not a transient socket message, because the point of an alert is to
be there when nobody was looking.

---

## Next-day direction classifier (exploratory)

`app/services/classifier.py` is a logistic regression written in plain Python
(no numpy/sklearn) over five features — 1- and 5-day return, robust-z volume,
and trailing 3-day news count and sentiment. It is evaluated **walk-forward**
(train on the past, predict the next day) and the response always includes the
majority-class baseline next to the accuracy, plus the top feature weights, so
the number can't be read as more than it is.

On the seeded sample it typically lands **at or below** the baseline — the
honest result for ~80 rows of synthetic data with no intraday or fundamental
features. The UI labels it "experimental" and "not investment advice" rather
than dressing it up. It exists to show the evaluation shape and give the data
pipeline a real consumer.

---

## Configuration reference

All settings are environment variables (or a `.env` file) read by
`app/config.py`. Nothing is hard-coded.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | `sqlite:///./data/stock.db` | SQLAlchemy URL (Postgres/Timescale in Docker) |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker + pub/sub |
| `SECRET_KEY` | `dev-only-secret` | JWT signing key — rotate before deploy |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | token lifetime |
| `CORS_ORIGINS` | `http://localhost:5173,…` | allowed browser origins |
| `INLINE_JOBS` | `false` | run jobs in-process instead of via Celery |
| `SEED_ON_STARTUP` | `true` | seed sample data when the DB is empty |
| `LOG_LEVEL` | `INFO` | logging verbosity |
| `DEMO_MODE` | `true` | seed demo users + serve `/demo-accounts` |
| `DEMO_*_EMAIL` / `_USERNAME` / `_PASSWORD` | see `.env.example` | the three role accounts |
| `CRAWL_USER_AGENT` | `nepse-research-bot/0.1 …` | descriptive UA |
| `CRAWL_DELAY_SECONDS` | `1.5` | default per-portal download delay |
| `CRAWL_PORTAL_DELAYS` | `{}` | JSON overrides, e.g. `{"sharesansar": 3.0}` |
| `CRAWL_MAX_PAGES_PER_PORTAL` | `40` | page budget per run |
| `VOLUME_ANOMALY_Z` | `3.5` | robust-z alert threshold |
| `VOLUME_ANOMALY_LOOKBACK` | `20` | sessions in the rolling window |

---

## Testing & CI

```bash
cd backend
ruff check .          # lint (E, F, I, W, B, UP)
pytest -q             # API-surface suite
```

`backend/tests/` covers auth, RBAC, the untagged review queue, recategorize,
CSV reports, the alert scan + dedup + ack, and the direction forecast including
its 422 path. GitHub Actions (`.github/workflows/ci.yml`) runs `ruff` + `pytest`
on the backend and `npm run build` (typecheck + bundle) on the frontend for every
push and PR.

---

## Verification / smoke flow

The flow actually run before submitting:

```
 1. seed            -> 6 companies, 540 price-days, 361 floorsheet rows, 156 articles
 2. login admin     -> GET companies / prices / behavior-summary / comparison / news  (all 200)
 3. behavior-summary -> vwap, pressure score, broker table, news r
 4. viewer  -> GET  /api/admin/users            => 403
 5. viewer  -> POST /api/admin/retag            => 403
 6. viewer  -> GET  /api/reports/comparison.csv => 403
 7. analyst -> POST /api/news/:id/recategorize  => tag added, article shows it
 8. analyst -> GET  /api/reports/{news,behavior,comparison}.csv => 200 + text/csv
 9. analyst -> GET  /api/news?untagged=true     => returns the review queue only
10. admin   -> POST /api/admin/alerts/check     => 6 alerts created; ack 200;
                                                   second check creates 0 (unique constraint holds)
11. admin   -> POST /api/admin/retag            => 200, re-tagged N articles
12. admin   -> POST /api/admin/crawl-runs?portal=market
                                                   => run recorded; with scrapy absent it is marked
                                                      error with the reason attached (no hang, no blank console)
13. websocket connect -> trigger retag -> received a `retag_finished` frame
14. GET /api/companies/:id/direction-forecast   => prediction + walk-forward accuracy + baseline;
                                                   422 with the envelope when history is too short
15. ruff check . => clean;           pytest -q => 21 passed
16. frontend `npm run build` => clean typecheck + production bundle
```

---

## Assumptions, limitations & next steps

- **Secrets & passwords.** `SECRET_KEY` and the demo passwords come from the
  environment; the `.env.example` values are development defaults only. Before
  any real deployment: rotate the key, set `DEMO_MODE=false` (stops seeding the
  demo users and takes the credentials off `/demo-accounts`), and drop the seeded
  accounts.
- **Offline data.** The bundled seed is **synthetic** and labelled as such in the
  UI footer. It exists so review isn't gated on NEPSE being up; it is not real
  market data.
- **Categorization.** Keyword-first, per the trade-offs above. The correction log
  is the bridge to a learned tagger.
- **Floorsheet coverage.** Only a sample of trading days is pulled — enough for a
  broker breakdown, not a full microstructure study. A backfill job plus an
  incremental daily pull is the next step.
- **Scaling past 10 companies.** Fine as-is (per-request queries are bounded),
  but `comparison` loads the whole window into memory per call; past a few dozen
  symbols that should become a materialized summary table.
- **Tests.** The pytest suite covers the API surface; the spiders themselves are
  covered by the manual smoke flow rather than automation.
- **No live URL.** The deliverable is the repo plus `docker-compose` for the full
  stack; deployment was out of scope for the time box.

---

<sub>Prepared for the Omway Technologies assignment. Sample data is synthetic and
the direction model is exploratory — none of this is investment advice.</sub>
