"""Statistics-related request and response schemas."""

from pydantic import BaseModel, Field


class StudySessionCreate(BaseModel):
    task_id: int | None = None
    duration_minutes: int = Field(..., ge=1, le=720)
    source: str = Field(default="focus_timer", min_length=1, max_length=50)


class StudySessionResponse(BaseModel):
    task_id: int | None = None
    duration_minutes: int
    total_study_minutes: int = 0


class DailyStats(BaseModel):
    date: str
    study_minutes: int = 0
    tasks_created: int = 0
    tasks_completed: int = 0
    chat_count: int = 0
    session_count: int = 0


class WeeklyStats(BaseModel):
    week_start: str
    week_end: str
    total_study_minutes: int = 0
    total_tasks: int = 0
    completed_tasks: int = 0
    daily_breakdown: dict[str, int] = Field(default_factory=dict)
    streak_days: int = 0


class TaskStats(BaseModel):
    total_tasks: int = 0
    completed_tasks: int = 0
    pending_tasks: int = 0
    in_progress_tasks: int = 0
    overdue_tasks: int = 0
    completion_rate: float = 0.0
    priority_distribution: dict[str, int] = Field(default_factory=dict)
    phase_completion_rate: float = 0.0


class StatsOverview(BaseModel):
    total_tasks: int = 0
    completed_tasks: int = 0
    total_study_minutes: int = 0
    completion_rate: float = 0.0
    daily_breakdown: dict[str, int] = Field(default_factory=dict)
    priority_distribution: dict[str, int] = Field(default_factory=dict)
    activity_breakdown: dict[str, int] = Field(default_factory=dict)
    weekday_distribution: dict[str, int] = Field(default_factory=dict)
    completion_rhythm: dict[str, int] = Field(default_factory=dict)
    streak_days: int = 0
    total_sessions: int = 0
    phase_completion_rate: float = 0.0
    chat_diagnostic_total: int = 0
    clarify_reason_distribution: dict[str, int] = Field(default_factory=dict)
    orchestration_event_distribution: dict[str, int] = Field(default_factory=dict)
    clarify_path_switch_hit_rate: float = 0.0
    action_completion_rate: float = 0.0
