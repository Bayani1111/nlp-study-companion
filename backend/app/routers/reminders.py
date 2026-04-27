from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import decode_access_token, get_current_user
from app.schemas.reminders import ReminderSettingResponse, ReminderSettingUpdate
from app.services import reminder_settings_service
from app.services.reminder_service import manager

router = APIRouter()


@router.websocket("/ws")
async def websocket_reminders(ws: WebSocket):
    token = ws.cookies.get(settings.AUTH_COOKIE_NAME) or ws.query_params.get("token")
    if not token:
        await ws.close(code=4001, reason="缺少认证信息")
        return

    try:
        user_id = decode_access_token(token)
    except Exception:
        await ws.close(code=4001, reason="无效的认证令牌")
        return

    await manager.connect(user_id, ws)
    try:
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(user_id, ws)


@router.get("/settings", response_model=ReminderSettingResponse)
async def get_reminder_settings(
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    setting = await reminder_settings_service.get_or_create_settings(user_id, db)
    return ReminderSettingResponse.model_validate(setting)


@router.put("/settings", response_model=ReminderSettingResponse)
async def update_reminder_settings(
    body: ReminderSettingUpdate,
    user_id: int = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    setting = await reminder_settings_service.get_or_create_settings(user_id, db)
    setting = await reminder_settings_service.update_settings(setting, body, db)
    return ReminderSettingResponse.model_validate(setting)
