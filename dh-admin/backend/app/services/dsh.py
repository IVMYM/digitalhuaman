"""DeepSeek Harness（datafine OneChat DSH 开放接口）服务端调用：换票、专家列表、验证对话。

协议与展示端 fine-digital-human/dsh_brain.py 一致：
POST /api/open/dsh/token 换票 → GET /api/open/dsh/agents 查已授权专家 →
POST /api/open/dsh/messages 发消息 → GET /api/open/dsh/events 订阅 SSE 收回复。
"""

import asyncio
import json
import re
import time

import httpx

_ID = re.compile(r"[^A-Za-z0-9_.:-]")


class DshError(Exception):
    pass


def safe_id(value: str, fallback: str, limit: int) -> str:
    cleaned = _ID.sub("-", (value or "").strip())[:limit].strip("-")
    return cleaned or fallback


def speakable(text: str) -> str:
    raw = text or ""
    stripped = raw.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")):
        return raw
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        return raw
    if not isinstance(obj, dict):
        return ""
    for key in ("text", "answer", "content", "reply", "message"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip() and not val.strip().startswith("{"):
            return val
    return ""


class TurnText:
    """把整段快照和逐字分片都收成新增量。与展示端实现保持一致。"""

    def __init__(self) -> None:
        self.text = ""
        self.done = False
        self.error = ""
        self.fresh = False

    def feed(self, event: str, data: str) -> str:
        name = (event or "").strip().lower()
        payload = (data or "").strip()
        if not payload or name == "heartbeat" or payload == "[DONE]":
            if payload == "[DONE]":
                self.done = True
            return ""
        if name == "error":
            self.error = payload[:300]
            self.done = True
            return ""
        if name in {"turn_end", "done", "message_stop"}:
            self.done = True
            return ""
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return self._append(payload)
        if not isinstance(obj, dict):
            return ""
        code = str(obj.get("code") or "")
        if code and code not in {"200", "202", "0"}:
            self.error = str(obj.get("message") or obj.get("msg") or "对话流已中断")[:300]
            self.done = True
            return ""
        if obj.get("done") is True or obj.get("type") in {"turn_end", "message_stop"}:
            self.done = True
        piece = _piece(_payload(obj))
        if not piece:
            return ""
        if name == "message" and not self.fresh:
            return ""
        delta = self._append(piece)
        if name == "progress" and delta:
            self.fresh = True
        if name == "message" and self.fresh:
            self.done = True
        return delta

    def _append(self, piece: str) -> str:
        piece = speakable(piece)
        if not piece:
            return ""
        if piece.startswith(self.text):
            delta = piece[len(self.text):]
            self.text = piece
            return delta
        if self.text.startswith(piece):
            return ""
        self.text += piece
        return piece


def _payload(obj: dict) -> dict:
    inner = obj.get("data")
    if isinstance(inner, dict):
        return inner
    return obj


def _piece(obj: dict) -> str:
    delta = obj.get("delta")
    if isinstance(delta, str):
        return delta
    if isinstance(delta, dict):
        content = delta.get("content") or delta.get("text") or ""
        if isinstance(content, str):
            return content
    for key in ("text", "content", "answer", "reply"):
        val = obj.get(key)
        if isinstance(val, str):
            return val
    choices = obj.get("choices") or []
    if choices and isinstance(choices[0], dict):
        choice = choices[0]
        inner = choice.get("delta") or choice.get("message") or {}
        if isinstance(inner, dict):
            return str(inner.get("content") or "")
    return ""


def _ok(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise DshError("大脑返回无法识别")
    code = payload.get("code")
    if code is not None and str(code) not in {"200", "202", "0"}:
        raise DshError(str(payload.get("message") or payload.get("msg") or "大脑拒绝了请求"))
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _plain_error(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:300]
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("msg") or body)[:300]
    return body.strip()[:300]


def agent_name(agent: dict) -> str:
    for key in ("name", "agentName", "title", "label", "nickName"):
        val = agent.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return str(agent.get("agentId") or "")


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)


async def fetch_token(client: httpx.AsyncClient, base: str, app_id: str, app_secret: str) -> str:
    response = await client.post(f"{base}/api/open/dsh/token", json={"appId": app_id, "appSecret": app_secret})
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise DshError("换取令牌失败：平台返回无法识别") from exc
    data = _ok(payload)
    token = str(data.get("accessToken") or "")
    if not token:
        raise DshError("没有拿到访问令牌（检查 App ID / App Secret）")
    return token


async def fetch_agents(client: httpx.AsyncClient, base: str, token: str) -> list[dict]:
    response = await client.get(f"{base}/api/open/dsh/agents", headers={"Authorization": f"Bearer {token}"})
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise DshError("读取专家列表失败") from exc
    agents = _ok(payload).get("agents") or []
    return [item for item in agents if isinstance(item, dict) and item.get("agentId")]


