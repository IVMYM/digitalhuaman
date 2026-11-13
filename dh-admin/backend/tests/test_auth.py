def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_login_and_me(client):
    denied = client.get("/api/auth/me")
    assert denied.status_code == 401

    bad = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert bad.status_code == 401
    assert "密码" in bad.json()["detail"]

    ok = client.post("/api/auth/login", json={"username": "admin", "password": "secret-pass"})
    assert ok.status_code == 200
    token = ok.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "admin"


def test_change_password(client):
    login = client.post("/api/auth/login", json={"username": "admin", "password": "secret-pass"})
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    wrong = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "secret-pass", "new_password": "short"},
    )
    assert wrong.status_code == 422

    changed = client.post(
        "/api/auth/change-password",
        headers=headers,
        json={"old_password": "secret-pass", "new_password": "new-secret-9"},
    )
    assert changed.status_code == 200
    assert client.post("/api/auth/login", json={"username": "admin", "password": "secret-pass"}).status_code == 401
    again = client.post("/api/auth/login", json={"username": "admin", "password": "new-secret-9"})
    assert again.status_code == 200


def test_dashboard_requires_auth_and_counts(client, auth):
    assert client.get("/api/dashboard").status_code == 401
    response = client.get("/api/dashboard", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["counts"]["avatars"] == 0
    assert body["status"]["database"] == "ok"
    assert body["status"]["runtime_token_configured"] is True
    assert body["status"]["data_dir_writable"] is True
