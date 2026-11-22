"""📝 Guruh nomi (title) — bazadan tugma matnigacha.

Qamlov:
- bazada ``groups.title`` ustuni bor va migratsiya xavfsiz (eski ma'lumot
  o'chmaydi);
- skaner orqali qo'shilgan guruh nomi saqlanadi;
- ``🗑`` tugmasida guruh **nomi** ko'rinadi (nom yo'q bo'lsa — username);
- ro'yxatda nom va ochiq havola birga chiqadi;
- nomi yo'q guruhlar uchun fon task'da nom Telegram'dan olinadi;
- nom olish **foydalanuvchini kechiktirmaydi** (fon task).
"""

from __future__ import annotations

import os
import sqlite3
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

from bot import groups as G
from bot import keyboards as KB
from bot import my_groups as MG
from core import database as db
from core import session_crypto

UID = 5151
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


def _buttons(markup) -> list:
    return [btn for row in markup.inline_keyboard for btn in row]


def _texts(markup) -> list[str]:
    return [btn.text for btn in _buttons(markup)]


class GroupTitleDatabaseTests(unittest.IsolatedAsyncioTestCase):
    """Baza qatlami — ``title`` ustuni va uning API si."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_add_chat_saves_title(self) -> None:
        """``add_chat`` — nomni saqlaydi."""
        ok, reason = await db.add_chat(UID, "@g1", title="Taxi Toshkent")
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

        records = await db.get_chat_records(UID)
        self.assertEqual(records[0]["title"], "Taxi Toshkent")

    async def test_add_chat_without_title_is_empty(self) -> None:
        """Nomsiz qo'shish — ``title`` bo'sh bo'ladi (backward compatible)."""
        await db.add_chat(UID, "@g1")
        records = await db.get_chat_records(UID)
        self.assertEqual(records[0]["title"], "")

    async def test_set_chat_title_fills_only_empty(self) -> None:
        """Faqat bo'sh nom to'ldiriladi — mavjud nom qayta yozilmaydi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        self.assertTrue(await db.set_chat_title(UID, group_id, "Taxi Toshkent"))
        self.assertFalse(await db.set_chat_title(UID, group_id, "Boshqa nom"))

        records = await db.get_chat_records(UID)
        self.assertEqual(records[0]["title"], "Taxi Toshkent")

    async def test_set_chat_title_empty_rejected(self) -> None:
        """Bo'sh nom saqlanmaydi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]
        self.assertFalse(await db.set_chat_title(UID, group_id, "   "))

    async def test_duplicate_still_blocked(self) -> None:
        """Takror qo'shish bloklanadi (nom bilan ham)."""
        await db.add_chat(UID, "@g1", title="Birinchi")
        ok, reason = await db.add_chat(UID, "@g1", title="Ikkinchi")
        self.assertFalse(ok)
        self.assertEqual(reason, "duplicate")

    async def test_migration_adds_title_column_without_data_loss(self) -> None:
        """Eski bazada ``title`` ustuni qo'shiladi, ma'lumut saqlanadi."""
        await db.close_db()
        legacy = Path(self.temp.name) / "legacy.db"
        conn = sqlite3.connect(str(legacy))
        conn.execute(
            "CREATE TABLE users (uid INTEGER PRIMARY KEY, name TEXT DEFAULT '', "
            "username TEXT DEFAULT '', phone TEXT DEFAULT '', "
            "session TEXT DEFAULT '', pending_session TEXT DEFAULT '', "
            "is_admin INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0, "
            "awaiting_approval INTEGER DEFAULT 0, tariff_expires_at TEXT, "
            "warned_at TEXT, interval_min INTEGER DEFAULT 60, "
            "running INTEGER DEFAULT 0, referrer_uid INTEGER, "
            "referral_counted INTEGER DEFAULT 0, plan TEXT DEFAULT '', "
            "max_groups INTEGER DEFAULT 0, max_posts INTEGER DEFAULT 0, "
            "daily_limit INTEGER DEFAULT 0, active_hours TEXT DEFAULT '', "
            "referral_bonus_days INTEGER DEFAULT 0, "
            "referral_bonus_note TEXT DEFAULT '', last_active_at TEXT, "
            "created_at TEXT, updated_at TEXT, is_team_admin INTEGER DEFAULT 0, "
            "team_id INTEGER DEFAULT 0, owner_admin_uid INTEGER DEFAULT 0)"
        )
        conn.execute(
            "CREATE TABLE groups (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "uid INTEGER NOT NULL, value TEXT NOT NULL, created_at TEXT, "
            "UNIQUE(uid, value))"
        )
        conn.execute("INSERT INTO users (uid, name) VALUES (77, 'Eski')")
        conn.execute(
            "INSERT INTO groups (uid, value, created_at) "
            "VALUES (77, '@eski', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        db.DB_PATH = legacy
        await db.init_db()

        records = await db.get_chat_records(77)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], "@eski")
        self.assertEqual(records[0]["title"], "")

        conn = sqlite3.connect(str(legacy))
        cols = {r[1] for r in conn.execute("PRAGMA table_info(groups)")}
        conn.close()
        self.assertIn("title", cols)


