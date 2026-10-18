"""Подключение к базе данных: движок, фабрика сессий и зависимость FastAPI."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Базовый класс моделей (SQLAlchemy 2.0, декларативный стиль)."""


# Движок создаётся один раз на процесс. Соединение устанавливается лениво,
# поэтому импорт модуля не требует запущенного PostgreSQL.
engine = create_engine(settings.database_url, pool_pre_ping=True, echo=settings.debug)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Зависимость FastAPI: выдаёт сессию и гарантированно её закрывает."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
