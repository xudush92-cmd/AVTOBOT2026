"""Bounded, reusable Telethon client pool with per-UID lifecycle locks."""

from __future__ import annotations

import asyncio
import contextlib
import time
from contextlib import asynccontextmanager

from telethon import TelegramClient
from telethon.errors import AuthKeyUnregisteredError, UserDeactivatedBanError
from telethon.sessions import StringSession

from core.logger import log


class PoolBusyError(Exception):
    """Pool vaqtincha band yoki limitga yetgan."""


class SessionInvalidError(Exception):
    """Saqlangan Telegram sessiyasi yaroqsiz."""


class PooledClient:
    __slots__ = (
        "client",
        "created_at",
        "last_used",
        "references",
        "session_str",
        "uid",
    )

    def __init__(self, client: TelegramClient, uid: int, session_str: str):
        now = time.monotonic()
        self.client = client
        self.uid = uid
        self.session_str = session_str
        self.references = 1
        self.created_at = now
        self.last_used = now


class ClientPool:
    def __init__(self, api_id: int, api_hash: str, max_clients: int = 50):
        self.api_id = api_id
        self.api_hash = api_hash
        self.max_clients = max(1, int(max_clients))
        self._pool: dict[int, PooledClient] = {}
        self._lock = asyncio.Lock()
        # Bounded striped locklar: bir UID lifecycle'i serial, xotira esa bounded.
        self._uid_locks = tuple(asyncio.Lock() for _ in range(256))
        self._reservations: set[int] = set()
        self._stopping = False

    def _uid_lock(self, uid: int) -> asyncio.Lock:
        return self._uid_locks[int(uid) % len(self._uid_locks)]

    async def start(self) -> None:
        self._stopping = False
        log(f"🌊 Client pool ishga tushdi (max {self.max_clients})")

    async def stop(self) -> None:
        self._stopping = True
        async with self._lock:
            clients = [entry.client for entry in self._pool.values()]
            self._pool.clear()
            self._reservations.clear()
        await asyncio.gather(
            *(self._disconnect(client) for client in clients),
            return_exceptions=True,
        )
        log("🌊 Client pool to'xtatildi")

    async def _disconnect(self, client: TelegramClient) -> None:
        with contextlib.suppress(Exception):
            await client.disconnect()

    async def acquire(self, uid: int, session_str: str) -> TelegramClient:
        """Client oladi; idle LRU clientni zarur bo'lsa chiqarib yuboradi."""
        uid = int(uid)
        if not session_str:
            raise SessionInvalidError(f"uid={uid} sessiya yo'q")

        async with self._uid_lock(uid):
            if self._stopping:
                raise PoolBusyError("Pool to'xtatilmoqda")

            stale: PooledClient | None = None
            async with self._lock:
                existing = self._pool.get(uid)
                if existing and existing.session_str != session_str:
                    stale = self._pool.pop(uid)
                    existing = None
            if stale:
                await self._disconnect(stale.client)

            if existing:
                if not existing.client.is_connected():
                    try:
                        await asyncio.wait_for(existing.client.connect(), timeout=20)
                    except Exception as exc:
                        async with self._lock:
                            if self._pool.get(uid) is existing:
                                self._pool.pop(uid, None)
                        await self._disconnect(existing.client)
                        raise PoolBusyError(f"uid={uid} qayta ulanmadi") from exc
                async with self._lock:
                    if self._pool.get(uid) is not existing:
                        raise PoolBusyError(f"uid={uid} client almashtirildi")
                    existing.references += 1
                    existing.last_used = time.monotonic()
                return existing.client

            evicted: PooledClient | None = None
            async with self._lock:
                occupied = len(self._pool) + len(self._reservations)
                if occupied >= self.max_clients:
                    idle = [
                        entry for entry in self._pool.values() if entry.references == 0
                    ]
                    if idle:
                        evicted = min(idle, key=lambda entry: entry.last_used)
                        self._pool.pop(evicted.uid, None)
                    else:
                        raise PoolBusyError(f"Pool to'la ({self.max_clients})")
                self._reservations.add(uid)
            if evicted:
                try:
                    await self._disconnect(evicted.client)
                except asyncio.CancelledError:
                    async with self._lock:
                        self._reservations.discard(uid)
                    raise
                log(f"🌊 Pool: idle client chiqarildi {evicted.uid}")

            client: TelegramClient | None = None
            try:
                client = TelegramClient(
                    StringSession(session_str), self.api_id, self.api_hash
                )
                await asyncio.wait_for(client.connect(), timeout=20)
                if not await asyncio.wait_for(client.is_user_authorized(), timeout=15):
                    raise SessionInvalidError(f"uid={uid} sessiya yaroqsiz")
            except asyncio.CancelledError:
                if client:
                    await self._disconnect(client)
                raise
            except (AuthKeyUnregisteredError, UserDeactivatedBanError) as exc:
                if client:
                    await self._disconnect(client)
                raise SessionInvalidError(f"uid={uid} {type(exc).__name__}") from exc
            except (ValueError, SessionInvalidError) as exc:
                if client:
                    await self._disconnect(client)
                if isinstance(exc, SessionInvalidError):
                    raise
                raise SessionInvalidError(
                    f"uid={uid} sessiya formati yaroqsiz"
                ) from exc
            except Exception as exc:
                if client:
                    await self._disconnect(client)
                log(
                    f"❌ Pool yangi client xato {uid}: {type(exc).__name__}",
                    "warning",
                )
                raise PoolBusyError(f"uid={uid} ulanmadi") from exc
            finally:
                async with self._lock:
                    self._reservations.discard(uid)

            assert client is not None

            entry = PooledClient(client, uid, session_str)
            async with self._lock:
                stopping = self._stopping
                if not stopping:
                    self._pool[uid] = entry
                total = len(self._pool)
            if stopping:
                await self._disconnect(client)
                raise PoolBusyError("Pool to'xtatilmoqda")
            log(f"🌊 Pool: +client {uid} (jami {total})")
            return client

    async def release(self, uid: int) -> None:
        async with self._lock:
            entry = self._pool.get(int(uid))
            if entry:
                entry.references = max(0, entry.references - 1)
                entry.last_used = time.monotonic()

    async def remove(self, uid: int) -> None:
        uid = int(uid)
        async with self._uid_lock(uid):
            async with self._lock:
                entry = self._pool.pop(uid, None)
            if entry:
                await self._disconnect(entry.client)
                log(f"🌊 Pool: -client {uid} (jami {len(self._pool)})")

    @asynccontextmanager
    async def lease(self, uid: int, session_str: str):
        client = await self.acquire(uid, session_str)
        try:
            yield client
        finally:
            await self.release(uid)

    def stats(self) -> dict:
        total = len(self._pool)
        in_use = sum(1 for entry in self._pool.values() if entry.references > 0)
        references = sum(entry.references for entry in self._pool.values())
        return {
            "total_clients": total,
            "in_use": in_use,
            "references": references,
            "available": total - in_use,
            "max": self.max_clients,
        }
