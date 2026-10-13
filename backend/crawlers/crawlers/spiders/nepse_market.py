"""Market data spider: daily OHLCV plus floorsheet rows.

Endpoints here are the ones in the public NEPSE/NepseAlpha docs as of this
build. Both sites have been known to shuffle their APIs; when an endpoint 404s
the spider simply yields nothing and the run shows an error in the admin view
instead of dying silently. The demo ships with seeded data precisely so the
app remains meaningful on a machine without NEPSE access.
"""
import json
from datetime import date, datetime, timedelta

import scrapy

FLOORSHEET_URL = "https://newweb.nepalstock.com/api/nots/floorSheet"
SNAPSHOT_URL = "https://nepsealpha.com/api/v1/daily-snapshot-prices"
HISTORY_URL = "https://nepsealpha.com/api/v1/traded-stocks/{{symbol}}/daily"

_SAMPLE_DAYS = 6  # floorsheet is heavy; a week of it is plenty for analysis


def _trading_days(n: int):
    days, d = [], date.today()
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    return days


class NepseMarketSpider(scrapy.Spider):
    name = "nepse_market"
    allowed_domains = [
        "newweb.nepalstock.com",
        "nepsealpha.com",
        "api.nepsealpha.com",
    ]

    def __init__(self, watch="[]", out_file=None, run_id=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.watch = json.loads(watch)
        self.out_file = out_file
        self.run_id = int(run_id or 0)
        self.today = date.today().isoformat()

    def start_requests(self):
        if not self.watch:
            self.logger.warning("empty watchlist; nothing to fetch")
            return
        yield scrapy.Request(
            HISTORY_URL.replace("{{symbol}}", self.watch[0]["symbol"]),
            callback=self.parse_prices,
            errback=self.on_price_error,
            dont_filter=True,
        )
        yield scrapy.Request(
            FLOORSHEET_URL,
            method="POST",
            body=json.dumps(
                {"startDate": _trading_days(_SAMPLE_DAYS)[0].isoformat(), "endDate": self.today}
            ).encode(),
            headers={"Content-Type": "application/json"},
            callback=self.parse_floorsheet,
            errback=self.on_floor_error,
            dont_filter=True,
        )

    def parse_prices(self, response):
        # first request tests the endpoint; the rest of the watchlist follows
        yield from self._emit_symbol_prices(self.watch[0]["symbol"], self.watch[0]["id"], response)
        for sym in self.watch[1:]:
            yield scrapy.Request(
                HISTORY_URL.replace("{{symbol}}", sym["symbol"]),
                callback=self._price_for,
                cb_kwargs={"company_id": sym["id"], "symbol": sym["symbol"]},
                errback=self.on_price_error,
                dont_filter=True,
            )

    def _price_for(self, response, company_id, symbol):
        yield from self._emit_symbol_prices(symbol, company_id, response)

    def _emit_symbol_prices(self, symbol, company_id, response):
        try:
            data = response.json()
        except Exception:
            self.logger.error("%s: price payload is not json", symbol)
            return
        rows = data if isinstance(data, list) else data.get("data") or data.get("result", [])
        keep = []
        seen_dates = set()
        for r in rows:
            d = (r.get("date") or r.get("tradeDate") or "").split("T")[0]
            if not d or d in seen_dates:
                continue
            seen_dates.add(d)
            try:
                keep.append(
                    {
                        "date": d,
                        "open": float(r.get("open", 0)),
                        "high": float(r.get("high", 0)),
                        "low": float(r.get("low", 0)),
                        "close": float(r.get("close", 0)),
                        "volume": float(r.get("volume") or r.get("ltdTurnoverQty") or 0),
                        "turnover": float(r.get("amount") or r.get("ltpTurnover") or 0),
                    }
                )
            except (TypeError, ValueError):
                continue
        if not keep:
            self.logger.warning("%s: no price rows parsed", symbol)
            return
        yield {"kind": "price", "company_id": company_id, "symbol": symbol, "rows": keep}

    def parse_floorsheet(self, response):
        rows = response.json()
        by_symbol = {}
        for r in rows:
            sym = r.get("stockSymbol") or r.get("symbol")
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(r)
        by_watch = {w["symbol"]: w for w in self.watch}
        for sym, rs in by_symbol.items():
            w = by_watch.get(sym)
            if not w:
                continue
            out = []
            for r in rs:
                date_s = str(r.get("tradeDate", ""))[:10]
                rate = float(r.get("contractRate") or 0)
                qty = float(r.get("stockQty") or 0)
                if not rate or not qty:
                    continue
                out.append(
                    {
                        "date": date_s,
                        "buyer_broker": r.get("buyerMember") or r.get("buyerBroker", ""),
                        "seller_broker": r.get("sellerMember") or r.get("sellerBroker", ""),
                        "quantity": qty,
                        "rate": rate,
                        "amount": rate * qty,
                    }
                )
            if out:
                yield {"kind": "floorsheet", "company_id": w["id"], "symbol": sym, "rows": out}

    def on_price_error(self, failure):
        self.logger.error("price endpoint failed: %s", failure.getErrorMessage())

    def on_floor_error(self, failure):
        self.logger.error("floorsheet endpoint failed: %s", failure.getErrorMessage())