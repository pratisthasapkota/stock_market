import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

try:
    from celery import shared_task
except ImportError:  # inline mode (INLINE_JOBS=true) runs without celery installed

    def shared_task(*args, **kwargs):
        def _wrap(fn):
            fn.delay = lambda *a, **k: fn(*a, **k)  # type: ignore[attr-defined]
            return fn

        return _wrap(args[0]) if args and callable(args[0]) else _wrap

from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..database import SessionLocal
from ..events import publish
from ..services.alerts import scan_volume_anomalies
from ..services.ingest import (
    upsert_articles,
    upsert_floorsheet,
    upsert_prices,
)

log = logging.getLogger("tasks.crawl")

CRAWLERS_DIR = Path(__file__).resolve().parents[2] / "crawlers"

# spider name per portal. Keeping the map small on purpose: adding a portal
# means adding a spider, not editing this table forever.
NEWS_SPIDERS = {
    "merolagani": "merolagani_news",
    "sharesansar": "sharesansar_news",
    "nepsealpha": "nepsealpha_news",
    "bizmandu": "bizmandu_news",
}
MARKET_SPIDER = "nepse_market"


def _scrapy_run(
    spider: str, args: list[str], run_id: int, portal: str, page_budget: int | None = None
) -> tuple[str, int, str, int]:
    """Runs one spider in a subprocess so port memory + crash isolation.

    Rate limiting is per portal: the download delay (and its AutoThrottle start
    value) come from the portal's config override, falling back to the global
    default, and the user agent is centralised too. Returns
    (out_file, item_count, error_text, returncode)."""
    fd, out_file = tempfile.mkstemp(suffix=".jsonl", prefix="crawl_")
    os.close(fd)  # scrapy's pipeline reopens it for writing
    delay = settings.crawl_delay_for(portal)
    cmd = [
        sys.executable,
        "-m",
        "scrapy",
        "crawl",
        spider,
        "-a",
        f"out_file={out_file}",
        "-a",
        f"run_id={run_id}",
        "-s",
        "LOG_LEVEL=WARNING",
        "-s",
        f"DOWNLOAD_DELAY={delay}",
        "-s",
        f"AUTOTHROTTLE_START_DELAY={delay}",
        "-s",
        f"USER_AGENT={settings.crawl_user_agent}",
    ]
    if page_budget is not None:
        cmd += ["-a", f"page_budget={page_budget}"]
    cmd += args
    proc = subprocess.run(cmd, cwd=str(CRAWLERS_DIR), capture_output=True, text=True, timeout=420)
    has_data = Path(out_file).exists() and Path(out_file).stat().st_size > 0
    n = sum(1 for _ in open(out_file, encoding="utf-8")) if has_data else 0
    if n == 0:
        Path(out_file).unlink(missing_ok=True)
        out_file = ""
    return out_file, n, (proc.stderr[-1500:] if proc.returncode else ""), proc.returncode


def _mark_run(db: Session, run: models.CrawlRun, status="ok", error=""):
    run.status = status
    run.finished_at = datetime.utcnow()
    run.error = error
    db.commit()


@shared_task(name="app.tasks.crawl.crawl_portal")
def crawl_portal(portal: str, triggered_by: int | None = None, run_id: int | None = None):
    spider = NEWS_SPIDERS.get(portal)
    if not spider:
        log.error("unknown portal %s", portal)
        return
    db = SessionLocal()
    if run_id:
        run = db.get(models.CrawlRun, run_id)
        if not run:
            log.error("run %s not found", run_id)
            db.close()
            return
    else:
        run = models.CrawlRun(portal=portal, triggered_by_id=triggered_by)
        db.add(run)
    run.status = "running"
    run.started_at = datetime.utcnow()
    db.commit()

    ok = True
    try:
        out_file, n_written, err, code = _scrapy_run(
            spider, [], run.id, portal, page_budget=settings.crawl_max_pages_per_portal
        )
        run.items_found = n_written
        if out_file:
            run.items_new = _ingest_news_file(db, out_file, run.id)
        ok = code == 0  # a clean exit with no items just means "nothing new"
    except Exception as exc:
        ok = False
        err = str(exc)
    finally:
        _mark_run(db, run, "ok" if ok else "error", "" if ok else err)
        db.close()

    publish(
        {
            "type": "crawl_finished",
            "portal": portal,
            "run_id": run.id,
            "status": run.status,
            "items_found": run.items_found,
            "items_new": run.items_new,
            "at": datetime.utcnow().isoformat(),
        }
    )
    return {"run_id": run.id, "status": run.status, "items_new": run.items_new}


@shared_task(name="app.tasks.crawl.crawl_market")
def crawl_market(triggered_by: int | None = None, run_id: int | None = None):
    db = SessionLocal()
    companies = (
        db.query(models.Company).filter(models.Company.is_active == True).all()  # noqa: E712
    )
    watch = json.dumps(
        [{"symbol": c.symbol, "name": c.name, "id": c.id} for c in companies]
    )
    if not companies:
        db.close()
        return {"status": "skipped", "reason": "no companies in watchlist"}

    if run_id:
        run = db.get(models.CrawlRun, run_id)
        if not run:
            db.close()
            return {"status": "error", "reason": "run not found"}
    else:
        run = models.CrawlRun(portal="nepse_market", triggered_by_id=triggered_by)
        db.add(run)
    run.status = "running"
    run.started_at = datetime.utcnow()
    db.commit()

    ok, err = True, ""
    new_alerts = []
    try:
        out_file, n_written, err, code = _scrapy_run(
            MARKET_SPIDER, ["-a", f"watch={watch}"], run.id, "market"
        )
        run.items_found = n_written
        if out_file:
            run.items_new = _ingest_market_file(db, out_file)
        ok = code == 0
        # fresh prices in hand, so re-check the anomaly thresholds
        new_alerts = scan_volume_anomalies(db)
    except Exception as exc:
        ok = False
        err = str(exc)
    finally:
        _mark_run(db, run, "ok" if ok else "error", "" if ok else err)
        db.close()

    for a in new_alerts:
        publish(
            {
                "type": "alert_created",
                "alert_id": a.id,
                "company_id": a.company_id,
                "severity": a.severity,
                "message": a.message,
                "at": datetime.utcnow().isoformat(),
            }
        )

    publish(
        {
            "type": "market_finished",
            "run_id": run.id,
            "status": run.status,
            "at": datetime.utcnow().isoformat(),
        }
    )
    return {"run_id": run.id, "status": run.status}


def _ingest_news_file(db: Session, out_file: str, run_id: int) -> int:
    """Reading the spider's file is safe because dedupe happens on the DB
    side; repeated runs only re-touch existing urls."""
    items = []
    with open(out_file, encoding="utf-8") as fh:
        items = [json.loads(line) for line in fh]
    new = upsert_articles(db, items)
    run = db.get(models.CrawlRun, run_id)
    run.items_new = new
    db.commit()
    Path(out_file).unlink(missing_ok=True)
    return new


def _ingest_market_file(db: Session, out_file: str) -> int:
    prices_n = floorsheet_n = 0
    with open(out_file, encoding="utf-8") as fh:
        for line in fh:
            item = json.loads(line)
            if item.get("kind") == "price":
                prices_n += upsert_prices(db, item["company_id"], item["rows"])
            elif item.get("kind") == "floorsheet":
                floorsheet_n += upsert_floorsheet(db, item["company_id"], item["rows"])
    db.commit()
    Path(out_file).unlink(missing_ok=True)
    return prices_n + floorsheet_n
