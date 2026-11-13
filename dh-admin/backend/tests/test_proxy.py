import app.services.llm as llm


class Recorder:
    calls = []


class FakeResponse:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = ""
        self.content = b""
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload


class FakeStream:
    def __init__(self, lines):
        self.status_code = 200
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b""


class FakeClient:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, json=None, headers=None):
        Recorder.calls.append({"url": url, "json": json, "headers": headers, "stream": False})
        return FakeResponse(
            {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": "模拟回复"}, "finish_reason": "stop"}
                ],
            }
        )

    def stream(self, method, url, json=None, headers=None):
        Recorder.calls.append({"url": url, "json": json, "headers": headers, "stream": True})
        return FakeStream(
            [
                'data: {"choices":[{"delta":{"content":"你"}}]}',
                'data: {"choices":[{"delta":{"content":"好"}}]}',
                "data: [DONE]",
            ]
        )


def _install(monkeypatch):
    Recorder.calls = []
    monkeypatch.setattr(llm.httpx, "AsyncClient", FakeClient)


def _persona(client, auth, *, name, prompt, default=False, kb_id=None):
    voice = client.post(
        "/api/voices",
        headers=auth,
        json={"name": f"声音-{name}", "engine": "fish-speech", "endpoint_url": "http://127.0.0.1:8080", "voice_id": "v1"},
    ).json()
    avatar = client.post(
        "/api/avatars",
        headers=auth,
        json={"name": f"形象-{name}", "type": "ernerf", "livetalking_avatar_id": f"avatar-{name}"},
    ).json()
    brain = client.post(
        "/api/brains",
        headers=auth,
        json={
            "name": f"大脑-{name}",
            "base_url": "http://llm.internal/v1",
            "api_key": "sk-upstream-key",
            "model_name": "qwen-real",
            "temperature": 0.3,
            "max_tokens": 128,
            "system_prompt": prompt,
        },
    ).json()
    payload = {
        "name": name,
        "avatar_id": avatar["id"],
        "brain_id": brain["id"],
        "voice_id": voice["id"],
        "enabled": True,
        "is_default": default,
    }
    if kb_id:
        payload["knowledge_base_id"] = kb_id
    created = client.post("/api/personas", headers=auth, json=payload)
    assert created.status_code == 200, created.text
    return created.json()


def test_chat_proxy_and_sse(client, auth, monkeypatch):
    _install(monkeypatch)
    kb = client.post("/api/knowledge-bases", headers=auth, json={"name": "手册", "description": ""}).json()
    uploaded = client.post(
        f"/api/knowledge-bases/{kb['id']}/documents",
        headers=auth,
        files={"file": ("policy.md", "退款政策：七天内可退。".encode(), "text/markdown")},
    )
    assert uploaded.status_code == 200
    default = _persona(client, auth, name="默认角色", prompt="PROMPT-DEFAULT", default=True, kb_id=kb["id"])
    other = _persona(client, auth, name="备用角色", prompt="PROMPT-OTHER", default=False)

    denied = client.post("/v1/chat/completions", json={"model": "默认角色", "messages": [{"role": "user", "content": "在吗"}]})
    assert denied.status_code == 401

    direct = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer runtime-token"},
        json={
            "model": "not-a-persona",
            "messages": [{"role": "system", "content": "上游自带人设"}, {"role": "user", "content": "退款怎么走"}],
            "stream": False,
        },
    )
    assert direct.status_code == 200, direct.text
    assert direct.json()["choices"][0]["message"]["content"] == "模拟回复"
    sent = Recorder.calls[-1]
    assert sent["stream"] is False
    assert sent["url"] == "http://llm.internal/v1/chat/completions"
    assert sent["headers"]["Authorization"] == "Bearer sk-upstream-key"
    assert sent["json"]["model"] == "qwen-real"
    system = sent["json"]["messages"][0]["content"]
    assert "PROMPT-DEFAULT" in system
    assert "退款政策" in system
    assert "上游自带人设" in system

    streamed = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer runtime-token"},
        json={"model": other["name"], "messages": [{"role": "user", "content": "你好"}], "stream": True},
    )
    assert streamed.status_code == 200
    assert "你" in streamed.text and "好" in streamed.text
    assert "PROMPT-OTHER" in Recorder.calls[-1]["json"]["messages"][0]["content"]
    assert Recorder.calls[-1]["json"]["stream"] is True

    stopped = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer runtime-token", "X-Persona-Id": str(default["id"])},
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}], "stream": False},
    )
    # 默认角色仍启用，显式 id 可以命中。
    assert stopped.status_code == 200

    client.put(
        f"/api/personas/{other['id']}",
        headers=auth,
        json={
            "name": other["name"],
            "avatar_id": other["avatar_id"],
            "brain_id": other["brain_id"],
            "voice_id": other["voice_id"],
            "enabled": False,
            "is_default": False,
        },
    )
    blocked = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer runtime-token", "X-Persona-Id": str(other["id"])},
        json={"model": "qwen-plus", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert blocked.status_code == 409

    chat = client.post(
        "/api/chat/stream",
        headers=auth,
        json={"persona_id": default["id"], "messages": [{"role": "user", "content": "退款"}]},
    )
    assert chat.status_code == 200
    assert "你" in chat.text and "好" in chat.text
    assert '"done": true' in chat.text or '"done":true' in chat.text.replace(" ", "")
