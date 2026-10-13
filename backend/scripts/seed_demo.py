"""Seeds the database with a few months of realistic-ish market data so the app
is useful before any live crawl has run (e.g. for reviews/offline demo).

Price series is a geometric random walk with sector-appropriate volatility;
news is templated boilerplate that reads like NEPSE items; floorsheet rows are
distributed across a handful of broker codes. A couple of deliberate volume
spikes per company give the anomaly-alert and classifier screens something to
find. None of this is real market data and it is explicitly labelled as demo in
the admin UI.
"""
import random
from datetime import date, datetime, timedelta, timezone

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402
from app import models  # noqa: E402
from app.services.demo import seed_demo_users  # noqa: E402
from app.services.ingest import (  # noqa: E402
    upsert_articles,
    upsert_company,
    upsert_floorsheet,
    upsert_prices,
)

RNG = random.Random(20261013)

COMPANIES = [
    {"symbol": "NABIL", "name": "Nabil Bank Limited", "sector": "Commercial Bank",
     "aliases": "Nabil Bank, NABIL Bank", "base": 620.0, "vol": 0.012},
    {"symbol": "ADBL", "name": "Agricultural Development Bank Ltd", "sector": "Commercial Bank",
     "aliases": "ADBL", "base": 240.0, "vol": 0.014},
    {"symbol": "CHCL", "name": "Chilime Hydropower Company", "sector": "Hydropower",
     "aliases": "Chilime", "base": 210.0, "vol": 0.02},
    {"symbol": "NRIC", "name": "NRN Infrastructure and Development Ltd", "sector": "Infrastructure",
     "aliases": "NRN Infra, NRN Infrastructure", "base": 430.0, "vol": 0.016},
    {"symbol": "NRG", "name": "Nepal Reinsurance Company Limited", "sector": "Life Insurance",
     "aliases": "Nepal Re, Nepali Reinsurance", "base": 560.0, "vol": 0.015},
    {"symbol": "NMB", "name": "NMB Bank Limited", "sector": "Commercial Bank",
     "aliases": "NMBB", "base": 165.0, "vol": 0.013},
]

BROKERS = ["48", "58", "27", "16", "32", "12"]

HEADLINES = [
    "{name} posts strong Q2 profit on higher net interest income",
    "{name} board approves dividend of {pct}% for FY last year",
    "Foreign investor interest rises in {name} shares",
    "{name} reports lower non-performing loans this quarter",
    "Shareholders of {name} approve rights issue proposal",
    "{name} leadership defends expansion plan at AGM",
    "Analysts flag valuation concerns after {name} rally",
    "{name} stock moves on news of merger talks",
    "{name} completes merger formalities, trading resumes today",
    "Regulator questions disclosure pattern of {name}",
]

GENERIC_HEADLINES = [
    "NEPSE index ends lower on profit booking after three-day rally",
    "Turnover crosses {val} crore as investors return to market",
    "NEPSE sheds {val} points; banks drag the benchmark",
    "Broker licenses suspended temporarily over settlement issues",
    "SEBON issues new disclosure rules for listed companies",
    "Market waits for monetary policy; volumes stay thin",
]

BODIES = [
    ("{name} has reported a strong financial performance for the second quarter, "
     "driven primarily by higher net interest income and improved operating efficiency. "
     "The company's earnings per share stood at {eps} as of mid-year."),
    ("The board of {name} has recommended a dividend of {pct}% for the last fiscal year. "
     "The proposal will be presented to shareholders at the upcoming AGM for approval. "
     "Final book closure dates are expected to be announced next week."),
    ("Trading in {name} picked up sharply with volume more than double the recent average. "
     "Source says institutional buyers were active through the session."),
]

FIRST_HALVES = [
    "Kathmandu,",
    "Kathmandu —",
    "Market desk,",
    "",
]


def trading_days(n: int):
    days, d = [], date.today()
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return days[::-1]


