"""🧭 Soddalashtirilgan foydalanuvchi menyusi.

Qamlov:
- asosiy menyuda faqat kerakli tugmalar bor (Start/Stop, qidiruv, guruhlar,
  post qo'shish/o'chirish, interval, referal);
- ``📈 Hisobot`` / ``📊 Status`` / ``📦 Paket`` butunlay olib tashlangan;
- ``⏱ Interval`` oynasi umumiy yoki bitta guruh uchun tanlash;
- ``💬 Guruhlar`` oynasi havolalar + faqat o'chirish tugmalari;
- login ekranida jamoa tugmalari yo'q.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from bot import keyboards as KB
from bot import menu as M
from bot import my_groups as MG
from bot import texts as T
from core import database as db

UID = 555000111
ADMIN_UID = 999000222


def _reply_texts(markup) -> list[str]:
    return [b.text for row in markup.keyboard for b in row]


def _inline_buttons(markup) -> list:
    return [b for row in markup.inline_keyboard for b in row]


class SimplifiedMenuTests(unittest.IsolatedAsyncioTestCase):
    """Menyu tuzilmasi va yangi oynalar."""

    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name) / "test.sqlite3"
        db._write_lock = __import__("asyncio").Lock()
        await db.init_db()
        await db.upsert_user(UID, name="Oddiy", is_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self._old_db
        self._tmp.cleanup()

    # ── Menyu tuzilmasi ───────────────────────────────────────────────

    async def test_menu_contains_only_required_buttons(self) -> None:
        """Asosiy menyuda faqat kerakli tugmalar bor."""
        texts = _reply_texts(KB.kb_main())

        for button in (
            T.BTN_START,
            T.BTN_STOP,
            T.BTN_FIND_GROUPS,
            T.BTN_GROUPS,
            T.BTN_ADD_POST,
            T.BTN_DEL_POST,
            T.BTN_INTERVAL,
            T.BTN_REFERRAL,
        ):
            self.assertIn(button, texts)

    async def test_menu_has_no_report_status_or_plan(self) -> None:
        """Hisobot/Status/Paket butunlay olib tashlangan."""
        texts = _reply_texts(KB.kb_main())
        for button in (T.BTN_REPORT, T.BTN_PLAN, T.BTN_STATUS):
            self.assertNotIn(button, texts)

    async def test_menu_has_no_legacy_interval_buttons(self) -> None:
        """Eski interval tugmalari bitta «⏱ Interval» ga birlashtirilgan."""
        texts = _reply_texts(KB.kb_main())
        self.assertNotIn(T.BTN_GROUP_INTERVAL, texts)
        self.assertNotIn(T.BTN_TIMER, texts)
        self.assertIn(T.BTN_INTERVAL, texts)

    async def test_start_and_stop_are_separate_buttons(self) -> None:
        """Start va Stop — doimiy, alohida tugmalar (holat yorlig'isiz)."""
        stopped = _reply_texts(KB.kb_main(running=False))
        running = _reply_texts(KB.kb_main(running=True))

        self.assertIn(T.BTN_START, stopped)
        self.assertIn(T.BTN_STOP, stopped)
        # Holat yorlig'i yo'q — ikkalasi ham doimiy bir xil.
        self.assertEqual(stopped, running)
        self.assertNotIn(f"{T.BTN_START} (🔴 OFF)", stopped)
        self.assertNotIn(f"{T.BTN_STOP} (🟢 ON)", running)

    async def test_login_keyboard_has_only_login_button(self) -> None:
        """Kirish ekranida jamoa tugmalari yo'q."""
        texts = _reply_texts(KB.kb_login())
        self.assertEqual(texts, [T.BTN_LOGIN])
        self.assertNotIn(T.BTN_TEAM_ADMIN, texts)
        self.assertNotIn(T.BTN_TEAM_PICK, texts)

    async def test_plain_user_menu_has_no_team_buttons(self) -> None:
        """Jamoasiz foydalanuvchida jamoa tugmalari ko'rinmaydi."""
        markup = await KB.kb_main_for(UID)
        texts = _reply_texts(markup)
        self.assertNotIn(T.BTN_TEAM_MENU, texts)
        self.assertNotIn(T.BTN_TEAM_ADMIN, texts)
        self.assertNotIn(T.BTN_TEAM_PICK, texts)

    async def test_team_member_menu_has_team_menu_button(self) -> None:
        """Jamoa a'zosida «👥 Jamoam» bor, boshqa jamoa tugmalari yo'q."""
        team = await db.create_team("Jamoa", ADMIN_UID, max_users=5)
        await db.upsert_user(
            UID, name="A'zo", team_id=int(team["id"]), owner_admin_uid=ADMIN_UID
        )
        texts = _reply_texts(await KB.kb_main_for(UID))
        self.assertIn(T.BTN_TEAM_MENU, texts)
        self.assertNotIn(T.BTN_TEAM_ADMIN, texts)
        self.assertNotIn(T.BTN_TEAM_PICK, texts)

    # ── ⏱ Interval oynasi ────────────────────────────────────────────

    async def test_interval_choice_has_two_options(self) -> None:
        """Interval oynasida ikki variant bor."""
        buttons = _inline_buttons(KB.kb_interval_choice())
        datas = [b.callback_data for b in buttons]
        labels = [b.text for b in buttons]

        self.assertIn("int:global", datas)
        self.assertIn("int:one", datas)
        self.assertIn("🌐 Barcha guruhlar uchun", labels)
        self.assertIn("⏱ Bitta guruh uchun", labels)

    async def test_interval_button_opens_choice_window(self) -> None:
        """«⏱ Interval» tugmasi ikki variantli oynani ochadi."""
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        )
        handled = await M.route_menu_button(update, T.BTN_INTERVAL)
        self.assertTrue(handled)
        message.reply_text.assert_awaited_once()
        markup = message.reply_text.await_args.kwargs["reply_markup"]
        self.assertIn("int:global", [b.callback_data for b in _inline_buttons(markup)])

    async def test_legacy_timer_button_opens_interval_choice(self) -> None:
        """Eski «⏱ Posting oralig'i» ham interval oynasiga boradi."""
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        )
        handled = await M.route_menu_button(update, T.BTN_TIMER)
        self.assertTrue(handled)
        markup = message.reply_text.await_args.kwargs["reply_markup"]
        self.assertIn("int:one", [b.callback_data for b in _inline_buttons(markup)])

    # ── 💬 Guruhlar oynasi ────────────────────────────────────────────

    async def test_groups_window_lists_only_delete_buttons(self) -> None:
        """Guruhlar oynasida faqat o'chirish tugmalari bor."""
        await db.add_chat(UID, "@taxi_tashkent")
        await db.add_chat(UID, "@avtoelon_uz")

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        )
        await MG.show_my_groups(update, UID)

        markup = message.reply_text.await_args.kwargs["reply_markup"]
        datas = [b.callback_data for b in _inline_buttons(markup)]
        labels = [b.text for b in _inline_buttons(markup)]

        # Faqat o'chirish va orqaga — interval tugmasi va takror
        # qidiruv tugmasi yo'q (skaner asosiy menyuda).
        self.assertNotIn("mg:find", datas)
        self.assertFalse(any(d.startswith("mg:gint:") for d in datas))
        self.assertNotIn("mg:global", datas)
        # O'chirish tugmalari guruh nomi bilan.
        self.assertTrue(any("🗑" in label and "@taxi_tashkent" in label for label in labels))

    async def test_groups_window_shows_numbered_links(self) -> None:
        """Guruh havolalari ro'yxatda raqam bilan chiqadi."""
        await db.add_chat(UID, "@taxi_tashkent")
        await db.add_chat(UID, "@avtoelon_uz")

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        )
        await MG.show_my_groups(update, UID)

        text = message.reply_text.await_args.args[0]
        self.assertIn("🔗 Guruh havolalari", text)
        # Telegram HTML: "_" italic belgisi — escape qilingan bo'lishi kerak.
        self.assertIn(r"https://t.me/taxi\_tashkent", text)
        self.assertIn(r"https://t.me/avtoelon\_uz", text)

    async def test_public_link_helper(self) -> None:
        """Ochiq havola yordamchisi to'g'ri ishlaydi."""
        self.assertEqual(MG.public_link("@g1"), "https://t.me/g1")
        self.assertEqual(MG.public_link("https://t.me/g1"), "https://t.me/g1")
        # Yopiq guruhda havola yo'q.
        self.assertEqual(MG.public_link("-1001234567890"), "")
        self.assertEqual(MG.public_link(""), "")

    async def test_groups_window_keeps_delete_button_after_interval_move(self) -> None:
        """Interval oynasiga ko'chirilgandan keyin ham o'chirish ishlaydi."""
        await db.add_chat(UID, "@g1")
        await db.add_chat(UID, "@g2")

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            message=message,
        )
        await MG.show_my_groups(update, UID)

        markup = message.reply_text.await_args.kwargs["reply_markup"]
        dels = [
            b.callback_data
            for b in _inline_buttons(markup)
            if (b.callback_data or "").startswith("mg:del:")
        ]
        self.assertEqual(len(dels), 2)


if __name__ == "__main__":
    unittest.main()
