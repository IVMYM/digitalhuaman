import json

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Persona
from app.schemas import ChatIn
from app.services.llm import UpstreamError, completions_url, compose_messages, iter_deltas, last_user_text, split_incoming
from app.services.personas import decrypted_brain_key, get_or_404, persona_dependencies
from app.services.retrieval import build_context

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(get_current_user)])


@router.post("/stream")
async def stream_chat(body: ChatIn, db: Session = Depends(get_db)):
    persona = get_or_404(db, Persona, body.persona_id, "角色")
    _avatar, brain, _voice, _knowledge = persona_dependencies(db, persona)
    _extra, history = split_incoming(body.messages)
    context = build_context(db, persona.knowledge_base_id, last_user_text(history))
    system = brain.system_prompt or ""
    messages = compose_messages(system, history, context)
    payload = {
        "model": brain.model_name,
        "messages": messages,
        "temperature": brain.temperature,
        "max_tokens": brain.max_tokens,
        "stream": True,
    }
    url = completions_url(brain.base_url)
    api_key = decrypted_brain_key(brain)

    async def events():
        import time

        started = time.perf_counter()
        try:
            async for delta in iter_deltas(url, payload, api_key):
                yield f"data: {json.dumps({'delta': delta}, ensure_ascii=False)}\n\n"
            latency = int((time.perf_counter() - started) * 1000)
            yield f"data: {json.dumps({'done': True, 'latency_ms': latency})}\n\n"
        except UpstreamError as exc:
            yield f"data: {json.dumps({'error': exc.body or '上游错误'}, ensure_ascii=False)}\n\n"
        except httpx.HTTPError as exc:
            yield f"data: {json.dumps({'error': f'无法连接大脑：{exc}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
