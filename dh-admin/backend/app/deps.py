import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User
from app.security import decode_access_token


def _bearer(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, token = get_authorization_scheme_param(authorization)
    if scheme.lower() == "bearer" and token:
        return token
    return ""


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = _bearer(request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", "0"))
    except Exception:
        raise HTTPException(status_code=401, detail="登录已失效")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def require_runtime_token(request: Request) -> None:
    expected = get_settings().runtime_api_token.strip()
    if not expected:
        raise HTTPException(status_code=503, detail="服务器未配置 RUNTIME_API_TOKEN")
    provided = request.headers.get("x-runtime-token", "").strip() or _bearer(request)
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="运行时令牌无效")
