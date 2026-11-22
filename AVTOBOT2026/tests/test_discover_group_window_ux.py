"""🔍 Guruhlarni topish — guruhlar oynasi UX tuzatishlari (PR #40).

Qamlov:
- ``💬 Guruhlar`` inline oynasida **takror** «🔍 Guruhlarni topish»
  tugmasi yo'q (u faqat asosiy menyuda);
- allaqachon botga qo'shilgan guruhlar keyingi skanerda
  takror taklif qilinmaydi;
- «🚫 Bekor qilish» skaner xabarini **o'chiradi** (eskirgan oyna qolmaydi);
- «✅ Qo'shish»dan keyin yangilangan guruhlar oynasi ko'rinadi;
- qo'shilgan guruhlar baza va oynada ko'rinadi.
"""

from __future__ import annotations

import os
import sys
import tempfile
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
from bot import keyboards as KB
from bot import my_groups as MY_GROUPS
from core import database as db
from core import session_crypto
from worker import worker as W

UID = 4101
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


def _all_button_data(markup) -> list[str]:
    """Inline klaviaturadagi barcha ``callback_data`` ro'yxati."""
    return [btn.callback_data for row in markup.inline_keyboard for btn in row]


def _all_button_texts(markup) -> list[str]:
    """Inline klaviaturadagi barcha tugma matnlari."""
    return [btn.text for row in markup.inline_keyboard for btn in row]


class MyGroupsWindowKeyboardTests(unittest.TestCase):
    """«💬 Guruhlar» oynasi — takror tugmalar bo'lmasligi kerak."""

    def test_no_duplicate_find_button_in_my_groups(self) -> None:
        """Oynada «🔍 Guruhlarni topish» tugmasi BO'LMASligi kerak."""
        groups = [
            {"id": 1, "value": "@alpha"},
            {"id": 2, "value": "@beta"},
        ]
        markup = KB.kb_my_groups(groups, 0)
        texts = _all_button_texts(markup)
        data = _all_button_data(markup)

        self.assertNotIn("🔍 Guruhlarni topish", texts)
        self.assertNotIn("mg:find", data)

    def test_delete_buttons_still_present(self) -> None:
        """O'chirish tugmalari saqlanib qoladi."""
        groups = [
            {"id": 7, "value": "@alpha"},
            {"id": 8, "value": "@beta"},
        ]
        markup = KB.kb_my_groups(groups, 0)
        data = _all_button_data(markup)

        self.assertIn("mg:del:7", data)
        self.assertIn("mg:del:8", data)
        self.assertIn("mg:back", data)

    def test_find_button_exists_in_main_keyboard_source(self) -> None:
        """Asosiy menyu klaviaturasida skaner tugmasi mavjudligi (statik tekshiruv)."""
        import inspect

        source = inspect.getsource(KB)
        self.assertIn("🔍 Guruhlarni topish", source)


