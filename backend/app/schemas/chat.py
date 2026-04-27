from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import strip_text, validate_non_empty_text


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: int | None = None
    proposal_id: str | None = Field(default=None, max_length=64)

    @field_validator("message", mode="before")
    @classmethod
    def normalize_message(cls, value: str) -> str:
        return strip_text(value)

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        return validate_non_empty_text(value)


class ChatResponse(BaseModel):
    reply: str
    intent: str
    session_id: int
    extracted_tasks: list[dict] | None = None
    extracted_plans: list[dict] | None = None
    sync_summary: str | None = None
    next_prompt: str | None = None
    next_prompt_options: list[str] | None = None
    proposal_id: str | None = None
    scenario_type: str | None = None
    scenario_label: str | None = None


class MessageInfo(BaseModel):
    id: int
    role: str
    content: str
    intent: str | None = None
    entities: dict | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SessionInfo(BaseModel):
    id: int
    title: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
