"""Everything that moves data into the store, so spiders never touch the DB
through their own code paths.

Spiders emit items, the crawler pipeline calls upsert_* here, and the batch
re-tag job reuses the same functions. Keep it here and the rules stay in one
place.
"""
import logging

from sqlalchemy.orm import Session

from .. import models
from .categorize import tag_article

log = logging.getLogger("ingest")


def upsert_company(db: Session, symbol, name, sector="", aliases="") -> models.Company:
    row = db.query(models.Company).filter_by(symbol=symbol).first()
    if row:
        row.name, row.sector = name, sector
        if aliases:
            row.aliases = aliases
        return row
    row = models.Company(symbol=symbol, name=name, sector=sector, aliases=aliases)
    db.add(row)
    db.flush()
    return row


def upsert_prices(db: Session, company_id: int, rows) -> int:
    """rows: list of dict(date, open, high, low, close, volume, turnover).
    Returns the number of new rows inserted (updates don't count)."""
    new = 0
    for r in rows:
        existing = (
            db.query(models.PriceDaily)
            .filter_by(company_id=company_id, date=r["date"])
            .first()
        )
        if existing:
            for k, v in r.items():
                setattr(existing, k, v)
            continue
        db.add(models.PriceDaily(company_id=company_id, **r))
        new += 1
    db.flush()
    return new


def upsert_floorsheet(db: Session, company_id: int, rows) -> int:
    new = 0
    for r in rows:
        existing = (
            db.query(models.Floorsheet)
            .filter_by(
                company_id=company_id,
                date=r["date"],
                buyer_broker=r["buyer_broker"],
                seller_broker=r["seller_broker"],
                rate=r["rate"],
            )
            .first()
        )
        if existing:
            continue
        db.add(models.Floorsheet(company_id=company_id, **r))
        new += 1
    db.flush()
    return new


def upsert_articles(db: Session, items) -> int:
    """Dedupes on url. New articles are tagged straight away with the current
    watchlist, so the dashboard never shows an untagged story."""

    def _load_companies():
        return db.query(models.Company).filter(models.Company.is_active == True).all()  # noqa: E712

    companies = _load_companies()
    new = 0
    for it in items:
        url = (it.get("url") or "").strip()
        if not url:
            continue
        existing = db.query(models.Article).filter_by(url=url).first()
        if existing:
            continue
        article = models.Article(
            title=it.get("title", "").strip(),
            excerpt=it.get("excerpt", "")[:1200] or "",
            body=it.get("body", ""),
            source=it.get("source", ""),
            url=url,
            published_at=it.get("published_at"),
        )
        db.add(article)
        db.flush()
        for tag in tag_article(article.title, article.body, companies):
            added = models.ArticleTag(**tag, article_id=article.id)
            db.add(added)
        new += 1
    db.commit()
    return new


def retag_all(db: Session):
    """Re-runs tagging across every untagged or stale-credibility article.
    Called after the watchlist changes, which makes "add a company" a data
    change instead of a code change."""
    companies = (
        db.query(models.Company).filter(models.Company.is_active == True).all()  # noqa: E712
    )
    articles = db.query(models.Article).all()
    changed = 0
    for a in articles:
        db.query(models.ArticleTag).filter_by(article_id=a.id).delete()
        for tag in tag_article(a.title, a.body, companies):
            db.add(models.ArticleTag(**tag, article_id=a.id))
        changed += 1
    db.commit()
    return changed