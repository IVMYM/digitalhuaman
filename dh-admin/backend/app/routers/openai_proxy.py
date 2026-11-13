import json

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_runtime_token
from app.services.llm import (
    UpstreamError,
    completions_url,
    compose_messages,
    iter_sse_lines,
    last_user_text,
    post_json,
    split_incoming,
)
from app.services.personas import decrypted_brain_key, persona_dependencies, resolve_persona
from app.services.retrieval import build_context

router = APIRouter(prefix="/v1", tags=["openai"])


def _payload(brain, persona_system: str, body: dict, kb_context: str) -> dict:
    extra_system, history = split_incoming(body.get("messages") or [])
    system = persona_system or ""
    if extra_system:
        system = f"{system}\n\n{extra_system}".strip()
    payload = {
        "model": brain.model_name,
        "messages": compose_messages(system, history, kb_context),
        "temperature": brain.temperature,
        "max_tokens": brain.max_tokens,
        "stream": bool(body.get("stream")),
    }
    if payload["stream"] and isinstance(body.get("stream_options"), dict):
        payload["stream_options"] = body["stream_options"]
    return payload


@router.post("/chat/completions")
async def chat_completions(request: Request, db: Session = Depends(get_db), _: None = Depends(require_runtime_token)):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": {"message": "请求体不是 JSON", "type": "invalid_request"}})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": {"message": "请求体必须是 JSON 对象", "type": "invalid_request"}})
    persona = resolve_persona(db, request, body)
    _avatar, brain, _voice, _knowledge = persona_dependencies(db, persona)
    _extra, history = split_incoming(body.get("messages") or [])
    context = build_context(db, persona.knowledge_base_id, last_user_text(history))
    payload = _payload(brain, brain.system_prompt or "", body, context)
    url = completions_url(brain.base_url)
    api_key = decrypted_brain_key(brain)

    if payload["stream"]:

        async def forward():
            try:
                async for line in iter_sse_lines(url, payload, api_key):
                    if line == "":
                        yield "\n"
                    else:
                        yield line + "\n"
            except UpstreamError as exc:
                message = exc.body or "上游错误"
                yield f"data: {json.dumps({'error': {'message': message}}, ensure_ascii=False)}\n\n"
            except httpx.HTTPError as exc:
                yield f"data: {json.dumps({'error': {'message': f'无法连接大脑：{exc}'}}, ensure_ascii=False)}\n\n"

        return StreamingResponse(
            forward(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    try:
        response = await post_json(url, payload, api_key)
    except httpx.HTTPError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": {"message": f"无法连接大脑：{exc}", "type": "upstream_error"}},
        )
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return JSONResponse(status_code=response.status_code, content=response.json())
        except ValueError:
            pass
    return Response(content=response.content, status_code=response.status_code, media_type=content_type or "application/json")
