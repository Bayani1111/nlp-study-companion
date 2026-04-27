import logging
from urllib.parse import urlparse

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings

logger = logging.getLogger(__name__)

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _normalize_origin(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


def _is_trusted_origin(origin: str | None) -> bool:
    normalized = _normalize_origin(origin)
    if not normalized:
        return False
    return normalized in settings.CORS_ORIGINS


def register_middleware(app: FastAPI) -> None:
    """Register exception handling plus origin and CSRF protection."""

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error("Database operation failed: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "服务器内部错误，请稍后重试"},
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error("Unhandled exception: %s", exc, exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "服务器内部错误"},
        )

    @app.middleware("http")
    async def origin_and_csrf_middleware(request: Request, call_next):
        if request.method in _SAFE_METHODS or not request.url.path.startswith("/api/"):
            return await call_next(request)

        auth_cookie = request.cookies.get(settings.AUTH_COOKIE_NAME)
        if not auth_cookie:
            return await call_next(request)

        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        source = origin or referer
        if not _is_trusted_origin(source):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "不受信任的请求来源"},
            )

        csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
        csrf_header = request.headers.get(settings.CSRF_HEADER_NAME)
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "CSRF 校验失败"},
            )

        return await call_next(request)
