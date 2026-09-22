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
    kb_admin_groups,
    kb_admin_posts,
    kb_groups_menu,
    kb_main,
    kb_posts_menu,
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

        self.assertIn(T.BTN_START, stopped)
        self.assertNotIn(T.BTN_STOP, stopped)
        self.assertIn(T.BTN_STOP, running)
        self.assertNotIn(T.BTN_START, running)
        self.assertEqual(stopped[0], T.BTN_START)
        self.assertEqual(running[0], T.BTN_STOP)

    def test_regular_top_level_is_compact_and_actions_are_in_submenus(self) -> None:
        top_level = reply_texts(kb_main())
        for button in (
            T.BTN_GROUPS,
            T.BTN_POSTS,
            T.BTN_TIMER,
            T.BTN_REFERRAL,
        ):
            self.assertIn(button, top_level)
        for button in (
            T.BTN_ADD_GROUP,
            T.BTN_DEL_GROUP,
            T.BTN_ADD_POST,
            T.BTN_DEL_POST,
            T.BTN_ADMIN,
        ):
            self.assertNotIn(button, top_level)

        self.assertIn(T.BTN_ADD_GROUP, reply_texts(kb_groups_menu()))
        self.assertIn(T.BTN_DEL_GROUP, reply_texts(kb_groups_menu()))
        self.assertIn(T.BTN_ADD_POST, reply_texts(kb_posts_menu()))
        self.assertIn(T.BTN_DEL_POST, reply_texts(kb_posts_menu()))


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
            "uc:logout:2001",
            "uc:groups:2001",
            "uc:posts:2001",
            "uc:interval:2001",
            "uc:expire:2001",
            "uc:block:2001",
            "uc:detail:2001",
            "uc:delete:2001",
            "adm:users",
        }
        self.assertTrue(expected <= callbacks)
        self.assertNotIn("uc:sess:2001", callbacks)

    def test_group_and_post_screens_offer_add_delete_and_back(self) -> None:
        groups = callback_data(kb_admin_groups(2001, ["@one", "@two"]))
        self.assertTrue(
            {
                "uc:addg:2001",
                "uc:delg:2001:0:0",
                "uc:delg:2001:1:0",
                "uc:back:2001",
            }
            <= groups
        )

        posts = callback_data(
            kb_admin_posts(2001, [{"text": "one"}, {"text": "two"}])
        )
        self.assertTrue(
            {
                "uc:addp:2001",
                "uc:delp:2001:0:0",
                "uc:delp:2001:1:0",
                "uc:back:2001",
            }
            <= posts
        )

    async def test_admin_can_delete_selected_users_group_and_post(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        with (
            patch.object(
                admin_actions.db,
                "remove_chat",
                new=AsyncMock(return_value="@one"),
            ) as remove_chat,
            patch.object(
                admin_actions.db,
                "get_chats",
                new=AsyncMock(return_value=[]),
            ),
        ):
            await admin_actions.action_delete_group(
                update,
                SUPER_ADMIN,
                2001,
                ["uc", "delg", "2001", "0", "0"],
            )
        remove_chat.assert_awaited_once_with(2001, 0)

        with (
            patch(
                "bot.posts.delete_post_by_index",
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
                ["uc", "delp", "2001", "0", "0"],
            )
        delete_post.assert_awaited_once_with(2001, 0)

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
