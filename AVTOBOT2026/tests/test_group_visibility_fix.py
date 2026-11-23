"""🐛 «Guruhlar yo'q» holatini tuzatish.

Muammo: guruhlar bazaga yozilgan deb hisoblanardi (``+3`` log), lekin
``«💬 Guruhlar»`` oynasi bo'sh chiqardi. Sabab bo'lishi mumkin bo'lgan
joylar tuzatildi:

- ``db.add_chat`` endi FK xatosini ``duplicate`` dan ajratadi;
- ``db.add_chat`` commitdan keyin yozuv bazada borini tekshiradi;
- ``db.delete_user`` bog'liq guruhlarni aniq o'chirdi (FK CASCADE ishonchi
  emas);
- guruh o'chirishda ``log()`` yoziladi (iz qoladi);
- ``disc:apply`` natijani bazadagi haqiqiy ro'yxat bilan tekshiradi;
- bo'sh «Guruhlar» oynasida skaner topilgan guruhlar haqida eslatma chiqadi.

Qamlov:
- FK xatosi ``foreign_key`` qaytaradi (``duplicate`` emas);
- yozuv commitdan keyin yo'q bo'lsa ``saved=False``;
- ``delete_user`` guruhlarni o'chirdi;
- o'chirish loglarda iz qoldiradi;
- ``disc:apply`` bazada 0 ta guruh bo'lsa xato xabarini beradi;
- bo'sh oynada skaner eslatmasi chiqadi.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from bot import discover_sessions as DS
from bot import groups as G
from bot import my_groups as MG
from core import database as db

UID = 6169018469


class _DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    """Kattaqtoral DB bilan ishlash uchun umumiy asos."""

    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        await db.init_db()
        await db.upsert_user(UID, name="Eshmat Toshmatov", is_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        self.temp.cleanup()


class AddChatIntegrityTests(_DatabaseTestCase):
    @staticmethod
    def _patched_execute(rule):
        """``conn.execute`` ni almashtiradi.

        ``aiosqlite.Connection.execute`` — ``asynccontextmanager`` bilan
        bezangan obyekt qaytaradi. Bu obyektni ham ``await`` bilan, ham
        ``async with`` bilan ishlatish mumkin — shuning uchun wrapper
        ikkala shaklni ham qo'llaydi.
        """

        class _Wrapper:
            def __init__(self, sql, parameters=None):
                self._sql = sql
                self._parameters = parameters or []

            def _action(self) -> str:
                return rule(str(self._sql))

            async def _run(self):
                action = self._action()
                if action == "raise_fk":
                    raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
                if action == "empty":
                    sql = "SELECT 1 FROM groups WHERE 1=0"
                    parameters = []
                else:
                    sql = self._sql
                    parameters = self._parameters
                # ``_execute`` — ichki metodi; kursorni yopmaydi.
                cursor = await db._conn()._execute(
                    db._conn()._conn.execute, sql, parameters
                )
                from aiosqlite import Cursor

                return Cursor(db._conn(), cursor)

            def __await__(self):
                return self._run().__await__()

            async def __aenter__(self):
                return await self._run()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def _execute(sql, parameters=None):
            return _Wrapper(sql, parameters)

        return _execute

    async def test_foreign_key_error_is_not_reported_as_duplicate(self) -> None:
        """FK xatosi "duplicate" deb yolg'on qaytarilmasin."""

        def _rule(sql: str) -> str:
            if sql.strip().upper().startswith("INSERT INTO GROUPS"):
                return "raise_fk"
            return "normal"

        with patch.object(db._conn(), "execute", new=self._patched_execute(_rule)):
            saved, reason = await db.add_chat(UID, "@some_group")

        self.assertFalse(saved)
        self.assertEqual(reason, "foreign_key")
        self.assertNotEqual(reason, "duplicate")

    async def test_real_duplicate_still_returns_duplicate(self) -> None:
        """Haqiqiy takror ("UNIQUE") eski holicha "duplicate" qaytaradi."""
        saved, _ = await db.add_chat(UID, "@some_group")
        self.assertTrue(saved)

        saved2, reason = await db.add_chat(UID, "@some_group")
        self.assertFalse(saved2)
        self.assertEqual(reason, "duplicate")

    async def test_missing_row_after_commit_is_detected(self) -> None:
        """Commitdan keyin yozuv topilmasa — ``saved=False`` qaytariladi."""

        def _rule(sql: str) -> str:
            if sql.strip().upper().startswith("SELECT 1 FROM GROUPS"):
                return "empty"
            return "normal"

        with patch.object(db._conn(), "execute", new=self._patched_execute(_rule)):
            saved, reason = await db.add_chat(UID, "@vanishing_group")

        self.assertFalse(saved)
        self.assertEqual(reason, "error")

    async def test_successful_add_returns_ok(self) -> None:
        saved, reason = await db.add_chat(UID, "@ok_group", title="Yaxshi Guruh")
        self.assertTrue(saved)
        self.assertEqual(reason, "ok")

        rows = await db.get_chat_records(UID)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Yaxshi Guruh")


