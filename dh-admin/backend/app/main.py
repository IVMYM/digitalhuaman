import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app import __version__
from app import database
from app.config import get_settings
from app.routers import auth, avatars, brains, chat, dashboard, knowledge, openai_proxy, personas, runtime, system, voices
from app.services.bootstrap import ensure_admin, warn_weak_secrets

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("dh_admin")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    database.init_engine(settings.sqlalchemy_url)
    db = database.SessionLocal()
    try:
        ensure_admin(db, settings)
    finally:
        db.close()
    import app.routers.dashboard as dashboard_router

    dashboard_router.STARTED_AT = time.time()
    warn_weak_secrets(settings)
    logger.info("数字人管理后台 %s 已启动", __version__)
    yield
    database.reset()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request: Request, exc: RequestValidationError):
        parts = []
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", []) if part != "body")
            message = item.get("msg", "参数错误")
            parts.append(f"{loc}: {message}" if loc else message)
        return JSONResponse(status_code=422, content={"detail": "；".join(parts) or "参数错误"})

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/api/health")
    def health():
        return {"status": "ok", "version": __version__}

    app.include_router(auth.router, prefix="/api")
    app.include_router(avatars.router, prefix="/api")
    app.include_router(brains.router, prefix="/api")
    app.include_router(voices.router, prefix="/api")
    app.include_router(knowledge.router, prefix="/api")
    app.include_router(personas.router, prefix="/api")
    app.include_router(dashboard.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(system.router, prefix="/api")
    app.include_router(runtime.router, prefix="/api")
    app.include_router(openai_proxy.router)

    static_dir = settings.static_dir.strip()
    if static_dir:
        root = Path(static_dir)
        index = root / "index.html"
        if index.is_file():

            @app.get("/", include_in_schema=False)
            def spa_index():
                return FileResponse(index)

            @app.get("/{full_path:path}", include_in_schema=False)
            def spa_fallback(full_path: str):
                if full_path.startswith("api/") or full_path.startswith("v1/") or full_path in {"api", "v1"}:
                    raise HTTPException(status_code=404, detail="不存在")
                candidate = (root / full_path).resolve()
                if candidate != root and root.resolve() not in candidate.parents:
                    raise HTTPException(status_code=404, detail="不存在")
                if candidate.is_file():
                    return FileResponse(candidate)
                return FileResponse(index)

    return app


app = create_app()
