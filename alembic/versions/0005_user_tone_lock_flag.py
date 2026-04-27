"""add user tone lock flag

Revision ID: 0005_user_tone_lock_flag
Revises: 0004_user_tone_style_preference
Create Date: 2026-04-27 08:36:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_user_tone_lock_flag"
down_revision = "0004_user_tone_style_preference"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column(
                "companion_tone_locked",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("companion_tone_locked")
