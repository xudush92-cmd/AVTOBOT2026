"""
Inline callback xatolari — ``gint:`` / ``mg:`` / ``gchk:`` oynalari.

Ikki xato live logda ko'rildi (UID ``6169018469``):

1. ``NoneType' object has no attribute 'reply_text'`` —
   inline kontekstda ``update.message`` = ``None``. ``update.message.reply_text``
   chaqirilsa layt sindiriladi.

2. ``BadRequest: Message is not modified`` —
   Telegram yangi matn va klaviatura avvalgisi bilan bir xil bo'lsa
   xato beradi. Bu normal holat (foydalanuvchi bir xil tugmani ikki marta
   bosadi), lekin kod uni xato deb hisoblar edi.

Ushbu fayl ikkala holatni ham qaytarib beradi:

- ``core.utils.edit_text_safe`` — "not modified" ni jim qoldiradi,
  boshqa xatolarni logga yozadi va oqimni buzmaydi;
- ``core.utils.reply_text_safe`` — inline kontekstda ham ishlaydi
  (``update.message`` None bo'lsa ``callback_query.message`` ishlatiladi);
- ``bot.timer`` / ``bot.my_groups`` / ``bot.groups`` — ``gint:`` va ``mg:``
  handler'larida xavfsiz yordamchilarni ishlatadi.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from core.utils import edit_text_safe, reply_text_safe

UID = 6169018469


def make_inline_update(data: str = "gint:list:0") -> SimpleNamespace:
    """Inline tugma bosilgandek update (``update.message`` = None)."""
    query_message = SimpleNamespace(
        reply_text=AsyncMock(),
        chat_id=UID,
        message_id=1,
    )
    query = SimpleNamespace(
        message=query_message,
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    return SimpleNamespace(
        callback_query=query,
        message=None,
        effective_user=SimpleNamespace(id=UID),
    )


class EditTextSafeTests(unittest.IsolatedAsyncioTestCase):
    """``edit_text_safe`` — "Message is not modified" ni yutib oladi."""

    async def test_successful_edit_returns_true(self) -> None:
        query = SimpleNamespace(edit_message_text=AsyncMock())
        ok = await edit_text_safe(query, "Matn", reply_markup=None)
        self.assertTrue(ok)
        query.edit_message_text.assert_awaited_once()

    async def test_none_query_returns_false(self) -> None:
        self.assertFalse(await edit_text_safe(None, "Matn"))

    async def test_message_not_modified_is_benign(self) -> None:
        """Telegram 'Message is not modified' — muvaffaqiyat deb hisoblanadi."""
        from telegram.error import BadRequest

        query = SimpleNamespace(
            edit_message_text=AsyncMock(
                side_effect=BadRequest("Message is not modified")
            )
        )
        ok = await edit_text_safe(query, "Matn")
        self.assertTrue(ok)
        query.edit_message_text.assert_awaited_once()

    async def test_message_not_modified_variants(self) -> None:
        """Telegram xato matni turlicha bo'lishi mumkin."""
        from telegram.error import BadRequest

        for message in (
            "Message is not modified",
            "MESSAGE_IS_NOT_MODIFIED",
            "Bad Request: MESSAGE_IS_NOT_MODIFIED",
        ):
            query = SimpleNamespace(
                edit_message_text=AsyncMock(side_effect=BadRequest(message))
            )
            with self.subTest(message=message):
                self.assertTrue(await edit_text_safe(query, "Matn"))

    async def test_other_error_is_logged_and_swallowed(self) -> None:
        """Boshqa xato — logga yoziladi, lekin oqim buzilmaydi."""
        from telegram.error import BadRequest

        query = SimpleNamespace(
            edit_message_text=AsyncMock(
                side_effect=BadRequest("chat not found")
            )
        )
        with patch("core.utils.log") as fake_log:
            ok = await edit_text_safe(query, "Matn")
        self.assertFalse(ok)
        fake_log.assert_called()

    async def test_generic_exception_is_swallowed(self) -> None:
        query = SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=RuntimeError("boom"))
        )
        with patch("core.utils.log"):
            self.assertFalse(await edit_text_safe(query, "Matn"))


class ReplyTextSafeInlineTests(unittest.IsolatedAsyncioTestCase):
    """``reply_text_safe`` — inline kontekstda xabar yubora oladi."""

    async def test_inline_update_uses_callback_message(self) -> None:
        update = make_inline_update()
        ok = await reply_text_safe(update, "Salom")
        self.assertTrue(ok)
        update.callback_query.message.reply_text.assert_awaited_once()

    async def test_in_place_edit_survives_not_modified(self) -> None:
        """``in_place=True`` — 'not modified' xatosi oqimni buzmaydi."""
        from telegram.error import BadRequest

        update = make_inline_update()
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )
        ok = await reply_text_safe(update, "Salom", in_place=True)
        self.assertTrue(ok)


