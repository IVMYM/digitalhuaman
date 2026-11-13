GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!"
    b"\xf9\x04\x00\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00"
    b"\x00\x02\x02D\x01\x00;"
)


def test_avatar_voice_persona_and_knowledge(client, auth):
    voice = client.post(
        "/api/voices",
        headers=auth,
        json={"name": "云夏", "engine": "edge-tts", "endpoint_url": "", "voice_id": "zh-CN-YunxiaNeural"},
    )
    assert voice.status_code == 200, voice.text
    voice_id = voice.json()["id"]
    assert voice.json()["livetalking_tts"] == "edgetts"

    avatar = client.post(
        "/api/avatars",
        headers=auth,
        json={
            "name": "讲解员",
            "type": "wav2lip",
            "livetalking_avatar_id": "wav2lip256_avatar1",
            "default_voice_id": voice_id,
            "is_default": True,
        },
    )
    assert avatar.status_code == 200, avatar.text
    avatar_id = avatar.json()["id"]
    assert avatar.json()["is_default"] is True
    assert avatar.json()["default_voice_name"] == "云夏"

    preview = client.post(
        f"/api/avatars/{avatar_id}/preview",
        headers=auth,
        files={"file": ("face.gif", GIF, "image/gif")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["has_preview"] is True
    image = client.get(f"/api/avatars/{avatar_id}/preview", headers=auth)
    assert image.status_code == 200
    assert image.content.startswith(b"GIF89a")

    rejected = client.post(
        f"/api/avatars/{avatar_id}/preview",
        headers=auth,
        files={"file": ("notes.txt", b"nope", "text/plain")},
    )
    assert rejected.status_code == 400

    brain = client.post(
        "/api/brains",
        headers=auth,
        json={
            "name": "通义",
            "preset": "qwen",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-live-VERYSECRET-9999",
            "model_name": "qwen-plus",
            "temperature": 0.4,
            "max_tokens": 512,
            "system_prompt": "你是讲解员。",
        },
    )
    assert brain.status_code == 200, brain.text
    brain_id = brain.json()["id"]

    kb = client.post(
        "/api/knowledge-bases",
        headers=auth,
        json={"name": "售后", "description": "退换货说明"},
    )
    assert kb.status_code == 200, kb.text
    kb_id = kb.json()["id"]
    document = client.post(
        f"/api/knowledge-bases/{kb_id}/documents",
        headers=auth,
        files={"file": ("policy.md", "退款政策：七天内可退。".encode(), "text/markdown")},
    )
    assert document.status_code == 200, document.text
    assert document.json()["has_text"] is True
    listed = client.get(f"/api/knowledge-bases/{kb_id}/documents", headers=auth)
    assert listed.status_code == 200
    assert listed.json()[0]["original_name"] == "policy.md"

    persona = client.post(
        "/api/personas",
        headers=auth,
        json={
            "name": "展厅讲解员",
            "description": "默认接待",
            "avatar_id": avatar_id,
            "brain_id": brain_id,
            "voice_id": voice_id,
            "knowledge_base_id": kb_id,
            "enabled": True,
            "is_default": True,
        },
    )
    assert persona.status_code == 200, persona.text
    persona_id = persona.json()["id"]
    assert persona.json()["knowledge_base_name"] == "售后"

    renamed = client.put(
        f"/api/personas/{persona_id}",
        headers=auth,
        json={
            "name": "展厅讲解员",
            "description": "已更新",
            "avatar_id": avatar_id,
            "brain_id": brain_id,
            "voice_id": voice_id,
            "knowledge_base_id": kb_id,
            "enabled": False,
            "is_default": True,
        },
    )
    assert renamed.status_code == 200
    assert renamed.json()["enabled"] is False
    assert renamed.json()["is_default"] is False

    blocked = client.delete(f"/api/brains/{brain_id}", headers=auth)
    assert blocked.status_code == 409

    removed_doc = client.delete(f"/api/knowledge-bases/{kb_id}/documents/{document.json()['id']}", headers=auth)
    assert removed_doc.status_code == 200
    assert client.get(f"/api/knowledge-bases/{kb_id}/documents", headers=auth).json() == []

    assert client.delete(f"/api/personas/{persona_id}", headers=auth).status_code == 200
    assert client.delete(f"/api/avatars/{avatar_id}", headers=auth).status_code == 200
    assert client.delete(f"/api/voices/{voice_id}", headers=auth).status_code == 200
    assert client.delete(f"/api/brains/{brain_id}", headers=auth).status_code == 200
    assert client.delete(f"/api/knowledge-bases/{kb_id}", headers=auth).status_code == 200


def test_presets_and_single_default_avatar(client, auth):
    presets = client.get("/api/brains/presets", headers=auth)
    assert presets.status_code == 200
    ids = {item["id"] for item in presets.json()}
    assert {"ollama", "vllm", "deepseek", "qwen", "openai"} <= ids

    first = client.post(
        "/api/avatars",
        headers=auth,
        json={"name": "甲", "type": "live2d", "is_default": True},
    )
    second = client.post(
        "/api/avatars",
        headers=auth,
        json={"name": "乙", "type": "other", "is_default": True},
    )
    assert first.status_code == 200 and second.status_code == 200
    rows = {item["name"]: item["is_default"] for item in client.get("/api/avatars", headers=auth).json()}
    assert rows["甲"] is False
    assert rows["乙"] is True
