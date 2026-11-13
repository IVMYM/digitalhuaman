from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from app.models import Avatar, Brain, KnowledgeBase, Persona, Voice
from app.security import decrypt_secret


def get_or_404(db: Session, model, item_id: int, label: str):
    row = db.get(model, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label}不存在")
    return row


def clear_other_defaults(db: Session, model, current_id: int) -> None:
    db.query(model).filter(model.id != current_id, model.is_default.is_(True)).update(
        {model.is_default: False}, synchronize_session=False
    )


def persona_dependencies(db: Session, persona: Persona) -> tuple[Avatar, Brain, Voice, KnowledgeBase | None]:
    avatar = get_or_404(db, Avatar, persona.avatar_id, "形象")
    brain = get_or_404(db, Brain, persona.brain_id, "大脑")
    voice = get_or_404(db, Voice, persona.voice_id, "声音")
    knowledge = None
    if persona.knowledge_base_id:
        knowledge = db.get(KnowledgeBase, persona.knowledge_base_id)
    return avatar, brain, voice, knowledge


def resolve_persona(db: Session, request: Request, body: dict) -> Persona:
    header = (request.headers.get("x-persona-id") or "").strip()
    model_name = str(body.get("model") or "").strip()
    if model_name.startswith("persona:"):
        model_name = model_name.split(":", 1)[1].strip()
    persona = _lookup(db, header) if header else None
    if persona is None and model_name:
        persona = _lookup(db, model_name)
    if persona is None:
        persona = (
            db.query(Persona)
            .filter(Persona.is_default.is_(True), Persona.enabled.is_(True))
            .order_by(Persona.id.asc())
            .first()
        )
    if persona is None:
        persona = db.query(Persona).filter(Persona.enabled.is_(True)).order_by(Persona.id.asc()).first()
    if persona is None:
        raise HTTPException(status_code=404, detail="没有可用的数字人角色")
    if not persona.enabled:
        raise HTTPException(status_code=409, detail="角色已停用")
    return persona


def _lookup(db: Session, key: str) -> Persona | None:
    if not key:
        return None
    if key.isdigit():
        row = db.get(Persona, int(key))
        if row is not None:
            return row
    return db.query(Persona).filter(Persona.name == key).first()


def decrypted_brain_key(brain: Brain) -> str:
    try:
        return decrypt_secret(brain.api_key_encrypted)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
