"""
Telethon client pool.

Bir vaqtda bir nechta foydalanuvchi sessiyasi bilan ishlash uchun.
RAM tejash uchun client'lar qayta ishlatiladi.
"""

from __future__ import annotations

import asyncio
import contextlib

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyUnregisteredError,
    UserDeactivatedBanError,
)
from telethon.sessions import StringSession

from config.config import API_HASH, API_ID
from core.logger import log


# ─────────────────────────────────────────────────────────────────────────
# XATOLAR
# ─────────────────────────────────────────────────────────────────────────
class PoolBusyError(Exception):
    """Pool band — vaqtincha urinib ko'rish kerak."""
    pass


class SessionInvalidError(Exception):
    """Sessiya yaroqsiz — login qilish kerak."""
    pass


# ─────────────────────────────────────────────────────────────────────────
# CLIENT WRAPPER
# ─────────────────────────────────────────────────────────────────────────
class PooledClient:
    """Pool ichida saqlanadigan client."""
    __slots__ = ("client", "uid", "session_str", "in_use", "created_at")

    def __init__(self, client: TelegramClient, uid: int, session_str: str):
        self.client = client
        self.uid = uid
        self.session_str = session_str
        self.in_use = False
        self.created_at = __import__("time").time()


# ─────────────────────────────────────────────────────────────────────────
# CLIENT POOL
# ─────────────────────────────────────────────────────────────────────────
class ClientPool:
    """
    Telethon client pool.

    Ishlatish:
        pool = ClientPool(API_ID, API_HASH, max_clients=50)
        await pool.start()

        client = await pool.acquire(uid, session_str)
        try:
            await client.send_message(...)
        finally:
            await pool.release(uid)
    """

    def __init__(self, api_id: int, api_hash: str, max_clients: int = 50):
        self.api_id = api_id
        self.api_hash = api_hash
        self.max_clients = max_clients
        self._pool: dict[int, PooledClient] = {}
        self._lock = asyncio.Lock()

    # ─────────────────────────────────────────────────────────────
    # ISHGA TUSHIRISH / TO'XTATISH
    # ─────────────────────────────────────────────────────────────
    async def start(self) -> None:
        log(f"🌊 Client pool ishga tushdi (max {self.max_clients})")

    async def stop(self) -> None:
        """Barcha clientlarni yopadi."""
        async with self._lock:
            for uid, pc in list(self._pool.items()):
                with contextlib.suppress(Exception):
                    await pc.client.disconnect()
            self._pool.clear()
        log("🌊 Client pool to'xtatildi")

    # ─────────────────────────────────────────────────────────────
    # OLISH
    # ─────────────────────────────────────────────────────────────
    async def acquire(self, uid: int, session_str: str) -> TelegramClient:
        """
        Client'ni olish (yoki mavjudini qaytarish).

        Raises:
            PoolBusyError       — pool to'la
            SessionInvalidError — sessiya yaroqsiz
        """
        async with self._lock:
            # Mavjudmi?
            existing = self._pool.get(uid)
            if existing:
                # Sessiya o'zgarganmi?
                if existing.session_str != session_str:
                    with contextlib.suppress(Exception):
                        await existing.client.disconnect()
                    del self._pool[uid]
                else:
                    if existing.in_use:
                        raise PoolBusyError(f"uid={uid} allaqachon band")
                    # Ulanish tekshirish
                    if not existing.client.is_connected():
                        try:
                            await asyncio.wait_for(
                                existing.client.connect(), timeout=15
                            )
                        except Exception:
                            del self._pool[uid]
                            raise SessionInvalidError(f"uid={uid} qayta ulanmadi")
                    existing.in_use = True
                    return existing.client

            # Pool to'la?
            if len(self._pool) >= self.max_clients:
                raise PoolBusyError(f"Pool to'la ({self.max_clients})")

            # Yangi client yaratamiz
            client = TelegramClient(StringSession(session_str), self.api_id, self.api_hash)
            try:
                await asyncio.wait_for(client.connect(), timeout=20)
                if not await client.is_user_authorized():
                    raise SessionInvalidError(f"uid={uid} sessiya yaroqsiz")
            except (AuthKeyUnregisteredError, UserDeactivatedBanError) as e:
                with contextlib.suppress(Exception):
                    await client.disconnect()
                raise SessionInvalidError(f"uid={uid} {type(e).__name__}")
            except SessionInvalidError:
                with contextlib.suppress(Exception):
                    await client.disconnect()
                raise
            except Exception as e:
                with contextlib.suppress(Exception):
                    await client.disconnect()
                log(f"❌ Pool yangi client xato {uid}: {type(e).__name__}: {e}", "warning")
                raise PoolBusyError(f"uid={uid} ulanmadi")

            pc = PooledClient(client, uid, session_str)
            pc.in_use = True
            self._pool[uid] = pc
            log(f"🌊 Pool: +client {uid} (jami {len(self._pool)})")
            return client

    # ─────────────────────────────────────────────────────────────
    # QAYTARISH
    # ─────────────────────────────────────────────────────────────
    async def release(self, uid: int) -> None:
        """Client'ni bo'shatadi (lekin yopmaydi)."""
        async with self._lock:
            pc = self._pool.get(uid)
            if pc:
                pc.in_use = False

    # ─────────────────────────────────────────────────────────────
    # O'CHIRISH
    # ─────────────────────────────────────────────────────────────
    async def remove(self, uid: int) -> None:
        """Client'ni butunlay o'chiradi (sessiya yangilanganda)."""
        async with self._lock:
            pc = self._pool.pop(uid, None)
            if pc:
                with contextlib.suppress(Exception):
                    await pc.client.disconnect()
                log(f"🌊 Pool: -client {uid} (jami {len(self._pool)})")

    # ─────────────────────────────────────────────────────────────
    # STATISTIKA
    # ─────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        total = len(self._pool)
        in_use = sum(1 for pc in self._pool.values() if pc.in_use)
        return {
            "total_clients": total,
            "in_use": in_use,
            "available": total - in_use,
            "max": self.max_clients,
      }
