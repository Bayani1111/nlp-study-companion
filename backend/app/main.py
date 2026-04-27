from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.dependencies import decode_access_token
from app.logging_config import configure_logging
from app.middleware import register_middleware
from app.services.reminder_service import check_and_send_reminders, manager

configure_logging(settings.LOG_LEVEL, settings.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        minutes=1,
        id="check_and_send_reminders",
        coalesce=True,
        max_instances=1,
        replace_existing=True,
    )
    scheduler.start()
    app.state.scheduler = scheduler

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(
    title="NLP 学习陪伴系统",
    description="一个集成认证、任务、计划、聊天和提醒能力的学习陪伴 API。",
    version="0.1.0",
    lifespan=lifespan,
)

register_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", settings.CSRF_HEADER_NAME],
)

try:
    from app.routers import auth

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
except (ImportError, AttributeError):
    pass

try:
    from app.routers import chat

    app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
except (ImportError, AttributeError):
    pass

try:
    from app.routers import tasks

    app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
except (ImportError, AttributeError):
    pass

try:
    from app.routers import plans

    app.include_router(plans.router, prefix="/api/plans", tags=["plans"])
except (ImportError, AttributeError):
    pass

try:
    from app.routers import stats

    app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
except (ImportError, AttributeError):
    pass

try:
    from app.routers import reminders

    app.include_router(reminders.router, prefix="/api/reminders", tags=["reminders"])
except (ImportError, AttributeError):
    pass

try:
    from app.routers import health

    app.include_router(health.router, prefix="/api/health", tags=["health"])
except (ImportError, AttributeError):
    pass


@app.websocket("/ws/reminders")
async def ws_reminders_root(ws: WebSocket):
    origin = ws.headers.get("origin")
    if origin and origin.rstrip("/") not in settings.CORS_ORIGINS:
        await ws.close(code=4003, reason="不受信任的请求来源")
        return

    token = ws.cookies.get(settings.AUTH_COOKIE_NAME) or ws.query_params.get("token")
    if not token:
        await ws.close(code=4001, reason="缺少认证信息")
        return

    try:
        uid = decode_access_token(token)
    except Exception:
        await ws.close(code=4001, reason="无效的认证令牌")
        return

    await manager.connect(uid, ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(uid, ws)


_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