class GroupTitleDisplayTests(unittest.IsolatedAsyncioTestCase):
    """Ko'rsatish qatlami — nom tugmada va ro'yxatda."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _update(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        ), message

    async def test_delete_button_shows_title(self) -> None:
        """✅ ``🗑`` tugmasida guruh NOMI ko'rinadi."""
        await db.add_chat(UID, "@taxi_x", title="Taxi Xorazm Toshken")

        markup = KB.kb_my_groups(await db.get_chat_records(UID), 0)
        labels = _texts(markup)

        self.assertTrue(
            any("Taxi Xorazm Toshken" in label for label in labels),
            f"nom tugmada yo'q: {labels}",
        )
        # Username ham kerak emas — nom yetarli.
        self.assertFalse(
            any("@taxi_x" in label for label in labels),
            f"username kerak emas: {labels}",
        )

    async def test_delete_button_falls_back_to_username(self) -> None:
        """Nomi yo'q bo'lsa — username ko'rsatiladi."""
        await db.add_chat(UID, "@taxi_x")

        markup = KB.kb_my_groups(await db.get_chat_records(UID), 0)
        labels = _texts(markup)

        self.assertTrue(any("@taxi_x" in label for label in labels), labels)

    async def test_button_label_within_telegram_limit(self) -> None:
        """Tugma matni 64 belgi limitidan oshmasligi kerak."""
        long_title = "X" * 300
        await db.add_chat(UID, "@g", title=long_title)

        markup = KB.kb_my_groups(await db.get_chat_records(UID), 0)
        for label in _texts(markup):
            self.assertLessEqual(len(label), 64, f"tugma matni uzun: {len(label)}")

    async def test_window_shows_title_with_link(self) -> None:
        """Ro'yxatda nom va havola birga chiqadi."""
        await db.add_chat(UID, "@taxi_x", title="Taxi Xorazm")

        text, _markup = await MG.build_groups_window(UID)

        self.assertIn("Taxi Xorazm", text)
        self.assertIn(r"https://t.me/taxi\_x", text)

    async def test_window_shows_username_when_no_title(self) -> None:
        """Nomi yo'q bo'lsa — username ko'rinadi."""
        await db.add_chat(UID, "@taxi_x")

        text, _markup = await MG.build_groups_window(UID)

        self.assertIn(r"@taxi\_x", text)

    def test_group_label_helper(self) -> None:
        """``group_label`` — nom, aks holda username."""
        self.assertEqual(
            MG.group_label({"title": "Taxi Xorazm", "value": "@taxi_x"}),
            "Taxi Xorazm",
        )
        self.assertEqual(
            MG.group_label({"title": "", "value": "@taxi_x"}), "@taxi_x"
        )
        # Nomi username bilan bir xil bo'lsa — username.
        self.assertEqual(
            MG.group_label({"title": "@taxi_x", "value": "@taxi_x"}), "@taxi_x"
        )


