"""Compact user menus and selected-user admin controls."""

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

import main  # noqa: E402
from admin import admin_actions  # noqa: E402
from bot import texts as T  # noqa: E402
from bot.keyboards import (  # noqa: E402
    kb_admin_group_interval,
    kb_admin_groups,
    kb_admin_posts,
    kb_group_interval_options,
    kb_group_interval_picker,
    kb_db_panel,
    kb_expire_options,
    kb_main,
    kb_pending_users,
    kb_super_admin,
    kb_user_card,
)
from config.config import SUPER_ADMIN  # noqa: E402


def reply_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


def callback_data(markup) -> set[str]:
    return {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }


class CompactMenuTests(unittest.TestCase):
    def test_super_admin_reply_menu_only_contains_admin_panel(self) -> None:
        self.assertEqual(reply_texts(kb_super_admin()), [T.BTN_ADMIN])
        self.assertEqual(reply_texts(kb_main(super_admin=True)), [T.BTN_ADMIN])

    def test_regular_menu_has_one_state_dependent_start_stop_position(self) -> None:
        stopped = reply_texts(kb_main(running=False))
        running = reply_texts(kb_main(running=True))

        # Holat (ON/OFF) Start/Stop tugmasining o'zida — alohida Status tugmasi yo'q.
        self.assertEqual(stopped[0], f"{T.BTN_START} (🔴 OFF)")
        self.assertEqual(running[0], f"{T.BTN_STOP} (🟢 ON)")
        self.assertTrue(stopped[0].startswith(T.BTN_START))
        self.assertTrue(running[0].startswith(T.BTN_STOP))
        for label in (*stopped, *running):
            self.assertFalse(label.startswith(T.BTN_STATUS))

    def test_regular_menu_is_flat_without_submenus_or_account_button(self) -> None:
        """Foydalanuvchi menyusi yassi: barcha asosiy amallar bitta ekranda."""
        top_level = reply_texts(kb_main())

        # Yangi yassi menyuda bo'lishi kerak bo'lgan tugmalar.
        for button in (
            T.BTN_FIND_GROUPS,
            T.BTN_DEL_GROUP,
            T.BTN_ADD_POST,
            T.BTN_DEL_POST,
            T.BTN_TIMER,
            T.BTN_REPORT,
            T.BTN_REFERRAL,
        ):
            self.assertIn(button, top_level)

        # Ichki menyular va olib tashlangan tugmalar asosiy ekranda bo'lmasligi kerak.
        for button in (
            T.BTN_GROUPS,
            T.BTN_POSTS,
            T.BTN_ADD_GROUP,
            T.BTN_GROUP_INTERVAL,
            T.BTN_CHECK_GROUPS,
            T.BTN_EDIT_POST,
            T.BTN_PREVIEW_POST,
            T.BTN_TEST_SEND,
            T.BTN_ACCOUNT,
            T.BTN_ADMIN,
        ):
            self.assertNotIn(button, top_level)

        # Status va Paket alohida tugma emas — ular Start/Stop va Hisobot ichida.
        for label in top_level:
            self.assertFalse(label.startswith(T.BTN_STATUS))
            self.assertFalse(label.startswith(T.BTN_PLAN))


class SuperAdminEntryTests(unittest.IsolatedAsyncioTestCase):
    async def test_start_opens_admin_panel_without_reading_session(self) -> None:
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=message,
        )
        context = SimpleNamespace(args=[])
        stats = {
            "total_users": 2,
            "admins": 2,
            "waiting": 0,
            "running": 1,
            "blocked": 0,
        }

        with (
            patch.object(main.rate_limiter, "is_allowed", return_value=True),
            patch.object(main.db, "upsert_user", new=AsyncMock()) as upsert,
            patch.object(main.db, "get_stats", new=AsyncMock(return_value=stats)),
            patch.object(main.db, "get_user", new=AsyncMock()) as get_user,
        ):
            await main.cmd_start(update, context)

        upsert.assert_awaited_once_with(SUPER_ADMIN, is_admin=1)
        get_user.assert_not_awaited()
        first_markup = message.reply_text.await_args_list[0].kwargs["reply_markup"]
        self.assertEqual(reply_texts(first_markup), [T.BTN_ADMIN])
        panel_markup = message.reply_text.await_args_list[1].kwargs["reply_markup"]
        self.assertIn("adm:users", callback_data(panel_markup))


