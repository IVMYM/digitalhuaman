from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

engine = None
SessionLocal = None


def reset() -> None:
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
    engine = None
    SessionLocal = None


def init_engine(url: str) -> None:
    global engine, SessionLocal
    reset()
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_conn, _connection_record):
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    _ensure_brain_columns(engine)


def _ensure_brain_columns(engine) -> None:
    # brains 表早期版本没有 app_id / agent_id 两列（DSH 专家大脑用），缺了就补上。
    from sqlalchemy import inspect, text

    columns = {item["name"] for item in inspect(engine).get_columns("brains")}
    with engine.begin() as conn:
        if "app_id" not in columns:
            conn.execute(text("ALTER TABLE brains ADD COLUMN app_id VARCHAR(200) DEFAULT ''"))
        if "agent_id" not in columns:
            conn.execute(text("ALTER TABLE brains ADD COLUMN agent_id VARCHAR(200) DEFAULT ''"))


def get_db() -> Generator[Session, None, None]:
    if SessionLocal is None:
        raise RuntimeError("数据库尚未初始化")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
