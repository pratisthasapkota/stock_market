"""Exploratory next-day direction classifier.

This is deliberately small and dependency-free (no numpy/sklearn): a logistic
regression trained with plain gradient descent on features built from the price
series and the tagged-news stream. The point is not to ship a predictor -- a few
dozen observations per company cannot support one -- but to show the honest
evaluation shape (walk-forward, compared against a majority baseline) and to
give the UI something concrete to display with its caveat attached.
"""
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy.orm import Session

from .. import models

POSITIVE = (
    "profit", "growth", "gain", "rise", "rises", "up", "surge", "dividend",
    "bonus", "expansion", "acquire", "wins", "record", "strong", "increases",
)
NEGATIVE = (
    "loss", "losses", "fall", "falls", "drop", "decline", "debt", "penalty",
    "fine", "fraud", "lawsuit", "down", "weak", "cuts", "warning", "default",
)

FEATURE_NAMES = ["ret_1d", "ret_5d", "volume_z", "news_count_3d", "news_sentiment_3d"]


def _sigmoid(z: float) -> float:
    if z < -60:
        return 0.0
    if z > 60:
        return 1.0
    return 1.0 / (1.0 + pow(2.718281828459045, -z))


def _sentiment(text: str) -> float:
    t = (text or "").lower()
    pos = sum(1 for w in POSITIVE if w in t)
    neg = sum(1 for w in NEGATIVE if w in t)
    if pos == 0 and neg == 0:
        return 0.0
    return (pos - neg) / (pos + neg)


def _robust_z(window: list[float], value: float) -> float:
    """median/MAD z of `value` against a prior window (leak-free)."""
    if len(window) < 5:
        return 0.0
    med = median(window)
    devs = [abs(x - med) for x in window]
    mad = median(devs) or 1e-9
    return (value - med) / (1.4826 * mad)


def build_features(db: Session, company: models.Company, lookback_days: int = 120):
    since = datetime.utcnow() - timedelta(days=lookback_days)
    prices = (
        db.query(models.PriceDaily)
        .filter(models.PriceDaily.company_id == company.id, models.PriceDaily.date >= since.date())
        .order_by(models.PriceDaily.date)
        .all()
    )
    # news stream -> per-day count and sentiment
    rows = (
        db.query(models.Article)
        .join(models.ArticleTag, models.ArticleTag.article_id == models.Article.id)
        .filter(models.ArticleTag.company_id == company.id, models.Article.published_at >= since)
        .all()
    )
    per_day: dict[str, list[float]] = {}
    for a in rows:
        key = a.published_at.strftime("%Y-%m-%d")
        per_day.setdefault(key, []).append(_sentiment(f"{a.title} {a.excerpt or ''}"))

    X, y, dates = [], [], []
    closes = [p.close for p in prices]
    vols = [float(p.volume) for p in prices]
    day_keys = [p.date.strftime("%Y-%m-%d") for p in prices]
    for i in range(5, len(prices) - 1):
        ret1 = (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0
        ret5 = (closes[i] - closes[i - 5]) / closes[i - 5] if closes[i - 5] else 0.0
        vz = _robust_z(vols[max(0, i - 20):i], vols[i])
        news3 = per_day.get(day_keys[i], []) + per_day.get(day_keys[i - 1], []) + per_day.get(
            day_keys[i - 2], []
        )
        cnt = float(len(news3))
        sent = sum(news3) if news3 else 0.0
        X.append([ret1, ret5, vz, cnt, sent])
        y.append(1 if closes[i + 1] > closes[i] else 0)
        dates.append(day_keys[i])
    return X, y, dates, prices, prices[-1] if prices else None


def _standardize_fit(X):
    n, d = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(d)]
    stds = []
    for j in range(d):
        var = sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(1, n - 1)
        stds.append(var ** 0.5 or 1e-9)
    return means, stds


def _scale(row, means, stds):
    return [(row[j] - means[j]) / stds[j] for j in range(len(row))]


def _train(X, y, epochs: int = 400, lr: float = 0.1, l2: float = 0.01):
    d = len(X[0])
    w = [0.0] * d
    b = 0.0
    n = len(X)
    for _ in range(epochs):
        gw = [0.0] * d
        gb = 0.0
        for xi, yi in zip(X, y, strict=False):
            p = _sigmoid(sum(w[j] * xi[j] for j in range(d)) + b)
            err = p - yi
            for j in range(d):
                gw[j] += err * xi[j]
            gb += err
        for j in range(d):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * gb / n
    return w, b


def _predict_prob(row, w, b):
    return _sigmoid(sum(w[j] * row[j] for j in range(len(w))) + b)


def forecast(db: Session, company: models.Company, lookback_days: int = 120) -> dict:
    X, y, dates, prices, last = build_features(db, company, lookback_days)
    if len(X) < 30:
        raise ValueError(
            f"not enough price history to train ({len(X)} rows; need >=30). "
            "seed or crawl more days for this company."
        )

    # walk-forward: train on everything up to t-1, predict t
    correct = 0
    tests = 0
    up_labels = 0
    for split in range(25, len(X)):
        means, stds = _standardize_fit(X[:split])
        Xs = [_scale(r, means, stds) for r in X[:split]]
        w, b = _train(Xs, y[:split])
        row = _scale(X[split], means, stds)
        pred = 1 if _predict_prob(row, w, b) >= 0.5 else 0
        correct += int(pred == y[split])
        up_labels += int(y[split])
        tests += 1

    wf_acc = correct / tests if tests else None
    baseline = max(up_labels, tests - up_labels) / tests if tests else None

    # final model on all data, forecast the next (unknown) day
    means, stds = _standardize_fit(X)
    Xs = [_scale(r, means, stds) for r in X]
    w, b = _train(Xs, y)

    # features for the "next" day: recompute on the latest bar with the same
    # trailing-news logic (t+1 news is unknown, so carry the last 3 days)
    next_row = X[-1]
    prob_up = _predict_prob(_scale(next_row, means, stds), w, b)

    ranked = sorted(
        zip(FEATURE_NAMES, w, strict=False), key=lambda kv: abs(kv[1]), reverse=True
    )[:3]
    top_features = [
        {"name": n, "weight": round(val, 4), "direction": "up" if val >= 0 else "down"}
        for n, val in ranked
    ]

    return {
        "company_id": company.id,
        "symbol": company.symbol,
        "method": "logistic regression (plain gradient descent), walk-forward",
        "train_size": len(X),
        "test_size": tests,
        "walk_forward_accuracy": round(wf_acc, 3) if wf_acc is not None else None,
        "baseline_accuracy": round(baseline, 3) if baseline is not None else None,
        "prob_up": round(prob_up, 3),
        "prediction": "up" if prob_up >= 0.5 else "down",
        "top_features": top_features,
        "generated_at": datetime.utcnow(),
    }
