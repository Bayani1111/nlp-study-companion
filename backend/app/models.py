"""SQLAlchemy ORM models for the study companion application."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class shared by all ORM models."""


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(50), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    companion_tone_style: Mapped[str | None] = mapped_column(String(20), nullable=True)
    companion_tone_locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    study_plans: Mapped[list["StudyPlan"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    learning_records: Mapped[list["LearningRecord"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    reminder_setting: Mapped["ReminderSetting | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_chat_sessions_user_id", "user_id"),)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(
        Enum("user", "assistant", "system", name="message_role"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entities_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["ChatSession"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_chat_messages_session_id", "session_id"),)


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("active", "completed", "archived", name="plan_status"),
        nullable=False,
        default="active",
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="study_plans")
    phases: Mapped[list["PlanPhase"]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PlanPhase.sequence.asc()",
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="plan")

    __table_args__ = (Index("ix_study_plans_user_id", "user_id"),)


class PlanPhase(Base):
    __tablename__ = "plan_phases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("study_plans.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    plan: Mapped["StudyPlan"] = relationship(back_populates="phases")
    tasks: Mapped[list["Task"]] = relationship(back_populates="phase")

    __table_args__ = (
        Index("ix_plan_phases_plan_id", "plan_id"),
        Index("ix_plan_phases_sequence", "sequence"),
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("study_plans.id", ondelete="SET NULL"), nullable=True
    )
    phase_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("plan_phases.id", ondelete="SET NULL"), nullable=True
    )
    parent_task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        Enum("high", "medium", "low", name="task_priority"),
        nullable=False,
        default="medium",
    )
    status: Mapped[str] = mapped_column(
        Enum("pending", "in_progress", "completed", "overdue", name="task_status"),
        nullable=False,
        default="pending",
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="tasks")
    plan: Mapped["StudyPlan | None"] = relationship(back_populates="tasks")
    phase: Mapped["PlanPhase | None"] = relationship(back_populates="tasks")
    parent_task: Mapped["Task | None"] = relationship(
        back_populates="children",
        remote_side="Task.id",
        foreign_keys=[parent_task_id],
    )
    children: Mapped[list["Task"]] = relationship(
        back_populates="parent_task",
        cascade="all, delete-orphan",
        foreign_keys=[parent_task_id],
        order_by="Task.created_at.asc()",
    )
    learning_records: Mapped[list["LearningRecord"]] = relationship(back_populates="task")

    __table_args__ = (
        Index("ix_tasks_user_id", "user_id"),
        Index("ix_tasks_due_date", "due_date"),
        Index("ix_tasks_plan_id", "plan_id"),
        Index("ix_tasks_phase_id", "phase_id"),
        Index("ix_tasks_scheduled_date", "scheduled_date"),
        Index("ix_tasks_parent_task_id", "parent_task_id"),
    )


class LearningRecord(Base):
    __tablename__ = "learning_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True
    )
    activity_type: Mapped[str] = mapped_column(
        Enum(
            "chat",
            "task_create",
            "task_complete",
            "study_session",
            name="activity_type",
        ),
        nullable=False,
    )
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="learning_records")
    task: Mapped["Task | None"] = relationship(back_populates="learning_records")

    __table_args__ = (Index("ix_learning_records_user_id", "user_id"),)


class ReminderSetting(Base):
    __tablename__ = "reminder_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    before_start_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    before_due_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    overdue_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quiet_start_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    quiet_end_hour: Mapped[int] = mapped_column(Integer, nullable=False, default=8)

    user: Mapped["User"] = relationship(back_populates="reminder_setting")

    __table_args__ = (Index("ix_reminder_settings_user_id", "user_id"),)
