# NEPSE Research Dashboard

Crawls a handful of Nepali news portals and NEPSE trading data, tags every
article with the company (or companies) it is about, runs a few buyer/seller
behaviour checks over the price + floorsheet series, and serves all of it
through a role-gated API and a live dashboard.

This was built against the brief for the Python/AI-ML Full Stack assignment.
The interesting decisions and their trade-offs are written down below rather
than left as comments in the code.

---

## What is in here

```
backend/
  app/
    routers/      auth, companies, news, admin, reports, ws   (FastAPI)
    services/     categorize.py, analysis.py, ingest.py, alerts.py, classifier.py
    errors.py     one error envelope for every failure
    tasks/        celery app, crawl tasks, categorize task
    models.py     SQLAlchemy models
    events.py     redis pub/sub -> websocket fanout
  crawlers/       scrapy project: 4 news spiders + 1 market spider
  scripts/        seed_demo.py  (generates the bundled sample data)
  tests/          pytest suite for the API surface
  pyproject.toml  ruff + pytest config
frontend/         React + Vite dashboard (recharts for the charts)
deploy/           timescale init sql
docker-compose.yml
.github/workflows/ci.yml   lint + pytest (backend), typecheck + build (frontend)
```

## Running it

### Option A — Docker (the whole stack)

```
cp .env.example .env
docker compose up --build
```

- dashboard: http://localhost:5173
- API + Swagger: http://localhost:8000/docs

That brings up TimescaleDB, Redis, the API, one celery worker, celery beat
(the scheduler) and the nginx-served frontend. On first boot the API sees an
empty database and seeds it, so the dashboard is not blank before you have run
a crawl.

### Option B — local, no Docker

Backend (Python 3.11+):

