from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_role
from ..models import Article, ArticleTag, Company, PriceDaily, User
from ..schemas import (
    BehaviorSummary,
    CompanyCreate,
    CompanyOut,
    ComparisonOut,
    DirectionForecast,
    PriceOut,
)
from ..services.analysis import behavior_summary as build_behavior

router = APIRouter()


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return (
        db.query(Company)
        .filter(Company.is_active == True)  # noqa: E712
        .order_by(Company.symbol)
        .all()
    )


@router.post("", response_model=CompanyOut, status_code=201)
def add_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    exists = db.query(Company).filter(Company.symbol == payload.symbol).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, "symbol already tracked")
    company = Company(**payload.model_dump())
    db.add(company)
    db.commit()
    # new watchlist entry => re-run tagging so old articles pick it up
    from ..services.ingest import retag_all

    try:
        retag_all(db)
    except Exception:
        db.rollback()
    return company


@router.patch("/{company_id}", response_model=CompanyOut)
def update_company(
    company_id: int,
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
    for k, v in payload.model_dump().items():
        setattr(company, k, v)
    db.commit()
    return company


@router.get("/{company_id}/prices", response_model=list[PriceOut])
def prices(
    company_id: int,
    range: str = Query("30d", pattern=r"^\d+[dwm]$"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
    mult = {"d": 1, "w": 7, "m": 30}[range[-1]]
    n = int(range[:-1]) * mult
    since = date.today() - timedelta(days=n)
    rows = (
        db.query(PriceDaily)
        .filter(PriceDaily.company_id == company_id, PriceDaily.date >= since)
        .order_by(PriceDaily.date)
        .all()
    )
    if not rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no price data for this range, seed or crawl first")
    return rows


@router.get("/{company_id}/behavior-summary", response_model=BehaviorSummary)
def behavior(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
    return build_behavior(db, company)


@router.get("/{company_id}/direction-forecast", response_model=DirectionForecast)
def direction_forecast(
    company_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Exploratory, not advice. See services/classifier.py for the caveat and
    the walk-forward evaluation it reports alongside the prediction."""
    company = db.get(Company, company_id)
    if not company:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
    from ..services.classifier import forecast

    try:
        return forecast(db, company)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("/comparison", response_model=ComparisonOut)
def comparison(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """The three cross-company lenses the viewer screen uses. With a 5-10
    symbol watchlist it's cheaper and clearer to pull the window's prices and
    compute the metrics in python than to hand-write windowed SQL."""
    thirty = date.today() - timedelta(days=30)
    companies = (
        db.query(Company).filter(Company.is_active == True).all()  # noqa: E712
    )
    rows = (
        db.query(PriceDaily)
        .filter(PriceDaily.date >= thirty)
        .order_by(PriceDaily.date)
        .all()
    )
    by_company: dict[int, list[PriceDaily]] = {}
    for r in rows:
        by_company.setdefault(r.company_id, []).append(r)

    def _stdev(xs):
        if len(xs) < 2:
            return 0.0
        m = sum(xs) / len(xs)
        return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5

    most_volatile = []
    most_active = []
    for co in companies:
        prices = by_company.get(co.id, [])
        if not prices:
            continue
        rets = [
            (prices[i].close - prices[i - 1].close) / prices[i - 1].close
            for i in range(1, len(prices))
            if prices[i - 1].close
        ]
        vol = _stdev(rets)
        most_volatile.append(
            {
                "company_id": co.id,
                "symbol": co.symbol,
                "metric": "daily_volatility",
                "value": round(vol, 4),
                "label": f"{vol*100:.2f}% avg daily swing",
            }
        )
        total_vol = sum(p.volume for p in prices)
        most_active.append(
            {
                "company_id": co.id,
                "symbol": co.symbol,
                "metric": "volume",
                "value": round(total_vol, 2),
                "label": f"{total_vol/1e6:.1f}M shares",
            }
        )

    most_volatile.sort(key=lambda x: x["value"], reverse=True)
    most_active.sort(key=lambda x: x["value"], reverse=True)

    hot = (
        db.query(Company.id, Company.symbol, func.count(ArticleTag.id).label("n"))
        .join(ArticleTag, ArticleTag.company_id == Company.id)
        .join(Article, Article.id == ArticleTag.article_id)
        .filter(Article.published_at >= datetime.combine(thirty, time.min))
        .group_by(Company.id, Company.symbol)
        .order_by(func.count(ArticleTag.id).desc())
        .all()
    )
    most_in_news = []
    for r in hot:
        if not r.n:
            continue
        most_in_news.append(
            {
                "company_id": r.id,
                "symbol": r.symbol,
                "metric": "articles",
                "value": int(r.n),
                "label": f"{r.n} tagged articles",
            }
        )

    return {
        "most_volatile": most_volatile[:8],
        "most_active": most_active[:8],
        "most_in_news": most_in_news[:8],
    }
