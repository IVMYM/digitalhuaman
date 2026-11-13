from sqlalchemy.orm import Session

from app.models import Avatar, Brain, KnowledgeBase, KnowledgeDocument, Persona, Voice
from app.presets import TTS_FLAG
from app.security import decrypt_secret, mask_secret


def iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def voice_dict(row: Voice) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "engine": row.engine,
        "endpoint_url": row.endpoint_url or "",
        "voice_id": row.voice_id or "",
        "has_reference": bool(row.reference_path),
        "reference_filename": row.reference_filename or "",
        "livetalking_tts": TTS_FLAG.get(row.engine, ""),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def avatar_dict(row: Avatar, db: Session) -> dict:
    voice_name = ""
    if row.default_voice_id:
        voice = db.get(Voice, row.default_voice_id)
        voice_name = voice.name if voice else ""
    return {
        "id": row.id,
        "name": row.name,
        "type": row.type,
        "livetalking_avatar_id": row.livetalking_avatar_id or "",
        "default_voice_id": row.default_voice_id,
        "default_voice_name": voice_name,
        "is_default": row.is_default,
        "has_preview": bool(row.preview_path),
        "preview_filename": row.preview_filename or "",
        "has_source": bool(row.source_path),
        "source_filename": row.source_filename or "",
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def brain_dict(row: Brain) -> dict:
    plain = ""
    broken = False
    if row.api_key_encrypted:
        try:
            plain = decrypt_secret(row.api_key_encrypted)
        except ValueError:
            broken = True
    return {
        "id": row.id,
        "name": row.name,
        "preset": row.preset or "",
        "base_url": row.base_url,
        "model_name": row.model_name,
        "temperature": row.temperature,
        "max_tokens": row.max_tokens,
        "system_prompt": row.system_prompt or "",
        "app_id": row.app_id or "",
        "agent_id": row.agent_id or "",
        "has_api_key": bool(row.api_key_encrypted),
        "api_key_masked": "无法解密" if broken else mask_secret(plain),
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def knowledge_base_dict(row: KnowledgeBase, document_count: int) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "document_count": document_count,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }


def document_dict(row: KnowledgeDocument) -> dict:
    return {
        "id": row.id,
        "knowledge_base_id": row.knowledge_base_id,
        "original_name": row.original_name,
        "content_type": row.content_type or "",
        "size_bytes": row.size_bytes,
        "has_text": bool(row.text_content),
        "text_chars": len(row.text_content or ""),
        "created_at": iso(row.created_at),
    }


def persona_dict(row: Persona, db: Session) -> dict:
    avatar = db.get(Avatar, row.avatar_id)
    brain = db.get(Brain, row.brain_id)
    voice = db.get(Voice, row.voice_id)
    knowledge = db.get(KnowledgeBase, row.knowledge_base_id) if row.knowledge_base_id else None
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description or "",
        "avatar_id": row.avatar_id,
        "avatar_name": avatar.name if avatar else "",
        "brain_id": row.brain_id,
        "brain_name": brain.name if brain else "",
        "voice_id": row.voice_id,
        "voice_name": voice.name if voice else "",
        "knowledge_base_id": row.knowledge_base_id,
        "knowledge_base_name": knowledge.name if knowledge else "",
        "enabled": row.enabled,
        "is_default": row.is_default,
        "created_at": iso(row.created_at),
        "updated_at": iso(row.updated_at),
    }
