"""提醒设置相关的 Pydantic 请求/响应模型。"""

from pydantic import BaseModel, Field


class ReminderSettingResponse(BaseModel):
    """提醒设置响应。"""

    id: int
    before_start_minutes: int = 30
    before_due_minutes: int = 60
    overdue_enabled: bool = True
    quiet_start_hour: int = 22
    quiet_end_hour: int = 8

    model_config = {"from_attributes": True}


class ReminderSettingUpdate(BaseModel):
    """更新提醒设置请求。"""

    before_start_minutes: int | None = Field(None, ge=0, le=1440)
    before_due_minutes: int | None = Field(None, ge=0, le=1440)
    overdue_enabled: bool | None = None
    quiet_start_hour: int | None = Field(None, ge=0, le=23)
    quiet_end_hour: int | None = Field(None, ge=0, le=23)
