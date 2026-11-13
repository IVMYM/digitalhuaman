from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _env_files() -> tuple[str, ...]:
    found = []
    for path in (_REPO_ROOT / ".env", Path(".env")):
        if path.is_file():
            found.append(str(path))
    return tuple(found)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files() or None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "数字人管理后台"
    app_env: str = "production"
    data_dir: str = "./data"
    database_url: str = ""
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 24 * 7
    encryption_key: str = ""
    admin_username: str = "admin"
    admin_password: str = "change-me"
    runtime_api_token: str = ""
    livetalking_url: str = "http://127.0.0.1:8010"
    static_dir: str = ""
    cors_origins: str = ""
    max_upload_mb: int = 200

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url.strip():
            return self.database_url.strip()
        path = Path(self.data_dir).resolve() / "app.db"
        return "sqlite:///" + path.as_posix()

    @property
    def secret_material(self) -> str:
        return (self.encryption_key or self.jwt_secret).strip()


@lru_cache
def get_settings() -> Settings:
    return Settings()
