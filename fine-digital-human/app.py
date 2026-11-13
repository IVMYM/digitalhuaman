import logging
import mimetypes
import os
import re
from pathlib import Path
import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import json
from pydantic import BaseModel

logger = logging.getLogger("uvicorn.error")

from dsh_brain import DshBrain, DshError

load_dotenv(Path(__file__).resolve().parent / ".env")
dsh_brain = DshBrain()
mimetypes.add_type("application/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")
app = FastAPI(title="fine-digital-human")
ROOT = Path(__file__).parent


def mount_static(url: str, directory: Path, name: str) -> None:
    if directory.is_dir():
        app.mount(url, StaticFiles(directory=directory), name=name)
    else:
        logger.warning("跳过静态目录 %s，%s 不存在", url, directory)


mount_static("/backgrounds", ROOT / "static" / "backgrounds", "backgrounds")
mount_static("/vendor", ROOT / "static" / "vendor", "vendor")

class ChatRequest(BaseModel):
    message: str
    history: list[dict] = []
    sessionid: str | None = None
    channelUserId: str | None = None
    conversationId: str | None = None

class TalkRequest(BaseModel):
    text: str
    sessionid: str | None = None
    interrupt: bool = False

class SessionRequest(BaseModel):
    sessionid: str | None = None

def wake_enabled() -> bool:
    return os.getenv("WAKE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}

def _turn_env_path() -> Path | None:
    """GPU 上用 /content，本机页面用仓库 .secrets。都不进仓库。"""
    candidates = []
    explicit = os.getenv("TURN_ENV_FILE", "").strip()
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(Path("/content/livetalking/turn.env"))
    candidates.append(ROOT.parent / ".secrets" / "turn.env")
    for path in candidates:
        if path.is_file():
            return path
    return None


def turn_config() -> dict:
    """浏览器侧 TURN。没配到时页面会退回公网 STUN，用户态 Tailscale 上几十秒就断。"""
    path = _turn_env_path()
    vals = {}
    if path is not None:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            vals[key.strip()] = value.strip()
    host = vals.get("TURN_PUBLIC_HOST", "")
    user = vals.get("TURN_USER", "")
    password = vals.get("TURN_PASS", "")
    port = vals.get("TURN_PORT", "3478")
    if not (host and user and password):
        return {}
    return {
        "ice_servers": [{
            "urls": [f"turn:{host}:{port}?transport=tcp"],
            "username": user,
            "credential": password,
        }],
        "ice_transport_policy": "relay",
    }

class OfferRequest(BaseModel):
    sdp: str
    type: str
    avatar: str | None = None
    refaudio: str | None = None
    reftext: str | None = None

def _brain_ids(req: ChatRequest) -> tuple[str, str]:
    user = req.channelUserId or req.sessionid or "xiaoxin"
    conv = req.conversationId or req.sessionid or "conv-xiaoxin"
    return user, conv


def _for_speech(text: str) -> str:
    text = re.sub(r"```[\s\S]*?```", " ", text or "")
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*]\([^)]*\)", " ", text)
    text = re.sub(r"\[([^\]]+)]\([^)]*\)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[*_~|>]", "", text)
    text = re.sub(r"^\s*[-+]\s+", "", text, flags=re.M)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:800]


async def _echo_reply(text: str, sessionid: str | None, interrupt: bool) -> bool:
    speech = _for_speech(text)
    if not speech:
        return True
    if not sessionid:
        logger.info("POST /api/human skipped, no session")
        return False
    url = os.getenv("LIVETALKING_URL", "").rstrip("/") + "/human"
    payload = {"text": speech, "type": "echo", "interrupt": interrupt, "sessionid": sessionid}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            body = response.text[:300]
        failed = response.status_code >= 400 or '"code": -1' in body or '"code":-1' in body
        logger.info("POST /api/human %s %s", response.status_code, speech[:80])
        if failed:
            logger.info("POST /api/human failed %s", body)
        return not failed
    except Exception as exc:
        logger.info("POST /api/human failed %s", exc)
        return False


@app.post("/api/chat_stream")
async def chat_stream(req: ChatRequest):
    if dsh_brain.enabled():
        user, conv = _brain_ids(req)

        async def from_dsh():
            try:
                async for delta in dsh_brain.stream(req.message, user, conv):
                    yield json.dumps({"delta": delta}, ensure_ascii=False) + "\n"
            except DshError as exc:
                yield json.dumps({"error": str(exc)}, ensure_ascii=False) + "\n"

        return StreamingResponse(
            from_dsh(),
            media_type="application/x-ndjson",
            headers={"Cache-Control": "no-store"},
        )

    base = os.getenv("DEEPSEEK_BASE_URL", os.getenv("IFM_BASE_URL", os.getenv("MOSS_BASE_URL", ""))).rstrip("/")
    api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("IFM_API_KEY", os.getenv("MOSS_API_KEY", "")))
    messages = []
    system_prompt = os.getenv("SYSTEM_PROMPT", "").strip()
    if system_prompt: messages.append({"role": "system", "content": system_prompt})
    messages.extend(req.history)
    messages.append({"role": "user", "content": req.message})
    async def generate():
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", f"{base}/chat/completions", headers=headers,
                json={"model": os.getenv("DEEPSEEK_MODEL", os.getenv("IFM_MODEL", "IFM/K2-Horizon-375B-A23B")), "messages": messages, "stream": True}) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.startswith("data:"): continue
                    raw = line[5:].strip()
                    if raw == "[DONE]": break
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue
                    err = data.get("error")
                    if err:
                        message = err.get("message") if isinstance(err, dict) else str(err)
                        if message:
                            yield json.dumps({"error": message}, ensure_ascii=False) + "\n"
                        continue
                    # 有的大脑在结束时另发一条 choices 为空的用量包。
                    choices = data.get("choices") or []
                    if not choices or not isinstance(choices[0], dict):
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
                    text = delta.get("content") or ""
                    if not text and isinstance(choice.get("message"), dict):
                        text = choice["message"].get("content") or ""
                    if isinstance(text, list):
                        text = "".join(
                            part.get("text", "") if isinstance(part, dict) else str(part)
                            for part in text
                        )
                    if text:
                        yield json.dumps({"delta": text}, ensure_ascii=False) + "\n"
    return StreamingResponse(generate(), media_type="application/x-ndjson")

