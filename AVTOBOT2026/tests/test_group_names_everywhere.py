"""Guruh **nomi** hamma foydalanuvchi ko'rinadigan oynalarda chiqishi kerak.

Asosiy muammo: PR #41 nomni faqat «💬 Guruhlar» oynasiga qo'shgan edi.
Interval tanlash, o'chirish va qo'shish oynalari to'g'ridan-to'g'ri
``value`` (internal ID) ni chiqarardi.

Asosiy sabab: ``db.get_chat_record()`` ning SELECT ro'yxatida ``title``
yo'q edi — faqat ``get_chat_records()`` da bor edi.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from bot import groups as G
from bot import keyboards as KB
from bot import my_groups as MG
from bot import texts as T
from bot import timer as Tm
from core import database as db

UID = 6169018469
TITLE = "КАНГЛИ ЯККА ТУРОНГИЛ МФЙ"
VALUE = "-1003119200089"


class _Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name) / "t.db"
        await db.init_db()
        await db.upsert_user(UID, name="Test", session="SESS")

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self._old_db
        self._tmp.cleanup()


class GroupLabelTests(_Base):
    def test_title_preferred(self) -> None:
        item = {"id": 1, "value": VALUE, "title": TITLE}
        self.assertEqual(MG.group_label(item), TITLE)

    def test_username_fallback(self) -> None:
        item = {"id": 1, "value": "@guruh99999999", "title": ""}
        self.assertEqual(MG.group_label(item), "@guruh99999999")

    def test_private_group_without_title_is_hidden(self) -> None:
        """Yopiq guruh ID'si ko'rsatilmaydi."""
        item = {"id": 1, "value": VALUE, "title": ""}
        self.assertEqual(MG.group_label(item), "Yopiq guruh")

    def test_title_equal_to_value_is_not_a_name(self) -> None:
        """``title`` maydoni ``value`` bilan bir xil bo'lsa — nom emas."""
        item = {"id": 1, "value": "@guruh99999999", "title": "@guruh99999999"}
        self.assertEqual(MG.group_label(item), "@guruh99999999")


class DatabaseTitleTests(_Base):
    async def test_get_chat_record_returns_title(self) -> None:
        """``get_chat_record()`` ``title`` ni qaytarishi kerak.

        Bu — asosiy sabab: bitta guruhni ko'rsatadigan oynalar shu
        funksiyadan ma'lumot oladi.
        """
        await db.add_chat(UID, VALUE, title=TITLE)
        rows = await db.get_chat_records(UID)
        record = await db.get_chat_record(UID, int(rows[0]["id"]))
        self.assertIsNotNone(record)
        assert record is not None
        self.assertEqual(record["title"], TITLE)


class IntervalPickerTests(_Base):
    async def test_picker_button_shows_title(self) -> None:
        """Interval tanlash tugmasi **nom** ko'rsatishi kerak (ID emas)."""
        await db.add_chat(UID, VALUE, title=TITLE)
        groups = await db.get_chat_records(UID)
        markup = KB.kb_group_interval_picker(groups, 6)
        button_text = markup.inline_keyboard[0][0].text
        self.assertIn(TITLE, button_text)
        self.assertNotIn(VALUE, button_text)

    async def test_picker_button_falls_back_to_value(self) -> None:
        """Nomi yo'q bo'lsa — username/ID ko'rsatiladi."""
        await db.add_chat(UID, "@guruh99999999")
        groups = await db.get_chat_records(UID)
        markup = KB.kb_group_interval_picker(groups, 6)
        button_text = markup.inline_keyboard[0][0].text
        self.assertIn("@guruh99999999", button_text)


class SingleGroupIntervalWindowTests(_Base):
    async def test_window_shows_title(self) -> None:
        """Bitta guruh intervali oynasida nom chiqishi kerak."""
        await db.add_chat(UID, VALUE, title=TITLE)
        rows = await db.get_chat_records(UID)
        group_id = int(rows[0]["id"])

        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"gint:select:{group_id}",
            message=None,
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        await Tm.handle_group_interval_callback(update, UID, callback.data)

        edit.assert_awaited()
        text = edit.await_args.args[0]
        self.assertIn(TITLE, text)
        self.assertNotIn(VALUE, text)

    async def test_manual_prompt_shows_title(self) -> None:
        """Qo'lda interval kiritish so'rogida nom chiqishi kerak."""
        await db.add_chat(UID, VALUE, title=TITLE)
        rows = await db.get_chat_records(UID)
        group_id = int(rows[0]["id"])

        edit = AsyncMock()
        reply = AsyncMock()
        callback = SimpleNamespace(
            data=f"gint:manual:{group_id}",
            message=SimpleNamespace(reply_text=reply),
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
            message=SimpleNamespace(reply_text=reply),
        )

        await Tm.handle_group_interval_callback(update, UID, callback.data)

        edit.assert_awaited()
        text = edit.await_args.args[0]
        self.assertIn(TITLE, text)
        self.assertNotIn(VALUE, text)


class ManagementWindowTests(_Base):
    async def test_my_groups_window_shows_title(self) -> None:
        """«💬 Guruhlar» oynasi nomni ko'rsatishi kerak."""
        await db.add_chat(UID, VALUE, title=TITLE)
        text, _markup = await MG.build_groups_window(UID)
        self.assertIn(TITLE, text)
        self.assertNotIn(VALUE, text)

    async def test_delete_notice_shows_title(self) -> None:
        """O'chirish xabari nomni ko'rsatishi kerak (ID emas)."""
        await db.add_chat(UID, VALUE, title=TITLE)
        groups = await db.get_chat_records(UID)
        group = groups[0]

        edit = AsyncMock()
        callback = SimpleNamespace(
            data=f"mg:del:{int(group['id'])}",
            message=None,
            answer=AsyncMock(),
            edit_message_text=edit,
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        with contextlib.suppress(Exception):
            await MG.handle_my_groups_callback(update, UID, callback.data)

        callback.answer.assert_awaited()
        answer_text = callback.answer.await_args.args[0]
        self.assertIn(TITLE, answer_text)
        self.assertNotIn(VALUE, answer_text)


class DeletionListTests(_Base):
    async def test_delete_text_shows_title(self) -> None:
        """O'chirish ro'yxatida nom chiqishi kerak."""
        await db.add_chat(UID, VALUE, title=TITLE)
        groups = await db.get_chat_records(UID)
        text = T.groups_delete_text(groups)
        self.assertIn(TITLE, text)
        self.assertNotIn(VALUE, text)


class ShowGroupsTests(_Base):
    async def test_show_groups_lists_title(self) -> None:
        """`groups.show_groups()` nomni chiqarishi kerak."""
        await db.add_chat(UID, VALUE, title=TITLE)

        sent: list[str] = []

        async def _reply(text, **kwargs):
            sent.append(text)

        message = SimpleNamespace(reply_text=AsyncMock(side_effect=_reply))
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        )

        with contextlib.suppress(Exception):
            await G.show_groups(update)

        joined = "\n".join(
            call.args[0]
            for call in message.reply_text.await_args_list
            if call.args
        )
        self.assertIn(TITLE, joined)
        self.assertNotIn(VALUE, joined)


if __name__ == "__main__":
    unittest.main()
