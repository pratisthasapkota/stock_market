from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

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