```
cd backend
python -m venv .venv && .venv\Scripts\activate     # or source on linux/mac
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The defaults in `.env.example` point at a local SQLite file and assume no
Redis. If Redis is not there and `INLINE_JOBS=true`, crawl and categorize jobs
run in a worker thread inside the API instead of through Celery, so you can
still click "trigger crawl" on the admin screen without standing up the whole
box. With Redis present, set `INLINE_JOBS=false` and the jobs go to the queue.

Frontend:

```
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api and /ws to :8000
```

### Sample logins (created by the seed)

| user | password | role |
|------|----------|------|
| admin | admin123 | admin |
| analyst | analyst123 | analyst |
| viewer | viewer123 | viewer |

Change these before this is exposed anywhere real (see Assumptions).

---

## Data sources

News spiders: **merolagani.com**, **sharesansar.com**, **nepsealpha.com**,
**bizmandu.com**. Each spider crawls a listing page, follows article links,
pulls headline / excerpt / body / date / source / url, and stops after a page
budget so a pagination loop can't run away. Dedup is by URL, enforced by a
unique index, so re-crawling is safe.

Market spider (`nepse_market`): daily OHLCV per watchlist symbol plus
floorsheet rows (buyer broker, seller broker, quantity, rate). It reads the
NEPSE/NepseAlpha public endpoints.

**The honest caveat about live crawling:** NEPSE and the news portals change
their markup and move their JSON endpoints around, and some block datacenter
IPs. I could not verify every selector against the live sites from this
environment, so the spiders are written defensively: if a listing page yields
nothing the run records zero items and moves on, and if a market endpoint 404s
the run is marked `error` with the reason shown in the Admin screen. The
pipeline itself (queue, rate limiting, dedup, ingestion, tagging, live push) is
exercised end to end by the bundled seed, so the app is fully demonstrable
without depending on those sites being reachable on the day.

`ROBOTSTXT_OBEY = True`, a descriptive user agent, and a 1.5s download delay
with AutoThrottle are on by default. Tune them in `crawlers/crawlers/settings.py`.

---

## How the pipeline is wired

1. **Celery beat** drops one crawl task per portal on a staggered 4-hourly
   schedule (7/22/37/52 past the hour so four portals are not hit at once),
   plus a daily market-data run after the exchange closes. There is also a
   manual trigger from the admin screen (`POST /api/admin/crawl-runs`).
2. Tasks run the relevant Scrapy spider **in a subprocess**. Spiders are
   stateless: they write their items to a JSONL file and never touch the DB.
3. The Celery task reads that file and ingests it through `services/ingest.py`,
   which is where dedup and tagging live. One place owns DB writes.
4. New articles are tagged immediately on ingest. If the watchlist changes,
   the admin endpoint (and the scheduled job) re-tags the whole corpus.
5. Crawl/categorize outcomes go to `crawl_runs` / `job_log` for the admin
   screen, and an event is published to Redis which the API fans out to every
   connected dashboard over `/ws/updates`.

Splitting "fetch" (spiders) from "persist" (tasks + ingest) is what makes the
subprocess isolation possible without giving each spider its own DB session,
and it means a spider can be re-run against a corrupted item without the
crawler being down.

---

## News categorization — approach and why

`services/categorize.py` does **weighted keyword/alias matching**, producing a
multi-label result with a confidence per company.

I picked this over embeddings or an LLM for three reasons that held up in the
time I had:

- It needs no external call, so re-tagging the whole corpus whenever a company
  is added is free and instant. That is exactly the "adding a company is a
  config change" requirement.
- Nepali market news names companies literally ("Nabil Bank", "NABIL"), so the
  obvious cases are already covered, and a per-company alias list handles the
  rest.
- Every label is explainable, which is what the analyst correction workflow
  needs to be useful.

Mechanically: a company's name/symbol/aliases are matched against title and
body with title hits weighted higher, a bare-ticker match in the headline gets
a boost, and boilerplate words are de-weighted. Confidence is `1 - exp(-score)`,
so one strong headline hit already clears the 0.35 threshold while a passing
mention in the body stays below it.

The trade-off, stated plainly: a story that says "the bank" without naming it
will not be tagged. That is the gap the analyst review queue exists to close.
Corrections are recorded in `correction_log` (article, from-company,
to-company, action, user) specifically so a supervised retrain can use them
later. If I extended this, embeddings over the article body compared to a small
set of company descriptions would be the next step — but I would keep the
keyword tagger as a fast path and as a sanity check on the model.

---

## Buyer/seller behaviour analysis

All in `services/analysis.py`, surfaced by
`GET /api/companies/:id/behavior-summary`. No numpy/pandas — the numbers are
small and staying dependency-light keeps the worker image thin.

- **VWAP vs close.** VWAP uses the typical price `(h+l+c)/3` weighted by
  volume over the window. A close well above VWAP is treated as buyers having
  won the period.
- **Pressure indicator.** A score in `[-1, 1]` averaging two signals: how far
  the last close sits from VWAP, and the signed-volume balance
  (up-day volume minus down-day volume). Above +0.15 is "buy", below -0.15 is
  "sell", otherwise "neutral". I kept it deliberately explainable; on
  gap-prone NEPSE data a fancier model would want intraday prints we don't
  reliably have.
- **Volume anomaly.** Rolling **robust z-score**: median + MAD over the prior
  20 sessions, flagged at `|0.6745 * (v - median) / MAD| > 3.5`. I used
  median/MAD rather than mean/std because one block trade drags the mean enough
  that later days stop looking unusual. 3.5 robust-sigma is roughly the
  familiar >3σ rare-event line.
- **Broker breakdown.** Floorsheet rows aggregated by buyer/seller broker into
  net quantity, top 10 by absolute net.
- **News vs next-day movement.** For each trading day, that day's article count
  is paired with the *next* day's absolute return and volume change; Pearson r
  over the pairs. It is a weak-signal check by construction (daily data, no
  intraday), and it is reported as such rather than dressed up.

A short read of what the technique actually found on the seeded sample, and
what it would need to mean something on real data, is in `FINDINGS.md`.

---

## Reporting

Analysts export the three lenses as CSV (`app/routers/reports.py`): the news
stream, the per-company behaviour summary, and the cross-company comparison. The
comparison export calls the exact same function the dashboard calls, so an
export can never disagree with what is on screen. The frontend downloads them as
authenticated blobs (the token can't ride along on a plain `<a href>`).

---

## Alerting

`app/services/alerts.py` turns the volume-anomaly detector into a durable
signal: one `alerts` row per `(company, day, kind)`, deduped by a unique
constraint so a re-scan can't create duplicates. Alerts are created two ways —
unattended at the end of every market crawl, and on demand from the admin
"check now" button (`POST /api/admin/alerts/check`), which is also what makes
the demo produce alerts right after seeding. Each new alert is published as an
`alert_created` websocket event, and the Admin screen keeps an acknowledge list.
I made alerts a table rather than a transient socket message because the point
of an alert is to be there when nobody was looking.

---

## Next-day direction (exploratory)

`app/services/classifier.py` is a logistic regression written out in plain
Python (no numpy/sklearn) over five features — 1- and 5-day return, robust-z
volume, and trailing 3-day news count and sentiment. It is evaluated
**walk-forward** (train on the past, predict the next day) and the response
always includes the majority-class baseline next to the accuracy, plus the top
feature weights, so the number can't be read as more than it is. On the seeded
sample it typically lands *at or below* the baseline — which is the honest
result for ~80 rows of synthetic data with no intraday or fundamental features,
and exactly why the UI labels it "experimental" and "not investment advice"
rather than dressing it up. It exists to show the evaluation shape and give the
data pipeline a real consumer.

---

## Roles

Server-side, in `deps.py` (`require_role`) — the frontend hides things but the
API is the gate, and there is a test in the smoke flow below that confirms a
viewer gets 403 on admin routes.

| role | can |
|------|-----|
| viewer | read dashboards, prices, news, behaviour, comparison, direction forecast |
| analyst | everything a viewer can, plus correct news categories, export CSV reports |
| admin | everything, plus watchlist, crawl trigger/retry, re-tag, user roles, alerts |

Roles are ranked (viewer < analyst < admin), so `require_role("analyst")` also
admits admins.

---

## API surface

Companies & market data
- `GET  /api/companies`
- `POST /api/companies` (admin) — add/update watchlist entry, re-tags corpus
- `PATCH /api/companies/:id` (admin)
- `GET  /api/companies/:id/prices?range=30d`
- `GET  /api/companies/:id/behavior-summary`
- `GET  /api/companies/:id/direction-forecast` — exploratory, see below
- `GET  /api/companies/comparison`

News & analysis
- `GET  /api/news?company_id=&source=&q=&untagged=&limit=` — `untagged=true` is
  the analyst review queue (articles no tagger matched)
- `POST /api/news/:id/recategorize` (analyst) — `{company_id, action: add|remove}`

Reports (analyst) — CSV, same data the dashboards read
- `GET  /api/reports/news.csv?company_id=&days=`
- `GET  /api/reports/behavior.csv?company_id=&days=`
- `GET  /api/reports/comparison.csv`

Auth
- `POST /api/auth/login` (OAuth2 password form) → bearer token
- `GET  /api/auth/me`
- `POST /api/auth/register` (admin)

Admin & real-time
- `GET  /api/admin/crawl-runs`
- `POST /api/admin/crawl-runs?portal=all|merolagani|sharesansar|nepsealpha|bizmandu|market`
- `POST /api/admin/crawl-runs/:id/retry`
- `POST /api/admin/retag`
- `GET  /api/admin/users`, `POST /api/admin/users/:id/role`
- `GET  /api/admin/alerts?only_open=`, `POST /api/admin/alerts/check`,
  `POST /api/admin/alerts/:id/ack`
- `WS   /ws/updates?token=<jwt>` — pushes `hello`, `crawl_finished`,
  `market_finished`, `retag_finished`, `alert_created`

Every failure comes back in one shape — `{detail, error: {code, message, ...}}`
— from `app/errors.py`, so the frontend has a single thing to parse. `detail` is
kept as the plain message for the existing fetch helper.

Full OpenAPI is at `/docs`. A ready-to-import Postman collection is not
included; the Swagger UI plus the smoke flow below cover the same ground.

---

## Storage

Price rows live in `price_daily`, which the Timescale init script turns into a
hypertable on `date` (in Docker). Locally the same table runs under plain
PostgreSQL or SQLite — the app is written to the SQLAlchemy layer, and the only
place that is aware of Timescale is `deploy/timescale-init.sql`. That was the
cheapest way to satisfy "time-series-aware storage" without tying the whole
thing to a product that is awkward to run on a laptop.

Failures are never console-only: crawl problems land in `crawl_runs.error` and
job problems in `job_log`, both visible on the admin screen.

---

## Frontend

React + Vite + TypeScript. Three screens behind a login: per-company view
(price/volume chart with a running VWAP line, categorized news feed with inline
correction for analysts, behaviour panel, an "experimental" direction-forecast
card, and CSV export buttons for analysts), cross-company comparison (most
volatile / most active / most in the news, plus an export button), and the admin
screen (crawl board, manual trigger and retry, re-tag, watchlist, user roles, the
news-correction review queue with an "untagged only" toggle, and the alert
list with acknowledge). One WebSocket keeps all of them fresh: when a crawl
finishes the connected pages refetch and a toast reports what landed (including
new alerts). The layout collapses to a single column under 900px for tablet.

---

## Smoke flow I ran before submitting

```
1. seed -> 6 companies, 540 price-days, 361 floorsheet rows, 156 articles
2. login admin -> GET companies/prices/behavior-summary/comparison/news  (all 200)
3. behavior-summary on a symbol -> vwap, pressure score, broker table, news r
4. viewer -> GET /api/admin/users  => 403
5. viewer -> POST /api/admin/retag => 403
6. viewer -> GET /api/reports/comparison.csv => 403
7. analyst -> POST /api/news/:id/recategorize => tag added, article shows it
8. analyst -> GET /api/reports/{news,behavior,comparison}.csv => 200 + text/csv
9. analyst -> GET /api/news?untagged=true => returns the review queue only
10. admin -> POST /api/admin/alerts/check => 6 alerts created; listed; ack 200;
    a second check creates 0 (unique constraint holds)
