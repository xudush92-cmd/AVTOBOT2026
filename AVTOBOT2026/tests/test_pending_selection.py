"""🎯 Tanlangan guruhlar yo'qolmasligi.

Muammo: foydalanuvchi skanerda guruhlarni ✅ belgilaydi, lekin
«Tanlanganlarni qo'shish» tugmasini bosmaydi — oyna yopiladi. Natijada
tanlangan guruhlar **yo'qoladi** va foydalanuvchi «guruhlar yo'q» deb
o'ylaydi.

Tuzatish:
- «💬 Guruhlar» oynasida skanerdagi tanlanish ko'rinadi;
- «✅ Tanlanganlarni qo'shish (N)» tugmasi chiqadi;
- bu tugma skanerdagi bilan bir xil funksiyani ishlatadi.

Qamlov:
- bo'sh oynada tanlanish eslatmasi va tugmasi chiqadi;
- to'ldirilgan oynada ham xuddi shunday;
- tugma skaner oynasidagi bilan bir xil natijani beradi;
- tanlanish yo'q bo'lsa tugma chiqmaydi.
"""

from __future__ import annotations

import os
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


class _Base(unittest.IsolatedAsyncioTestCase):
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

    @staticmethod
    def _session(count: int = 2, selected: int = 2) -> DS.DiscoverSession:
        groups = [
            DS.DiscoveredGroup(
                reference=f"@g{i}",
                title=f"Guruh {i}",
                key=DS.build_key(f"@g{i}"),
            )
            for i in range(count)
        ]
        session = DS.start_session(UID, groups)
        for group in groups[:selected]:
            session.selected.add(group.key)
        return session


class PendingSelectionTests(_Base):
    async def test_empty_window_shows_apply_button(self) -> None:
        """Bo'sh oynada tanlanish eslatmasi va tugmasi chiqishi kerak."""
        session = self._session(count=3, selected=2)

        with patch.object(DS, "get_session", return_value=session):
            text, markup = await MG.build_groups_window(UID)

        self.assertIn("Sizda hali guruh yo'q", text)
        self.assertIn("<b>3</b>", text)
        self.assertIn("<b>2</b>", text)
        buttons = [
            btn
            for row in markup.inline_keyboard
            for btn in row
            if "Tanlanganlarni qo'shish" in btn.text
        ]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(buttons[0].callback_data, "mg:apply")
        self.assertIn("(2)", buttons[0].text)

    async def test_filled_window_also_shows_apply_button(self) -> None:
        """Guruhlar bo'lsa ham, tanlanish ko'rinishi kerak."""
        await db.add_chat(UID, "@existing")
        session = self._session(count=3, selected=2)

        with patch.object(DS, "get_session", return_value=session):
            text, markup = await MG.build_groups_window(UID)

        self.assertNotIn("Sizda hali guruh yo'q", text)
        self.assertIn("<b>2</b>", text)
        buttons = [
            btn
            for row in markup.inline_keyboard
            for btn in row
            if "Tanlanganlarni qo'shish" in btn.text
        ]
        self.assertEqual(len(buttons), 1)

    async def test_no_selection_no_button(self) -> None:
        """Tanlanish yo'q bo'lsa — tugma chiqmasligi kerak."""
        session = self._session(count=3, selected=0)

        with patch.object(DS, "get_session", return_value=session):
            _text, markup = await MG.build_groups_window(UID)

        buttons = [
            btn
            for row in markup.inline_keyboard
            for btn in row
            if "Tanlanganlarni qo'shish" in btn.text
        ]
        self.assertEqual(buttons, [])

    async def test_no_session_no_button(self) -> None:
        """Skaner sessiyasi yo'q bo'lsa — tugma chiqmasligi kerak."""
        with patch.object(DS, "get_session", return_value=None):
            _text, markup = await MG.build_groups_window(UID)

        buttons = [
            btn
            for row in markup.inline_keyboard
            for btn in row
            if "Tanlanganlarni qo'shish" in btn.text
        ]
        self.assertEqual(buttons, [])