class GroupIntervalCallbackTests(unittest.IsolatedAsyncioTestCase):
    """``gint:`` callback'lari — inline kontekstda xatosiz ishlashi."""

    async def test_gint_list_without_message(self) -> None:
        """``gint:list`` — ``update.message`` None bo'lsa ham ishlaydi."""
        from bot import timer

        update = make_inline_update("gint:list:0")

        async def fake_records(_uid):
            return [{"id": 1, "value": "-100123", "title": "Test Guruh"}]

        async def fake_interval(_uid):
            return 10

        with (
            patch.object(timer.db, "get_chat_records", fake_records),
            patch.object(timer.db, "get_interval", fake_interval),
        ):
            await timer.handle_group_interval_callback(update, UID, "gint:list:0")

        update.callback_query.edit_message_text.assert_awaited()

    async def test_gint_manual_without_message(self) -> None:
        """``gint:manual`` — ``q.message.reply_text`` ishlatilmaydi."""
        from bot import timer

        update = make_inline_update("gint:manual:1")

        async def fake_record(_uid, _gid):
            return {"id": 1, "value": "-100123", "title": "Test Guruh"}

        with patch.object(timer.db, "get_chat_record", fake_record):
            await timer.handle_group_interval_callback(
                update, UID, "gint:manual:1"
            )

        # Xabar inline kontekstda yuborildi (callback_query.message orqali).
        update.callback_query.message.reply_text.assert_awaited()

    async def test_gint_reset_not_modified_is_safe(self) -> None:
        """``gint:reset`` — 'Message is not modified' laytni sindirmaydi."""
        from telegram.error import BadRequest

        from bot import timer

        update = make_inline_update("gint:reset:1")
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )

        async def fake_record(_uid, _gid):
            return {"id": 1, "value": "-100123", "title": "Test Guruh"}

        async def fake_interval(_uid):
            return 10

        async def fake_set(_uid, _gid, _value):
            return True

        with (
            patch.object(timer.db, "get_chat_record", fake_record),
            patch.object(timer.db, "get_interval", fake_interval),
            patch.object(timer.db, "set_chat_interval", fake_set),
        ):
            await timer.handle_group_interval_callback(
                update, UID, "gint:reset:1"
            )

    async def test_gint_back_edits_in_place(self) -> None:
        """``gint:back`` — xabar tahrlanadi, yangisi yuborilmaydi."""
        from bot import timer

        update = make_inline_update("gint:back")

        async def fake_window(_uid, note="", page=0):
            return "Matn", None

        with patch(
            "bot.my_groups.build_groups_window", fake_window
        ):
            await timer.handle_group_interval_callback(update, UID, "gint:back")

        update.callback_query.edit_message_text.assert_awaited()
        update.callback_query.message.reply_text.assert_not_awaited()


class MyGroupsCallbackTests(unittest.IsolatedAsyncioTestCase):
    """``mg:`` callback'lari — inline kontekstda xatosiz ishlashi."""

    async def test_mg_manual_without_message(self) -> None:
        """``mg:manual`` — ``update.message`` None bo'lsa ham ishlaydi."""
        from bot import my_groups

        update = make_inline_update("mg:manual:1")

        async def fake_record(_uid, _gid):
            return {"id": 1, "value": "-100123", "title": "Test Guruh"}

        with patch.object(my_groups.db, "get_chat_record", fake_record):
            await my_groups.handle_my_groups_callback(
                update, UID, "mg:manual:1"
            )

        update.callback_query.message.reply_text.assert_awaited()

    async def test_render_groups_inline_without_message(self) -> None:
        """``render_groups_inline`` — inline kontekstda xatosiz."""
        from bot import my_groups

        update = make_inline_update("mg:open")

        async def fake_window(_uid, note="", page=0):
            return "Matn", None

        with patch("bot.my_groups.build_groups_window", fake_window):
            await my_groups.render_groups_inline(update, UID)

        update.callback_query.message.reply_text.assert_awaited()

    async def test_show_group_interval_not_modified_is_safe(self) -> None:
        """``show_group_interval`` — 'not modified' laytni sindirmaydi."""
        from telegram.error import BadRequest

        from bot import my_groups

        update = make_inline_update("mg:interval:1")
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )

        async def fake_record(_uid, _gid):
            return {"id": 1, "value": "-100123", "title": "Test Guruh"}

        async def fake_interval(_uid):
            return 10

        with (
            patch.object(my_groups.db, "get_chat_record", fake_record),
            patch.object(my_groups.db, "get_interval", fake_interval),
        ):
            await my_groups.show_group_interval(update, UID, 1)


class GroupCheckCallbackTests(unittest.IsolatedAsyncioTestCase):
    """``gchk:`` callback'lari — inline kontekstda xatosiz ishlashi."""

    async def test_gchk_page_not_modified_is_safe(self) -> None:
        """``gchk:page`` — 'not modified' laytni sindirmaydi."""
        from telegram.error import BadRequest

        from bot import groups

        update = make_inline_update("gchk:page:0")
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )

        async def fake_records(_uid):
            return [{"id": 1, "value": "-100123", "title": "Test Guruh"}]

        with patch.object(groups.db, "get_chat_records", fake_records):
            await groups.handle_group_check_callback(
                update, UID, "gchk:page:0"
            )


if __name__ == "__main__":
    unittest.main()
