"""🔍 Guruhlarni topish — qo'lda belgilash oqimi testlari.

Qamlov:
- skaner hech qanday guruhni avtomatik qo'shmaydi;
- ro'yxat sahifalash bilan chiqadi (15 ta/sahifa);
- ✅ belgisi faqat tanlangan guruhni qo'shadi;
- belgilanmagan guruhlar hech qachon qo'shilmaydi;
- sessiya muddati tugagan taqdirda xabar beriladi.
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

from cryptography.fernet import Fernet
from telethon.tl import types

from bot import discover_sessions
from bot import groups as G
from core import database as db
from core import session_crypto
from worker import worker as W

UID = 3101
_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


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


class DiscoverSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")
        G.reset_discover_guards()
        discover_sessions.reset()
        self._sleep_patch = patch.object(G.asyncio, "sleep", new=AsyncMock())
        self._uniform_patch = patch.object(G.random, "uniform", return_value=0)
        self._sleep_patch.start()
        self._uniform_patch.start()

    async def asyncTearDown(self) -> None:
        self._sleep_patch.stop()
        self._uniform_patch.stop()
        G.reset_discover_guards()
        discover_sessions.reset()
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

    def _scan(self, count: int = 3):
        """`count` ta guruh topib, tanlov sessiyasini yaratadi."""
        dialogs = []
        permissions = {}
        for i in range(count):
            name = f"grp{i}"
            dialogs.append(
                SimpleNamespace(entity=_channel(2000 + i, name, f"Guruh {i}"))
            )
            permissions[name] = perms_ok()
        client = self._client(dialogs, permissions)
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client),
            release=AsyncMock(),
        )
        return pool

    def _callback(self, data: str):
        q = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        return SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=UID),
            message=SimpleNamespace(reply_text=AsyncMock()),
        ), q

    async def test_scan_does_not_add_any_group(self) -> None:
        """Skaner hech qanday guruhni botga qo'shmaydi."""
        pool = self._scan(3)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        self.assertEqual(await db.get_chats(UID), [], "hech narsa qo'shilmasligi kerak")

    async def test_list_is_shown_with_count(self) -> None:
        """Ro'yxat xabari chiqadi va topilgan guruhlar soni ko'rsatiladi."""
        pool = self._scan(3)
        update, status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        header = status.edit_text.await_args.args[0]
        self.assertIn("Guruhlar ro'yxati", header)
        self.assertIn("Topilgan guruh: 3 ta", header)
        self.assertIn("✅ Belgilangan: 0 ta", header)

    async def test_toggle_selects_group(self) -> None:
        """✅ belgisi guruhni tanlaydi."""
        pool = self._scan(3)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        target = selection.groups[1]
        cb_update, q = self._callback("disc:toggle:1")
        await G.handle_discover_callback(cb_update, UID, "disc:toggle:1")

        self.assertTrue(selection.is_selected(target.key))
        self.assertIn("Tanlandi", q.answer.await_args.args[0])

    async def test_apply_adds_only_selected_groups(self) -> None:
        """Faqat belgilangan guruhlar qo'shiladi."""
        pool = self._scan(3)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        selection.toggle(selection.groups[0].key)
        selection.toggle(selection.groups[2].key)

        cb_update, q = self._callback("disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply:yes")

        values = await db.get_chats(UID)
        self.assertIn("@grp0", values)
        self.assertIn("@grp2", values)
        # Belgilanmagan guruh qo'shilmadi!
        self.assertNotIn("@grp1", values)
        report = q.edit_message_text.await_args.args[0]
        self.assertIn("Qo'shildi: 2 ta", report)

    async def test_apply_without_selection_adds_nothing(self) -> None:
        """Hech narsa belgilanmagan bo'lsa — hech narsa qo'shilmaydi."""
        pool = self._scan(2)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        cb_update, q = self._callback("disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply:yes")

        self.assertEqual(await db.get_chats(UID), [])
        self.assertIn("belgilanmagan", q.answer.await_args.args[0])

    async def test_pagination_15_per_page(self) -> None:
        """Sahifada 15 ta guruh ko'rsatiladi."""
        pool = self._scan(20)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        self.assertEqual(selection.page_count(), 2)
        self.assertEqual(len(selection.page_groups(0)), 15)
        self.assertEqual(len(selection.page_groups(1)), 5)

    async def test_expired_session_reports_error(self) -> None:
        """Sessiya muddati tugagan bo'lsa — xabar beriladi."""
        pool = self._scan(2)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        selection.updated_at -= discover_sessions.DISCOVER_SELECTION_TTL_S + 60

        cb_update, q = self._callback("disc:toggle:0")
        await G.handle_discover_callback(cb_update, UID, "disc:toggle:0")

        self.assertIn("muddati tugagan", q.answer.await_args.args[0])

    async def test_cancel_discards_selection(self) -> None:
        """Bekor qilish — hech narsa qo'shilmaydi."""
        pool = self._scan(2)
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        selection.toggle(selection.groups[0].key)

        cb_update, _q = self._callback("disc:cancel")
        await G.handle_discover_callback(cb_update, UID, "disc:cancel")

        self.assertIsNone(discover_sessions.get_session(UID))
        self.assertEqual(await db.get_chats(UID), [])


class DiscoverKeyTests(unittest.TestCase):
    """Dedupe kaliti — hech qachon bo'sh bo'lmasligi kerak."""

    def test_normal_key(self) -> None:
        self.assertEqual(discover_sessions.build_key("@mygroup"), "@mygroup")

    def test_numeric_username_gets_fallback(self) -> None:
        """Raqam bilan tugaydigan username uchun fallback kalit."""
        key = discover_sessions.build_key("@g0")
        self.assertTrue(key, "kalit bo'sh bo'lmasligi kerak")
        self.assertNotEqual(key, discover_sessions.build_key("@g1"))

    def test_fallback_is_case_insensitive(self) -> None:
        self.assertEqual(
            discover_sessions.build_key("@AbC"), discover_sessions.build_key("@abc")
        )

    def test_empty_reference(self) -> None:
        self.assertEqual(discover_sessions.build_key(""), "")


class DiscoverSessionUnitTests(unittest.TestCase):
    """Sessiya obyekti mantiqi."""

    def test_page_count(self) -> None:
        session = discover_sessions.DiscoverSession()
        self.assertEqual(session.page_count(), 1)
        session.groups = [
            discover_sessions.DiscoveredGroup(
                reference=f"@g{i}", title=f"G{i}", key=f"g{i}"
            )
            for i in range(31)
        ]
        self.assertEqual(session.page_count(), 3)

    def test_toggle_on_off(self) -> None:
        group = discover_sessions.DiscoveredGroup(
            reference="@g", title="G", key="g"
        )
        session = discover_sessions.DiscoverSession(groups=[group])
        self.assertTrue(session.toggle("g"))
        self.assertTrue(session.is_selected("g"))
        self.assertFalse(session.toggle("g"))
        self.assertFalse(session.is_selected("g"))

    def test_expiry(self) -> None:
        session = discover_sessions.DiscoverSession()
        self.assertFalse(session.is_expired())
        session.updated_at -= discover_sessions.DISCOVER_SELECTION_TTL_S + 10
        self.assertTrue(session.is_expired())


if __name__ == "__main__":
    unittest.main()
