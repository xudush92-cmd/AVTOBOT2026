"""💬 Foydalanuvchining o'z guruhlarini boshqarish oynasi.

Qamlov:
- asosiy menyuda ``💬 Guruhlar`` va ``⏱ Interval`` tugmalari bor;
- ``💬 Guruhlar`` oynasi ro'yxat + **guruh havolalari** + o'chirish;
- ``⏱ Interval`` oynasi umumiy yoki bitta guruh uchun tanlash;
- alohida interval o'rnatiladi va umumiyga qaytariladi;
- qo'lda kiritish ishlaydi;
- super admin bu oynani ishlatmaydi (u ``uc:`` orqali boshqaradi);
- foydalanuvchi **faqat o'z** guruhlarini boshqaradi (izolyatsiya).
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

from cryptography.fernet import Fernet

from bot import keyboards as KB
from bot import menu as M
from bot import my_groups as MG
from bot import texts as T
from core import database as db
from core import session_crypto

UID = 3501
OTHER_UID = 3502
SUPER_ADMIN = 123456789


def _buttons(markup) -> list:
    """Inline klaviaturadagi barcha tugmalar."""
    return [btn for row in markup.inline_keyboard for btn in row]


def _reply_texts(markup) -> list:
    """Reply klaviaturadagi barcha tugmalar."""
    return [btn.text for row in markup.keyboard for btn in row]


class MyGroupsScreenTests(unittest.IsolatedAsyncioTestCase):
    """O'z guruhlarini boshqarish oynasi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")
        await db.upsert_user(OTHER_UID, name="Ali", is_admin=1, session="SESS2")

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _update(self, uid: int = UID):
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=status))
        return (
            SimpleNamespace(
                effective_user=SimpleNamespace(id=uid),
                message=message,
            ),
            status,
        )

    def _callback(self, data: str):
        q = SimpleNamespace(
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
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

    # ── Menyu ──────────────────────────────────────────────────────────

    async def test_main_menu_has_groups_and_interval_buttons(self) -> None:
        """Asosiy menyuda ikkala tugma ham bo'lishi kerak."""
        texts = _reply_texts(KB.kb_main())
        self.assertIn(T.BTN_GROUPS, texts)
        self.assertIn(T.BTN_INTERVAL, texts)
        # Eski tugmalar olib tashlandi (ikki xil oyna bo'lmasligi uchun).
        self.assertNotIn(T.BTN_DEL_GROUP, texts)
        self.assertNotIn(T.BTN_GROUP_INTERVAL, texts)
        self.assertNotIn(T.BTN_TIMER, texts)
        self.assertNotIn(T.BTN_REPORT, texts)

    async def test_groups_button_routes_to_my_groups_screen(self) -> None:
        """💬 Guruhlar tugmasi o'z guruhlar oynasini ochadi."""
        update, _status = self._update()
        with patch.object(MG, "show_my_groups", new=AsyncMock()) as spy:
            handled = await M.route_menu_button(update, T.BTN_GROUPS)
        self.assertTrue(handled)
        spy.assert_awaited_once()

    async def test_interval_button_routes_to_interval_choice(self) -> None:
        """⏱ Interval tugmasi umumiy/individual tanlash oynasini ochadi."""
        update, _status = self._update()
        with patch.object(M, "show_interval_choice", new=AsyncMock()) as spy:
            handled = await M.route_menu_button(update, T.BTN_INTERVAL)
        self.assertTrue(handled)
        spy.assert_awaited_once()

    async def test_group_interval_button_routes_to_interval_choice(self) -> None:
        """Eski ⏱ Guruh intervali tugmasi ham interval oynasiga yo'naltiradi."""
        update, _status = self._update()
        with patch.object(M, "show_interval_choice", new=AsyncMock()) as spy:
            handled = await M.route_menu_button(update, T.BTN_GROUP_INTERVAL)
        self.assertTrue(handled)
        spy.assert_awaited_once()

    # ── Ro'yxat oynasi ────────────────────────────────────────────────

    async def test_empty_groups_shows_hint(self) -> None:
        """Guruh yo'q bo'lsa — qidiruvga yo'naltiriladi."""
        update, _status = self._update()
        await MG.show_my_groups(update, UID)
        text = update.message.reply_text.await_args.args[0]
        self.assertIn("GURUHLAR", text)
        self.assertIn("🔍 Guruhlarni topish", text)

    async def test_groups_list_shows_public_links(self) -> None:
        """Oyna matnida guruh havolalari raqam bilan ko'rsatiladi."""
        await db.add_chat(UID, "@taxi_tashkent")
        await db.add_chat(UID, "@avtoelon_uz")

        update, _status = self._update()
        await MG.show_my_groups(update, UID)

        text = update.message.reply_text.await_args.args[0]
        self.assertIn("🔗 Guruh havolalari", text)
        # Telegram HTML: "_" italic belgisi — escape qilingan bo'lishi kerak.
        self.assertIn(r"1. https://t.me/taxi\_tashkent", text)
        self.assertIn(r"2. https://t.me/avtoelon\_uz", text)

    async def test_groups_list_skips_link_for_closed_group(self) -> None:
        """Yopiq guruhda ochiq havola yo'q — u ro'yxatda chiqmaydi."""
        await db.add_chat(UID, "@taxi_tashkent")
        await db.add_chat(UID, "-1001234567890")

        update, _status = self._update()
        await MG.show_my_groups(update, UID)

        text = update.message.reply_text.await_args.args[0]
        self.assertIn(r"1. https://t.me/taxi\_tashkent", text)
        self.assertNotIn("-1001234567890", text)

    async def test_groups_list_has_no_find_button(self) -> None:
        """Ro'yxatda takror qidiruv tugmasi yo'q; interval tugmasi ham yo'q.

        Skaner tugmasi faqat asosiy menyuda — bir xil amal ikki joyda
        bo'lmasligi kerak.
        """
        await db.add_chat(UID, "@g1")
        update, _status = self._update()
        await MG.show_my_groups(update, UID)

        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        datas = [btn.callback_data for btn in _buttons(markup)]
        self.assertNotIn("mg:find", datas)
        self.assertNotIn("mg:global", datas)
        self.assertFalse(any(d.startswith("mg:gint:") for d in datas))

    async def test_groups_list_has_delete_button_per_group(self) -> None:
        """Har guruh uchun faqat o'chirish tugmasi bor (nomi bilan)."""
        await db.add_chat(UID, "@g1")
        update, _status = self._update()
        await MG.show_my_groups(update, UID)

        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        buttons = _buttons(markup)
        datas = [btn.callback_data for btn in buttons]
        labels = [btn.text for btn in buttons]
        self.assertTrue(any(d.startswith("mg:del:") for d in datas))
        self.assertTrue(any(label.startswith("🗑") and "@g1" in label for label in labels))

    # ── Alohida interval ──────────────────────────────────────────────

    async def test_interval_button_opens_options(self) -> None:
        """⏱ tugmasi interval variantlarini ochadi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        cb_update, q = self._callback(f"mg:gint:{group_id}")
        await MG.handle_my_groups_callback(cb_update, UID, f"mg:gint:{group_id}")

        markup = q.edit_message_text.await_args.kwargs["reply_markup"]
        datas = [btn.callback_data for btn in _buttons(markup)]
        self.assertTrue(any(d.startswith("mg:set:") for d in datas))
        self.assertTrue(any("reset" in d for d in datas))

    async def test_set_interval_saves_value(self) -> None:
        """Alohida interval o'rnatiladi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        cb_update, _q = self._callback(f"mg:set:{group_id}:45")
        await MG.handle_my_groups_callback(
            cb_update, UID, f"mg:set:{group_id}:45"
        )

        record = await db.get_chat_record(UID, group_id)
        self.assertEqual(int(record["interval_min"]), 45)

    async def test_reset_interval_returns_to_general(self) -> None:
        """Umumiy intervalga qaytarish ishlaydi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]
        await db.set_chat_interval(UID, group_id, 45)

        cb_update, _q = self._callback(f"mg:reset:{group_id}")
        await MG.handle_my_groups_callback(cb_update, UID, f"mg:reset:{group_id}")

        record = await db.get_chat_record(UID, group_id)
        self.assertIsNone(record["interval_min"])

    async def test_invalid_interval_is_rejected(self) -> None:
        """Noto'g'ri interval saqlanmaydi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        cb_update, _q = self._callback(f"mg:set:{group_id}:1")
        await MG.handle_my_groups_callback(cb_update, UID, f"mg:set:{group_id}:1")

        record = await db.get_chat_record(UID, group_id)
        self.assertIsNone(record["interval_min"])

    # ── Qo'lda kiritish ───────────────────────────────────────────────

    async def test_manual_interval_saves_value(self) -> None:
        """Qo'lda kiritilgan interval saqlanadi."""
        from bot.login import user_states

        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        cb_update, _q = self._callback(f"mg:manual:{group_id}")
        await MG.handle_my_groups_callback(cb_update, UID, f"mg:manual:{group_id}")
        self.assertEqual(
            user_states.get(UID, {}).get("step"), MG.STEP_MANUAL_INTERVAL
        )

        update, _status = self._update()
        await MG.handle_manual_interval(update, UID, "60")

        record = await db.get_chat_record(UID, group_id)
        self.assertEqual(int(record["interval_min"]), 60)

    async def test_manual_interval_invalid_number(self) -> None:
        """Noto'g'ri son — xato xabari."""
        from bot.login import user_states

        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]
        user_states[UID] = {
            "step": MG.STEP_MANUAL_INTERVAL,
            "ts": 0,
            "group_id": group_id,
        }

        update, _status = self._update()
        await MG.handle_manual_interval(update, UID, "abc")

        record = await db.get_chat_record(UID, group_id)
        self.assertIsNone(record["interval_min"])

    # ── O'chirish ─────────────────────────────────────────────────────

    async def test_delete_removes_group(self) -> None:
        """Guruh o'chirish ishlaydi."""
        await db.add_chat(UID, "@g1")
        group_id = (await db.get_chat_records(UID))[0]["id"]

        cb_update, _q = self._callback(f"mg:del:{group_id}")
        await MG.handle_my_groups_callback(cb_update, UID, f"mg:del:{group_id}")

        self.assertEqual(await db.get_chat_records(UID), [])

    # ── Izolyatsiya ───────────────────────────────────────────────────

    async def test_cannot_touch_other_users_group(self) -> None:
        """Foydalanuvchi boshqaning guruhiga tegishi mumkin emas."""
        await db.add_chat(OTHER_UID, "@other")
        other_id = (await db.get_chat_records(OTHER_UID))[0]["id"]

        # Boshqaning guruh id'si bilan o'z oynasini ochsa — topilmaydi.
        cb_update, _q = self._callback(f"mg:gint:{other_id}")
        await MG.handle_my_groups_callback(cb_update, UID, f"mg:gint:{other_id}")

        # O'z guruhlari oynasi boshqaning guruhini ko'rsatmasligi kerak.
        update, _status = self._update()
        await MG.show_my_groups(update, UID)
        markup = update.message.reply_text.await_args.kwargs["reply_markup"]
        datas = [btn.callback_data for btn in _buttons(markup)]
        self.assertFalse(any(str(other_id) in d for d in datas))

    async def test_super_admin_does_not_use_this_screen(self) -> None:
        """Super admin o'z guruhlar oynasini ishlatmaydi."""
        update, _status = self._update(SUPER_ADMIN)
        await MG.show_my_groups(update, SUPER_ADMIN)
        text = update.message.reply_text.await_args.args[0]
        self.assertIn("Super admin", text)

    async def test_super_admin_cannot_use_mg_callbacks(self) -> None:
        """Super admin ``mg:`` callback orqali boshqa guruhga tegmaydi."""
        await db.add_chat(OTHER_UID, "@other")
        other_id = (await db.get_chat_records(OTHER_UID))[0]["id"]

        cb_update, _q = self._callback(f"mg:del:{other_id}")
        cb_update.effective_user = SimpleNamespace(id=SUPER_ADMIN)
        await MG.handle_my_groups_callback(
            cb_update, SUPER_ADMIN, f"mg:del:{other_id}"
        )

        # Boshqaning guruhi joyida qolishi kerak.
        self.assertEqual(len(await db.get_chat_records(OTHER_UID)), 1)

    async def test_mg_callbacks_require_active_session(self) -> None:
        """Sessiyasi yo'q foydalanuvchi ``mg:`` ishlat olmaydi."""
        await db.upsert_user(OTHER_UID, name="Ali", is_admin=1, session="")
        await db.add_chat(OTHER_UID, "@other")
        other_id = (await db.get_chat_records(OTHER_UID))[0]["id"]

        from bot import callbacks as CB

        cb_update, _q = self._callback(f"mg:del:{other_id}")
        cb_update.effective_user = SimpleNamespace(id=OTHER_UID)
        cb_update.callback_query.from_user = SimpleNamespace(id=OTHER_UID)
        with patch.object(CB, "application", new=SimpleNamespace(bot=None)):
            await CB.handle_callback(cb_update, SimpleNamespace())

        self.assertEqual(len(await db.get_chat_records(OTHER_UID)), 1)


if __name__ == "__main__":
    unittest.main()
