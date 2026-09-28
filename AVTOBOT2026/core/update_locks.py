"""Bir foydalanuvchining parallel Telegram updatelarini tartibga solish."""

from __future__ import annotations

import asyncio

# Ikki alohida bounded lock namespace:
# - update lock bir actorning parallel Bot API updatelarini serial qiladi;
# - operation lock admin va user fon vazifalarini target UID bo'yicha serial qiladi.
_UPDATE_LOCKS = tuple(asyncio.Lock() for _ in range(256))
_OPERATION_LOCKS = tuple(asyncio.Lock() for _ in range(256))


def user_update_lock(uid: int) -> asyncio.Lock:
    return _UPDATE_LOCKS[int(uid) % len(_UPDATE_LOCKS)]


def user_operation_lock(uid: int) -> asyncio.Lock:
    return _OPERATION_LOCKS[int(uid) % len(_OPERATION_LOCKS)]