async def list_experts(base_url: str, app_id: str, app_secret: str) -> list[dict]:
    base = base_url.rstrip("/")
    async with httpx.AsyncClient(timeout=_timeout()) as client:
        token = await fetch_token(client, base, app_id, app_secret)
        agents = await fetch_agents(client, base, token)
    return [{"agent_id": str(item.get("agentId")), "name": agent_name(item)} for item in agents]


async def _collect_reply(client: httpx.AsyncClient, base: str, token: str, agent_id: str, question: str) -> str:
    user = "admin-verify"
    conv = safe_id(f"admin-verify-{int(time.time())}", "admin-verify", 128)
    response = await client.post(
        f"{base}/api/open/dsh/messages",
        headers={"Authorization": f"Bearer {token}"},
        json={"agentId": agent_id, "channelUserId": user, "conversationId": conv, "content": question},
    )
    try:
        accepted = response.json()
    except json.JSONDecodeError as exc:
        raise DshError("发送消息失败") from exc
    _ok(accepted)
    params = {"agentId": agent_id, "channelUserId": user, "conversationId": conv}
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream", "Accept-Encoding": "identity"}
    async with client.stream("GET", f"{base}/api/open/dsh/events", params=params, headers=headers) as stream:
        if stream.status_code >= 400 or "text/event-stream" not in stream.headers.get("content-type", ""):
            body = (await stream.aread()).decode("utf-8", errors="replace")[:300]
            raise DshError(_plain_error(body) or f"事件流失败 {stream.status_code}")
        turn = TurnText()
        event = ""
        lines = stream.aiter_lines().__aiter__()
        while not turn.done:
            idle = 120.0 if turn.text else 40.0
            try:
                line = await asyncio.wait_for(lines.__anext__(), timeout=idle)
            except StopAsyncIteration:
                break
            except (asyncio.TimeoutError, TimeoutError) as exc:
                raise DshError("大脑长时间没有响应") from exc
            if line.startswith("event:"):
                event = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            turn.feed(event, line[5:].strip())
            event = ""
        if turn.error and not turn.text:
            raise DshError(turn.error)
        return turn.text


async def verify(base_url: str, app_id: str, app_secret: str, agent_id: str, question: str) -> dict:
    """跑完整验证链，逐步回报：换票 → 专家列表/定位专家 → 发测试消息收回复。"""
    base = base_url.rstrip("/")
    steps: list[dict] = []
    if not app_id.strip() or not app_secret.strip():
        return {"ok": False, "steps": steps, "error": "App ID 和 App Secret 都要填", "reply": "", "agent_id": "", "agent_name": ""}

    def mark(name: str, started: float, detail: str) -> None:
        steps.append({"name": name, "ok": True, "detail": detail, "ms": int((time.time() - started) * 1000)})

    def fail(name: str, started: float, exc: Exception) -> dict:
        steps.append({"name": name, "ok": False, "detail": str(exc)[:300], "ms": int((time.time() - started) * 1000)})
        return {"ok": False, "steps": steps, "error": str(exc)[:300], "reply": "", "agent_id": "", "agent_name": ""}

    async with httpx.AsyncClient(timeout=_timeout()) as client:
        started = time.time()
        try:
            token = await fetch_token(client, base, app_id.strip(), app_secret.strip())
        except (DshError, httpx.HTTPError) as exc:
            return fail("换取令牌", started, exc if isinstance(exc, DshError) else DshError(f"网络错误：{exc}"))
        mark("换取令牌", started, "已拿到访问令牌")

        started = time.time()
        try:
            agents = await fetch_agents(client, base, token)
        except (DshError, httpx.HTTPError) as exc:
            return fail("读取专家列表", started, exc if isinstance(exc, DshError) else DshError(f"网络错误：{exc}"))
        if not agents:
            return fail("读取专家列表", started, DshError("这个应用没有已授权的专家"))
        chosen = None
        wanted = (agent_id or "").strip()
        for item in agents:
            if str(item.get("agentId")) == wanted:
                chosen = item
                break
        if wanted and chosen is None:
            names = "、".join(agent_name(item) for item in agents)
            return fail("读取专家列表", started, DshError(f"所选专家不在已授权列表里。已授权：{names}"))
        if chosen is None:
            chosen = agents[0]
        chosen_id = str(chosen.get("agentId"))
        chosen_name = agent_name(chosen)
        mark("读取专家列表", started, f"共 {len(agents)} 个已授权专家，使用「{chosen_name}」")

        started = time.time()
        try:
            reply = await _collect_reply(client, base, token, chosen_id, question)
        except (DshError, httpx.HTTPError) as exc:
            return fail("发送测试消息", started, exc if isinstance(exc, DshError) else DshError(f"网络错误：{exc}"))
        if not reply.strip():
            return fail("发送测试消息", started, DshError("专家没有返回内容"))
        mark("发送测试消息", started, "已收到专家回复")
    return {"ok": True, "steps": steps, "error": "", "reply": reply, "agent_id": chosen_id, "agent_name": chosen_name}
