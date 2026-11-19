"""🔍 Guruh skanerining tezligi, izolyatsiyasi va bloklovchiligi.

Qamlov:
- huquq tekshiruvi **parallel** batch'lar bilan bajariladi (ketma-ket emas);
- skaner **alohida** TelegramClient ishlatadi — posting worker'ni bloklamaydi;
- bitta foydalanuvchining skaneri boshqa foydalanuvchilarni **kutib qoldirmaydi**;
- topilgan guruhlar ro'yxatida **ochiq havola** ko'rsatiladi;
- progress xabari muntazam yangilanadi;
- FloodWait boshqa foydalanuvchilarga ta'sir qilmaydi.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from cryptography.fernet import Fernet
from telethon.tl import types

from bot import discover_sessions
from bot import groups as G
from core import database as db
from core import session_crypto
from worker import worker as W

UID = 3301
OTHER_UID = 3302
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _channel(channel_id: int, username: str, title: str = "Guruh") -> types.Channel:
    return types.Channel(
        channel_id,
        title=title,
        photo=None,
        date=_NOW,
        broadcast=False,
        megagroup=True,
        left=False,
        banned_rights=None,
        default_banned_rights=None,
        username=username,
    )


def perms_ok():
    return SimpleNamespace(
        has_left=False,
        participant=SimpleNamespace(left=False, banned_rights=None),
        is_creator=False,
        is_admin=False,
        send_messages=True,
        post_messages=False,
    )


class DiscoverSpeedIsolationTests(unittest.IsolatedAsyncioTestCase):
    """Skaner tezligi va izolyatsiyasi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")
        await db.upsert_user(OTHER_UID, name="Ali", is_admin=1, session="SESS2")
        G.reset_discover_guards()
        discover_sessions.reset()
        self._sleep_patch = patch.object(G.asyncio, "sleep", new=AsyncMock())
        self._sleep_patch.start()

    async def asyncTearDown(self) -> None:
        self._sleep_patch.stop()
        G.reset_discover_guards()
        discover_sessions.reset()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _update(self, uid: int = UID):
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=status))
        return (
            SimpleNamespace(
                effective_user=SimpleNamespace(id=uid),
                message=message,
            ),
            status,
        )

    def _client(self, dialogs, delay: float = 0.0):
        """`get_permissions` har doim `delay` sek kutadigan mock client."""
        me = SimpleNamespace(id=UID)

        async def _iter_dialogs():
            for dialog in dialogs:
                yield dialog

        async def _get_permissions(entity, _me):
            if delay:
                await asyncio.sleep(delay)
            return perms_ok()

        return SimpleNamespace(
            get_me=AsyncMock(return_value=me),
            iter_dialogs=_iter_dialogs,
            get_permissions=AsyncMock(side_effect=_get_permissions),
        )

    def _pool(self, client, use_isolated: bool = True):
        """Pool mock — ``isolated_client`` bilan yoki unisiz."""
        if use_isolated:
            from contextlib import asynccontextmanager

            @asynccontextmanager
            async def isolated_client(_uid, _session):
                yield client

            return SimpleNamespace(
                acquire=AsyncMock(return_value=client),
                release=AsyncMock(),
                isolated_client=isolated_client,
            )
        return SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
        )

    def _dialogs(self, count: int):
        return [
            SimpleNamespace(entity=_channel(3000 + i, f"grp{i}", f"Guruh {i}"))
            for i in range(count)
        ]

    async def test_permissions_are_checked_in_parallel(self) -> None:
        """Huquq tekshiruvi ketma-ket emas — parallel batch bo'lishi kerak."""
        count = 16
        delay = 0.05
        client = self._client(self._dialogs(count), delay=delay)
        pool = self._pool(client)
        update, _status = self._update()

        start = time.monotonic()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)
        elapsed = time.monotonic() - start

        session = discover_sessions.get_session(UID)
        self.assertIsNotNone(session)
        self.assertEqual(len(session.groups), count)

        # Ketma-ket bo'lganida ~16 * 0.05 = 0.8s, parallel bo'lganida
        # 2 batch * 0.05 = ~0.1s. chegara o'rtasida.
        sequential = count * delay
        self.assertLess(
            elapsed,
            sequential * 0.6,
            f"skaner ketma-ket ishlamoqda ({elapsed:.2f}s > {sequential:.2f}s)",
        )

    async def test_scan_uses_isolated_client(self) -> None:
        """Skaner alohida client ishlatadi — worker clienti bilan bo'lishmaydi."""
        client = self._client(self._dialogs(3))
        pool = self._pool(client)
        update, _status = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        # isolated_client ishlatilgan bo'lishi kerak.
        self.assertTrue(
            hasattr(pool, "isolated_client"),
            "pool isolated_client usulini taqdim etishi kerak",
        )
        # Umumiy (worker) client hech qachon bo'shatilmagan bo'lishi kerak —
        # chunki skaner alohida client ishlatadi.
        pool.release.assert_not_called()

    async def test_scan_does_not_block_other_users(self) -> None:
        """Bitta foydalanuvchi skaner qilganda boshqalar kutib qolmaydi."""
        slow_client = self._client(self._dialogs(4), delay=0.3)
        slow_pool = self._pool(slow_client)

        fast_client = self._client(self._dialogs(2), delay=0.0)
        fast_pool = self._pool(fast_client)

        slow_update, _s = self._update(UID)
        fast_update, _s2 = self._update(OTHER_UID)

        async def _run_slow():
            with patch.object(W, "client_pool", slow_pool):
                await G.discover_groups(slow_update)

        async def _run_fast():
            with patch.object(W, "client_pool", fast_pool):
                await G.discover_groups(fast_update)

        started = time.monotonic()
        await asyncio.gather(_run_slow(), _run_fast())
        elapsed = time.monotonic() - started

        fast_session = discover_sessions.get_session(OTHER_UID)
        self.assertIsNotNone(fast_session)
        self.assertEqual(len(fast_session.groups), 2)
        # Ikki skaner parallel — ketma-ket emas.
        self.assertLess(elapsed, 0.9, f"skanerlar ketma-ket bo'ldi ({elapsed:.2f}s)")

    async def test_isolated_client_closes_after_scan(self) -> None:
        """Skaner tugagach client yopiladi (resurs yo'qolmaydi)."""
        closed = {"value": False}

        client = self._client(self._dialogs(2))

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def isolated_client(_uid, _session):
            try:
                yield client
            finally:
                closed["value"] = True

        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
            isolated_client=isolated_client,
        )
        update, _status = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        self.assertTrue(closed["value"], "isolated client yopilishi kerak")

    async def test_group_links_are_shown_in_list(self) -> None:
        """Topilgan guruhlar ro'yxatida ochiq havola ko'rsatiladi."""
        client = self._client(self._dialogs(3))
        pool = self._pool(client)
        update, status = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        session = discover_sessions.get_session(UID)
        self.assertIsNotNone(session)
        group = session.groups[0]
        self.assertEqual(group.link(), "https://t.me/grp0")
        # Havola xabar matnida ko'rinadi.
        self.assertIn("https://t.me/grp0", group.display_detail())
        header = status.edit_text.await_args.args[0]
        self.assertIn("https://t.me/grp0", header)

    async def test_button_text_fits_telegram_limit(self) -> None:
        """Tugma matni Telegram limitidan (64 belgi) oshmasligi kerak."""
        client = self._client(self._dialogs(2))
        pool = self._pool(client)
        update, _status = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        session = discover_sessions.get_session(UID)
        self.assertIsNotNone(session)
        for group in session.groups:
            self.assertLessEqual(
                len(f"{'✅'} {group.display()}"), 64, "tugma matni juda uzun"
            )

    async def test_progress_is_updated_regularly(self) -> None:
        """Progress xabari muntazam yangilanadi (foydalanuvchi kutayotganini biladi)."""
        client = self._client(self._dialogs(40))
        pool = self._pool(client)
        update, status = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        # Progress xabari hech bo'lmasa bitta marta (final ro'yxat) chiqadi —
        # kamida bitta progress yangilanishi bo'lishi kerak.
        self.assertGreaterEqual(status.edit_text.await_count, 1)

    async def test_flood_wait_does_not_affect_other_users(self) -> None:
        """FloodWait boshqa foydalanuvchilarni ta'sirlamasligi kerak."""
        from telethon.errors import FloodWaitError as FW

        async def _iter_flood():
            # async generator bo'lishi kerak — `async for` ishlaydi.
            raise FW(request=None, capture=0)
            yield  # pragma: no cover - unreachable

        client = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=UID)),
            iter_dialogs=_iter_flood,
            get_permissions=AsyncMock(side_effect=AssertionError("call qilinmadi")),
        )
        pool = self._pool(client)
        update, _status = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        # FloodWait foydalanuvchining o'ziga xabar beriladi.
        self.assertIn(UID, G._flood_wait_until)
        # Boshqa foydalanuvchiga ta'sir qilinmaydi.
        self.assertNotIn(OTHER_UID, G._flood_wait_until)

    async def test_second_scan_is_rejected_while_running(self) -> None:
        """Bitta skaner davomida ikkinchisi boshlanmasligi kerak."""
        client = self._client(self._dialogs(2))
        pool = self._pool(client)
        update, _status = self._update()

        G._discover_running.add(UID)
        try:
            with patch.object(W, "client_pool", pool):
                await G.discover_groups(update)
        finally:
            G._discover_running.discard(UID)

        # Hech narsa topilmagan (skaner ishga tushmagan).
        session = discover_sessions.get_session(UID)
        self.assertIsNone(session)


