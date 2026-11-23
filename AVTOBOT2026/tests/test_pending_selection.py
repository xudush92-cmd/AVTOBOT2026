"""🎯 Tanlangan guruhlar yo'qolmasligi.

Muammo: foydalanuvchi skanerda guruhlarni ✅ belgilaydi, lekin
«Tanlanganlarni saqlash» tugmasini bosmaydi — oyna yopiladi. Natijada
tanlangan guruhlar **yo'qoladi** va foydalanuvchi «guruhlar yo'q» deb
o'ylaydi.

Tuzatish:
- «💬 Guruhlar» oynasida skanerdagi tanlanish ko'rinadi;
- «✅ Tanlanganlarni saqlash (N)» tugmasi chiqadi;
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
            if "Tanlanganlarni saqlash" in btn.text
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
            if "Tanlanganlarni saqlash" in btn.text
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
            if "Tanlanganlarni saqlash" in btn.text
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
            if "Tanlanganlarni saqlash" in btn.text
        ]
        self.assertEqual(buttons, [])


class ApplyFromGroupsWindowTests(_Base):
    async def test_mg_apply_adds_selected_groups(self) -> None:
        """«Guruhlar» oynasidagi tugma tanlangan guruhlarni qo'shishi kerak.

        Oqim ikki bosqichli: avval tasdiqlash oynasi, keyin saqlash.
        """
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
            # 1) Hali saqlanmadi — faqat tasdiqlash so'raldi.
            self.assertEqual(await db.get_chat_records(UID), [])
            # 2) Tasdiqlash — endi saqlanadi.
            await G.handle_discover_callback(update, UID, "disc:apply:yes")

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
            await G.handle_discover_callback(update, UID, "disc:apply:yes")

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


class ApplyConfirmationTests(_Base):
    """Ikki bosqichli oqim: tasdiqlash → saqlash."""

    async def test_first_click_asks_confirmation(self) -> None:
        """Birinchi bosilishda hech narsa saqlanmasligi kerak."""
        self._session(count=2, selected=2)

        edit = AsyncMock()
        callback = SimpleNamespace(
            data="disc:apply",
            message=None,
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        await G.handle_discover_callback(update, UID, "disc:apply")

        # Hali saqlanmagan.
        self.assertEqual(await db.get_chat_records(UID), [])
        # Tasdiqlash oynasi ochilgan.
        edit.assert_awaited()
        text = edit.await_args.args[0]
        self.assertIn("saqlash", text.lower())
        self.assertIn("Guruh 0", text)
        self.assertIn("Guruh 1", text)
        # Ha/Yo'q tugmalari bor.
        markup = edit.await_args.kwargs.get("reply_markup")
        datas = [
            btn.callback_data
            for row in markup.inline_keyboard
            for btn in row
        ]
        self.assertIn("disc:apply:yes", datas)
        self.assertIn("disc:apply:no", datas)

    async def test_confirmation_yes_saves_groups(self) -> None:
        """«✅ Ha, saqla» — guruhlar bazaga yoziladi."""
        self._session(count=2, selected=2)

        callback = SimpleNamespace(
            data="disc:apply:yes",
            message=SimpleNamespace(
                reply_text=AsyncMock(), delete_message=AsyncMock()
            ),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        await G.handle_discover_callback(update, UID, "disc:apply:yes")

        rows = await db.get_chat_records(UID)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sorted(r["value"] for r in rows), ["@g0", "@g1"])

    async def test_confirmation_no_does_not_save(self) -> None:
        """«❌ Yo'q, bekor qil» — guruhlar saqlanmaydi."""
        self._session(count=2, selected=2)

        callback = SimpleNamespace(
            data="disc:apply:no",
            message=SimpleNamespace(
                reply_text=AsyncMock(), delete_message=AsyncMock()
            ),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        await G.handle_discover_callback(update, UID, "disc:apply:no")

        self.assertEqual(await db.get_chat_records(UID), [])
        # Sessiya tozalandi — qayta tanlash kerak.
        self.assertIsNone(DS.get_session(UID))

    async def test_save_button_text_is_clear(self) -> None:
        """Tugma matni aniq bo'lishi kerak — «saqlash» deishi kerak."""
        from bot import keyboards as KB

        session = self._session(count=2, selected=2)
        markup = KB.kb_discover_groups(session.groups, session.selected)
        buttons = [
            btn
            for row in markup.inline_keyboard
            for btn in row
            if "saqlash" in btn.text
        ]
        self.assertEqual(len(buttons), 1)
        self.assertIn("💾", buttons[0].text)
        self.assertIn("(2)", buttons[0].text)

    async def test_groups_window_save_button_text(self) -> None:
        """«Guruhlar» oynasidagi tugma ham «saqlash» deishi kerak."""
        session = self._session(count=3, selected=2)

        with patch.object(DS, "get_session", return_value=session):
            _text, markup = await MG.build_groups_window(UID)

        buttons = [
            btn
            for row in markup.inline_keyboard
            for btn in row
            if "saqlash" in btn.text
        ]
        self.assertEqual(len(buttons), 1)
        self.assertIn("(2)", buttons[0].text)

    async def test_scanner_header_explains_last_button(self) -> None:
        """Skaner matni oxiridagi tugmani tushuntirishi kerak."""
        from bot import texts as T

        header = T.DISCOVER_PICK_HEADER.format(
            total=3, page=1, pages=1, selected=2
        )
        self.assertIn("saqlash", header.lower())
        self.assertIn("pastidagi", header.lower())


if __name__ == "__main__":
    unittest.main()
