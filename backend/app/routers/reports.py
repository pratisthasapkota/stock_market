"""CSV exports for the analyst role.

Analysts are the ones who "export reports" per the brief. Everything streams
out of the same data the dashboards read, so an export can never disagree with
what is on screen.
"""
import csv
import io
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_role
from ..models import Article, ArticleTag, Company, User
from ..services.analysis import behavior_summary

router = APIRouter()


def _csv_response(rows: list[list], header: list[str], filename: str) -> Response:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/news.csv")
def news_csv(
    company_id: int | None = None,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("analyst")),
):
    since = datetime.combine(date.today() - timedelta(days=days), time.min)
    q = (
        db.query(Article)
        .filter(Article.published_at >= since)
        .order_by(Article.published_at.desc())
    )
    if company_id:
        q = q.join(ArticleTag, ArticleTag.article_id == Article.id).filter(
            ArticleTag.company_id == company_id
        )
    symbols = {c.id: c.symbol for c in db.query(Company).all()}

    rows = []
    for a in q.all():
        tags = ";".join(
            f"{symbols.get(t.company_id, '?')}:{t.confidence:.2f}{'*' if t.corrected else ''}"
            for t in a.tags
        )
        rows.append(
            [
                a.id,
                a.published_at.isoformat() if a.published_at else "",
                a.source,
                tags,
                a.title.replace("\n", " "),
                a.url,
            ]
        )
    return _csv_response(
        rows,
        ["id", "published_at", "source", "company_tags", "title", "url"],
        f"news_report_{date.today().isoformat()}.csv",
    )


@router.get("/behavior.csv")
def behavior_csv(
    company_id: int,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("analyst")),
):
    company = db.get(Company, company_id)
    if not company:
        from ..errors import NotFound

        raise NotFound("company not found")

    summary = behavior_summary(db, company, days)
    rows = [["section", "key", "value"]]
    rows.append(["summary", "symbol", company.symbol])
    rows.append(["summary", "window_days", days])
    rows.append(["summary", "vwap", summary["vwap"]])
    rows.append(["summary", "last_close", summary["last_close"]])
    rows.append(["summary", "pressure", summary["pressure"]])
    rows.append(["summary", "pressure_score", summary["pressure_score"]])
    np = summary["news_price_check"]
    rows.append(["news_vs_move", "sample_size", np.get("sample_size")])
    rows.append(["news_vs_move", "pearson_abs_return", np.get("pearson_abs_return")])
    rows.append(["news_vs_move", "pearson_volume", np.get("pearson_volume")])
    for a in summary["volume_anomalies"]:
        rows.append(["anomaly", a["date"], f"z={a['robust_z']} vol={a['volume']}"])
    for b in summary["broker_breakdown"]:
        rows.append(["broker", b["broker"], f"net={b['net_qty']} buy={b['buy_qty']} sell={b['sell_qty']}"])

    return _csv_response(
        rows[1:],
        rows[0],
        f"behavior_{company.symbol}_{date.today().isoformat()}.csv",
    )


@router.get("/comparison.csv")
def comparison_csv(
    db: Session = Depends(get_db),
    _: User = Depends(require_role("analyst")),
):
    # reuse the exact function the dashboard calls so the export can't drift
    from .companies import comparison

    data = comparison(db=db, _=None)  # type: ignore[arg-type]
    rows = []
    for key in ("most_volatile", "most_active", "most_in_news"):
        for r in data[key]:
            rows.append([key, r["company_id"], r["symbol"], r["metric"], r["value"], r["label"]])
    return _csv_response(
        rows,
        ["group", "company_id", "symbol", "metric", "value", "label"],
        f"comparison_{date.today().isoformat()}.csv",
    )
