import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .config import settings
from .database import SessionLocal, engine
from .errors import register_error_handlers
from .events import manager, start_listener
from .routers import admin, auth, companies, news, reports, ws

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
log = logging.getLogger("main")

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _bootstrap():
    models.Base.metadata.create_all(bind=engine)
    if not settings.seed_on_startup:
        return
    db = SessionLocal()
    try:
        has_company = db.query(models.Company).first()
        if not has_company:
            log.info("empty db, seeding demo data")
            import subprocess
            import sys

            subprocess.run(
                [sys.executable, "-m", "scripts.seed_demo"],
                cwd=str(BACKEND_DIR),
                check=False,
            )
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _bootstrap()
    manager.loop = asyncio.get_running_loop()
    listener = start_listener(manager)
    try:
        yield
    finally:
        listener.cancel()


app = FastAPI(
    title="NEPSE Research Dashboard",
    version="0.1.0",
    lifespan=lifespan,
    description=(
        "Crawls NEPSE news + trading data, tags articles by company, computes "
        "buyer/seller behaviour indicators and pushes live updates to dashboards."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(companies.router, prefix="/api/companies", tags=["companies"])
app.include_router(news.router, prefix="/api/news", tags=["news"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(reports.router, prefix="/api/reports", tags=["reports"])
app.include_router(ws.router, prefix="/ws", tags=["ws"])

register_error_handlers(app)


@app.get("/api/health")
def health():
    return {"ok": True, "ws_clients": manager.count}
