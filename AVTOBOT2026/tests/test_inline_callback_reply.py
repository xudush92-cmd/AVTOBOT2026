"""
Inline callback tugmalari — ``update.message`` None bo'lganda xato bermasligi.

Telegram'da inline tugma bosilganda ``update.message`` = ``None`` bo'ladi.
Shu sabab ``update.message.reply_text(...)`` chaqirilsa ``AttributeError``
chiqadi va foydalanuvchiga «Xatolik yuz berdi» xabari ko'rinadi.

Real xato (server logida):
    data='adm:addteamadmin'
    AttributeError: 'NoneType' object has no attribute 'reply_text'
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from core import database as db
from core.utils import reply_text_safe


def make_inline_update() -> SimpleNamespace:
    """Inline tugma bosilgandek update (update.message = None)."""
    query_message = SimpleNamespace(
        reply_text=AsyncMock(),
        chat_id=991460501,
        message_id=1,
    )
    query = SimpleNamespace(
        message=query_message,
        data="adm:addteamadmin",
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=query,
        message=None,
        effective_user=SimpleNamespace(id=991460501),
    )


def make_message_update() -> SimpleNamespace:
    """Oddiy matn xabari kelgandek update."""
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(
        callback_query=None,
        message=message,
        effective_user=SimpleNamespace(id=991460501),
    )


class ReplyTextSafeTests(unittest.IsolatedAsyncioTestCase):
    """``reply_text_safe`` — inline va matn xabarida ishlashi."""

    async def test_inline_update_uses_callback_message(self) -> None:
        update = make_inline_update()
        ok = await reply_text_safe(update, "Salom", reply_markup=None)
        self.assertTrue(ok)
        update.callback_query.message.reply_text.assert_awaited_once()
        self.assertEqual(
            update.callback_query.message.reply_text.await_args.args[0], "Salom"
        )

    async def test_message_update_uses_message(self) -> None:
        update = make_message_update()
        ok = await reply_text_safe(update, "Salom")
        self.assertTrue(ok)
        update.message.reply_text.assert_awaited_once()

    async def test_no_message_returns_false(self) -> None:
        update = SimpleNamespace(callback_query=None, message=None)
        self.assertFalse(await reply_text_safe(update, "Salom"))


class InlineCallbackRegressionTests(unittest.IsolatedAsyncioTestCase):
    """Super admin va jamoa admini inline tugmalari — xatosiz ishlashi."""

    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        await db.init_db()
        await db.upsert_user(
            991460501, name="Super", is_admin=1, is_team_admin=0, team_id=None
        )

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        self.temp.cleanup()

    async def test_add_team_admin_button_works_from_inline(self) -> None:
        """«➕ Admin qo'shish» inline tugmasi xato bermasligi kerak."""
        from admin import admin_panel

        update = make_inline_update()
        # SUPER_ADMIN boshqa testlar bilan bo'lishishi mumkin — lokal o'rnak.
        with patch.object(admin_panel, "SUPER_ADMIN", 991460501):
            await admin_panel.handle_admin_callback(
                update, 991460501, "adm:addteamadmin"
            )

        # Xabar yuborilgan bo'lishi kerak (callback message orqali).
        update.callback_query.message.reply_text.assert_awaited_once()
        text = update.callback_query.message.reply_text.await_args.args[0]
        self.assertIn("+998", text)

        # Holat ham saqlangan bo'lishi kerak.
        from bot.login import user_states

        self.assertEqual(
            user_states.get(991460501, {}).get("step"), "super_add_team_admin"
        )
        user_states.pop(991460501, None)

    async def test_team_admin_panel_works_from_inline(self) -> None:
        """Jamoa admini paneli inline tugmadan ochilganda xato bermasligi."""
        from bot import teams

        update = make_inline_update()
        await teams.show_team_admin_panel(update, 991460501)
        update.callback_query.message.reply_text.assert_awaited_once()

    async def test_begin_add_friend_works_from_inline(self) -> None:
        """«Do'st qo'shish» inline tugmasi xato bermasligi."""
        from bot import teams

        update = make_inline_update()
        await teams.begin_add_friend(update, 991460501)
        # Jamoa yo'q bo'lsa ham xato bermasligi kerak.
        update.callback_query.message.reply_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
