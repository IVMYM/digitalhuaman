import shutil
import time
import httpx
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import __version__
from app.config import get_settings
from app.database import get_db
from app.deps import get_current_user
from app.models import Avatar, Brain, KnowledgeBase, KnowledgeDocument, Persona, Voice
from app.services.storage import data_root

router = APIRouter(prefix="/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])

STARTED_AT = time.time()


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                continue
    return total


@router.get("")
def dashboard(db: Session = Depends(get_db)):
    settings = get_settings()
    root = data_root()
    writable = True
    try:
        probe = root / ".write-probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        writable = False
    usage = shutil.disk_usage(root)
    default_avatar = db.query(Avatar).filter(Avatar.is_default.is_(True)).first()
    default_persona = db.query(Persona).filter(Persona.is_default.is_(True)).first()
    scheme = settings.sqlalchemy_url.split(":", 1)[0]
    livetalking = {"configured": bool(settings.livetalking_url.strip()), "url": settings.livetalking_url.rstrip("/"), "online": False, "sessions": 0, "max_session": None, "error": ""}
    try:
        with httpx.Client(timeout=2) as client:
            config = client.get(f"{livetalking['url']}/api/admin/config").json()
            sessions = client.get(f"{livetalking['url']}/api/admin/sessions").json()
        cfg = config.get("data", {}).get("config", {})
        rows = sessions.get("data", {}).get("sessions", [])
        livetalking.update({"online": True, "sessions": len(rows), "max_session": cfg.get("max_session"), "model": cfg.get("model"), "transport": cfg.get("transport")})
    except Exception as exc:
        livetalking["error"] = str(exc)
    return {
        "counts": {
            "avatars": db.query(Avatar).count(),
            "brains": db.query(Brain).count(),
            "voices": db.query(Voice).count(),
            "personas": db.query(Persona).count(),
            "personas_enabled": db.query(Persona).filter(Persona.enabled.is_(True)).count(),
            "knowledge_bases": db.query(KnowledgeBase).count(),
            "documents": db.query(KnowledgeDocument).count(),
        },
        "status": {
            "database": "ok",
            "database_scheme": scheme,
            "data_dir": str(root),
            "data_dir_writable": writable,
            "data_dir_bytes": _dir_size(root),
            "disk_free_bytes": usage.free,
            "disk_total_bytes": usage.total,
            "runtime_token_configured": bool(settings.runtime_api_token.strip()),
            "default_avatar": default_avatar.name if default_avatar else "",
            "default_persona": default_persona.name if default_persona else "",
            "version": __version__,
            "uptime_seconds": int(time.time() - STARTED_AT),
            "livetalking": livetalking,
        },
    }
