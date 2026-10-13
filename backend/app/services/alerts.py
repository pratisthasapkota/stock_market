"""Alert scanning.

Right now there is one alert kind: a volume anomaly. The scan is a plain
function so it can be called from the market-crawl task (unattended), from an
admin "check now" button, or from a test, without duplicating the logic.
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from .analysis import detect_volume_anomalies

ALERT_KIND = "volume_anomaly"


def scan_volume_anomalies(db: Session, threshold: float | None = None, lookback_days: int = 60):
    """Create one alert per (company, day) that trips the robust-z threshold.
    Returns the alerts that were newly created by this call."""
    threshold = settings.volume_anomaly_z if threshold is None else threshold
    window = settings.volume_anomaly_lookback
    since = date.today() - timedelta(days=lookback_days)

    created = []
    companies = (
        db.query(models.Company).filter(models.Company.is_active == True).all()  # noqa: E712
    )
    for company in companies:
        prices = (
            db.query(models.PriceDaily)
            .filter(models.PriceDaily.company_id == company.id, models.PriceDaily.date >= since)
            .order_by(models.PriceDaily.date)
            .all()
        )
        if len(prices) < window + 1:
            continue
        for a in detect_volume_anomalies(prices, lookback=window, threshold=threshold):
            day = date.fromisoformat(a["date"])
            exists = (
                db.query(models.Alert)
                .filter_by(company_id=company.id, date=day, kind=ALERT_KIND)
                .first()
            )
            if exists:
                continue
            alert = models.Alert(
                company_id=company.id,
                date=day,
                kind=ALERT_KIND,
                severity="high" if abs(a["robust_z"]) >= 5 else "medium",
                message=f"{company.symbol}: {a['direction']} in volume "
                f"(z={a['robust_z']}, vol={a['volume']:.0f})",
                value=a["robust_z"],
            )
            db.add(alert)
            created.append(alert)

    if created:
        db.commit()
        for a in created:
            db.refresh(a)
    return created