def make_prices(spec):
    price = spec["base"]
    rows = []
    days = trading_days(90)
    # pick 2 days to be volume spikes so the anomaly detector has signal
    spike_days = {RNG.randrange(30, len(days)) for _ in range(2)}
    for i, d in enumerate(days):
        price *= (1 + RNG.gauss(0.0, spec["vol"]))
        price = max(price, spec["base"] * 0.5)
        o, c = price, price * (1 + RNG.gauss(0.0, spec["vol"] * 0.6))
        h = max(o, c) * (1 + abs(RNG.gauss(0.0, spec["vol"] * 0.4)))
        low = min(o, c) * (1 - abs(RNG.gauss(0.0, spec["vol"] * 0.4)))
        vol = RNG.randint(8, 90) * 1000
        if i in spike_days:
            vol = int(vol * RNG.uniform(6, 9))
        rows.append(
            {
                "date": d,
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(low, 2),
                "close": round(c, 2),
                "volume": float(vol),
                "turnover": round(vol * c, 2),
            }
        )
    return rows


def make_floorsheet(spec, company_id):
    rows = []
    for d in trading_days(7)[:6]:
        n_trades = RNG.randint(6, 14)
        for _ in range(n_trades):
            qty = RNG.randint(1, 60) * 10
            rate = round(max(spec["base"] * 0.5, spec["base"] * RNG.uniform(0.94, 1.06)), 2)
            rows.append(
                {
                    "date": d,
                    "buyer_broker": RNG.choice(BROKERS),
                    "seller_broker": RNG.choice(BROKERS),
                    "quantity": float(qty),
                    "rate": rate,
                    "amount": round(qty * rate, 2),
                }
            )
    return rows


def make_news():
    items = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # naive UTC, matches the column
    for _ in range(160):
        d = now - timedelta(days=RNG.randint(0, 88), hours=RNG.randint(0, 12))
        source = RNG.choice(["merolagani", "sharesansar", "nepsealpha", "bizmandu"])
        if RNG.random() < 0.22:
            title = RNG.choice(GENERIC_HEADLINES).format(
                val=RNG.choice([80, 122, 145, 190, 260])
            )
            body = " ".join(RNG.choice(BODIES).format(name="the market", eps=1, pct=10)[:120].split()) or "Market commentary for the day."
            url = f"https://{source}.com/generic/{int(d.timestamp())}"
        else:
            spec = RNG.choice(COMPANIES)
            title = RNG.choice(HEADLINES).format(
                name=spec["name"], pct=RNG.choice([10, 15, 18, 25, 30])
            )
            body = RNG.choice(BODIES).format(name=spec["name"], eps=RNG.randint(20, 90), pct=10)
            url = f"https://{source}.com/article/{int(d.timestamp())}"
        items.append(
            {
                "title": title,
                "excerpt": body[:200],
                "body": body,
                "source": source,
                "url": url,
                "published_at": d,
            }
        )
    return items


def main():
    db = SessionLocal()
    try:
        seed_demo_users(db)

        price_days = floors = news_days = 0
        for spec in COMPANIES:
            co = upsert_company(db, spec["symbol"], spec["name"], spec["sector"], spec["aliases"])
            price_days += upsert_prices(db, co.id, make_prices(spec))
            floors += upsert_floorsheet(db, co.id, make_floorsheet(spec, co.id))
        news_days = upsert_articles(db, make_news())

        db.commit()
        print(f"seeded: {len(COMPANIES)} companies, {price_days} price-days, "
              f"{floors} floorsheet rows, {news_days} new articles")
        if settings.demo_mode:
            roles = ", ".join(f"{a['username']} ({a['role']})" for a in settings.demo_accounts)
            print(f"demo logins: {roles}; passwords come from the DEMO_* env vars "
                  "(see README / .env.example)")
        else:
            print("demo accounts skipped (DEMO_MODE=false)")
    finally:
        db.close()


if __name__ == "__main__":
    models.Base.metadata.create_all(bind=engine)
    main()
