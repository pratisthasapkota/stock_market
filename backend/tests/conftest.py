"""Test setup.

The env vars are set before any `app.*` import so Settings picks up an isolated
sqlite file and never tries to seed or reach redis. Data is inserted directly
through the ORM so the tests exercise the routers/services, not the seeding
script.
"""
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

TEST_DB = BACKEND_DIR / "data" / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["REDIS_URL"] = "redis://127.0.0.1:6399/0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import hash_password  # noqa: E402

USERS = {
    "admin": "admin123",
    "analyst": "analyst123",
    "viewer": "viewer123",
}


def _make_prices(days: int, volume_spike_last: bool):
    rows = []
    price = 500.0
    for i in range(days):
        price = price * (1.0 + (0.004 if i % 2 else -0.003))
        vol = float(1000 if i % 2 else 1100)
        if volume_spike_last and i == days - 1:
            vol = 8000.0
        day = date.today() - timedelta(days=days - 1 - i)
        rows.append(
            {
                "date": day,
                "open": round(price * 0.99, 2),
                "high": round(price * 1.02, 2),
                "low": round(price * 0.98, 2),
                "close": round(price, 2),
                "volume": vol,
                "turnover": round(vol * price, 2),
            }
        )
    return rows


@pytest.fixture(scope="session", autouse=True)
def _db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for username, pw in USERS.items():
            db.add(
                models.User(
                    email=f"{username}@example.com",
                    username=username,
                    role=username,
                    password_hash=hash_password(pw),
                )
            )
        db.flush()

        long_co = models.Company(
            symbol="TESTCO", name="Test Company Ltd", sector="Commercial Bank", aliases="Test Co"
        )
        short_co = models.Company(symbol="SHORT", name="Short History Ltd", sector="Others")
        db.add_all([long_co, short_co])
        db.flush()

        db.add_all(
            [models.PriceDaily(company_id=long_co.id, **r) for r in _make_prices(45, True)]
            + [models.PriceDaily(company_id=short_co.id, **r) for r in _make_prices(5, False)]
        )

        tagged = models.Article(
            title="TESTCO posts strong profit",
            body="Test Company reported profit growth.",
            source="merolagani",
            url="https://example.com/a/1",
            published_at=datetime.utcnow() - timedelta(days=1),
        )
        untagged = models.Article(
            title="NEPSE index ends lower",
            body="Market commentary.",
            source="merolagani",
            url="https://example.com/a/2",
            published_at=datetime.utcnow() - timedelta(days=2),
        )
        db.add_all([tagged, untagged])
        db.flush()
        db.add(
            models.ArticleTag(
                article_id=tagged.id,
                company_id=long_co.id,
                confidence=0.9,
                method="keyword",
            )
        )
        db.commit()

        state = {"long_id": long_co.id, "short_id": short_co.id, "tagged": tagged.id, "untagged": untagged.id}
        yield state
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
        if TEST_DB.exists():
            TEST_DB.unlink()


@pytest.fixture
def ids(_db):
    return _db


@pytest.fixture
def client():
    # deliberately not a context manager: skips lifespan, so no seeding and no
    # redis listener task. Tables/data come from the _db fixture instead.
    return TestClient(app)


def _login(client, username):
    res = client.post(
        "/api/auth/login", data={"username": username, "password": USERS[username]}
    )
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def as_admin(client):
    return _login(client, "admin")


@pytest.fixture
def as_analyst(client):
    return _login(client, "analyst")


@pytest.fixture
def as_viewer(client):
    return _login(client, "viewer")
