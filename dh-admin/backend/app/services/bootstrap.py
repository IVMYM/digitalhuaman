import logging

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import User
from app.security import hash_password

logger = logging.getLogger("dh_admin")


def ensure_admin(db: Session, settings: Settings) -> None:
    if db.query(User).count() > 0:
        return
    username = settings.admin_username.strip()
    password = settings.admin_password
    if not username or not password:
        raise RuntimeError("首次启动需要 ADMIN_USERNAME 和 ADMIN_PASSWORD")
    db.add(User(username=username, password_hash=hash_password(password)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return
    logger.info("已创建初始管理员 %s", username)


def warn_weak_secrets(settings: Settings) -> None:
    blob = " ".join([settings.jwt_secret, settings.encryption_key, settings.admin_password, settings.runtime_api_token])
    if "please-change-me" in blob or "change-me" == settings.jwt_secret:
        logger.warning("仍在使用示例密钥或密码，请修改 .env 后再对公网或同事开放")
    if not settings.runtime_api_token.strip():
        logger.warning("未配置 RUNTIME_API_TOKEN，LiveTalking 运行时接口会拒绝访问")