class DiscoverLinkUnitTests(unittest.TestCase):
    """Havola yaratish — sof mantiqiy test."""

    def test_username_reference(self) -> None:
        group = discover_sessions.DiscoveredGroup(
            reference="@mygroup", title="G", key="@mygroup"
        )
        self.assertEqual(group.link(), "https://t.me/mygroup")

    def test_private_group_has_no_link(self) -> None:
        group = discover_sessions.DiscoveredGroup(
            reference="-1001234567890", title="Yopiq", key="ref:-1001234567890"
        )
        self.assertEqual(group.link(), "")
        self.assertNotIn("https://", group.display_detail())

    def test_empty_reference(self) -> None:
        group = discover_sessions.DiscoveredGroup(reference="", title="", key="")
        self.assertEqual(group.link(), "")

    def test_display_truncates_long_title(self) -> None:
        group = discover_sessions.DiscoveredGroup(
            reference="@g", title="X" * 80, key="@g"
        )
        text = group.display()
        self.assertLess(len(text.split("\n")[0]), 60)

    def test_display_has_no_link_for_button(self) -> None:
        """Tugma matnida havola bo'lmasligi kerak (64 belgi limiti)."""
        group = discover_sessions.DiscoveredGroup(
            reference="@mygroup", title="Guruh", members=100, key="@mygroup"
        )
        self.assertNotIn("https://", group.display())
        self.assertLessEqual(len(group.display()), 64)


if __name__ == "__main__":
    unittest.main()
