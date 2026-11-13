"""datafine OneChat DSH 开放接口：换票、发消息、订阅 SSE，吐出可播报的增量文本。"""

import asyncio
import json
import os
import re
import time
from typing import AsyncIterator

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
    """把整段快照和逐字分片都收成新增量。"""

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
        # 订阅一建立就会先推上一轮的 message。本轮正文从 progress 开始。
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


def _denied(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    message = str(payload.get("message") or payload.get("msg") or "")
    return str(payload.get("code") or "") == "403" or "无权" in message


def _plain_error(body: str) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()[:300]
    if isinstance(payload, dict):
        return str(payload.get("message") or payload.get("msg") or body)[:300]
    return body.strip()[:300]


def _ok(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise DshError("大脑返回无法识别")
    code = payload.get("code")
    if code is not None and str(code) not in {"200", "202", "0"}:
        raise DshError(str(payload.get("message") or payload.get("msg") or "大脑拒绝了请求"))
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


class DshBrain:
    def __init__(self) -> None:
        self.base = os.getenv("DSH_BASE_URL", "https://www.datafine.cn/onechat/dsh").rstrip("/")
        self.app_id = os.getenv("DSH_APP_ID", "").strip()
        self.app_secret = os.getenv("DSH_APP_SECRET", "").strip()
        self.agent_id = os.getenv("DSH_AGENT_ID", "").strip()
        self._agent_ready = False
        self._token = ""
        self._exp = 0.0

    def enabled(self) -> bool:
        return bool(self.base and self.app_id and self.app_secret)

    async def _token_value(self, client: httpx.AsyncClient, force: bool = False) -> str:
        now = time.time()
        if self._token and self._exp > now + 60 and not force:
            return self._token
        response = await client.post(
            f"{self.base}/api/open/dsh/token",
            json={"appId": self.app_id, "appSecret": self.app_secret},
        )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise DshError("换取令牌失败") from exc
        data = _ok(payload)
        token = str(data.get("accessToken") or "")
        if not token:
            raise DshError("没有拿到访问令牌")
        self._token = token
        self._exp = now + float(data.get("expiresIn") or 7200)
        return token

    async def stream(self, content: str, channel_user_id: str, conversation_id: str) -> AsyncIterator[str]:
        if not self.enabled():
            raise DshError("未配置 DSH 大脑")
        user = safe_id(channel_user_id, "xiaoxin", 128)
        conv = safe_id(conversation_id, "conv-xiaoxin", 128)
        timeout = httpx.Timeout(connect=15.0, read=180.0, write=30.0, pool=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            token = await self._token_value(client)
            await self._ensure_agent(client, token)
            accepted = await self._send(client, token, user, conv, content)
            if _denied(accepted):
                self._agent_ready = False
                self.agent_id = ""
                await self._ensure_agent(client, token)
                accepted = await self._send(client, token, user, conv, content)
            elif str(accepted.get("code") or "") == "401":
                token = await self._token_value(client, force=True)
                accepted = await self._send(client, token, user, conv, content)
            _ok(accepted)
            params = {"agentId": self.agent_id, "channelUserId": user, "conversationId": conv}
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "text/event-stream",
                "Accept-Encoding": "identity",
            }
            async with client.stream("GET", f"{self.base}/api/open/dsh/events", params=params, headers=headers) as response:
                if response.status_code >= 400 or "text/event-stream" not in response.headers.get("content-type", ""):
                    body = (await response.aread()).decode("utf-8", errors="replace")[:300]
                    raise DshError(_plain_error(body) or f"事件流失败 {response.status_code}")
                turn = TurnText()
                event = ""
                lines = response.aiter_lines().__aiter__()
                while not turn.done:
                    # idle guard: if the platform stalls, the event stream stays
                    # silent forever (old read timeout was 600s) and the page sits
                    # on "thinking". No first token for 40s = no response; once
                    # output has started, allow 120s gaps.
                    idle = 120.0 if turn.text else 40.0
                    try:
                        line = await asyncio.wait_for(lines.__anext__(), timeout=idle)
                    except StopAsyncIteration:
                        break
                    except (asyncio.TimeoutError, TimeoutError):
                        raise DshError("大脑长时间没有响应，请重说一遍")
                    if line.startswith("event:"):
                        event = line[6:].strip()
                        continue
                    if not line.startswith("data:"):
                        continue
                    delta = turn.feed(event, line[5:].strip())
                    event = ""
                    if delta:
                        yield delta
                if turn.error and not turn.text:
                    raise DshError(turn.error)

    async def _ensure_agent(self, client: httpx.AsyncClient, token: str) -> str:
        if self._agent_ready and self.agent_id:
            return self.agent_id
        response = await client.get(
            f"{self.base}/api/open/dsh/agents",
            headers={"Authorization": f"Bearer {token}"},
        )
        try:
            payload = response.json()
        except json.JSONDecodeError as exc:
            raise DshError("读取专家列表失败") from exc
        agents = _ok(payload).get("agents") or []
        ids = [str(item.get("agentId") or "") for item in agents if isinstance(item, dict) and item.get("agentId")]
        if self.agent_id and self.agent_id in ids:
            self._agent_ready = True
            return self.agent_id
        if not ids:
            raise DshError("没有已授权专家")
        self.agent_id = ids[0]
        self._agent_ready = True
        return self.agent_id

    async def _send(self, client: httpx.AsyncClient, token: str, user: str, conv: str, content: str) -> dict:
        response = await client.post(
            f"{self.base}/api/open/dsh/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "agentId": self.agent_id,
                "channelUserId": user,
                "conversationId": conv,
                "content": content,
            },
        )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise DshError("发送消息失败") from exc

    async def complete(self, content: str, channel_user_id: str, conversation_id: str) -> str:
        parts: list[str] = []
        async for delta in self.stream(content, channel_user_id, conversation_id):
            parts.append(delta)
        return "".join(parts)
