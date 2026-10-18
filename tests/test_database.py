"""Тест зависимости ``get_db``: сессия создаётся на запрос и закрывается."""

from __future__ import annotations

import pytest

from app import database
from app.database import get_db


class _FakeSession:
    """Заглушка сессии, фиксирующая вызов ``close``."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_get_db_yields_and_closes_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_db`` выдаёт сессию и закрывает её при завершении зависимости."""
    fake = _FakeSession()
    monkeypatch.setattr(database, "SessionLocal", lambda: fake)

    dependency = get_db()
    assert next(dependency) is fake

    dependency.close()
    assert fake.closed is True
