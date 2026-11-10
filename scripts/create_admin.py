"""Создание администратора.

Находит пользователя по email или создаёт его, затем назначает роль ADMIN.

Пример::

    uv run python scripts/create_admin.py admin@example.com 'пароль' 'Администратор'

Если пользователь уже существует, меняется только роль; пароль и имя не
затрагиваются (параметры пароль/имя тогда игнорируются).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

if __package__ is None or __package__ == "":
    # Позволяет запускать как `python scripts/create_admin.py` без установки пакета.
    sys.path.insert(0, ".")

from src.core.database import async_session_factory  # noqa: E402 — после sys.path
from src.core.security import hash_password  # noqa: E402
from src.models.user import UserRole  # noqa: E402
from src.repositories.user_repo import UserRepository  # noqa: E402
from src.utils.unit_of_work import UnitOfWork  # noqa: E402


async def _run(email: str, password: str, name: str) -> int:
    async with async_session_factory() as session:
        repo = UserRepository(session)
        uow = UnitOfWork(session)
        user = await repo.get_by_email(email)
        if user is None:
            user = await repo.create(
                email=email,
                hashed_password=hash_password(password),
                name=name,
                role=UserRole.ADMIN.value,
            )
        elif user.role != UserRole.ADMIN.value:
            user.role = UserRole.ADMIN.value
        await uow.commit()
        print(f"Пользователь {email} — роль {user.role} (id={user.id}).")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Email администратора")
    parser.add_argument("password", help="Пароль (нужен только при создании)")
    parser.add_argument("name", nargs="?", default="Администратор", help="Имя")
    args = parser.parse_args()
    try:
        raise SystemExit(asyncio.run(_run(args.email, args.password, args.name)))
    except Exception as exc:  # noqa: BLE001 — верхнеуровневый вывод причины
        print(f"Не удалось назначить администратора: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
