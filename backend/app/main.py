from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from . import auth, backup, library, reviews, stats
from .config import settings
from .database import engine
from .static import SPAFiles


@asynccontextmanager
async def lifespan(app):
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    yield


app = FastAPI(title="拾忆 API", version="1.0.0", lifespan=lifespan,
              description="三科知识与图片错题管理、FSRS 复习调度。外部工具使用 Authorization: Bearer sy_... 鉴权；密钥在网页设置中创建。",
              docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=[host.strip() for host in settings.trusted_hosts.split(",")])


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api") and "/media/" not in request.url.path:
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(IntegrityError)
async def conflict(request, exc):
    return JSONResponse(status_code=409, content={"detail": "记录已存在或存在关联冲突，请刷新后重试"})


@app.get("/api/health", tags=["服务状态"])
def health():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ok", "version": "1.0.0"}


for router in (auth.router, library.router, reviews.router, stats.router, backup.router):
    app.include_router(router)

if (settings.frontend_dir / "index.html").is_file():
    app.mount("/", SPAFiles(directory=settings.frontend_dir, html=True), name="frontend")
