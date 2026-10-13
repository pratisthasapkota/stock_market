from urllib.parse import urlparse

from celery import Celery
from celery.schedules import crontab

from ..config import settings

_parts = urlparse(settings.redis_url)
_result_backend = f"redis://{_parts.hostname or 'localhost'}:{_parts.port or 6379}/1"

celery = Celery("stock", broker=settings.redis_url, backend=_result_backend)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kathmandu",
    enable_utc=True,
    task_queues={
        "crawl": {},
        "categorize": {},
        "default": {"binding": True},
    },
    task_routes={
        "app.tasks.crawl.*": {"queue": "crawl"},
        "app.tasks.categorize.*": {"queue": "categorize"},
    },
    beat_schedule={
        # news crawls run on an offset so we're not hammering all portals at once
        "crawl-merolagani": {
            "task": "app.tasks.crawl.crawl_portal",
            "schedule": crontab(hour="*/4", minute=7),
            "args": ("merolagani",),
        },
        "crawl-sharesansar": {
            "task": "app.tasks.crawl.crawl_portal",
            "schedule": crontab(hour="*/4", minute=22),
            "args": ("sharesansar",),
        },
        "crawl-nepsealpha": {
            "task": "app.tasks.crawl.crawl_portal",
            "schedule": crontab(hour="*/4", minute=37),
            "args": ("nepsealpha",),
        },
        "crawl-bizmandu": {
            "task": "app.tasks.crawl.crawl_portal",
            "schedule": crontab(hour="*/4", minute=52),
            "args": ("bizmandu",),
        },
        # market data is only meaningful after the exchange closes; run once daily
        "crawl-market-data": {
            "task": "app.tasks.crawl.crawl_market",
            "schedule": crontab(hour=19, minute=30),
        },
        # keep tagging consistent if watchlist changed mid-day
        "retag-everything": {
            "task": "app.tasks.categorize.retag_all",
            "schedule": crontab(hour="*/6", minute=45),
        },
    },
)

celery.autodiscover_tasks(["app.tasks"])