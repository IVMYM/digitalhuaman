from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_runtime_token
from app.models import Persona
from app.presets import TTS_FLAG
from app.services.personas import decrypted_brain_key, get_or_404, persona_dependencies

router = APIRouter(prefix="/runtime", tags=["runtime"], dependencies=[Depends(require_runtime_token)])


def _summary(row: Persona) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "enabled": row.enabled,
        "is_default": row.is_default,
        "description": row.description or "",
    }


def resolved_config(db: Session, persona: Persona, request: Request) -> dict:
    avatar, brain, voice, knowledge = persona_dependencies(db, persona)
    base = str(request.base_url).rstrip("/")
    return {
        "id": persona.id,
        "name": persona.name,
        "description": persona.description or "",
        "enabled": persona.enabled,
        "is_default": persona.is_default,
        "avatar": {
            "id": avatar.id,
            "name": avatar.name,
            "type": avatar.type,
            "livetalking_avatar_id": avatar.livetalking_avatar_id or "",
            "is_default": avatar.is_default,
            "default_voice_id": avatar.default_voice_id,
        },
        "brain": {
            "id": brain.id,
            "name": brain.name,
            "preset": brain.preset or "",
            "base_url": brain.base_url,
            "api_key": decrypted_brain_key(brain),
            "app_id": brain.app_id or "",
            "agent_id": brain.agent_id or "",
            "model_name": brain.model_name,
            "temperature": brain.temperature,
            "max_tokens": brain.max_tokens,
            "system_prompt": brain.system_prompt or "",
        },
        "voice": {
            "id": voice.id,
            "name": voice.name,
            "engine": voice.engine,
            "endpoint_url": voice.endpoint_url or "",
            "voice_id": voice.voice_id or "",
            "livetalking_tts": TTS_FLAG.get(voice.engine, ""),
        },
        "knowledge_base": None
        if knowledge is None
        else {"id": knowledge.id, "name": knowledge.name, "description": knowledge.description or ""},
        "llm_proxy": {
            "chat_completions_url": f"{base}/v1/chat/completions",
            "persona_model": persona.name,
            "persona_header": "X-Persona-Id",
        },
    }


@router.get("/personas")
def list_runtime_personas(db: Session = Depends(get_db)):
    rows = db.query(Persona).order_by(Persona.id.asc()).all()
    return [_summary(row) for row in rows]


@router.get("/personas/{persona_id}")
def get_runtime_persona(persona_id: int, request: Request, db: Session = Depends(get_db)):
    persona = get_or_404(db, Persona, persona_id, "角色")
    return resolved_config(db, persona, request)
