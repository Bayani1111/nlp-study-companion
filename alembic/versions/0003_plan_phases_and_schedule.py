"""add plan phases and scheduling

Revision ID: 0003_plan_phases_and_schedule
Revises: 0002_task_hierarchy
Create Date: 2026-04-24 22:10:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_plan_phases_and_schedule"
down_revision = "0002_task_hierarchy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("study_plans") as batch_op:
        batch_op.add_column(sa.Column("template_key", sa.String(length=50), nullable=True))

    op.create_table(
        "plan_phases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["study_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_phases_plan_id", "plan_phases", ["plan_id"], unique=False)
    op.create_index("ix_plan_phases_sequence", "plan_phases", ["sequence"], unique=False)

    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("phase_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("scheduled_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_foreign_key(
            "fk_tasks_phase_id_plan_phases",
            "plan_phases",
            ["phase_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_tasks_phase_id", ["phase_id"], unique=False)
        batch_op.create_index("ix_tasks_scheduled_date", ["scheduled_date"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_scheduled_date")
        batch_op.drop_index("ix_tasks_phase_id")
        batch_op.drop_constraint("fk_tasks_phase_id_plan_phases", type_="foreignkey")
        batch_op.drop_column("sort_order")
        batch_op.drop_column("scheduled_date")
        batch_op.drop_column("phase_id")

    op.drop_index("ix_plan_phases_sequence", table_name="plan_phases")
    op.drop_index("ix_plan_phases_plan_id", table_name="plan_phases")
    op.drop_table("plan_phases")

    with op.batch_alter_table("study_plans") as batch_op:
        batch_op.drop_column("template_key")
