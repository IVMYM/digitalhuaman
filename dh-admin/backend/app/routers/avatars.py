import mimetypes

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Avatar, Persona, User, Voice
from app.schemas import AvatarIn
from app.serialize import avatar_dict
from app.services.personas import clear_other_defaults, get_or_404
from app.services.storage import delete_storage, resolve_storage, save_upload

router = APIRouter(prefix="/avatars", tags=["avatars"], dependencies=[Depends(get_current_user)])

PREVIEW_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
SOURCE_EXT = {".mp4", ".webm", ".mov", ".mkv", ".zip", ".png", ".jpg", ".jpeg", ".json", ".wav"}


def _apply(row: Avatar, body: AvatarIn, db: Session) -> None:
    if body.default_voice_id is not None and db.get(Voice, body.default_voice_id) is None:
        raise HTTPException(status_code=400, detail="默认声音不存在")
    row.name = body.name.strip()
    row.type = body.type
    row.livetalking_avatar_id = body.livetalking_avatar_id.strip()
    row.default_voice_id = body.default_voice_id
    row.is_default = body.is_default


@router.get("")
def list_avatars(db: Session = Depends(get_db)):
    rows = db.query(Avatar).order_by(Avatar.id.desc()).all()
    return [avatar_dict(row, db) for row in rows]


@router.post("")
def create_avatar(body: AvatarIn, db: Session = Depends(get_db)):
    row = Avatar()
    _apply(row, body, db)
    db.add(row)
    db.commit()
    db.refresh(row)
    if row.is_default:
        clear_other_defaults(db, Avatar, row.id)
        db.commit()
    return avatar_dict(row, db)


@router.put("/{avatar_id}")
def update_avatar(avatar_id: int, body: AvatarIn, db: Session = Depends(get_db)):
    row = get_or_404(db, Avatar, avatar_id, "形象")
    _apply(row, body, db)
    if row.is_default:
        clear_other_defaults(db, Avatar, row.id)
    db.commit()
    db.refresh(row)
    return avatar_dict(row, db)


@router.delete("/{avatar_id}")
def delete_avatar(avatar_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Avatar, avatar_id, "形象")
    used = db.query(Persona).filter(Persona.avatar_id == row.id).count()
    if used:
        raise HTTPException(status_code=409, detail="仍有数字人角色在使用这个形象")
    delete_storage(row.preview_path)
    delete_storage(row.source_path)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/{avatar_id}/preview")
def upload_preview(
    avatar_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    row = get_or_404(db, Avatar, avatar_id, "形象")
    relative, original, _size = save_upload(file, "avatars/preview", PREVIEW_EXT)
    delete_storage(row.preview_path)
    row.preview_path = relative
    row.preview_filename = original
    db.commit()
    return avatar_dict(row, db)


@router.post("/{avatar_id}/source")
def upload_source(
    avatar_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    row = get_or_404(db, Avatar, avatar_id, "形象")
    relative, original, _size = save_upload(file, "avatars/source", SOURCE_EXT)
    delete_storage(row.source_path)
    row.source_path = relative
    row.source_filename = original
    db.commit()
    return avatar_dict(row, db)


@router.get("/{avatar_id}/preview")
def download_preview(avatar_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Avatar, avatar_id, "形象")
    path = resolve_storage(row.preview_path)
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media)


@router.get("/{avatar_id}/source")
def download_source(avatar_id: int, db: Session = Depends(get_db)):
    row = get_or_404(db, Avatar, avatar_id, "形象")
    path = resolve_storage(row.source_path)
    media = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media, filename=row.source_filename or path.name)
