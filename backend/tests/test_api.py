"""Smoke + behaviour tests for the API surface."""


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["ok"] is True


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