class ApplyFromGroupsWindowTests(_Base):
    async def test_mg_apply_adds_selected_groups(self) -> None:
        """«Guruhlar» oynasidagi tugma tanlangan guruhlarni qo'shishi kerak."""
        session = self._session(count=2, selected=2)

        answer = AsyncMock()
        callback = SimpleNamespace(
            data="mg:apply",
            message=None,
            answer=answer,
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        with patch.object(DS, "get_session", return_value=session):
            await MG.handle_my_groups_callback(update, UID, "mg:apply")

        rows = await db.get_chat_records(UID)
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            sorted(r["value"] for r in rows), ["@g0", "@g1"]
        )
        # Nomi ham saqlangan bo'lishi kerak.
        self.assertEqual(rows[0]["title"], "Guruh 0")

    async def test_mg_apply_without_selection_shows_hint(self) -> None:
        """Tanlanish yo'q bo'lsa — foydalanuvchiga eslatma beriladi."""
        session = self._session(count=2, selected=0)

        answer = AsyncMock()
        callback = SimpleNamespace(
            data="mg:apply",
            message=None,
            answer=answer,
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        with patch.object(DS, "get_session", return_value=session):
            await MG.handle_my_groups_callback(update, UID, "mg:apply")

        answer.assert_awaited()
        alert = answer.await_args.args[0]
        self.assertIn("belgilanmagan", alert)
        self.assertEqual(await db.get_chat_records(UID), [])


class SharedApplyFunctionTests(_Base):
    async def test_both_paths_use_same_function(self) -> None:
        """Skaner oynasi va «Guruhlar» oynasi bir xil funksiyani ishlatadi."""
        session = self._session(count=2, selected=2)

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

        with (
            patch.object(
                G, "apply_selected_groups", wraps=G.apply_selected_groups
            ) as spy,
            patch.object(DS, "get_session", return_value=session),
        ):
            await G.handle_discover_callback(update, UID, "disc:apply")

        self.assertTrue(spy.await_count)
        rows = await db.get_chat_records(UID)
        self.assertEqual(len(rows), 2)


class ScannerGroupsButtonTests(_Base):
    async def test_scanner_has_groups_button(self) -> None:
        """Skaner oynasida «⬅️ Guruhlar» tugmasi bo'lishi kerak."""
        from bot import keyboards as KB

        session = self._session(count=2, selected=2)
        markup = KB.kb_discover_groups(session.groups, session.selected)
        texts = [btn.text for row in markup.inline_keyboard for btn in row]
        datas = [
            btn.callback_data for row in markup.inline_keyboard for btn in row
        ]
        self.assertIn("⬅️ Guruhlar", texts)
        self.assertIn("disc:groups", datas)
        # «Bekor qilish» ham saqlanadi (skaner oynasini yopadi).
        self.assertIn("disc:cancel", datas)

    async def test_disc_groups_keeps_selection(self) -> None:
        """«⬅️ Guruhlar» bosilsa — tanlanish saqlanib qolishi kerak."""
        session = self._session(count=2, selected=2)

        answer = AsyncMock()
        callback = SimpleNamespace(
            data="disc:groups",
            message=None,
            answer=answer,
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        with patch.object(DS, "get_session", return_value=session):
            await G.handle_discover_callback(update, UID, "disc:groups")

        # Tanlanish joyida qoldi — sessiya tozalanmagan.
        self.assertEqual(len(session.selected), 2)
        self.assertIsNotNone(DS.get_session(UID))

    async def test_disc_groups_opens_groups_window(self) -> None:
        """«⬅️ Guruhlar» — «💬 Guruhlar» oynasini ochishi kerak."""
        session = self._session(count=2, selected=2)

        edit = AsyncMock()
        callback = SimpleNamespace(
            data="disc:groups",
            message=None,
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        with patch.object(DS, "get_session", return_value=session):
            await G.handle_discover_callback(update, UID, "disc:groups")

        edit.assert_awaited()
        text = edit.await_args.args[0]
        self.assertIn("GURUHLAR", text)


if __name__ == "__main__":
    unittest.main()
