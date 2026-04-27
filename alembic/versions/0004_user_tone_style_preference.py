"""add user tone style preference

Revision ID: 0004_user_tone_style_preference
Revises: 0003_plan_phases_and_schedule
Create Date: 2026-04-27 08:30:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_user_tone_style_preference"
down_revision = "0003_plan_phases_and_schedule"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("companion_tone_style", sa.String(length=20), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("companion_tone_style")
