"""🔍 Guruhlarni avtomatik topish (discover_groups) testlari.

Qamlov:
- akkaunt dialoglaridan yozish huquqi bor guruh/kanallar avtomatik qo'shiladi;
- takror, huquqsiz, chiqib ketilgan va foydalanuvchi dialoglari o'tkazib yuboriladi;
- username'siz yopiq guruh marked peer ID bilan saqlanadi;
- sessiya yo'qligi, pool bandligi va paket chegarasi to'g'ri xabar beradi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from telethon.errors import (  # noqa: E402
    FloodWaitError,
    UserNotParticipantError,
)
from telethon.tl import types  # noqa: E402

from bot import groups as G  # noqa: E402
from bot import texts as T  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402
from worker import worker as W  # noqa: E402
from worker.client_pool import PoolBusyError, SessionInvalidError  # noqa: E402

UID = 3001
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _channel(channel_id: int, **kwargs) -> types.Channel:
    params = dict(
        title="test",
        photo=None,
        date=_NOW,
        broadcast=False,
        megagroup=True,
        left=False,
        banned_rights=None,
        default_banned_rights=None,
    )
    params.update(kwargs)
    return types.Channel(channel_id, **params)


def _chat(chat_id: int, **kwargs) -> types.Chat:
    params = dict(
        title="test",
        photo=None,
        participants_count=1,
        date=_NOW,
        version=1,
        left=False,
        default_banned_rights=None,
    )
    params.update(kwargs)
    return types.Chat(chat_id, **params)


def perms_ok():
    return SimpleNamespace(
        has_left=False,
        participant=SimpleNamespace(left=False, banned_rights=None),
        is_creator=False,
        is_admin=False,
        send_messages=True,
        post_messages=False,
    )


def perms_no_write():
    base = perms_ok()
    base.send_messages = False
    return base


def perms_channel_reader():
    # Broadcast kanalda oddiy a'zo: post_messages yo'q → no_write.
    return SimpleNamespace(
        has_left=False,
        participant=SimpleNamespace(left=False, banned_rights=None),
        is_creator=False,
        is_admin=False,
        send_messages=False,
        post_messages=False,
    )


class DiscoverGroupsTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")
        # Anti-spam pauzalarni testda tezlashtiramiz va himoya holatini tozalaymiz.
        G.reset_discover_guards()
        self._sleep_patch = patch.object(G.asyncio, "sleep", new=AsyncMock())
        self._uniform_patch = patch.object(G.random, "uniform", return_value=0)
        self._sleep_patch.start()
        self._uniform_patch.start()

    async def asyncTearDown(self) -> None:
        self._sleep_patch.stop()
        self._uniform_patch.stop()
        G.reset_discover_guards()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _update(self):
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=status))
        return (
            SimpleNamespace(
                effective_user=SimpleNamespace(id=UID),
                message=message,
            ),
            status,
            message,
        )

    def _client(self, dialogs, permissions_map):
        me = SimpleNamespace(id=UID)

        async def _iter_dialogs():
            for dialog in dialogs:
                yield dialog

        async def _get_permissions(entity, _me):
            key = getattr(entity, "username", None) or f"id{entity.id}"
            value = permissions_map[key]
            if isinstance(value, Exception):
                raise value
            return value

        return SimpleNamespace(
            get_me=AsyncMock(return_value=me),
            iter_dialogs=_iter_dialogs,
            get_permissions=AsyncMock(side_effect=_get_permissions),
        )

    async def test_discovers_writable_groups_and_skips_rest(self) -> None:
        # Oldindan mavjud guruh — takror deb topiladi.
        await db.add_chat(UID, "@existing")

        writable_channel = _channel(1001, username="writable")
        readonly_channel = _channel(
            1002, username="news_channel", broadcast=True, megagroup=False
        )
        private_group = _chat(777, title="Yopiq guruh")
        forbidden = types.ChannelForbidden(
            id=1003, access_hash=1, title="forbidden",
            broadcast=False, megagroup=True,
        )
        left_channel = _channel(1004, username="left_one", left=True)
        private_no_access = _channel(555, username=None)
        # Akkaunt EGASI bo'lgan broadcast kanal ham — siyosat bo'yicha qo'shilmaydi.
        own_channel = _channel(
            1006, username="my_own_channel", broadcast=True, megagroup=False
        )
        user_dialog = types.User(id=999)

        dialogs = [
            SimpleNamespace(entity=user_dialog),
            SimpleNamespace(entity=writable_channel),
            SimpleNamespace(entity=readonly_channel),
            SimpleNamespace(entity=own_channel),
            SimpleNamespace(entity=private_group),
            SimpleNamespace(entity=forbidden),
            SimpleNamespace(entity=left_channel),
            SimpleNamespace(entity=private_no_access),
            SimpleNamespace(entity=_channel(1005, username="existing")),
        ]
        permissions_map = {
            "writable": perms_ok(),
            "news_channel": perms_channel_reader(),
            "my_own_channel": SimpleNamespace(
                has_left=False,
                participant=SimpleNamespace(left=False, banned_rights=None),
                is_creator=True,
                is_admin=True,
                send_messages=True,
                post_messages=True,
            ),
            "id777": perms_ok(),
            "id555": UserNotParticipantError(None),
            "existing": perms_ok(),
        }
        client = self._client(dialogs, permissions_map)
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
        )

        update, status, message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        values = await db.get_chats(UID)
        self.assertIn("@writable", values)
        self.assertIn("-777", values)
        # Broadcast kanallar — begona ham, o'z kanali ham qo'shilmaydi.
        self.assertNotIn("@news_channel", values)
        self.assertNotIn("@my_own_channel", values)
        self.assertNotIn("-100555", values)
        # Mavjud guruh qayta qo'shilmaydi.
        self.assertEqual(values.count("@existing"), 1)
        pool.release.assert_awaited_once()

        report = status.edit_text.await_args.args[0]
        self.assertIn("Qo'shildi: 2", report)
        self.assertIn("@writable", report)
        self.assertIn("-777", report)
        self.assertIn("Yozish huquqi", report)
        # Ikkita broadcast kanal (readonly + o'z kanal) alohida sanalgan.
        self.assertIn("Kanallar ataylab qo'shilmadi: 2", report)
        # Yakunda asosiy menyu qaytariladi.
        last_text = message.reply_text.await_args_list[-1].args[0]
        self.assertEqual(last_text, "🏠 Asosiy menyu")

    async def test_cooldown_blocks_second_scan(self) -> None:
        channel = _channel(2002, username="one")
        client = self._client(
            [SimpleNamespace(entity=channel)], {"one": perms_ok()}
        )
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
        )
        with patch.object(W, "client_pool", pool):
            update1, _status1, _msg1 = self._update()
            await G.discover_groups(update1)
            self.assertEqual(pool.acquire.await_count, 1)

            # Darhol ikkinchi marta bosildi — cooldown rad etadi, yangi ulanish yo'q.
            update2, _status2, msg2 = self._update()
            await G.discover_groups(update2)
            self.assertEqual(pool.acquire.await_count, 1)
            text = msg2.reply_text.await_args.args[0]
            self.assertIn("Anti-spam", text)

    async def test_flood_wait_blocks_next_scan_until_time_passes(self) -> None:
        channel = _channel(3002, username="flooded")
        client = self._client(
            [SimpleNamespace(entity=channel)],
            {"flooded": FloodWaitError(request=None, capture=12)},
        )
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
        )
        with patch.object(W, "client_pool", pool):
            update1, status1, _msg1 = self._update()
            await G.discover_groups(update1)
            self.assertIn("FloodWait", status1.edit_text.await_args.args[0])
            self.assertEqual(pool.acquire.await_count, 1)

            # FloodWait vaqti tugamay turib qayta urinish bloklanadi.
            update2, _status2, msg2 = self._update()
            await G.discover_groups(update2)
            self.assertEqual(pool.acquire.await_count, 1)
            text = msg2.reply_text.await_args.args[0]
            self.assertIn("FloodWait", text)

        # Vaqt o'tgach blok yechiladi.
        G._flood_wait_until[UID] = 0
        G._last_discover_ts.pop(UID, None)
        with patch.object(W, "client_pool", pool):
            update3, _status3, _msg3 = self._update()
            await G.discover_groups(update3)
            self.assertEqual(pool.acquire.await_count, 2)

    async def test_only_one_scan_runs_at_a_time(self) -> None:
        pool = SimpleNamespace(
            acquire=AsyncMock(),
            release=AsyncMock(),
        )
        G._discover_running.add(UID)
        try:
            update, _status, msg = self._update()
            with patch.object(W, "client_pool", pool):
                await G.discover_groups(update)
        finally:
            G._discover_running.discard(UID)
        pool.acquire.assert_not_awaited()
        self.assertEqual(
            msg.reply_text.await_args.args[0], T.DISCOVER_ALREADY_RUNNING
        )

    async def test_without_session_asks_to_login(self) -> None:
        await db.del_session(UID)
        pool = SimpleNamespace(acquire=AsyncMock(), release=AsyncMock())
        update, _status, message = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        pool.acquire.assert_not_awaited()
        text = message.reply_text.await_args.args[0]
        self.assertIn("Login", text)

    async def test_busy_pool_returns_busy_message(self) -> None:
        pool = SimpleNamespace(
            acquire=AsyncMock(side_effect=PoolBusyError("band")),
            release=AsyncMock(),
        )
        update, status, _message = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        self.assertIn("band", status.edit_text.await_args.args[0].lower())

    async def test_invalid_session_returns_login_message(self) -> None:
        pool = SimpleNamespace(
            acquire=AsyncMock(side_effect=SessionInvalidError("yaroqsiz")),
            release=AsyncMock(),
        )
        update, status, _message = self._update()

        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        self.assertIn("sessiya", status.edit_text.await_args.args[0].lower())

    async def test_plan_limit_stops_discovery(self) -> None:
        channel = _channel(2001, username="first")
        dialogs = [SimpleNamespace(entity=channel)]
        client = self._client(dialogs, {"first": perms_ok()})
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
        )

        async def fake_add_chat(uid, value):
            return False, "limit"

        update, status, _message = self._update()
        with (
            patch.object(W, "client_pool", pool),
            patch.object(G.db, "add_chat", new=fake_add_chat),
            patch.object(G.db, "get_limits", AsyncMock(return_value={"max_groups": 5})),
        ):
            await G.discover_groups(update)

        report = status.edit_text.await_args.args[0]
        self.assertIn("Paket chegarasi", report)
        pool.release.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
