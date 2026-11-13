import json
import time

import httpx

CONNECT_TIMEOUT = 10.0
READ_TIMEOUT = 120.0


class UpstreamError(Exception):
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(body)


def completions_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if url.endswith("/chat/completions"):
        return url
    return url + "/chat/completions"


def _headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _timeout(read: float = READ_TIMEOUT) -> httpx.Timeout:
    return httpx.Timeout(connect=CONNECT_TIMEOUT, read=read, write=30.0, pool=10.0)


def compose_messages(system_prompt: str, history: list[dict], kb_context: str = "") -> list[dict]:
    system = (system_prompt or "").strip() or "你是一个数字人助手，回答简短、口语化。"
    if kb_context:
        system += (
            "\n\n以下是知识库检索到的资料。请优先依据这些内容回答；资料不够时直接说明，不要编造。\n"
            + kb_context
        )
    messages = [{"role": "system", "content": system}]
    for item in history[-20:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        messages.append({"role": role, "content": text[:8000]})
    return messages


def split_incoming(messages: list) -> tuple[str, list[dict]]:
    extra_system: list[str] = []
    history: list[dict] = []
    if not isinstance(messages, list):
        return "", []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if not isinstance(content, str):
            continue
        if role == "system":
            if content.strip():
                extra_system.append(content.strip()[:4000])
        elif role in {"user", "assistant"}:
            history.append({"role": role, "content": content})
    return "\n".join(extra_system), history


def last_user_text(history: list[dict]) -> str:
    for item in reversed(history):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


async def post_json(url: str, payload: dict, api_key: str, read_timeout: float = READ_TIMEOUT) -> httpx.Response:
    async with httpx.AsyncClient(timeout=_timeout(read_timeout)) as client:
        return await client.post(url, json=payload, headers=_headers(api_key))


async def iter_sse_lines(url: str, payload: dict, api_key: str):
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        async with client.stream("POST", url, json=payload, headers=_headers(api_key)) as response:
            if response.status_code >= 400:
                body = (await response.aread()).decode("utf-8", errors="replace")[:800]
                raise UpstreamError(response.status_code, body or f"上游返回 {response.status_code}")
            async for line in response.aiter_lines():
                yield line


async def iter_deltas(url: str, payload: dict, api_key: str):
    async for line in iter_sse_lines(url, payload, api_key):
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = obj.get("choices") or []
        if not choices:
            continue
        choice = choices[0] or {}
        delta = choice.get("delta") or {}
        text = delta.get("content") or choice.get("text") or ""
        if text:
            yield text


async def test_connection(base_url: str, api_key: str, model_name: str) -> dict:
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "请只回复四个字：连接成功"}],
        "temperature": 0,
        "max_tokens": 64,
        "stream": False,
    }
    started = time.perf_counter()
    try:
        response = await post_json(completions_url(base_url), payload, api_key, read_timeout=30)
    except httpx.HTTPError as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return {"ok": False, "reply": "", "latency_ms": latency, "error": f"无法连接：{exc}"}
    latency = int((time.perf_counter() - started) * 1000)
    if response.status_code >= 400:
        return {"ok": False, "reply": "", "latency_ms": latency, "error": response.text[:500]}
    try:
        data = response.json()
        reply = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        return {"ok": False, "reply": "", "latency_ms": latency, "error": "上游返回的不是可用的对话结果"}
    return {"ok": True, "reply": reply or "", "latency_ms": latency, "error": ""}
