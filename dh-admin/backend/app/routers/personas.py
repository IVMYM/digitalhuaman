from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Avatar, Brain, KnowledgeBase, Persona, Voice
from app.schemas import PersonaIn
from app.serialize import persona_dict
from app.services.personas import clear_other_defaults, get_or_404

router = APIRouter(prefix="/personas", tags=["personas"], dependencies=[Depends(get_current_user)])


def _check_refs(db: Session, body: PersonaIn) -> None:
    if db.get(Avatar, body.avatar_id) is None:
        raise HTTPException(status_code=400, detail="形象不存在")
    if db.get(Brain, body.brain_id) is None:
        raise HTTPException(status_code=400, detail="大脑不存在")
    if db.get(Voice, body.voice_id) is None:
        raise HTTPException(status_code=400, detail="声音不存在")
    if body.knowledge_base_id is not None and db.get(KnowledgeBase, body.knowledge_base_id) is None:
        raise HTTPException(status_code=400, detail="知识库不存在")


def _apply(row: Persona, body: PersonaIn) -> None:
    row.name = body.name.strip()
    row.description = body.description.strip()
    row.avatar_id = body.avatar_id
    row.brain_id = body.brain_id
    row.voice_id = body.voice_id
    row.knowledge_base_id = body.knowledge_base_id
    # 停用优先于“默认”。默认角色必须处于启用状态。
    row.enabled = body.enabled
    row.is_default = body.is_default and body.enabled
    if not row.name:
        raise HTTPException(status_code=400, detail="名称不能为空")


@router.get("")
def list_personas(db: Session = Depends(get_db)):
    rows = db.query(Persona).order_by(Persona.id.desc()).all()
    return [persona_dict(row, db) for row in rows]


@router.post("")
def create_persona(body: PersonaIn, db: Session = Depends(get_db)):
    _check_refs(db, body)
    row = Persona(name="tmp", avatar_id=body.avatar_id, brain_id=body.brain_id, voice_id=body.voice_id)
    _apply(row, body)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="已有同名角色")
    db.refresh(row)
    if row.is_default:
        clear_other_defaults(db, Persona, row.id)
        db.commit()
    return persona_dict(row, db)


@router.put("/{persona_id}")
def update_persona(persona_id: int, body: PersonaIn, db: Session = Depends(get_db)):
    row = get_or_404(db, Persona, persona_id, "角色")
    _check_refs(db, body)
    _apply(row, body)
    if row.is_default:
        clear_other_defaults(db, Persona, row.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="已有同名角色")
    db.refresh(row)
    return persona_dict(row, db)


@router.delete("/{persona_id}")
def delete_persona(persona_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Persona, persona_id, "角色")
    db.delete(row)
    db.commit()
    return {"ok": True}
