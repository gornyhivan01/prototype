"""Отправка уведомлений о задачах.

В учебном проекте письмо не уходит по-настоящему: адресат и текст пишутся
в лог. Redis в compose оставлен под будущий Celery-воркер.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("app.notifications")


def send_task_created_email(recipient: str, task_title: str) -> None:
    """Имитирует отправку письма о создании задачи."""
    logger.info(
        "email: to=%s subject='Создана задача' body='Задача «%s» создана'",
        recipient,
        task_title,
    )