class DiscoverGroupWindowUXTests(unittest.IsolatedAsyncioTestCase):
    """Skaner + guruhlar oynasi integratsion testlari."""

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

    def _scan(self, names: list[str]):
        dialogs = []
        permissions = {}
        for i, name in enumerate(names):
            dialogs.append(
                SimpleNamespace(entity=_channel(3000 + i, name, f"Guruh {i}"))
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
            delete_message=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock()),
        )
        return (
            SimpleNamespace(
                callback_query=q,
                effective_user=SimpleNamespace(id=UID),
                message=SimpleNamespace(reply_text=AsyncMock()),
            ),
            q,
        )

    async def test_already_added_groups_excluded_from_next_scan(self) -> None:
        """Allaqachon qo'shilgan guruh keyingi skanerda taklif qilinmaydi."""
        # Birinchi skaner — 3 ta guruh topiladi.
        pool = self._scan(["aaa", "bbb", "ccc"])
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        self.assertIsNotNone(selection)
        self.assertEqual(len(selection.groups), 3)

        # Birinchisini qo'shamiz.
        selection.toggle(selection.groups[0].key)
        cb_update, _q = self._callback("disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply")

        self.assertEqual(await db.get_chats(UID), ["@aaa"])

        # Ikkinchi skaner — endi faqat 2 ta guruh chiqishi kerak.
        # Cooldown'ni tozalaymiz (haqiqiy foydalanuvchi ham qayta skaner
        # qilishi uchun kutishi kerak, test esa buni tekshirmaydi).
        discover_sessions.reset()
        G.reset_discover_guards()
        pool2 = self._scan(["aaa", "bbb", "ccc"])
        update2, _status2, _message2 = self._update()
        with patch.object(W, "client_pool", pool2):
            await G.discover_groups(update2)

        selection2 = discover_sessions.get_session(UID)
        self.assertIsNotNone(selection2)
        refs = [g.reference for g in selection2.groups]
        self.assertNotIn("@aaa", refs, "allaqachon qo'shilgan guruh chiqmasligi kerak")
        self.assertIn("@bbb", refs)
        self.assertIn("@ccc", refs)
        self.assertEqual(len(refs), 2)

    async def test_cancel_deletes_scanner_message(self) -> None:
        """«🚫 Bekor qilish» — skaner xabarini o'chiradi."""
        pool = self._scan(["aaa", "bbb"])
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        cb_update, q = self._callback("disc:cancel")
        await G.handle_discover_callback(cb_update, UID, "disc:cancel")

        q.delete_message.assert_awaited_once()
        # Eskirgan "Bekor qilindi" xabari qolmasligi kerak.
        q.edit_message_text.assert_not_awaited()
        self.assertIsNone(discover_sessions.get_session(UID))
        self.assertEqual(await db.get_chats(UID), [])

    async def test_cancel_falls_back_when_delete_fails(self) -> None:
        """O'chirish xatosi bo'lsa — hech qanday xabar qoldirmaydi."""
        pool = self._scan(["aaa"])
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        cb_update, q = self._callback("disc:cancel")
        q.delete_message = AsyncMock(side_effect=RuntimeError("too old"))
        await G.handle_discover_callback(cb_update, UID, "disc:cancel")

        # Xato yutilgan bo'lishi kerak — exception tashlanmasligi kerak.
        q.edit_message_text.assert_not_awaited()

    async def test_apply_shows_updated_groups_window(self) -> None:
        """Qo'shishdan keyin yangilangan «💬 Guruhlar» oynasi ko'rinadi."""
        pool = self._scan(["aaa", "bbb"])
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        selection.toggle(selection.groups[0].key)
        selection.toggle(selection.groups[1].key)

        cb_update, q = self._callback("disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply")

        q.edit_message_text.assert_awaited()
        args, kwargs = q.edit_message_text.await_args
        text = args[0]
        markup = kwargs.get("reply_markup")

        self.assertIn("GURUHLAR", text)
        self.assertIn("Guruhlar soni: 2 ta", text)
        # Havolalar ko'rinishi kerak.
        self.assertIn("https://t.me/aaa", text)
        self.assertIn("https://t.me/bbb", text)
        # O'chirish tugmalari bo'lishi kerak.
        self.assertIsNotNone(markup)
        data = _all_button_data(markup)
        self.assertTrue(any(d.startswith("mg:del:") for d in data))
        # Takror skaner tugmasi yo'q.
        self.assertNotIn("mg:find", data)
        self.assertNotIn("🔍 Guruhlarni topish", _all_button_texts(markup))

    async def test_apply_report_included_in_window(self) -> None:
        """Hisobot (nechta qo'shildi) yangilangan oynada saqlanadi."""
        pool = self._scan(["aaa"])
        update, _status, _message = self._update()
        with patch.object(W, "client_pool", pool):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        selection.toggle(selection.groups[0].key)

        cb_update, q = self._callback("disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply")

        text = q.edit_message_text.await_args.args[0]
        self.assertIn("Qo'shildi: 1 ta", text)

    async def test_groups_visible_in_window_after_add(self) -> None:
        """Guruh qo'shilgachin u «💬 Guruhlar» oynasida ko'rinadi."""
        await db.add_chat(UID, "@visible")
        text, markup = await MY_GROUPS.build_groups_window(UID)

        self.assertIn("Guruhlar soni: 1 ta", text)
        self.assertIn("https://t.me/visible", text)
        data = _all_button_data(markup)
        self.assertTrue(any(d.startswith("mg:del:") for d in data))
        self.assertNotIn("mg:find", data)

    async def test_empty_groups_window_mentions_main_menu_entry(self) -> None:
        """Guruh yo'q bo'lsa — asosiy menyudagi skaner tugmasi eslatiladi."""
        text, markup = await MY_GROUPS.build_groups_window(UID)

        self.assertIn("Guruhlar", text)
        self.assertIn("🔍 Guruhlarni topish", text)
        self.assertNotIn("mg:find", _all_button_data(markup))

    async def test_delete_refreshes_full_window_with_links(self) -> None:
        """O'chirishdan keyin oyna to'liq yangilanadi — havolalar ham ko'rinadi.

        Avval faqat «💬 GURUHLAR» sarlavhasi qolardi, guruhlar ro'yxati
        yo'qolardi — foydalanuvchi «gurchilar ko'rinmaydi» deb
        shikoyat qilgandi.
        """
        await db.add_chat(UID, "@first")
        await db.add_chat(UID, "@second")

        cb_update, q = self._callback("mg:del:1")
        # ``mg:`` handler super admin bo'lmagan foydalanuvchi uchun.
        await MY_GROUPS.handle_my_groups_callback(cb_update, UID, "mg:del:1")

        q.edit_message_text.assert_awaited()
        text = q.edit_message_text.await_args.args[0]
        self.assertIn("Guruhlar soni: 1 ta", text)
        self.assertIn("https://t.me/second", text)
        self.assertNotIn("https://t.me/first", text)

    async def test_page_refreshes_full_window(self) -> None:
        """Sahifa almashganda ham to'liq oyna (ro'yxat + havolalar)."""
        for i in range(15):
            await db.add_chat(UID, f"@grp{i}")

        cb_update, q = self._callback("mg:page:1")
        await MY_GROUPS.handle_my_groups_callback(cb_update, UID, "mg:page:1")

        q.edit_message_text.assert_awaited()
        text = q.edit_message_text.await_args.args[0]
        self.assertIn("Guruhlar soni: 15 ta", text)
        self.assertIn("https://t.me/grp14", text)

    async def test_back_deletes_window_message(self) -> None:
        """«⬅️ Asosiy menyu» — eskirgan oyna xabarini o'chiradi."""
        await db.add_chat(UID, "@x")

        cb_update, q = self._callback("mg:back")
        with patch("bot.menu.show_home", new=AsyncMock()):
            await MY_GROUPS.handle_my_groups_callback(cb_update, UID, "mg:back")

        q.delete_message.assert_awaited_once()
        q.edit_message_text.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
