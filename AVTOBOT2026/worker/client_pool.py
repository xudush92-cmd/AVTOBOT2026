"""
Telethon client pool.

Bir vaqtda bir nechta foydalanuvchi sessiyasi bilan ishlash uchun.
RAM tejash uchun client'lar qayta ishlatiladi.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

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
        self.created_at = time.time()


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
        # Har bir uid uchun alohida lock — ulanish boshqa userlarni
        # bloklamasligi uchun (global lock ostida tarmoqqa ulanilmaydi)
        self._uid_locks: dict[int, asyncio.Lock] = {}

    def _uid_lock(self, uid: int) -> asyncio.Lock:
        """Uid bo'yicha lock (ulanish ketma-ketligini ta'minlaydi)."""
        lock = self._uid_locks.get(uid)
        if lock is None:
            lock = asyncio.Lock()
            self._uid_locks[uid] = lock
        return lock

    def _drop_uid_lock(self, uid: int) -> None:
        self._uid_locks.pop(uid, None)

    # ─────────────────────────────────────────────────────────────
    # ISHGA TUSHIRISH / TO'XTATISH
    # ─────────────────────────────────────────────────────────────
    async def start(self) -> None:
        log(f"🌊 Client pool ishga tushdi (max {self.max_clients})")

    async def stop(self) -> None:
        """Barcha clientlarni yopadi."""
        async with self._lock:
            items = list(self._pool.items())
            self._pool.clear()
            self._uid_locks.clear()
        # Disconnect global lock TASHQARIDA — boshqa userlarni kutgan o'tirmasin
        for uid, pc in items:
            with contextlib.suppress(Exception):
                await pc.client.disconnect()
        log("🌊 Client pool to'xtatildi")

    # ─────────────────────────────────────────────────────────────
    # OLISH
    # ─────────────────────────────────────────────────────────────
    async def acquire(self, uid: int, session_str: str) -> TelegramClient:
        """
        Client'ni olish (yoki mavjudini qaytarish).

        Muhim: tarmoqqa ulanish (connect) global lock TASHQARIDA bajariladi.
        Aks holda bitta sekin ulanish BARCHA userlarning ishini to'xtatib
        qo'yadi. Har bir uid o'z lock'iga ega — parallel ulanishlar
        boshqa userlarga xalaqit bermaydi.

        Raises:
            PoolBusyError       — pool to'la yoki client band
            SessionInvalidError — sessiya yaroqsiz
        """
        # ── 1) TEZ YO'L: ulangan, bo'sh client darhol qaytariladi ──
        async with self._lock:
            existing = self._pool.get(uid)
            if (
                existing
                and existing.session_str == session_str
                and existing.client.is_connected()
            ):
                if existing.in_use:
                    raise PoolBusyError(f"uid={uid} allaqachon band")
                existing.in_use = True
                return existing.client

        # ── 2) SEKIN YO'L: uid lock ostida (tarmoq operatsiyalari) ──
        async with self._uid_lock(uid):
            # Qayta tekshirish — tez yo'ldan keyin holat o'zgarishi mumkin
            existing = None
            stale = None
            async with self._lock:
                existing = self._pool.get(uid)
                if existing and existing.session_str != session_str:
                    # Sessiya yangilangan — eskisini lock tashqarisida yopamiz
                    stale = existing
                    del self._pool[uid]
                    existing = None
                if (
                    existing
                    and existing.client.is_connected()
                ):
                    if existing.in_use:
                        raise PoolBusyError(f"uid={uid} allaqachon band")
                    existing.in_use = True
                    return existing.client

            # Eski (sessiyasi o'zgargan) clientni yopish — lock tashqarisida
            if stale is not None:
                with contextlib.suppress(Exception):
                    await stale.client.disconnect()
                log(f"🌊 Pool: -client {uid} (sessiya yangilandi)")

            # ── 2a) Mavjud, lekin uzilgan clientni qayta ulash ──
            if existing is not None:
                try:
                    await asyncio.wait_for(
                        existing.client.connect(), timeout=15
                    )
                except Exception:
                    async with self._lock:
                        if self._pool.get(uid) is existing:
                            del self._pool[uid]
                    with contextlib.suppress(Exception):
                        await existing.client.disconnect()
                    raise SessionInvalidError(f"uid={uid} qayta ulanmadi")

                async with self._lock:
                    if self._pool.get(uid) is not existing:
                        raise PoolBusyError(f"uid={uid} holati o'zgardi")
                    existing.in_use = True
                    return existing.client

            # ── 2b) Yangi client — connect GLOBAL LOCK TASHQARIDA ──
            async with self._lock:
                if len(self._pool) >= self.max_clients:
                    raise PoolBusyError(f"Pool to'la ({self.max_clients})")

            client = TelegramClient(
                StringSession(session_str), self.api_id, self.api_hash
            )
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
                log(
                    f"❌ Pool yangi client xato {uid}: "
                    f"{type(e).__name__}: {e}",
                    "warning",
                )
                raise PoolBusyError(f"uid={uid} ulanmadi")

            # Poolga qaytadan lock ostida qo'shamiz (poyga tekshiruvi bilan)
            async with self._lock:
                other = self._pool.get(uid)
                if other is not None:
                    # Parallel so'rov allaqachon qo'shib bo'lgan
                    with contextlib.suppress(Exception):
                        await client.disconnect()
                    if other.session_str == session_str and not other.in_use:
                        other.in_use = True
                        return other.client
                    raise PoolBusyError(f"uid={uid} allaqachon band")
                if len(self._pool) >= self.max_clients:
                    with contextlib.suppress(Exception):
                        await client.disconnect()
                    raise PoolBusyError(f"Pool to'la ({self.max_clients})")

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
        # Disconnect lock tashqarisida
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
