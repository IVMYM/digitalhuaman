import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("DATA_DIR", str(root))
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + (root / "test.db").as_posix())
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-value")
    monkeypatch.setenv("ENCRYPTION_KEY", "test-encryption-secret")
    monkeypatch.setenv("ADMIN_USERNAME", "admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "secret-pass")
    monkeypatch.setenv("RUNTIME_API_TOKEN", "runtime-token")
    monkeypatch.setenv("STATIC_DIR", "")
    monkeypatch.setenv("APP_ENV", "test")
    from app.config import get_settings

    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture()
def client(data_dir):
    from app.main import create_app

    application = create_app()
    with TestClient(application) as test_client:
        yield test_client


@pytest.fixture()
def auth(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": "secret-pass"})
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
