import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.config import get_settings


def data_root() -> Path:
    root = Path(get_settings().data_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def safe_original_name(name: str | None) -> str:
    cleaned = Path(name or "file").name.replace("\x00", "").strip()
    return (cleaned or "file")[:180]


def resolve_storage(relative: str) -> Path:
    if not relative:
        raise HTTPException(status_code=404, detail="没有文件")
    root = data_root()
    path = (root / relative).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=400, detail="非法路径")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")
    return path


def delete_storage(relative: str) -> None:
    if not relative:
        return
    root = data_root()
    path = (root / relative).resolve()
    if root in path.parents and path.is_file():
        path.unlink()


def save_upload(upload: UploadFile, subdir: str, allowed_ext: set[str]) -> tuple[str, str, int]:
    original = safe_original_name(upload.filename)
    ext = Path(original).suffix.lower()
    if ext not in allowed_ext:
        allowed = "、".join(sorted(allowed_ext))
        raise HTTPException(status_code=400, detail=f"不支持的文件类型 {ext or '（无后缀）'}，允许：{allowed}")
    dest_dir = data_root() / "uploads" / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{ext}"
    dest = dest_dir / stored_name
    limit = get_settings().max_upload_mb * 1024 * 1024
    size = 0
    try:
        with dest.open("wb") as handle:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise HTTPException(status_code=413, detail=f"文件超过 {get_settings().max_upload_mb} MB")
                handle.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件是空的")
    relative = str(dest.relative_to(data_root()))
    return relative.replace(os.sep, "/"), original, size
