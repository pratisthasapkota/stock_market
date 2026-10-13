"""Smoke + behaviour tests for the API surface."""


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_admin_expands_all_portals():
    from app.routers.admin import NEWS_PORTALS, _expand_portals

    assert _expand_portals("all") == NEWS_PORTALS
    assert _expand_portals("market") == ("market",)


def test_per_portal_delay_override(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "crawl_delay_seconds", 1.5)
    monkeypatch.setattr(settings, "crawl_portal_delays", {"sharesansar": 4.0})
    assert settings.crawl_delay_for("sharesansar") == 4.0
    assert settings.crawl_delay_for("merolagani") == 1.5


def test_login_and_me(client):
    res = client.post("/api/auth/login", data={"username": "viewer", "password": "viewer123"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["role"] == "viewer"


def test_login_bad_password(client):
    res = client.post("/api/auth/login", data={"username": "viewer", "password": "nope"})
    assert res.status_code == 401


def test_login_accepts_email(client):
    res = client.post(
        "/api/auth/login", data={"username": "viewer@example.com", "password": "viewer123"}
    )
    assert res.status_code == 200
    assert res.json()["role"] == "viewer"


def test_demo_accounts_listed(client):
    res = client.get("/api/auth/demo-accounts")
    assert res.status_code == 200
    body = res.json()
    assert {a["role"] for a in body} == {"admin", "analyst", "viewer"}
    assert all(a["password"] for a in body)


def test_demo_accounts_hidden_when_disabled(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "demo_mode", False)
    assert client.get("/api/auth/demo-accounts").status_code == 404


def test_demo_seed_reconciles_password(monkeypatch):
    """A changed DEMO_* config must overwrite an existing demo row, otherwise a
    re-pointed password would 401 against the hash left by the first seed."""
    from app import models
    from app.config import settings
    from app.database import SessionLocal
    from app.security import verify_password
    from app.services.demo import seed_demo_users

    monkeypatch.setattr(settings, "demo_admin_username", "reconcile_admin")
    monkeypatch.setattr(settings, "demo_admin_email", "reconcile_admin@demo.local")
    monkeypatch.setattr(settings, "demo_admin_password", "FirstPass@1")
    monkeypatch.setattr(settings, "demo_analyst_username", "reconcile_analyst")
    monkeypatch.setattr(settings, "demo_analyst_email", "reconcile_analyst@demo.local")
    monkeypatch.setattr(settings, "demo_viewer_username", "reconcile_viewer")
    monkeypatch.setattr(settings, "demo_viewer_email", "reconcile_viewer@demo.local")

    db = SessionLocal()
    try:
        seed_demo_users(db)
        db.commit()
        user = db.query(models.User).filter_by(username="reconcile_admin").one()
        assert verify_password("FirstPass@1", user.password_hash)

        monkeypatch.setattr(settings, "demo_admin_password", "SecondPass@2")
        assert seed_demo_users(db) >= 1
        db.commit()
        db.refresh(user)
        assert verify_password("SecondPass@2", user.password_hash)
    finally:
        for name in ("reconcile_admin", "reconcile_analyst", "reconcile_viewer"):
            db.query(models.User).filter_by(username=name).delete()
        db.commit()
        db.close()


def test_companies_requires_auth(client):
    assert client.get("/api/companies").status_code == 401


def test_companies_listed(client, as_viewer):
    res = client.get("/api/companies", headers=as_viewer)
    assert res.status_code == 200
    symbols = {c["symbol"] for c in res.json()}
    assert {"TESTCO", "SHORT"} <= symbols


def test_news_untagged_queue(client, as_analyst, ids):
    res = client.get("/api/news", params={"untagged": "true"}, headers=as_analyst)
    assert res.status_code == 200
    ids_returned = {a["id"] for a in res.json()}
    assert ids["untagged"] in ids_returned
    assert ids["tagged"] not in ids_returned


def test_recategorize_add_then_remove(client, as_analyst, ids):
    add = client.post(
        f"/api/news/{ids['untagged']}/recategorize",
        json={"company_id": ids["long_id"], "action": "add"},
        headers=as_analyst,
    )
    assert add.status_code == 200
    assert any(t["company_id"] == ids["long_id"] for t in add.json()["tags"])

    remove = client.post(
        f"/api/news/{ids['untagged']}/recategorize",
        json={"company_id": ids["long_id"], "action": "remove"},
        headers=as_analyst,
    )
    assert remove.status_code == 200
    assert not any(t["company_id"] == ids["long_id"] for t in remove.json()["tags"])


def test_recategorize_forbidden_for_viewer(client, as_viewer, ids):
    res = client.post(
        f"/api/news/{ids['tagged']}/recategorize",
        json={"company_id": ids["long_id"], "action": "add"},
        headers=as_viewer,
    )
    assert res.status_code == 403


def test_recategorize_unknown_article_is_enveloped(client, as_analyst, ids):
    res = client.post(
        "/api/news/999999/recategorize",
        json={"company_id": ids["long_id"], "action": "add"},
        headers=as_analyst,
    )
    assert res.status_code == 404
    body = res.json()
    assert body["error"]["code"] == "not_found"
    assert "detail" in body  # legacy field kept for the frontend


def test_reports_require_analyst(client, as_viewer, as_analyst, ids):
    assert client.get("/api/reports/comparison.csv", headers=as_viewer).status_code == 403
    ok = client.get("/api/reports/comparison.csv", headers=as_analyst)
    assert ok.status_code == 200
    assert ok.headers["content-type"].startswith("text/csv")
    assert "most_volatile" in ok.text


def test_behavior_report_unknown_company(client, as_analyst):
    res = client.get("/api/reports/behavior.csv", params={"company_id": 999999}, headers=as_analyst)
    assert res.status_code == 404


def test_alerts_scan_and_ack(client, as_admin, ids):
    check = client.post("/api/admin/alerts/check", headers=as_admin)
    assert check.status_code == 200
    assert check.json()["created"] >= 1

    listed = client.get("/api/admin/alerts", headers=as_admin)
    assert listed.status_code == 200
    alerts = listed.json()
    assert alerts
    first = alerts[0]
    assert first["kind"] == "volume_anomaly"
    assert first["company_id"] == ids["long_id"]

    ack = client.post(f"/api/admin/alerts/{first['id']}/ack", headers=as_admin)
    assert ack.status_code == 200

    # second scan must not duplicate the same (company, day, kind)
    again = client.post("/api/admin/alerts/check", headers=as_admin)
    assert again.json()["created"] == 0


def test_alerts_forbidden_for_analyst(client, as_analyst):
    assert client.get("/api/admin/alerts", headers=as_analyst).status_code == 403


def test_direction_forecast(client, as_viewer, ids):
    res = client.get(f"/api/companies/{ids['long_id']}/direction-forecast", headers=as_viewer)
    assert res.status_code == 200
    body = res.json()
    assert body["prediction"] in {"up", "down"}
    assert 0.0 <= body["prob_up"] <= 1.0
    assert body["test_size"] > 0
    assert body["top_features"]


def test_direction_forecast_needs_history(client, as_viewer, ids):
    res = client.get(f"/api/companies/{ids['short_id']}/direction-forecast", headers=as_viewer)
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "unprocessable"
