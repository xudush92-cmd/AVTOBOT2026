"""🔒 Alohida (isolated) client — izolyatsiya va resurs nazorati testlari.

Qamlov:
- alohida client — worker clientidan **alohida** (bloklamaydi);
- tugagach client yopiladi va hisob kamayadi;
- limit to'lsa — **kutilmaydi**, darhol ``PoolBusyError``;
- limit worker'ga ta'sir qilmaydi.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")


from worker.client_pool import ClientPool, PoolBusyError, SessionInvalidError

UID = 3401


class IsolatedClientTests(unittest.IsolatedAsyncioTestCase):
    """Alohida client — izolyatsiya va chegaralar."""

    async def asyncSetUp(self) -> None:
        self.pool = ClientPool(
            api_id=123456,
            api_hash="0123456789abcdef0123456789abcdef",
            max_clients=50,
            max_isolated=2,
        )
        self._clients: list = []

    async def asyncTearDown(self) -> None:
        await self.pool.stop()

    def _fake_client(self):
        """TelegramClient'ni mock qilamiz (tarmoq so'rovi yo'q)."""
        client = AsyncMock()
        client.is_connected.return_value = True
        client.connect = AsyncMock()
        client.disconnect = AsyncMock()
        me = AsyncMock()
        me.id = UID
        client.get_me = AsyncMock(return_value=me)
        self._clients.append(client)
        return client

    def _patch_telegram_client(self, client):
        """TelegramClient **va** StringSession'ni mock qilamiz.

        Haqiqiy ``StringSession`` bo'sh auth key bilan ``""`` qaytaradi —
        format tekshiruvi esa xato beradi. Test uchun ikkalasini ham
        patch qilamiz (tarmoq so'rovi umuman bo'lmaydi).
        """
        return patch.multiple(
            "worker.client_pool",
            TelegramClient=Mock(return_value=client),
            StringSession=Mock(return_value=Mock()),
        )

    async def test_isolated_client_is_separate_from_pool(self) -> None:
        """Alohida client — pool'dan tashqarida, worker'ni bloklamaydi."""
        client = self._fake_client()
        with self._patch_telegram_client(client):
            async with self.pool.isolated_client(UID, "SESSION") as tg:
                self.assertIs(tg, client)
                # Pool'da hech narsa yo'q — alohida client ishlatildi.
                self.assertEqual(self.pool.stats()["total_clients"], 0)

    async def test_isolated_client_disconnects_after(self) -> None:
        """Tugagach client yopiladi."""
        client = self._fake_client()
        with self._patch_telegram_client(client):
            async with self.pool.isolated_client(UID, "SESSION"):
                pass
        client.disconnect.assert_awaited()

    async def test_limit_raises_immediately(self) -> None:
        """Limit to'lsa — kutilmaydi, darhol PoolBusyError."""
        client = self._fake_client()
        with self._patch_telegram_client(client):
            async with self.pool.isolated_client(UID, "S1"):  # noqa: SIM117
                async with self.pool.isolated_client(UID, "S2"):
                    # Uchinchi — limitdan oshdi.
                    with self.assertRaises(PoolBusyError):
                        async with self.pool.isolated_client(UID, "S3"):
                            pass

    async def test_counter_released_after_use(self) -> None:
        """Tugagach hisob qaytariladi — keyin yana ishlatish mumkin."""
        client = self._fake_client()
        with self._patch_telegram_client(client):
            for _ in range(5):
                async with self.pool.isolated_client(UID, "S"):
                    pass
        self.assertEqual(self.pool._isolated_count, 0)

    async def test_invalid_session_raises_session_invalid(self) -> None:
        """Sessiya yaroqsiz bo'lsa — SessionInvalidError."""
        client = self._fake_client()
        client.get_me = AsyncMock(return_value=AsyncMock(id=999))
        with self._patch_telegram_client(client):  # noqa: SIM117
            with self.assertRaises(SessionInvalidError):
                async with self.pool.isolated_client(UID, "S"):
                    pass

    async def test_empty_session_raises(self) -> None:
        """Bo'sh sessiya — SessionInvalidError."""
        with self.assertRaises(SessionInvalidError):
            async with self.pool.isolated_client(UID, ""):
                pass

    async def test_limit_does_not_block_worker_pool(self) -> None:
        """Alohida client limiti worker client'ini ta'sirlamasligi kerak."""
        client = self._fake_client()
        with self._patch_telegram_client(client):
            async with self.pool.isolated_client(UID, "S1"):  # noqa: SIM117
                async with self.pool.isolated_client(UID, "S2"):
                    # Worker client'i — alohida client'lardan alohida.
                    worker_client = await self.pool.acquire(UID, "WORKER_SESSION")
                    self.assertIsNotNone(worker_client)
                    self.assertEqual(self.pool.stats()["total_clients"], 1)
                    await self.pool.release(UID)

    async def test_concurrent_isolated_clients_do_not_exceed_limit(self) -> None:
        """Ko'p foydalanuvchi bir vaqtda skaner qilsa — limit saqlanadi."""
        clients = []
        peak = {"value": 0}
        current = {"value": 0}

        def _side_effect(*_args, **_kwargs):
            current["value"] += 1
            peak["value"] = max(peak["value"], current["value"])
            c = AsyncMock()
            c.is_connected.return_value = True
            c.connect = AsyncMock()
            c.disconnect = AsyncMock()
            me = AsyncMock()
            me.id = UID
            c.get_me = AsyncMock(return_value=me)
            clients.append(c)
            original = c.disconnect

            async def _disconnect():
                current["value"] -= 1
                await original()

            c.disconnect = _disconnect
            return c

        async def _scan(idx: int):
            try:
                async with self.pool.isolated_client(
                    UID + idx, f"S{idx}"
                ):
                    await asyncio.sleep(0.01)
            except PoolBusyError:
                pass
            except SessionInvalidError:
                pass

        with patch(
            "worker.client_pool.TelegramClient", side_effect=_side_effect
        ), patch("worker.client_pool.StringSession", Mock(return_value=Mock())):
            await asyncio.gather(*(_scan(i) for i in range(8)))

        self.assertLessEqual(peak["value"], 2, f"limit buzildi: {peak['value']}")
        # Oxirida barcha alohida client'lar yopilgan bo'lishi kerak.
        self.assertEqual(self.pool._isolated_count, 0)


if __name__ == "__main__":
    unittest.main()
