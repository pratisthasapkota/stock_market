from datetime import datetime

try:
    from celery import shared_task
except ImportError:  # keeps inline mode free of the celery dependency

    def shared_task(*args, **kwargs):
        def _wrap(fn):
            fn.delay = lambda *a, **k: fn(*a, **k)  # type: ignore[attr-defined]
            return fn

        return _wrap(args[0]) if args and callable(args[0]) else _wrap

from ..database import SessionLocal
from ..events import publish
from ..services.ingest import retag_all


@shared_task(name="app.tasks.categorize.retag_all")
def retag_all_task():
    db = SessionLocal()
    try:
        changed = retag_all(db)
    finally:
        db.close()
    publish(
        {
            "type": "retag_finished",
            "articles_processed": changed,
            "at": datetime.utcnow().isoformat(),
        }
    )
    return {"articles_processed": changed}