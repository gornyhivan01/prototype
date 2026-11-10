"""task archive: задачи удалённых пользователей сохраняются

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK_NAME = "tasks_user_id_fkey"


def upgrade() -> None:
    """Добавляет архив задач и разрешает задаче остаться без владельца."""
    op.add_column("tasks", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tasks", sa.Column("archived_owner_email", sa.String(length=320), nullable=True))
    op.create_index(op.f("ix_tasks_archived_at"), "tasks", ["archived_at"], unique=False)

    # Владелец может исчезнуть: задача архивируется, а не удаляется каскадом.
    op.drop_constraint(FK_NAME, "tasks", type_="foreignkey")
    op.alter_column("tasks", "user_id", existing_type=sa.Integer(), nullable=True)
    op.create_foreign_key(
        FK_NAME,
        "tasks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Убирает архив: архивные задачи удаляются, FK снова каскадный."""
    op.execute("DELETE FROM tasks WHERE user_id IS NULL")

    op.drop_constraint(FK_NAME, "tasks", type_="foreignkey")
    op.alter_column("tasks", "user_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        FK_NAME,
        "tasks",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index(op.f("ix_tasks_archived_at"), table_name="tasks")
    op.drop_column("tasks", "archived_owner_email")
    op.drop_column("tasks", "archived_at")