@app.get("/")
async def index():
    return FileResponse(ROOT / "static" / "index.html", headers={"Cache-Control": "no-store"})

@app.get("/workbench")
async def workbench_page():
    return FileResponse(ROOT / "static" / "workbench.html", headers={"Cache-Control": "no-store"})

@app.get("/api/workbench")
async def workbench_api():
    from workbench import snapshot
    return await snapshot()

@app.get("/api/avatar-config")
async def avatar_config():
    base = os.getenv("DH_ADMIN_BASE_URL", "http://127.0.0.1:18200").rstrip("/")
    token = os.getenv("DH_ADMIN_RUNTIME_TOKEN", "")
    if not token:
        admin_env = Path(os.getenv("DH_ADMIN_ENV_FILE", ROOT.parent / "dh-admin" / ".env"))
        if admin_env.exists():
            for line in admin_env.read_text(encoding="utf-8").splitlines():
                if line.startswith("RUNTIME_API_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = {"avatar_id": os.getenv("LIVETALKING_AVATAR_ID", "wav2lip256_avatar1"),
              "background_url": os.getenv("DIGITAL_HUMAN_BACKGROUND_URL", "/backgrounds/zhengxin.png"),
              "persona": "", "wake_enabled": wake_enabled()}
    result.update(turn_config())
    if not token:
        return result
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            rows = (await client.get(f"{base}/api/runtime/personas", headers=headers)).json()
            chosen = next((x for x in rows if x.get("enabled") and x.get("is_default")), None)
            if chosen:
                detail = (await client.get(f"{base}/api/runtime/personas/{chosen['id']}", headers=headers)).json()
                result["avatar_id"] = detail.get("avatar", {}).get("livetalking_avatar_id") or result["avatar_id"]
                result["persona"] = detail.get("name", "")
        return result
    except Exception:
        return result

@app.post("/api/chat")
async def chat(req: ChatRequest):
    if dsh_brain.enabled():
        user, conv = _brain_ids(req)
        try:
            reply = await dsh_brain.complete(req.message, user, conv)
        except DshError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"reply": reply}
    base = os.getenv("DEEPSEEK_BASE_URL", os.getenv("IFM_BASE_URL", os.getenv("MOSS_BASE_URL", ""))).rstrip("/")
    if not base:
        return {"reply": "MOSS 服务尚未配置。请在 .env 中设置 MOSS_BASE_URL。"}
    messages = []
    system_prompt = os.getenv("SYSTEM_PROMPT", "").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.extend(req.history)
    messages.append({"role": "user", "content": req.message})
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("IFM_API_KEY", os.getenv("MOSS_API_KEY", "")))
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(f"{base}/chat/completions", headers=headers,
                                  json={"model": os.getenv("DEEPSEEK_MODEL", os.getenv("IFM_MODEL", os.getenv("MOSS_MODEL", "moss"))),
                                        "messages": messages})
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices") or []
        message = choices[0].get("message") if choices and isinstance(choices[0], dict) else None
        reply = message.get("content") if isinstance(message, dict) else ""
        if not reply:
            raise HTTPException(502, "大脑返回的不是可用的对话结果")
        return {"reply": reply}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"MOSS 调用失败: {e}")

@app.post("/api/talk")
async def talk(req: TalkRequest):
    bridge = os.getenv("LOCAL_AVATAR_URL", "").rstrip("/")
    url = (bridge + "/talk") if bridge else (os.getenv("LIVETALKING_URL", "").rstrip("/") + "/human")
    payload = {"text": req.text, "type": "chat", "interrupt": True}
    if req.sessionid or os.getenv("LIVETALKING_SESSION_ID"):
        payload["sessionid"] = req.sessionid or os.getenv("LIVETALKING_SESSION_ID")
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        raise HTTPException(502, f"LiveTalking 调用失败: {e}")

@app.post("/api/offer")
async def offer(req: OfferRequest):
    url = os.getenv("LIVETALKING_URL", "").rstrip("/") + "/offer"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=req.model_dump(exclude_none=True))
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"LiveTalking offer failed: {e.response.text[:500]}")
    except Exception as e:
        raise HTTPException(502, f"LiveTalking offer connection failed: {e}")

@app.post("/api/is_speaking")
async def is_speaking(req: SessionRequest):
    url = os.getenv("LIVETALKING_URL", "").rstrip("/") + "/is_speaking"
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(url, json={"sessionid": req.sessionid})
            r.raise_for_status()
            body = r.json()
            return {"speaking": bool(body.get("data"))}
    except Exception:
        return {"speaking": False}

@app.post("/api/human")
async def human(req: TalkRequest):
    # echo 只做语音合成并驱动嘴型。对话文本已由 /api/chat_stream 生成。
    url = os.getenv("LIVETALKING_URL", "").rstrip("/") + "/human"
    payload = {"text": req.text, "type": "echo", "interrupt": req.interrupt, "sessionid": req.sessionid}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(502, f"LiveTalking 播报失败: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(502, f"LiveTalking 播报失败: {e}")

