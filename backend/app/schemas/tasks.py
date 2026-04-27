from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import (
    strip_optional_text,
    strip_text,
    validate_non_empty_text,
    validate_positive_optional_int,
)

VALID_PRIORITIES = {"high", "medium", "low"}
VALID_STATUSES = {"pending", "in_progress", "completed", "overdue"}


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    priority: str = "medium"
    status: str = "pending"
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    plan_id: int | None = None
    phase_id: int | None = None
    parent_task_id: int | None = None
    scheduled_date: date | None = None
    sort_order: int = 0

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        return strip_text(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        return validate_non_empty_text(value)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return strip_optional_text(value)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str) -> str:
        if value not in VALID_PRIORITIES:
            raise ValueError("优先级必须是 high、medium 或 low")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in VALID_STATUSES:
            raise ValueError("状态必须是 pending、in_progress、completed 或 overdue")
        return value

    @field_validator("estimated_minutes")
    @classmethod
    def validate_estimated_minutes(cls, value: int | None) -> int | None:
        return validate_positive_optional_int(value, "estimated_minutes")

    @field_validator("plan_id", "phase_id", "parent_task_id")
    @classmethod
    def validate_positive_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("ID 必须大于 0")
        return value


class TaskUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)
    priority: str | None = None
    status: str | None = None
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    actual_minutes: int | None = None
    plan_id: int | None = None
    phase_id: int | None = None
    parent_task_id: int | None = None
    scheduled_date: date | None = None
    sort_order: int | None = None

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return strip_text(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_non_empty_text(value)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return strip_optional_text(value)

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_PRIORITIES:
            raise ValueError("优先级必须是 high、medium 或 low")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in VALID_STATUSES:
            raise ValueError("状态必须是 pending、in_progress、completed 或 overdue")
        return value

    @field_validator("estimated_minutes")
    @classmethod
    def validate_estimated_minutes(cls, value: int | None) -> int | None:
        return validate_positive_optional_int(value, "estimated_minutes")

    @field_validator("actual_minutes")
    @classmethod
    def validate_actual_minutes(cls, value: int | None) -> int | None:
        return validate_positive_optional_int(value, "actual_minutes")

    @field_validator("plan_id", "phase_id", "parent_task_id")
    @classmethod
    def validate_positive_id(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("ID 必须大于 0")
        return value


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    priority: str
    status: str
    due_date: datetime | None = None
    estimated_minutes: int | None = None
    actual_minutes: int = 0
    plan_id: int | None = None
    phase_id: int | None = None
    parent_task_id: int | None = None
    scheduled_date: date | None = None
    sort_order: int = 0
    subtask_count: int = 0
    completed_subtask_count: int = 0
    children: list["TaskResponse"] = Field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


TaskResponse.model_rebuild()


class AdvisoryCleanupCandidate(BaseModel):
    id: int
    parent_task_id: int | None = None
    title: str
    reason: str


class AdvisoryCleanupResponse(BaseModel):
    dry_run: bool
    scanned_subtasks: int
    matched_count: int
    deleted_count: int
    candidates: list[AdvisoryCleanupCandidate] = Field(default_factory=list)
