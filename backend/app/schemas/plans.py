from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import strip_optional_text, strip_text, validate_non_empty_text


class PlanPhaseInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=1000)
    start_date: date | None = None
    end_date: date | None = None
    sequence: int = 0

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

    @model_validator(mode="after")
    def validate_dates(self) -> "PlanPhaseInput":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("阶段开始日期不能晚于结束日期")
        return self


class PlanCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_date: date
    end_date: date
    template_key: str | None = Field(None, max_length=50)
    phases: list[PlanPhaseInput] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def validate_dates(self) -> "PlanCreate":
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class PlanUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_date: date | None = None
    end_date: date | None = None
    template_key: str | None = Field(None, max_length=50)
    phases: list[PlanPhaseInput] | None = None

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

    @model_validator(mode="after")
    def validate_dates(self) -> "PlanUpdate":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.start_date > self.end_date
        ):
            raise ValueError("开始日期不能晚于结束日期")
        return self


class PlanStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in {"active", "completed", "archived"}:
            raise ValueError("计划状态必须是 active、completed 或 archived")
        return value


class PlanQuickCreate(BaseModel):
    template_key: str = Field(..., min_length=1, max_length=50)
    title: str | None = Field(None, max_length=200)
    description: str | None = Field(None, max_length=2000)
    start_date: date

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return strip_text(value)

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return strip_optional_text(value)


class PlanPhaseResponse(BaseModel):
    id: int | None = None
    title: str
    description: str | None = None
    sequence: int
    start_date: date | None = None
    end_date: date | None = None
    task_count: int = 0
    completed_task_count: int = 0
    progress_percent: float = 0.0

    model_config = {"from_attributes": True}


class PlanScheduleItem(BaseModel):
    date: date
    label: str
    task_count: int = 0
    completed_task_count: int = 0
    task_titles: list[str] = Field(default_factory=list)


class PlanWeekSummary(BaseModel):
    week_label: str
    task_count: int = 0
    completed_task_count: int = 0
    dates: list[str] = Field(default_factory=list)


class PlanTemplateResponse(BaseModel):
    key: str
    title: str
    description: str
    duration_days: int
    phases: list[PlanPhaseInput]
    default_tasks: list[dict[str, object]] = Field(default_factory=list)


class PlanResponse(BaseModel):
    id: int
    title: str
    description: str | None = None
    template_key: str | None = None
    start_date: date
    end_date: date
    status: str
    created_at: datetime | None = None
    task_count: int = 0
    completed_task_count: int = 0
    progress_percent: float = 0.0
    subtask_count: int = 0
    completed_subtask_count: int = 0
    status_breakdown: dict[str, int] = Field(default_factory=dict)
    phases: list[PlanPhaseResponse] = Field(default_factory=list)
    day_schedule: list[PlanScheduleItem] = Field(default_factory=list)
    week_schedule: list[PlanWeekSummary] = Field(default_factory=list)

    model_config = {"from_attributes": True}
