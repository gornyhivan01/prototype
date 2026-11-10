"""Базовый класс моделей SQLAlchemy."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Декларативная база (SQLAlchemy 2.0)."""
