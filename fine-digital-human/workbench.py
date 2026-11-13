"""数字人链路上各节点的状态和最近日志。不返回密钥。"""

import os
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import httpx

_SECRET = re.compile(r"(?i)(secret|password|passwd|token|credential|authorization)(['\"=: ]+)(\S+)")
_TURN_USER = re.compile(r"user=[^:\s]+:\S+")


def _redact(line: str) -> str:
    line = _SECRET.sub(r"\1\2***", line)
    return _TURN_USER.sub("user=***", line)


def _tail(path: Path, limit: int = 400, max_bytes: int = 256_000) -> list[str]:
    if not path.is_file():
        return []
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()
        text = handle.read().decode("utf-8", errors="replace")
    return [_redact(line) for line in text.splitlines()[-limit:]]


def _port_open(port: int) -> bool:
    sock = socket.socket()
    sock.settimeout(0.4)
    try:
        sock.connect(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _node(name: str, level: str, detail: str, log: list[str]) -> dict:
    return {"name": name, "level": level, "detail": detail, "log": log[-40:]}


def _turn(lines: list[str]) -> dict:
    conf = Path(os.getenv("TURN_CONF", "/content/livetalking/turnserver.conf"))
    external = ""
    if conf.is_file():
        for line in conf.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("external-ip="):
                external = line.split("=", 1)[1].strip()
    listening = _port_open(int(os.getenv("TURN_PORT", "3478")))
    if not listening:
        level, detail = "down", "3478 没有在听"
    elif not external:
        level, detail = "warn", "在听，但没有公布中继地址"
    else:
        level, detail = "ok", f"3478 在听，中继 {external}"
    useful = [line for line in lines if line.strip() and not line.startswith("0: : ")]
    return _node("TURN", level, detail, useful or lines)


def _avatar(avatar_id: str) -> dict:
    roots = []
    if os.getenv("AVATAR_DIR"):
        roots.append(Path(os.environ["AVATAR_DIR"]))
    roots.append(Path("/content/livetalking/LiveTalking/data/avatars") / avatar_id)
    roots.append(Path(__file__).resolve().parent.parent / "assets" / "avatars" / avatar_id)
    found = next((path for path in roots if (path / "full_imgs").is_dir()), None)
    if found is None:
        return _node("形象", "down", f"没有找到 {avatar_id} 的帧", [])
    frames = len(list((found / "full_imgs").glob("*.png")))
    faces = len(list((found / "face_imgs").glob("*.png"))) if (found / "face_imgs").is_dir() else 0
    coords = (found / "coords.pkl").is_file()
    if frames <= 0 or not coords:
        level, detail = "down", f"{avatar_id} 帧不完整"
    else:
        level, detail = "ok", f"{avatar_id} 全身 {frames} 帧，脸 {faces} 帧"
    return _node("形象", level, detail, [])


def _brain(page_log: list[str]) -> dict:
    base = os.getenv("DSH_BASE_URL", "").strip()
    agent = os.getenv("DSH_AGENT_ID", "").strip() or "未指定"
    enabled = bool(base and os.getenv("DSH_APP_ID") and os.getenv("DSH_APP_SECRET"))
    interesting = [
        line for line in page_log
        if "chat_stream" in line or "/api/human" in line or "Error" in line or "Traceback" in line
    ]
    if not enabled:
        return _node("大脑", "down", "DSH 未配置", interesting)
    fail_at = max((i for i, line in enumerate(interesting) if "failed" in line or " Error" in line or line.startswith("ERROR")), default=-1)
    ok_at = max((i for i, line in enumerate(interesting) if "POST /api/human 200" in line), default=-1)
    if fail_at > ok_at:
        return _node("大脑", "warn", f"已配置 {agent}，最近一次播报失败", interesting)
    if ok_at >= 0:
        return _node("大脑", "ok", f"已配置 {agent}，最近回复已送去朗读", interesting)
    return _node("大脑", "ok", f"已配置 {agent}，还没有对话", interesting)


def _livetalking(payload: dict | None, error: str, voice_log: list[str]) -> tuple[dict, dict]:
    speech = [
        line for line in voice_log
        if "sleep qsize" not in line and "avg final fps" not in line and not line.startswith("DEBUG:")
    ]
    states = [line for line in speech if "Connection state" in line or "offer sessionid" in line or line.startswith("INFO:utils.logger:notify:")]
    if error or not payload:
        session = _node("会话", "down", "读不到会话", states)
        return _node("语音", "down", error or "LiveTalking 没有响应", speech), session
    session_body = payload.get("sessions") or {}
    if session_body.get("code") not in (0, None):
        return _node("语音", "down", str(session_body.get("msg") or "会话接口失败")[:180], speech), _node("会话", "down", "读不到会话", states)
    sessions = (session_body.get("data") or {}).get("sessions") or []
    config = ((payload.get("config") or {}).get("data") or {}).get("config") or {}
    speaking = sum(1 for row in sessions if row.get("speaking"))
    detail = f"{config.get('model') or 'wav2lip'} · {len(sessions)} 路会话"
    if speaking:
        detail += f"，{speaking} 路正在说"
    voice = _node("语音", "ok", detail, speech)
    if not sessions:
        session = _node("会话", "warn", "当前没有观众连接", states)
    else:
        bits = []
        for row in sessions[:4]:
            sid = str(row.get("sessionid") or "")[:8]
            bits.append(f"{sid} {'正在说' if row.get('speaking') else '待命'}")
        session = _node("会话", "ok", "，".join(bits), states)
    return voice, session


async def snapshot() -> dict:
    page_log = _tail(Path(os.getenv("PAGE_LOG", "/tmp/fine-digital-human.log")))
    voice_log = _tail(Path(os.getenv("LIVETALKING_LOG", "/tmp/livetalking_app.log")))
    turn_log = _tail(Path(os.getenv("TURN_LOG", "/tmp/turnserver.log")))
    avatar_id = os.getenv("LIVETALKING_AVATAR_ID", "zhengxin")
    url = os.getenv("LIVETALKING_URL", "http://127.0.0.1:8010").rstrip("/")
    payload = None
    error = ""
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            sessions = await client.get(f"{url}/api/admin/sessions")
            config = await client.get(f"{url}/api/admin/config")
            sessions.raise_for_status()
            config.raise_for_status()
            payload = {"sessions": sessions.json(), "config": config.json()}
    except Exception as exc:
        error = str(exc)[:180]
    voice, session = _livetalking(payload, error, voice_log)
    nodes = [
        _node("页面", "ok", "本服务在响应", [
            line for line in page_log
            if any(mark in line for mark in ("chat_stream", "/api/human", "Error", "Traceback", "Uvicorn", "Application", "Started"))
        ]),
        voice,
        _turn(turn_log),
        _brain(page_log),
        _avatar(avatar_id),
        session,
    ]
    rank = {"ok": 0, "warn": 1, "down": 2}
    worst = max(nodes, key=lambda node: rank[node["level"]])
    return {
        "checked_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "level": worst["level"],
        "summary": "链路正常" if worst["level"] == "ok" else worst["detail"],
        "nodes": nodes,
    }
