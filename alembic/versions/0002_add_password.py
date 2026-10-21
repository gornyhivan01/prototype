"""add hashed_password to users

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-21 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Добавляет колонку с хешем пароля.

    ``server_default=""`` нужен, чтобы миграция прошла на непустой таблице:
    у существующих строк окажется пустой хеш, и войти под ними нельзя до
    повторной регистрации. Сразу после заполнения default убирается, чтобы
    приложение всегда передавало хеш явно.
    """
    op.add_column(
        "users",
        sa.Column("hashed_password", sa.String(length=255), nullable=False, server_default=""),
    )
    op.alter_column("users", "hashed_password", server_default=None)


def downgrade() -> None:
    """Удаляет колонку с хешем пароля."""
    op.drop_column("users", "hashed_password")
