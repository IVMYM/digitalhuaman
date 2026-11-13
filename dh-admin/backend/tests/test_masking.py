import sqlite3


def _brain(client, auth, api_key="sk-live-VERYSECRET-9999"):
    response = client.post(
        "/api/brains",
        headers=auth,
        json={
            "name": "深度求索",
            "preset": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": api_key,
            "model_name": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 256,
            "system_prompt": "简短回答。",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _link(client, auth, brain_id):
    voice = client.post(
        "/api/voices",
        headers=auth,
        json={"name": "克隆", "engine": "cosyvoice", "endpoint_url": "http://127.0.0.1:9880", "voice_id": "demo"},
    ).json()
    avatar = client.post(
        "/api/avatars",
        headers=auth,
        json={"name": "形象", "type": "livetalking-musetalk", "livetalking_avatar_id": "musetalk_demo"},
    ).json()
    persona = client.post(
        "/api/personas",
        headers=auth,
        json={
            "name": "客服",
            "avatar_id": avatar["id"],
            "brain_id": brain_id,
            "voice_id": voice["id"],
            "enabled": True,
            "is_default": True,
        },
    )
    assert persona.status_code == 200, persona.text
    return persona.json()


def test_api_key_is_masked_and_encrypted(client, auth, data_dir):
    created = _brain(client, auth)
    assert created["has_api_key"] is True
    assert created["api_key_masked"] == "sk-••••9999"
    assert "VERYSECRET" not in client.get("/api/brains", headers=auth).text
    assert "api_key" not in created or created.get("api_key") in (None, "")

    database = sqlite3.connect(data_dir / "test.db")
    stored = database.execute("select api_key_encrypted from brains").fetchone()[0]
    database.close()
    assert stored
    assert "VERYSECRET" not in stored
    assert not stored.startswith("sk-")

    persona = _link(client, auth, created["id"])
    denied = client.get(f"/api/runtime/personas/{persona['id']}")
    assert denied.status_code == 401
    allowed = client.get(
        f"/api/runtime/personas/{persona['id']}",
        headers={"Authorization": "Bearer runtime-token"},
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["brain"]["api_key"] == "sk-live-VERYSECRET-9999"
    assert allowed.json()["avatar"]["livetalking_avatar_id"] == "musetalk_demo"
    assert allowed.json()["voice"]["engine"] == "cosyvoice"
    listing = client.get("/api/runtime/personas", headers={"X-Runtime-Token": "runtime-token"})
    assert listing.status_code == 200
    assert "api_key" not in listing.text

    kept = client.put(
        f"/api/brains/{created['id']}",
        headers=auth,
        json={
            "name": "深度求索",
            "preset": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "",
            "model_name": "deepseek-chat",
            "temperature": 0.2,
            "max_tokens": 256,
            "system_prompt": "简短回答。",
        },
    )
    assert kept.status_code == 200
    still = client.get(
        f"/api/runtime/personas/{persona['id']}",
        headers={"Authorization": "Bearer runtime-token"},
    )
    assert still.json()["brain"]["api_key"] == "sk-live-VERYSECRET-9999"

    masked = client.put(
        f"/api/brains/{created['id']}",
        headers=auth,
        json={
            "name": "深度求索",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-••••9999",
            "model_name": "deepseek-chat",
        },
    )
    assert masked.status_code == 422