11. admin -> POST /api/admin/retag => 200, re-tagged N articles
12. admin -> POST /api/admin/crawl-runs?portal=market => run recorded; with the
    scrapy binary absent it is marked error with the reason attached (not a
    hang, not a blank console)
13. websocket connect -> trigger retag -> received `retag_finished` frame
14. GET /api/companies/:id/direction-forecast => prediction + walk-forward
    accuracy + baseline; 422 with the envelope when history is too short
15. ruff check . => clean;  pytest -q => 15 passed
16. frontend `npm run build` -> clean typecheck + production bundle
```

---

## Assumptions and things I would do next

- **Secrets and passwords.** `SECRET_KEY` and the demo user passwords are
  development values. They come from the environment / `.env`, and the real
  fix before any deployment is to rotate the key and drop the seeded accounts.
- **Offline data.** The bundled seed is synthetic and labelled as such in the
  footer. It exists so the review is not gated on NEPSE being up; it is not
  real market data.
- **Categorization.** Keyword-first, as argued above. The correction log is the
  bridge to a learned tagger.
- **Floorsheet coverage.** Only a sample of trading days is pulled, which is
  enough for a broker breakdown but not for a full microstructure study. A
  backfill job and an incremental daily pull would be the next step.
- **Scaling past 10 companies.** Fine as-is (per-request queries are bounded),
  but the comparison endpoint loads the whole window into memory per call;
  past a few dozen symbols that should become a materialized summary table.
- **Tests.** `backend/tests/` is a pytest suite over the API surface (auth,
  RBAC, the untagged review queue, recategorize, CSV reports, the alert scan +
  dedup + ack, and the direction forecast including its 422 path), run with
  `pytest -q` and gated in CI alongside `ruff check .`. It does not yet cover the
  spiders themselves, which stay covered by the manual smoke flow above.
