"""Buyer/seller behaviour analytics.

Kept dependency-free (no numpy/pandas) on purpose: the worker image stays small
and the numbers are trivial to reason about when reviewing the code.
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func

from ..models import Article, ArticleTag, Floorsheet, PriceDaily


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs):
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _pearson(a, b):
    if len(a) < 3 or len(b) < 3 or len(a) != len(b):
        return None
    ma, mb = _mean(a), _mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = sum((x - ma) ** 2 for x in a) ** 0.5
    db = sum((y - mb) ** 2 for y in b) ** 0.5
    if da == 0 or db == 0:
        return None
    return round(num / (da * db), 3)


def compute_vwap(prices) -> float | None:
    """Volume weighted average price using the usual typical price."""
    tot_v = 0.0
    tot_pv = 0.0
    for p in prices:
        typical = (p.high + p.low + p.close) / 3.0
        tot_v += p.volume
        tot_pv += typical * p.volume
    if tot_v == 0:
        return None
    return round(tot_pv / tot_v, 2)


def compute_pressure(prices, lookback: int = 10) -> tuple[str, float]:
    """Buy/sell pressure in -1..1.

    Two signals, averaged:
      * close relative to VWAP over the window (are fills happening above avg?)
      * signed volume balance: up-days' volume minus down-days' volume.

    Deliberately simple and explainable. On gap-prone NEPSE data a fancier
    model would need intraday data we don't reliably have.
    """
    window = prices[-lookback:]
    if len(window) < 3:
        return "neutral", 0.0

    vwap = compute_vwap(window) or window[-1].close
    if vwap:
        vwap_sig = max(-1.0, min(1.0, (window[-1].close - vwap) / vwap * 10))
    else:
        vwap_sig = 0.0

    up_v = down_v = 0.0
    for i in range(1, len(window)):
        if window[i].close >= window[i - 1].close:
            up_v += window[i].volume
        else:
            down_v += window[i].volume
    total = up_v + down_v
    vol_sig = (up_v - down_v) / total if total else 0.0

    score = round((vwap_sig + vol_sig) / 2.0, 3)
    if score > 0.15:
        return "buy", score
    if score < -0.15:
        return "sell", score
    return "neutral", score


def detect_volume_anomalies(prices, lookback: int = 20, threshold: float = 3.5):
    """Rolling robust z-score on volume.

    I use median + MAD instead of mean/sd because NEPSE volume is very spiky:
    one block trade drags the mean so far that later days stop looking unusual.
    A day is flagged when |0.6745 * (v - median) / MAD| > 3.5. The 0.6745 makes
    MAD a consistent estimator of sigma for normal data, so 3.5 is close to the
    familiar >3 sigma "rare event" line.
    """
    flags = []
    for i, p in enumerate(prices):
        if i < lookback:
            continue
        hist = [x.volume for x in prices[i - lookback:i] if x.volume > 0]
        if len(hist) < 5:
            continue
        med = sorted(hist)[len(hist) // 2]
        mad = sorted(abs(v - med) for v in hist)[len(hist) // 2]
        if mad == 0:
            continue
        z = 0.6745 * (p.volume - med) / mad
        if abs(z) > threshold:
            flags.append(
                {
                    "date": p.date.isoformat(),
                    "volume": p.volume,
                    "median_volume": med,
                    "robust_z": round(z, 2),
                    "direction": "spike" if z > 0 else "drop",
                }
            )
    return flags


def broker_breakdown(db, company_id: int, days: int = 30, top: int = 10):
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(Floorsheet)
        .filter(Floorsheet.company_id == company_id, Floorsheet.date >= since)
        .all()
    )
    bought, sold = {}, {}
    for r in rows:
        bought[r.buyer_broker] = bought.get(r.buyer_broker, 0.0) + r.quantity
        sold[r.seller_broker] = sold.get(r.seller_broker, 0.0) + r.quantity

    brokers = set(bought) | set(sold)
    stats = [
        {
            "broker": b,
            "buy_qty": round(bought.get(b, 0.0), 2),
            "sell_qty": round(sold.get(b, 0.0), 2),
            "net_qty": round(bought.get(b, 0.0) - sold.get(b, 0.0), 2),
        }
        for b in brokers
    ]
    stats.sort(key=lambda s: abs(s["net_qty"]), reverse=True)
    return stats[:top]


def news_price_check(db, company_id: int, days: int = 30):
    """Do busier news days precede bigger moves?

    For each trading day we count that day's articles for the company and pair
    it with the *next* day's absolute return and volume change. Pearson is run
    on the full pairs; missing days are simply skipped.
    """
    since = date.today() - timedelta(days=days + 5)
    prices = (
        db.query(PriceDaily)
        .filter(PriceDaily.company_id == company_id, PriceDaily.date >= since)
        .order_by(PriceDaily.date)
        .all()
    )
    if len(prices) < 5:
        return {"sample_size": 0, "pearson_abs_return": None, "pearson_volume": None}

    news_by_day = {}
    for day_key, cnt in (
        db.query(func.date(Article.published_at), func.count(ArticleTag.id))
        .join(ArticleTag, ArticleTag.article_id == Article.id)
        .filter(ArticleTag.company_id == company_id)
        .group_by(func.date(Article.published_at))
        .all()
    ):
        # sqlite hands back a string, postgres a date; normalise to date
        if isinstance(day_key, str):
            try:
                day_key = date.fromisoformat(day_key[:10])
            except ValueError:
                continue
        news_by_day[day_key] = cnt

    counts, abs_rets, vol_changes = [], [], []
    for i in range(len(prices) - 1):
        d = prices[i].date
        n = news_by_day.get(d, 0)
        if isinstance(n, (list, tuple)):
            n = n[0]
        nxt = prices[i + 1]
        ret = abs(nxt.close - prices[i].close) / prices[i].close if prices[i].close else 0
        vchg = (nxt.volume - prices[i].volume) / prices[i].volume if prices[i].volume else 0
        counts.append(float(n))
        abs_rets.append(ret)
        vol_changes.append(vchg)

    return {
        "sample_size": len(counts),
        "total_articles": int(sum(counts)),
        "pearson_abs_return": _pearson(counts, abs_rets),
        "pearson_volume": _pearson(counts, vol_changes),
    }


def behavior_summary(db, company, days: int = 30):
    since = date.today() - timedelta(days=days)
    prices = (
        db.query(PriceDaily)
        .filter(PriceDaily.company_id == company.id, PriceDaily.date >= since)
        .order_by(PriceDaily.date)
        .all()
    )
    pressure, score = compute_pressure(prices)
    return {
        "company_id": company.id,
        "symbol": company.symbol,
        "window_days": days,
        "vwap": compute_vwap(prices),
        "last_close": prices[-1].close if prices else None,
        "pressure": pressure,
        "pressure_score": score,
        "volume_anomalies": detect_volume_anomalies(prices),
        "broker_breakdown": broker_breakdown(db, company.id, days),
        "news_price_check": news_price_check(db, company.id, days),
        "generated_at": datetime.utcnow(),
    }
