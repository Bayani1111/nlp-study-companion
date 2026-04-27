"""add task hierarchy

Revision ID: 0002_task_hierarchy
Revises: 0001_baseline
Create Date: 2026-04-24 20:20:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_task_hierarchy"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.add_column(sa.Column("parent_task_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_tasks_parent_task_id_tasks",
            "tasks",
            ["parent_task_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_index("ix_tasks_parent_task_id", ["parent_task_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("tasks") as batch_op:
        batch_op.drop_index("ix_tasks_parent_task_id")
        batch_op.drop_constraint("fk_tasks_parent_task_id_tasks", type_="foreignkey")
        batch_op.drop_column("parent_task_id")
