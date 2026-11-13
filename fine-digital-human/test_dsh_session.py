#!/usr/bin/env python3
"""打一轮 DSH 开放接口：换票、列专家、发消息、把 SSE 打到终端。"""

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime

BASE = "http://8.136.146.223:3088/onechat/dsh"
APP_ID = "app74837331"
APP_SECRET = "dhmVHLVBvc6DRCKzf2atB99H37oKz9oK"
QUESTION = "用一句话介绍你自己"
CHANNEL_USER = "xiaoxin-test"


def request(method, path, token="", body=None, timeout=30):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"{method} {path} HTTP {exc.code}: {raw[:500]}")
    payload = json.loads(raw)
    code = str(payload.get("code"))
    if code not in {"200", "202", "0"}:
        raise SystemExit(f"{method} {path} code={code} {payload.get('message') or payload}")
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def main():
    conv = "conv-" + datetime.now().strftime("%Y%m%d%H%M%S")
    print("base", BASE)
    print("conv", conv)

    print("=== 1. token ===")
    token_data = request("POST", "/api/open/dsh/token", body={"appId": APP_ID, "appSecret": APP_SECRET})
    token = token_data.get("accessToken") or ""
    print("expiresIn", token_data.get("expiresIn"), "tokenLen", len(token))
    if not token:
        raise SystemExit("没有 accessToken")

    print("=== 2. agents ===")
    agents = (request("GET", "/api/open/dsh/agents", token=token).get("agents") or [])
    if not agents:
        raise SystemExit("没有已授权专家")
    for agent in agents:
        print(agent.get("agentId"), agent.get("name") or "")
    agent_id = agents[0]["agentId"]

    print("=== 3. messages ===")
    sent = request(
        "POST",
        "/api/open/dsh/messages",
        token=token,
        body={
            "agentId": agent_id,
            "channelUserId": CHANNEL_USER,
            "conversationId": conv,
            "content": QUESTION,
        },
        timeout=60,
    )
    print(json.dumps(sent, ensure_ascii=False))
    request_id = sent.get("requestMsgId") or sent.get("msgId") or sent.get("messageId") or ""

    print("=== 4. events ===")
    query = f"agentId={urllib.request.quote(agent_id)}&channelUserId={CHANNEL_USER}&conversationId={conv}"
    if request_id:
        query += "&requestMsgId=" + urllib.request.quote(str(request_id))
    req = urllib.request.Request(
        BASE + "/api/open/dsh/events?" + query,
        headers={"Authorization": "Bearer " + token, "Accept": "text/event-stream"},
    )
    event = ""
    text = []
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            content_type = response.headers.get("Content-Type", "")
            print("content-type", content_type)
            if "text/event-stream" not in content_type:
                body = response.read(800).decode("utf-8", errors="replace")
                raise SystemExit("不是事件流: " + body)
            while True:
                line = response.readline()
                if not line:
                    break
                line = line.decode("utf-8", errors="replace").rstrip("\r\n")
                if line.startswith("event:"):
                    event = line[6:].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                print(f"event={event or '-'} {data[:500]}")
                if event == "error":
                    raise SystemExit("事件流错误: " + data[:300])
                piece = delta_of(event, data, "".join(text))
                if piece:
                    text.append(piece)
                    sys.stdout.write(piece)
                    sys.stdout.flush()
                if event in {"turn_end", "done", "message_stop"} or data == "[DONE]":
                    break
                event = ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"events HTTP {exc.code}: {body[:500]}")
    print()
    print("=== reply ===")
    print("".join(text) or "(空回复)")


def delta_of(event, data, have):
    if event in {"progress", "heartbeat", "turn_end", "done", "error"} or data in {"ok", "[DONE]"}:
        return ""
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return data
    if not isinstance(obj, dict):
        return ""
    if str(obj.get("kind") or obj.get("type") or "") == "progress":
        return ""
    piece = ""
    delta = obj.get("delta")
    if isinstance(delta, str):
        piece = delta
    elif isinstance(delta, dict):
        piece = str(delta.get("content") or delta.get("text") or "")
    else:
        for key in ("text", "content", "answer", "reply"):
            if isinstance(obj.get(key), str):
                piece = obj[key]
                break
        choices = obj.get("choices") or []
        if not piece and choices and isinstance(choices[0], dict):
            inner = choices[0].get("delta") or choices[0].get("message") or {}
            if isinstance(inner, dict):
                piece = str(inner.get("content") or "")
    if piece.startswith(have):
        return piece[len(have):]
    if have.startswith(piece):
        return ""
    return piece


if __name__ == "__main__":
    main()
