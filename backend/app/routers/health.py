from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("", summary="Health check")
async def health_check() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "debug": settings.DEBUG,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
