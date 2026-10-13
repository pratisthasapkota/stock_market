import logging
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

log = logging.getLogger("db")

connect_args = {}
if settings.database_url.startswith("sqlite"):
    # make sure the folder exists before sqlite tries to open the file
    path_part = settings.database_url.split("///")[-1]
    if path_part and path_part != ":memory:":
        Path(path_part).parent.mkdir(parents=True, exist_ok=True)
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
    # keep attribute values after commit: the crawl tasks read run counters
    # after they've closed their session, and we don't want a lazy reload
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


@event.listens_for(engine, "connect")
def _sqlite_pragmas(dbapi_conn, _record):
    # WAL keeps the crawler writers from blocking dashboard reads
    if settings.database_url.startswith("sqlite"):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_timeseries() -> bool:
    """Turn ``price_daily`` into a Timescale hypertable when on PostgreSQL.

    The ORM creates the tables at startup, which is *after* the Postgres init
    scripts have run, so the hypertable conversion lives here rather than in
    ``deploy/timescale-init.sql`` (that script would fail: the table does not
    exist yet). It is idempotent and a no-op on SQLite or a plain PostgreSQL
    without the Timescale extension, so local development is unaffected.

    Returns True if the hypertable is in place.
    """
    if engine.dialect.name != "postgresql":
        return False

    statements = (
        "CREATE EXTENSION IF NOT EXISTS timescaledb",
        "SELECT create_hypertable('price_daily', 'date', "
        "if_not_exists => TRUE, migrate_data => TRUE)",
        "CREATE INDEX IF NOT EXISTS ix_price_daily_company_date "
        "ON price_daily (company_id, date DESC)",
    )
    try:
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
        log.info("price_daily is a timescale hypertable")
        return True
    except Exception as exc:  # extension missing or no privilege
        log.warning("timescale hypertable setup skipped: %s", exc)
        return False