class GroupTitleScanTests(unittest.IsolatedAsyncioTestCase):
    """Skaner orqali qo'shish — nom saqlanadi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")
        G.reset_discover_guards()

    async def asyncTearDown(self) -> None:
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
        )

    def _callback(self, data: str):
        q = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            delete_message=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
            message=SimpleNamespace(edit_text=AsyncMock(), reply_text=AsyncMock()),
        )
        return (
            SimpleNamespace(
                callback_query=q,
                effective_user=SimpleNamespace(id=UID),
                message=SimpleNamespace(reply_text=AsyncMock()),
            ),
            q,
        )

    async def test_scan_stores_title(self) -> None:
        """Skanerda topilgan guruh nomi bazaga yoziladi."""
        from bot import discover_sessions
        from worker import worker as W

        entity = _channel(7001, "taxi_x", "Taxi Xorazm Toshken")
        dialogs = [SimpleNamespace(entity=entity)]

        async def _iter_dialogs():
            for d in dialogs:
                yield d

        client = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=UID)),
            iter_dialogs=_iter_dialogs,
            get_permissions=AsyncMock(side_effect=lambda e, m: perms_ok()),
        )
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=client), release=AsyncMock()
        )

        update, _status = self._update()
        with (
            patch.object(G.asyncio, "sleep", new=AsyncMock()),
            patch.object(G.random, "uniform", return_value=0),
            patch.object(W, "client_pool", pool),
        ):
            await G.discover_groups(update)

        selection = discover_sessions.get_session(UID)
        selection.toggle(selection.groups[0].key)

        cb_update, _q = self._callback("disc:apply")
        await G.handle_discover_callback(cb_update, UID, "disc:apply")

        records = await db.get_chat_records(UID)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["value"], "@taxi_x")
        self.assertEqual(records[0]["title"], "Taxi Xorazm Toshken")

        discover_sessions.reset()


async def _iter(items):
    for item in items:
        yield item


class GroupTitleBackgroundFillTests(unittest.IsolatedAsyncioTestCase):
    """Nomi yo'q guruhlar uchun fon task."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")
        MG._title_fill_tasks.clear()

    async def asyncTearDown(self) -> None:
        for task in list(MG._title_fill_tasks.values()):
            task.cancel()
        MG._title_fill_tasks.clear()
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_fill_missing_titles_stores_name(self) -> None:
        """Nomi yo'q guruh uchun Telegram'dan nom olinadi va saqlanadi."""
        await db.add_chat(UID, "@taxi_x")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        entity = SimpleNamespace(title="Taxi Xorazm Toshken")

        async def _resolve(client, reference):
            return entity

        with (
            patch.object(G, "resolve_group_entity", new=_resolve),
            patch.object(MG, "StringSession", new=lambda _s: "SESSION"),
            patch.object(MG, "TelegramClient") as client_cls,
        ):
            client = AsyncMock()
            client.connect = AsyncMock()
            client.get_me = AsyncMock(return_value=SimpleNamespace(id=UID))
            client.disconnect = AsyncMock()
            client_cls.return_value = client

            await MG._fill_missing_titles(UID)

        records = await db.get_chat_records(UID)
        self.assertEqual(records[0]["title"], "Taxi Xorazm Toshken")
        self.assertEqual(group_id, records[0]["id"])

    async def test_fill_skips_groups_with_title(self) -> None:
        """Nomi bor guruh — qayta so'ralmaydi."""
        await db.add_chat(UID, "@taxi_x", title="Allaqachon bor")

        with patch.object(MG, "TelegramClient") as client_cls:
            await MG._fill_missing_titles(UID)

        client_cls.assert_not_called()

    async def test_fill_without_session_does_nothing(self) -> None:
        """Sessiyo yo'q — Telegram'ga ulanmaydi."""
        await db.add_chat(UID, "@taxi_x")
        await db.set_session(UID, "")

        with patch.object(MG, "TelegramClient") as client_cls:
            await MG._fill_missing_titles(UID)

        client_cls.assert_not_called()

    async def test_schedule_title_fill_is_idempotent(self) -> None:
        """Bir foydalanuvchi uchun faqat bitta task ishlaydi."""
        with patch.object(MG, "_fill_missing_titles", new=AsyncMock()):
            MG.schedule_title_fill(UID)
            first = MG._title_fill_tasks.get(UID)
            MG.schedule_title_fill(UID)
            second = MG._title_fill_tasks.get(UID)

        self.assertIsNotNone(first)
        self.assertIs(first, second)


if __name__ == "__main__":
    unittest.main()
