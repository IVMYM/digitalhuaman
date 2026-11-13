from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Brain, Persona
from app.presets import PRESETS
from app.schemas import BrainIn, BrainTestIn, DshExpertsIn, DshVerifyIn
from app.security import encrypt_secret
from app.serialize import brain_dict
from app.services.dsh import DshError, list_experts, verify as dsh_verify
from app.services.llm import test_connection
from app.services.personas import decrypted_brain_key, get_or_404

router = APIRouter(prefix="/brains", tags=["brains"], dependencies=[Depends(get_current_user)])


def _apply_key(row: Brain, api_key: str | None, *, creating: bool) -> None:
    if api_key is None:
        return
    if api_key == "" and not creating:
        return
    row.api_key_encrypted = encrypt_secret(api_key) if api_key else ""


def _apply(row: Brain, body: BrainIn, *, creating: bool) -> None:
    row.name = body.name.strip()
    row.preset = body.preset.strip()
    row.base_url = body.base_url
    row.model_name = body.model_name.strip()
    row.temperature = body.temperature
    row.max_tokens = body.max_tokens
    row.system_prompt = body.system_prompt
    row.app_id = body.app_id.strip()
    row.agent_id = body.agent_id.strip()
    _apply_key(row, body.api_key, creating=creating)


@router.get("/presets")
def list_presets():
    return PRESETS


@router.get("")
def list_brains(db: Session = Depends(get_db)):
    rows = db.query(Brain).order_by(Brain.id.desc()).all()
    return [brain_dict(row) for row in rows]


@router.post("")
def create_brain(body: BrainIn, db: Session = Depends(get_db)):
    row = Brain()
    _apply(row, body, creating=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    return brain_dict(row)


@router.put("/{brain_id}")
def update_brain(brain_id: int, body: BrainIn, db: Session = Depends(get_db)):
    row = get_or_404(db, Brain, brain_id, "大脑")
    _apply(row, body, creating=False)
    db.commit()
    db.refresh(row)
    return brain_dict(row)


@router.delete("/{brain_id}")
def delete_brain(brain_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Brain, brain_id, "大脑")
    if db.query(Persona).filter(Persona.brain_id == row.id).count():
        raise HTTPException(status_code=409, detail="仍有数字人角色在使用这个大脑")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/test")
async def test_brain(body: BrainTestIn, db: Session = Depends(get_db)):
    api_key = (body.api_key or "").strip()
    if not api_key and body.brain_id:
        row = get_or_404(db, Brain, body.brain_id, "大脑")
        api_key = decrypted_brain_key(row)
    return await test_connection(body.base_url, api_key, body.model_name.strip())


@router.post("/{brain_id}/test")
async def test_saved_brain(brain_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Brain, brain_id, "大脑")
    return await test_connection(row.base_url, decrypted_brain_key(row), row.model_name)


def _dsh_credentials(body, db: Session) -> tuple[str, str]:
    """表单里没填的字段回落到已保存大脑的 App ID / App Secret。"""
    app_id = (getattr(body, "app_id", "") or "").strip()
    secret = (body.api_key or "").strip()
    if body.brain_id and (not app_id or not secret):
        row = get_or_404(db, Brain, body.brain_id, "大脑")
        if not app_id:
            app_id = (row.app_id or "").strip()
        if not secret:
            secret = decrypted_brain_key(row)
    return app_id, secret


@router.post("/dsh/experts")
async def dsh_experts(body: DshExpertsIn, db: Session = Depends(get_db)):
    app_id, secret = _dsh_credentials(body, db)
    if not app_id or not secret:
        raise HTTPException(status_code=400, detail="先填 App ID 和 App Secret")
    try:
        experts = await list_experts(body.base_url, app_id, secret)
    except DshError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"experts": experts}


@router.post("/dsh/verify")
async def dsh_verify_brain(body: DshVerifyIn, db: Session = Depends(get_db)):
    app_id, secret = _dsh_credentials(body, db)
    return await dsh_verify(body.base_url, app_id, secret, body.agent_id, body.question)