class DeleteUserCleanupTests(_DatabaseTestCase):
    async def test_delete_user_removes_groups(self) -> None:
        """Foydalanuvchi o'chirilsa, guruhlari ham o'chsin (nazorat ostida)."""
        await db.add_chat(UID, "@group_one")
        await db.add_chat(UID, "@group_two")

        ok = await db.delete_user(UID)
        self.assertTrue(ok)

        rows = await db.get_chat_records(UID)
        self.assertEqual(rows, [])


class GroupRemovalLoggingTests(_DatabaseTestCase):
    async def test_my_groups_removal_is_logged(self) -> None:
        """Foydalanuvchi guruh o'chirsin — logda iz qolsin."""
        await db.add_chat(UID, "@group_one")

        record = await db.get_chat_record(UID, 1)
        self.assertIsNotNone(record)

        answer = AsyncMock()
        callback = SimpleNamespace(
            data="mg:del:1",
            message=None,
            answer=answer,
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        with patch("bot.my_groups.log") as mock_log:
            await MG.handle_my_groups_callback(update, UID, "mg:del:1")

        self.assertTrue(mock_log.called)
        text = " ".join(str(call) for call in mock_log.call_args_list)
        self.assertIn("guruh o'chirildi", text)


class DiscoverApplyVerificationTests(_DatabaseTestCase):
    async def test_apply_reports_error_when_nothing_stored(self) -> None:
        """``add_chat`` "muvaffaqiyatli" bo'lsa ham, bazada 0 ta bo'lsa —
        foydalanuvchiga xato ko'rsatilsin (avval "qo'shildi" deyardi)."""
        session = DS.start_session(
            UID,
            [
                DS.DiscoveredGroup(
                    reference="@a", title="A", key=DS.build_key("@a")
                ),
                DS.DiscoveredGroup(
                    reference="@b", title="B", key=DS.build_key("@b")
                ),
            ],
        )
        session.selected.update({session.groups[0].key, session.groups[1].key})

        answer = AsyncMock()
        callback = SimpleNamespace(
            data="disc:apply",
            message=SimpleNamespace(
                reply_text=AsyncMock(), delete_message=AsyncMock()
            ),
            answer=answer,
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        async def _fake_add_chat(uid, value, title=""):
            return True, "ok"

        with patch.object(db, "add_chat", side_effect=_fake_add_chat):
            await G.handle_discover_callback(update, UID, "disc:apply")
            await G.handle_discover_callback(update, UID, "disc:apply:yes")

        # Foydalanuvchiga "qo'shildi" emas, xato ko'rsatilishi kerak.
        alerts = [call.args[0] for call in answer.call_args_list if call.args]
        self.assertTrue(alerts)
        self.assertIn("❌", alerts[-1])

    async def test_apply_reports_success_when_stored(self) -> None:
        """Normal holat — "qo'shildi" xabari chiqsin."""
        session = DS.start_session(
            UID, [DS.DiscoveredGroup(
                reference="@a", title="A", key=DS.build_key("@a")
            )]
        )
        session.selected.update({session.groups[0].key})

        answer = AsyncMock()
        callback = SimpleNamespace(
            data="disc:apply",
            message=SimpleNamespace(
                reply_text=AsyncMock(), delete_message=AsyncMock()
            ),
            answer=answer,
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        await G.handle_discover_callback(update, UID, "disc:apply")
        await G.handle_discover_callback(update, UID, "disc:apply:yes")

        alerts = [call.args[0] for call in answer.call_args_list if call.args]
        self.assertTrue(alerts)
        self.assertIn("qo'shildi", alerts[-1])
        rows = await db.get_chat_records(UID)
        self.assertEqual(len(rows), 1)


class EmptyGroupsWindowHintTests(_DatabaseTestCase):
    async def test_empty_window_mentions_scanner_results(self) -> None:
        """Skanerda tanlangan guruhlar bo'lsa — bo'sh oynada eslatma chiqsin."""
        session = DS.start_session(
            UID, [DS.DiscoveredGroup(
                reference="@a", title="A", key=DS.build_key("@a")
            )]
        )
        session.selected.update({session.groups[0].key})

        with patch.object(DS, "get_session", return_value=session):
            text, _markup = await MG.build_groups_window(UID)

        self.assertIn("Sizda hali guruh yo'q", text)
        self.assertIn("Tanlanganlarni saqlash", text)

    async def test_empty_window_without_session_is_unchanged(self) -> None:
        """Skaner sessiyasi yo'q bo'lsa — xabar o'zgfeitamente."""
        with patch.object(DS, "get_session", return_value=None):
            text, _markup = await MG.build_groups_window(UID)

        self.assertIn("Sizda hali guruh yo'q", text)
        self.assertNotIn("Tanlanganlarni saqlash", text)


if __name__ == "__main__":
    unittest.main()
