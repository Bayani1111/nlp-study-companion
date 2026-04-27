from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReminderSetting
from app.schemas.reminders import ReminderSettingUpdate


async def get_or_create_settings(user_id: int, db: AsyncSession) -> ReminderSetting:
    result = await db.execute(select(ReminderSetting).where(ReminderSetting.user_id == user_id))
    setting = result.scalar_one_or_none()
    if setting is None:
        setting = ReminderSetting(user_id=user_id)
        db.add(setting)
        await db.flush()
        await db.refresh(setting)
    return setting


async def update_settings(
    setting: ReminderSetting,
    body: ReminderSettingUpdate,
    db: AsyncSession,
) -> ReminderSetting:
    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(setting, field, value)

    await db.flush()
    await db.refresh(setting)
    return setting
