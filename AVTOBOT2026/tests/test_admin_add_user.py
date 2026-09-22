"""Super-admin panelidagi yangi foydalanuvchi wizard testlari."""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

import main  # noqa: E402
from admin import admin_actions  # noqa: E402
from bot import login  # noqa: E402
from bot.keyboards import (  # noqa: E402
    kb_admin_add_user_cancel,
    kb_admin_panel,
)
from bot.login import LoginCtx  # noqa: E402
from config.config import SUPER_ADMIN  # noqa: E402


class AdminAddUserWizardTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        self.old_login_app = login.application
        self.old_admin_app = admin_actions.application
        login.application = SimpleNamespace(bot=self.bot)
        admin_actions.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        for uid in list(login.login_ctx):
            await login.cleanup_login(uid)
        login.user_states.clear()
        login.application = self.old_login_app
        admin_actions.application = self.old_admin_app

    @staticmethod
    def _callback_update():
        return SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )

    @staticmethod
    def _message_update():
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

    def test_super_admin_menu_contains_add_user_and_cancel_buttons(self) -> None:
        panel_buttons = [
            button
            for row in kb_admin_panel().inline_keyboard
            for button in row
        ]
        add_button = next(
            button for button in panel_buttons
            if button.callback_data == "adm:adduser"
        )
        self.assertIn("Foydalanuvchi qo'shish", add_button.text)

        cancel_callbacks = {
            button.callback_data
            for row in kb_admin_add_user_cancel().inline_keyboard
            for button in row
        }
        self.assertEqual(cancel_callbacks, {"adm:adduser:cancel"})

    async def test_wizard_asks_full_name_then_phone(self) -> None:
        callback_update = self._callback_update()
        await admin_actions.begin_add_user(callback_update, SUPER_ADMIN)
        self.assertEqual(
            login.user_states[SUPER_ADMIN]["step"],
            "admin_new_user_full_name",
        )

        update = self._message_update()
        await main.handle_admin_fsm(
            update,
            SUPER_ADMIN,
            "admin_new_user_full_name",
            "Ali Valiyev",
        )
        state = login.user_states[SUPER_ADMIN]
        self.assertEqual(state["step"], "admin_new_user_phone")
        self.assertEqual(state["full_name"], "Ali Valiyev")

        with patch.object(
            main.AA,
            "request_new_user_session",
            new=AsyncMock(),
        ) as request_session:
            await main.handle_admin_fsm(
                update,
                SUPER_ADMIN,
                "admin_new_user_phone",
                "+998 90-123-45-67",
            )

        request_session.assert_awaited_once_with(
            SUPER_ADMIN,
            "Ali Valiyev",
            "+998901234567",
        )

    async def test_admin_code_screen_uses_inline_numpad(self) -> None:
        login.user_states[SUPER_ADMIN] = {
            "step": "code",
            "admin_add_user": True,
            "code_length": 5,
        }
        await login.send_numpad(SUPER_ADMIN)

        markup = self.bot.send_message.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertTrue({"np:back", "np:ok", "np:cancel"} <= callbacks)
        self.assertIn("np:0", callbacks)

    async def test_phone_request_enters_button_code_state(self) -> None:
        phone = "+998901234567"
        sent_code = SimpleNamespace(
            type=SimpleNamespace(length=6),
            phone_code_hash="hash",
            next_type=None,
            timeout=60,
        )
        client = SimpleNamespace(
            connect=AsyncMock(),
            send_code_request=AsyncMock(return_value=sent_code),
            disconnect=AsyncMock(),
        )

        with (
            patch.object(
                admin_actions.db,
                "get_phone",
                new=AsyncMock(return_value="+998900000000"),
            ),
            patch.object(
                admin_actions.db,
                "get_all_users",
                new=AsyncMock(return_value=[]),
            ),
            patch("telethon.TelegramClient", return_value=client),
        ):
            await admin_actions.request_new_user_session(
                SUPER_ADMIN,
                "Ali Valiyev",
                phone,
            )

        state = login.user_states[SUPER_ADMIN]
        self.assertEqual(state["step"], "code")
        self.assertEqual(state["code_length"], 6)
        self.assertTrue(state["admin_add_user"])
        self.assertEqual(login.login_ctx[SUPER_ADMIN].mode, "admin_add_user")
        markup = self.bot.send_message.await_args.kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
        }
        self.assertIn("np:ok", callbacks)

    async def test_admin_phone_is_rejected_before_requesting_code(self) -> None:
        phone = "+998901234567"
        login.user_states[SUPER_ADMIN] = {"step": "admin_new_user_phone"}

        with patch.object(
            admin_actions.db,
            "get_phone",
            new=AsyncMock(return_value=phone),
        ):
            await admin_actions.request_new_user_session(
                SUPER_ADMIN,
                "Super Admin",
                phone,
            )

        self.assertNotIn(SUPER_ADMIN, login.login_ctx)
        self.assertNotIn(SUPER_ADMIN, login.user_states)
        message = self.bot.send_message.await_args.args[1]
        self.assertIn("o'z telefon raqami", message)

    async def test_cancel_stops_wizard_and_disconnects_client(self) -> None:
        client = SimpleNamespace(disconnect=AsyncMock())
        login.login_ctx[SUPER_ADMIN] = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="hash",
            started_at=time.time(),
            target_name="Ali Valiyev",
            mode="admin_add_user",
        )
        login.user_states[SUPER_ADMIN] = {
            "step": "code",
            "admin_add_user": True,
        }

        update = self._callback_update()
        await admin_actions.cancel_add_user(update, SUPER_ADMIN)

        self.assertNotIn(SUPER_ADMIN, login.login_ctx)
        self.assertNotIn(SUPER_ADMIN, login.user_states)
        client.disconnect.assert_awaited_once()
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("bekor qilindi", text)

    async def test_success_uses_logged_in_account_id_not_admin_id(self) -> None:
        target_uid = 3001
        client = SimpleNamespace(
            get_me=AsyncMock(
                return_value=SimpleNamespace(id=target_uid, username="ali")
            ),
            session=SimpleNamespace(save=MagicMock(return_value="new-session")),
            disconnect=AsyncMock(),
            log_out=AsyncMock(),
        )
        ctx = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="hash",
            started_at=time.time(),
            target_name="Ali Valiyev",
            mode="admin_add_user",
        )
        login.login_ctx[SUPER_ADMIN] = ctx
        login.user_states[SUPER_ADMIN] = {
            "step": "code",
            "admin_add_user": True,
        }

        with (
            patch.object(login.db, "get_user", new=AsyncMock(return_value=None)),
            patch.object(login.db, "set_user_info", new=AsyncMock()) as set_info,
            patch.object(login.db, "set_phone", new=AsyncMock()) as set_phone,
            patch.object(login.db, "set_session", new=AsyncMock()) as set_session,
            patch.object(login.db, "del_pending", new=AsyncMock()),
            patch.object(login.db, "set_awaiting_approval", new=AsyncMock()),
            patch.object(login.db, "add_admin", new=AsyncMock()) as add_admin,
        ):
            await login._finalize_admin_added_user(SUPER_ADMIN, ctx)

        set_info.assert_awaited_once_with(target_uid, "Ali Valiyev", "ali")
        set_phone.assert_awaited_once_with(target_uid, "+998901234567")
        set_session.assert_awaited_once_with(target_uid, "new-session")
        add_admin.assert_awaited_once_with(target_uid)
        self.assertNotIn(SUPER_ADMIN, login.login_ctx)
        client.log_out.assert_not_awaited()
        admin_markup = self.bot.send_message.await_args_list[0].kwargs["reply_markup"]
        callbacks = {
            button.callback_data
            for row in admin_markup.inline_keyboard
            for button in row
        }
        self.assertIn(f"uc:groups:{target_uid}", callbacks)
        self.assertIn(f"uc:posts:{target_uid}", callbacks)
        self.assertIn(f"uc:interval:{target_uid}", callbacks)

    async def test_admin_phone_cannot_be_added_as_regular_user(self) -> None:
        client = SimpleNamespace(
            get_me=AsyncMock(
                return_value=SimpleNamespace(id=SUPER_ADMIN, username="admin")
            ),
            session=SimpleNamespace(save=MagicMock(return_value="bad-session")),
            disconnect=AsyncMock(),
            log_out=AsyncMock(),
        )
        ctx = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="hash",
            started_at=time.time(),
            target_name="Super Admin",
            mode="admin_add_user",
        )
        login.login_ctx[SUPER_ADMIN] = ctx

        with (
            patch.object(login.db, "get_user", new=AsyncMock(return_value=None)),
            patch.object(login.db, "set_session", new=AsyncMock()) as set_session,
        ):
            await login._finalize_admin_added_user(SUPER_ADMIN, ctx)

        client.log_out.assert_awaited_once()
        set_session.assert_not_awaited()
        admin_message = self.bot.send_message.await_args_list[-1].args[1]
        self.assertIn("Super admin", admin_message)


if __name__ == "__main__":
    unittest.main()
