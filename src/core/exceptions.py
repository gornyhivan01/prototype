"""Доменные исключения, не зависящие от HTTP-слоя."""

from __future__ import annotations


class AppError(Exception):
    """Базовая ошибка приложения с HTTP-статусом."""

    status_code: int = 400

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class UnauthorizedError(AppError):
    """Пользователь не аутентифицирован."""

    status_code = 401


class ForbiddenError(AppError):
    """Недостаточно прав."""

    status_code = 403


class NotFoundError(AppError):
    """Объект не найден."""

    status_code = 404


class ConflictError(AppError):
    """Конфликт данных (например, занятый email)."""

    status_code = 409


class BadRequestError(AppError):
    """Недопустимая операция (например, удаление последнего администратора)."""

    status_code = 400
