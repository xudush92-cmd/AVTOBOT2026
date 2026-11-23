"""Super admin paneli — muddat +/- va «Orqaga» oynani yopadi.

Vazifalar:
1. Jamoa admini va oddiy admin uchun muddatni **ko'paytirish/kamaytirish**.
2. Admin panel oynalari «⬅️ Orqaga» bosilganda **yopiladi** (yangi menyu
   ochilmaydi).
3. Admin panel **minimal va aniq** — qisqa nomlar, statistika bir qatorda.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from admin import admin_actions as AA
from admin import admin_panel as AP
from bot import keyboards as KB
from core import database as db
from core.utils import calc_expires, shift_expires

ADMIN = 123456789
USER = 555000111


class ShiftExpiresTests(unittest.TestCase):
    """``shift_expires`` — muddatni +/- kun siljitish."""

    def test_plus_extends(self) -> None:
        base = calc_expires(30)
        plus = shift_expires(base, 30)
        diff = datetime.strptime(
            plus, "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(diff, timedelta(days=30))

    def test_minus_shortens(self) -> None:
        """``−30`` kun — muddat 30 kun qisqaradi."""
        base = calc_expires(60)
        minus = shift_expires(base, -30)
        diff = datetime.strptime(
            base, "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(minus, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(diff, timedelta(days=30))

    def test_none_becomes_dated(self) -> None:
        """Cheksiz muddatga + berilsa — bugundan keyingi sana."""
        result = shift_expires(None, 7)
        self.assertTrue(result)
        parsed = datetime.strptime(result, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        self.assertGreater(parsed, datetime.now(timezone.utc))

    def test_expired_is_not_pushed_to_future(self) -> None:
        """O'tib ketgan muddat kamaytirilganda kelajakka surilmaydi."""
        past = (datetime.now(timezone.utc) - timedelta(days=10)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        result = shift_expires(past, -7)
        parsed = datetime.strptime(result, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        self.assertLessEqual(parsed, datetime.now(timezone.utc))


class _Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name) / "t.db"
        await db.init_db()
        await db.upsert_user(ADMIN, name="Super", is_admin=1)
        await db.upsert_user(USER, name="Vali", is_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self._old_db
        self._tmp.cleanup()


class TeamAdminTermTests(_Base):
    """Jamoa admini muddatini +/- qilish."""

    async def _make_team_admin(self) -> int:
        await db.upsert_user(USER, name="Vali", is_admin=1, is_team_admin=1)
        await db.set_admin_expires(USER, calc_expires(30))
        return USER

    async def test_card_has_shrink_button(self) -> None:
        """Kartada «kamaytirish» tugmasi bo'lishi kerak."""
        markup = KB.kb_team_admin_card(USER)
        labels = [b.text for row in markup.inline_keyboard for b in row]
        self.assertTrue(any("kamaytirish" in t.lower() for t in labels), labels)

    async def test_term_options_have_plus_and_minus(self) -> None:
        """Muddat oynasida ham +, ham − variantlari bo'lishi kerak."""
        markup = KB.kb_team_admin_term(USER, [1, 7, 30])
        callbacks = [
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data and b.callback_data.startswith("adm:teamsetterm:")
        ]
        self.assertIn(f"adm:teamsetterm:{USER}:7", callbacks)
        self.assertIn(f"adm:teamsetterm:{USER}:-7", callbacks)

    async def test_set_term_extends(self) -> None:
        """``+`` kun muddatni uzaytiradi."""
        await self._make_team_admin()
        before = await db.get_user(USER)
        base = before.get("admin_expires_at")

        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"adm:teamsetterm:{USER}:10",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AP.set_team_admin_term(update, USER, 10)

        after = await db.get_user(USER)
        diff = datetime.strptime(
            after["admin_expires_at"], "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(diff, timedelta(days=10))

    async def test_set_term_shortens(self) -> None:
        """``−`` kun muddatni kamaytiradi."""
        await self._make_team_admin()
        await db.set_admin_expires(USER, calc_expires(60))
        before = await db.get_user(USER)
        base = before.get("admin_expires_at")

        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"adm:teamsetterm:{USER}:-10",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AP.set_team_admin_term(update, USER, -10)

        after = await db.get_user(USER)
        diff = datetime.strptime(
            base, "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(after["admin_expires_at"], "%Y-%m-%d %H:%M:%S")
        self.assertEqual(diff, timedelta(days=10))


class UserExpireShiftTests(_Base):
    """Oddiy admin tarif muddati +/-."""

    async def test_options_have_plus_minus_buttons(self) -> None:
        markup = KB.kb_expire_options(USER)
        callbacks = [
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        ]
        self.assertIn(f"expadd:{USER}", callbacks)
        self.assertIn(f"expsub:{USER}", callbacks)

    async def test_shift_window_opens(self) -> None:
        """«Ko'paytirish» bosilganda oyna ochiladi."""
        await db.set_tariff_expires(USER, calc_expires(30))
        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"expadd:{USER}",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AA.handle_expire_shift(update, ADMIN, callback.data)

        edit.assert_awaited()
        text = edit.await_args.args[0]
        self.assertIn("Hozirgi muddat", text)

    async def test_plus_extends_tariff(self) -> None:
        await db.set_tariff_expires(USER, calc_expires(30))
        before = await db.get_user(USER)
        base = before.get("tariff_expires_at")

        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"exp:{USER}:plus:10",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AA.handle_expire(update, ADMIN, callback.data)

        after = await db.get_user(USER)
        diff = datetime.strptime(
            after["tariff_expires_at"], "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(base, "%Y-%m-%d %H:%M:%S")
        self.assertEqual(diff, timedelta(days=10))

    async def test_minus_shortens_tariff(self) -> None:
        await db.set_tariff_expires(USER, calc_expires(60))
        before = await db.get_user(USER)
        base = before.get("tariff_expires_at")

        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"exp:{USER}:minus:10",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AA.handle_expire(update, ADMIN, callback.data)

        after = await db.get_user(USER)
        diff = datetime.strptime(
            base, "%Y-%m-%d %H:%M:%S"
        ) - datetime.strptime(after["tariff_expires_at"], "%Y-%m-%d %H:%M:%S")
        self.assertEqual(diff, timedelta(days=10))


class AdminWindowCloseTests(_Base):
    """«Orqaga» bosilganda admin oynasi YOPILADI."""

    async def test_adm_back_deletes_message(self) -> None:
        """``adm:back`` — xabarni o'chiradi, panel ochiq qolmaydi."""
        delete = AsyncMock()
        edit = AsyncMock()
        callback = SimpleNamespace(
            data="adm:back",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=edit,
            delete_message=delete,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AP.handle_admin_callback(update, ADMIN, callback.data)

        delete.assert_awaited()
        edit.assert_not_awaited()

    async def test_team_admins_back_closes_and_reopens_list(self) -> None:
        """Jamoa adminlari ro'yxatiga qaytishda eski oyna yopiladi."""
        delete = AsyncMock()
        reply = AsyncMock()
        callback = SimpleNamespace(
            data="adm:teamadmins",
            message=SimpleNamespace(reply_text=reply),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            delete_message=delete,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AP.handle_admin_callback(update, ADMIN, callback.data)

        delete.assert_awaited()
        reply.assert_awaited()

    async def test_adm_back_shows_reopen_button(self) -> None:
        """Yopilgandan keyin panelni qayta ochish tugmasi ko'rsatiladi."""
        delete = AsyncMock()
        reply = AsyncMock()
        callback = SimpleNamespace(
            data="adm:back",
            message=SimpleNamespace(reply_text=reply),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            delete_message=delete,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AP.handle_admin_callback(update, ADMIN, callback.data)

        reply.assert_awaited()
        kwargs = reply.await_args.kwargs
        markup = kwargs.get("reply_markup")
        self.assertIsNotNone(markup)
        callbacks = {
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        }
        self.assertIn("adm:users", callbacks)

    async def test_close_falls_back_to_markup_removal(self) -> None:
        """Xabar o'chirib bo'lmasa — klaviatura olib tashlanadi."""

        async def _boom() -> None:
            raise RuntimeError("cannot delete")

        delete = AsyncMock(side_effect=_boom)
        edit_markup = AsyncMock()
        callback = SimpleNamespace(
            data="adm:back",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=edit_markup,
            delete_message=delete,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await AP.handle_admin_callback(update, ADMIN, callback.data)

        edit_markup.assert_awaited()


class AdminPanelMinimalTests(unittest.TestCase):
    """Panel — qisqa nomlar, statistika bir qatorda."""

    def test_panel_has_all_sections(self) -> None:
        markup = KB.kb_admin_panel()
        callbacks = {
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        }
        for expected in (
            "adm:adduser",
            "adm:users",
            "adm:pending",
            "adm:teamadmins",
            "adm:expired",
            "adm:stats",
            "adm:broadcast",
            "adm:blocked",
            "adm:db",
            "adm:system",
        ):
            self.assertIn(expected, callbacks)

    def test_panel_buttons_are_short(self) -> None:
        """Tugma nomlari qisqa bo'lishi kerak (64 belgi limitidan)."""
        markup = KB.kb_admin_panel()
        for row in markup.inline_keyboard:
            for button in row:
                self.assertLessEqual(len(button.text), 24, button.text)


if __name__ == "__main__":
    unittest.main()
