import mimetypes

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Avatar, Persona, Voice
from app.schemas import VoiceIn
from app.serialize import voice_dict
from app.services.personas import get_or_404
from app.services.storage import delete_storage, resolve_storage, save_upload

router = APIRouter(prefix="/voices", tags=["voices"], dependencies=[Depends(get_current_user)])

AUDIO_EXT = {".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"}


@router.get("")
def list_voices(db: Session = Depends(get_db)):
    rows = db.query(Voice).order_by(Voice.id.desc()).all()
    return [voice_dict(row) for row in rows]


@router.post("")
def create_voice(body: VoiceIn, db: Session = Depends(get_db)):
    row = Voice(
        name=body.name.strip(),
        engine=body.engine,
        endpoint_url=body.endpoint_url,
        voice_id=body.voice_id.strip(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return voice_dict(row)


@router.put("/{voice_id}")
def update_voice(voice_id: int, body: VoiceIn, db: Session = Depends(get_db)):
    row = get_or_404(db, Voice, voice_id, "声音")
    row.name = body.name.strip()
    row.engine = body.engine
    row.endpoint_url = body.endpoint_url
    row.voice_id = body.voice_id.strip()
    db.commit()
    db.refresh(row)
    return voice_dict(row)


@router.delete("/{voice_id}")
def delete_voice(voice_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Voice, voice_id, "声音")
    if db.query(Persona).filter(Persona.voice_id == row.id).count():
        raise HTTPException(status_code=409, detail="仍有数字人角色在使用这个声音")
    db.query(Avatar).filter(Avatar.default_voice_id == row.id).update(
        {Avatar.default_voice_id: None}, synchronize_session=False
    )
    delete_storage(row.reference_path)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{voice_id}/reference")
def upload_reference(
    voice_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    row = get_or_404(db, Voice, voice_id, "声音")
    relative, original, _size = save_upload(file, "voices", AUDIO_EXT)
    delete_storage(row.reference_path)
    row.reference_path = relative
    row.reference_filename = original
    db.commit()
    return voice_dict(row)


@router.get("/{voice_id}/reference")
def download_reference(voice_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Voice, voice_id, "声音")
    path = resolve_storage(row.reference_path)
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media, filename=row.reference_filename or path.name)