class SelectedUserControlsTests(unittest.IsolatedAsyncioTestCase):
    def test_pending_and_destructive_controls_are_unambiguous(self) -> None:
        pending = callback_data(
            kb_user_card(
                2001,
                has_session=False,
                approved=False,
                awaiting=True,
            )
        )
        self.assertIn("uc:approve:2001", pending)
        self.assertIn("uc:rejectask:2001", pending)
        self.assertIn("uc:deleteask:2001", pending)
        self.assertNotIn("uc:sess:2001", pending)
        self.assertNotIn("uc:groups:2001", pending)

        users = [{"uid": uid, "name": f"User {uid}"} for uid in range(15)]
        page = callback_data(kb_pending_users(users, page=0))
        self.assertIn("adm:pending:1", page)
        self.assertIn("exp:2001:forever", callback_data(kb_expire_options(2001)))
        self.assertIn("db:clearlogs:ask", callback_data(kb_db_panel()))

    def test_user_card_contains_complete_management_sections(self) -> None:
        callbacks = callback_data(
            kb_user_card(
                2001,
                running=False,
                blocked=False,
                has_session=True,
            )
        )
        expected = {
            "uc:start:2001",
            "uc:logoutask:2001",
            "uc:groups:2001",
            "uc:posts:2001",
            "uc:interval:2001",
            "uc:expire:2001",
            "uc:blockask:2001",
            "uc:detail:2001",
            "uc:deleteask:2001",
            "adm:users",
        }
        self.assertTrue(expected <= callbacks)
        self.assertNotIn("uc:sess:2001", callbacks)

    def test_group_and_post_screens_offer_add_delete_and_back(self) -> None:
        groups = callback_data(
            kb_admin_groups(
                2001,
                [{"id": 41, "value": "@one"}, {"id": 99, "value": "@two"}],
            )
        )
        self.assertTrue(
            {
                "uc:addg:2001",
                "uc:delg:2001:41:0",
                "uc:delg:2001:99:0",
                "uc:gint:2001:41",
                "uc:gint:2001:99",
                "uc:back:2001",
            }
            <= groups
        )

        user_picker = callback_data(
            kb_group_interval_picker(
                [{"id": 41, "value": "@one", "interval_min": None}], 60
            )
        )
        self.assertIn("gint:select:41", user_picker)
        user_options = callback_data(kb_group_interval_options(41, 30))
        self.assertTrue(
            {"gint:set:41:30", "gint:manual:41", "gint:reset:41"}
            <= user_options
        )
        admin_options = callback_data(kb_admin_group_interval(2001, 41, 30))
        self.assertTrue(
            {
                "uc:gint:2001:41:30",
                "uc:gint:2001:41:manual",
                "uc:gint:2001:41:general",
            }
            <= admin_options
        )

        posts = callback_data(
            kb_admin_posts(
                2001,
                [{"id": 51, "text": "one"}, {"id": 88, "text": "two"}],
            )
        )
        self.assertTrue(
            {
                "uc:addp:2001",
                "uc:delp:2001:51:0",
                "uc:delp:2001:88:0",
                "uc:back:2001",
            }
            <= posts
        )

    async def test_admin_group_screen_renders_database_value_records(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        records = [{"id": 41, "uid": 2001, "value": "@one", "created_at": "2026-01-01"}]
        with (
            patch.object(
                admin_actions.db,
                "get_chat_records",
                new=AsyncMock(return_value=records),
            ),
            patch.object(
                admin_actions.db,
                "get_interval",
                new=AsyncMock(return_value=60),
            ),
        ):
            await admin_actions.action_show_groups(update, 2001)

        text = update.callback_query.edit_message_text.await_args.args[0]
        markup = update.callback_query.edit_message_text.await_args.kwargs[
            "reply_markup"
        ]
        self.assertIn("1. @one", text)
        self.assertIn("uc:delg:2001:41:0", callback_data(markup))

    async def test_admin_can_delete_selected_users_group_and_post(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        with (
            patch.object(
                admin_actions.db,
                "get_user",
                new=AsyncMock(return_value={"uid": 2001}),
            ),
            patch.object(
                admin_actions.db,
                "remove_chat_by_id",
                new=AsyncMock(return_value="@one"),
            ) as remove_chat,
            patch.object(
                admin_actions.db,
                "get_chat_records",
                new=AsyncMock(return_value=[]),
            ),
            patch.object(
                admin_actions.db,
                "get_interval",
                new=AsyncMock(return_value=60),
            ),
        ):
            await admin_actions.action_delete_group(
                update,
                SUPER_ADMIN,
                2001,
                ["uc", "delg", "2001", "41", "0"],
            )
        remove_chat.assert_awaited_once_with(2001, 41)

        with (
            patch.object(
                admin_actions.db,
                "get_user",
                new=AsyncMock(return_value={"uid": 2001}),
            ),
            patch(
                "bot.posts.delete_post_by_id",
                new=AsyncMock(return_value=(True, "post")),
            ) as delete_post,
            patch.object(
                admin_actions.db,
                "get_posts",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await admin_actions.action_delete_post(
                update,
                SUPER_ADMIN,
                2001,
                ["uc", "delp", "2001", "51", "0"],
            )
        delete_post.assert_awaited_once_with(2001, 51)

    async def test_admin_can_set_a_selected_group_interval(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        before = {"id": 41, "uid": 2001, "value": "@one", "interval_min": None}
        after = {**before, "interval_min": 30}
        with (
            patch.object(
                admin_actions.db,
                "get_chat_record",
                new=AsyncMock(side_effect=[before, after]),
            ),
            patch.object(
                admin_actions.db,
                "get_user",
                new=AsyncMock(return_value={"uid": 2001}),
            ),
            patch.object(
                admin_actions.db,
                "get_interval",
                new=AsyncMock(return_value=60),
            ),
            patch.object(
                admin_actions.db,
                "set_chat_interval",
                new=AsyncMock(return_value=True),
            ) as set_interval,
        ):
            await admin_actions.action_group_interval(
                update,
                SUPER_ADMIN,
                2001,
                ["uc", "gint", "2001", "41", "30"],
            )

        set_interval.assert_awaited_once_with(2001, 41, 30)
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("Alohida interval 30 daqiqaga o'rnatildi", text)

    async def test_admin_can_set_selected_users_posting_interval(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        with (
            patch.object(
                admin_actions.db,
                "get_user",
                new=AsyncMock(return_value={"uid": 2001, "session": "session"}),
            ),
            patch.object(
                admin_actions.db,
                "set_interval",
                new=AsyncMock(),
            ) as set_interval,
        ):
            await admin_actions.handle_interval(
                update,
                SUPER_ADMIN,
                "aint:2001:30",
            )

        set_interval.assert_awaited_once_with(2001, 30)
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("30 daqiqa", text)


if __name__ == "__main__":
    unittest.main()
