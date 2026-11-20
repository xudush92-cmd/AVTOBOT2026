"""🧹 Eski foydalanuvchi menyularining tozalanishi.

Foydalanuvchi UI'si soddalashtirilgandan keyin alohida "Guruhlar" va
"Postlar" **ichki** menyulari olib tashlandi. Ularning o'rniga:

* ``💬 Guruhlar`` — yangi inline boshqaruv oynasi (havolalar + ``🗑 N.``);
* qolgan joylarda — asosiy menyu.

Qamlov:
- ``kb_groups_menu()`` / ``kb_posts_menu()`` kodda **yo'q**;
- eski tugmalar (``➕ Guruh qo'shish``, ``🔎 Guruhni tekshirish``,
  ``⏱ Guruh intervali``, ``✏️ Postni tahrirlash``, ``👁 Ko'rinishi``,
  ``🧪 Sinov yuborish``) foydalanuvchi ekranida **ko'rinmaydi**;
- ``/help`` matnida ``📈 Hisobot`` va ``video`` **yo'q**;
- ``gchk:back`` eski menyuga emas, **inline** oynaga qaytadi.
"""

from __future__ import annotations

import os
import sys
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

from bot import keyboards as KB  # noqa: E402
from bot import texts as T  # noqa: E402


class LegacyMenusRemovedTests(unittest.TestCase):
    """Eski ichki menyular butunlay olib tashlangan."""

    def test_legacy_menu_builders_are_gone(self) -> None:
        """``kb_groups_menu`` / ``kb_posts_menu`` kodda qolmasligi kerak."""
        self.assertFalse(
            hasattr(KB, "kb_groups_menu"),
            "eski 'Guruhlar' menyusi hali ham bor",
        )
        self.assertFalse(
            hasattr(KB, "kb_posts_menu"),
            "eski 'Postlar' menyusi hali ham bor",
        )

    def test_legacy_buttons_not_in_main_menu(self) -> None:
        """Eski tugmalar asosiy menyuda ko'rinmasligi kerak."""
        flat = [b.text for r in KB.kb_main().keyboard for b in r]
        for label in (
            T.BTN_ADD_GROUP,
            T.BTN_CHECK_GROUPS,
            T.BTN_GROUP_INTERVAL,
            T.BTN_POSTS,
            T.BTN_ACCOUNT,
            T.BTN_REPORT,
            T.BTN_STATUS,
            T.BTN_PLAN,
            T.BTN_TEAM_ADMIN,
            T.BTN_TEAM_PICK,
        ):
            self.assertNotIn(label, flat, f"{label} asosiy menyuda bo'lmasligi kerak")

    def test_legacy_buttons_not_in_login_menu(self) -> None:
        """Eski tugmalar login menyusida ham bo'lmasligi kerak."""
        flat = [b.text for r in KB.kb_login().keyboard for b in r]
        for label in (
            T.BTN_TEAM_ADMIN,
            T.BTN_TEAM_PICK,
            T.BTN_REPORT,
            T.BTN_STATUS,
        ):
            self.assertNotIn(label, flat, f"{label} login menyusida bo'lmasligi kerak")

    def test_help_text_has_no_report_nor_video(self) -> None:
        """``/help`` da olib tashlangan funksiyalar eslatilmasligi kerak."""
        self.assertNotIn("📈 Hisobot", T.HELP_TEXT)
        self.assertNotIn("video", T.HELP_TEXT.lower())

    def test_add_post_hint_has_no_video(self) -> None:
        """Post qo'shish ko'rsatmasi videoni eslatmasligi kerak."""
        self.assertNotIn("video", T.ASK_ADD_POST.lower())
        self.assertIn("rasm", T.ASK_ADD_POST.lower())

    def test_main_menu_is_minimal(self) -> None:
        """Asosiy menyu — sizning talabingizdagi 8 tugma."""
        rows = KB.kb_main().keyboard
        self.assertEqual(len(rows), 4, "asosiy menyu 4 qator bo'lishi kerak")
        flat = [b.text for r in rows for b in r]
        self.assertEqual(
            flat,
            [
                T.BTN_START,
                T.BTN_STOP,
                T.BTN_FIND_GROUPS,
                T.BTN_GROUPS,
                T.BTN_ADD_POST,
                T.BTN_DEL_POST,
                T.BTN_INTERVAL,
                T.BTN_REFERRAL,
            ],
        )

    def test_team_member_gets_team_button(self) -> None:
        """Jamoa a'zosida ``👥 Jamoam`` tugmasi qo'shiladi."""
        flat = [b.text for r in KB.kb_main(team_member=True).keyboard for b in r]
        self.assertIn(T.BTN_TEAM_MENU, flat)


class RenderGroupsInlineTests(unittest.IsolatedAsyncioTestCase):
    """``render_groups_inline`` yangi inline oynani chizadi."""

    async def test_inline_window_has_no_legacy_buttons(self) -> None:
        """Inline oynada eski tugmalar bo'lmasligi kerak."""
        groups = [
            {"id": 1, "value": "@taxi_tashkent"},
            {"id": 2, "value": "@avtoelon_uz"},
        ]
        markup = KB.kb_my_groups(groups, 0)
        flat = [b.text for row in markup.inline_keyboard for b in row]
        for label in (
            T.BTN_ADD_GROUP,
            T.BTN_CHECK_GROUPS,
            T.BTN_GROUP_INTERVAL,
        ):
            self.assertNotIn(label, flat, f"{label} inline oynada bo'lmasligi kerak")

    async def test_inline_window_has_numbered_delete_buttons(self) -> None:
        """Raqamlangan ``🗑 N. guruh`` tugmalari bo'lishi kerak."""
        groups = [
            {"id": 1, "value": "@taxi_tashkent"},
            {"id": 2, "value": "@avtoelon_uz"},
        ]
        markup = KB.kb_my_groups(groups, 0)
        flat = [b.text for row in markup.inline_keyboard for b in row]
        self.assertIn("🗑 1. @taxi_tashkent", flat)
        self.assertIn("🗑 2. @avtoelon_uz", flat)

    async def test_gchk_back_goes_to_inline_window(self) -> None:
        """``gchk:back`` eski menyuga emas, inline oynaga qaytadi."""
        from bot import groups as G

        q = SimpleNamespace(
            data="gchk:back",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=777),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

        with (
            patch.object(G.db, "get_chat_records", new=AsyncMock(return_value=[])),
        ):
            await G.handle_group_check_callback(update, 777, "gchk:back")

        # Inline oyna `edit_message_text` orqali chiziladi (eski menyu emas).
        q.edit_message_text.assert_awaited()
        args = q.edit_message_text.await_args
        self.assertIn("GURUHLAR", str(args.args[0]))
        markup = args.kwargs.get("reply_markup")
        self.assertIsNotNone(markup)
        flat = [b.text for row in markup.inline_keyboard for b in row]
        self.assertNotIn(T.BTN_CHECK_GROUPS, flat)


if __name__ == "__main__":
    unittest.main()
