"""baseline schema

Revision ID: 0001_baseline
Revises:
Create Date: 2026-04-24 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


message_role = postgresql.ENUM(
    "user", "assistant", "system", name="message_role", create_type=False
)
plan_status = postgresql.ENUM(
    "active", "completed", "archived", name="plan_status", create_type=False
)
task_priority = postgresql.ENUM("high", "medium", "low", name="task_priority", create_type=False)
task_status = postgresql.ENUM(
    "pending",
    "in_progress",
    "completed",
    "overdue",
    name="task_status",
    create_type=False,
)
activity_type = postgresql.ENUM(
    "chat",
    "task_create",
    "task_complete",
    "study_session",
    name="activity_type",
    create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in [message_role, plan_status, task_priority, task_status, activity_type]:
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=True),
        sa.Column("avatar_url", sa.String(length=256), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"], unique=False)

    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=50), nullable=True),
        sa.Column("entities_json", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"], unique=False)

    op.create_table(
        "study_plans",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", plan_status, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_study_plans_user_id", "study_plans", ["user_id"], unique=False)

    op.create_table(
        "tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", task_priority, nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("actual_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["study_plans.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_due_date", "tasks", ["due_date"], unique=False)
    op.create_index("ix_tasks_plan_id", "tasks", ["plan_id"], unique=False)
    op.create_index("ix_tasks_user_id", "tasks", ["user_id"], unique=False)

    op.create_table(
        "learning_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", activity_type, nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_learning_records_user_id", "learning_records", ["user_id"], unique=False)

    op.create_table(
        "reminder_settings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("before_start_minutes", sa.Integer(), nullable=False),
        sa.Column("before_due_minutes", sa.Integer(), nullable=False),
        sa.Column("overdue_enabled", sa.Boolean(), nullable=False),
        sa.Column("quiet_start_hour", sa.Integer(), nullable=False),
        sa.Column("quiet_end_hour", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_reminder_settings_user_id", "reminder_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_reminder_settings_user_id", table_name="reminder_settings")
    op.drop_table("reminder_settings")
    op.drop_index("ix_learning_records_user_id", table_name="learning_records")
    op.drop_table("learning_records")
    op.drop_index("ix_tasks_user_id", table_name="tasks")
    op.drop_index("ix_tasks_plan_id", table_name="tasks")
    op.drop_index("ix_tasks_due_date", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_study_plans_user_id", table_name="study_plans")
    op.drop_table("study_plans")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_sessions_user_id", table_name="chat_sessions")
    op.drop_table("chat_sessions")
    op.drop_table("users")

    bind = op.get_bind()
    for enum_type in [activity_type, task_status, task_priority, plan_status, message_role]:
        enum_type.drop(bind, checkfirst=True)
