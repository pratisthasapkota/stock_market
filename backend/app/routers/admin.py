from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..deps import require_role
from ..events import publish
from ..models import Alert, CrawlRun, JobLog, User
from ..schemas import AlertOut, CrawlRunOut, UserOut

router = APIRouter()
_pool = ThreadPoolExecutor(max_workers=2)


@router.get("/crawl-runs", response_model=list[CrawlRunOut])
def list_crawl_runs(
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    return (
        db.query(CrawlRun)
        .order_by(CrawlRun.id.desc())
        .limit(limit)
        .all()
    )


@router.post("/crawl-runs", response_model=CrawlRunOut, status_code=202)
def trigger_crawl(
    portal: str = Query(..., pattern=r"^(all|merolagani|sharesansar|nepsealpha|bizmandu|market)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Admin-only. Fans out to celery; without redis it runs inline in a
    worker thread so local demos still work."""
    run = CrawlRun(
        portal=portal,
        status="queued",  # admin sees it immediately even before the worker picks it up
        triggered_by_id=user.id,
    )
    db.add(run)
    db.commit()

    if settings.inline_jobs or not settings.redis_url:
        _pool.submit(_run_inline, portal, run.id)
    else:
        from ..tasks.crawl import crawl_market, crawl_portal

        if portal == "market":
            crawl_market.delay(triggered_by=user.id, run_id=run.id)
        elif portal == "all":
            for name in ("merolagani", "sharesansar", "nepsealpha", "bizmandu"):
                crawl_portal.delay(name, triggered_by=user.id, run_id=run.id)
        else:
            crawl_portal.delay(portal, triggered_by=user.id, run_id=run.id)
    return run


def _run_inline(portal: str, run_id: int):
    try:
        if portal == "market":
            from ..tasks.crawl import crawl_market

            crawl_market(triggered_by=None, run_id=run_id)
        elif portal == "all":
            from ..tasks.crawl import crawl_portal

            for name in ("merolagani", "sharesansar", "nepsealpha", "bizmandu"):
                crawl_portal(name, run_id=run_id)
        else:
            from ..tasks.crawl import crawl_portal

            crawl_portal(portal, run_id=run_id)
    except Exception as exc:  # surfaced to admin view, never just console
        db = SessionLocal()
        try:
            run = db.get(CrawlRun, run_id)
            run.status = "error"
            run.error = str(exc)[:2000]
            run.finished_at = datetime.utcnow()
            db.commit()
        finally:
            db.close()


@router.post("/crawl-runs/{run_id}/retry", response_model=CrawlRunOut)
def retry_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    run = db.get(CrawlRun, run_id)
    if not run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    # re-run the same portal as a fresh entry; the old record stays as history
    portal = "market" if run.portal == "nepse_market" else run.portal
    return trigger_crawl(portal, db, user)


@router.post("/retag")
def retag_now(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    try:
        from ..tasks.categorize import retag_all_task

        if settings.inline_jobs:
            result = retag_all_task()
        else:
            result = retag_all_task.delay().get(timeout=120)
    except Exception as exc:
        db.add(JobLog(kind="retag", status="error", detail=str(exc)[:2000]))
        db.commit()
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"retag failed: {exc}"
        ) from exc
    return {"retagged": result.get("articles_processed", 0)}


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    return db.query(User).order_by(User.id).all()


@router.post("/users/{user_id}/role")
def set_role(
    user_id: int,
    role: str = Query(..., pattern=r"^(viewer|analyst|admin)$"),
    db: Session = Depends(get_db),
    admin: User = Depends(require_role("admin")),
):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    if target.id == admin.id and role != "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "can't demote yourself")
    target.role = role
    db.commit()
    return {"ok": True, "user_id": user_id, "role": role}


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    only_open: bool = Query(False),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    q = db.query(Alert)
    if only_open:
        q = q.filter(Alert.acknowledged == False)  # noqa: E712
    return q.order_by(Alert.id.desc()).limit(limit).all()


@router.post("/alerts/check")
def check_alerts(db: Session = Depends(get_db), _: User = Depends(require_role("admin"))):
    """Run the anomaly scan now instead of waiting for the next market crawl.
    Useful right after seeding, and it is how the demo produces alerts."""
    from ..services.alerts import scan_volume_anomalies

    created = scan_volume_anomalies(db)
    for a in created:
        publish(
            {
                "type": "alert_created",
                "alert_id": a.id,
                "company_id": a.company_id,
                "severity": a.severity,
                "message": a.message,
            }
        )
    return {"created": len(created)}


@router.post("/alerts/{alert_id}/ack")
def ack_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role("admin")),
):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "alert not found")
    alert.acknowledged = True
    db.commit()
    return {"ok": True, "alert_id": alert_id}
