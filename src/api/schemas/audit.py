"""Схемы журнала аудита."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class AuditEntryRead(BaseModel):
    """Событие аудита, отдаваемое API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    actor_id: int | None
    target_user_id: int | None
    email: str | None
    ip_address: str | None
    details: dict[str, Any] | None
    created_at: datetime


class AuditPage(BaseModel):
    """Постраничная выдача журнала (новые записи первыми)."""

    total: int
    limit: int
    offset: int
    items: list[AuditEntryRead]
