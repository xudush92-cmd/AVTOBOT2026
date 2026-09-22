"""Login delivery diagnostics and QR fallback smoke tests.

Run from the application directory:
    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import os
import sys
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

# config.config validates these during import. Tests never contact Telegram.
os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from telethon.tl import types  # noqa: E402

from bot import login  # noqa: E402
from bot import texts as T  # noqa: E402
from bot.keyboards import kb_numpad, kb_qr_login  # noqa: E402
from bot.login import (  # noqa: E402
    LoginCtx,
    describe_code_delivery,
    make_qr_image,
    mask_phone,
)
from core.rate_limit import RateLimiter  # noqa: E402


class LoginDiagnosticsTests(unittest.TestCase):
    def test_mask_phone_hides_middle_digits(self) -> None:
        self.assertEqual(mask_phone("+998901234567"), "+998***567")
        self.assertEqual(mask_phone("123"), "***")

    def test_app_delivery_is_reported_as_telegram_chat(self) -> None:
        sent = types.auth.SentCode(
            type=types.auth.SentCodeTypeApp(length=5),
            phone_code_hash="hash",
            next_type=types.auth.CodeTypeSms(),
            timeout=60,
        )

        destination, type_name, next_name, timeout = describe_code_delivery(sent)

        self.assertIn("777000", destination)
        self.assertEqual(type_name, "SentCodeTypeApp")
        self.assertEqual(next_name, "CodeTypeSms")
        self.assertEqual(timeout, 60)

    def test_email_delivery_shows_masked_email_pattern(self) -> None:
        sent = types.auth.SentCode(
            type=types.auth.SentCodeTypeEmailCode(
                email_pattern="a***@example.com",
                length=6,
            ),
            phone_code_hash="hash",
        )

        destination, type_name, _, _ = describe_code_delivery(sent)

        self.assertIn("a***@example.com", destination)
        self.assertEqual(type_name, "SentCodeTypeEmailCode")

    def test_qr_image_is_a_png(self) -> None:
        image = make_qr_image("tg://login?token=test-token")
        self.assertEqual(image.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(image.getvalue()), 100)

    def test_numpad_contains_qr_fallback(self) -> None:
        callbacks = [
            button.callback_data
            for row in kb_numpad().inline_keyboard
            for button in row
        ]
        self.assertIn("np:qr", callbacks)

    def test_admin_add_user_numpad_has_digits_confirm_delete_and_cancel(self) -> None:
        callbacks = {
            button.callback_data
            for row in kb_numpad(admin_add_user=True).inline_keyboard
            for button in row
        }
        self.assertTrue({f"np:{digit}" for digit in range(10)} <= callbacks)
        self.assertTrue({"np:back", "np:ok", "np:cancel"} <= callbacks)
        self.assertNotIn("np:qr", callbacks)

    def test_qr_keyboard_contains_deep_link_and_cancel(self) -> None:
        url = "tg://login?token=test-token"
        keyboard = kb_qr_login(url).inline_keyboard
        self.assertEqual(keyboard[0][0].url, url)
        self.assertEqual(keyboard[1][0].callback_data, "qr:cancel")

    def test_login_rate_limit_uses_one_hour_window(self) -> None:
        limiter = RateLimiter()
        self.assertEqual(limiter._window_for("login"), 3600)
        self.assertEqual(limiter._window_for("message"), 60)

    def test_custom_rate_limit_window_is_kept_for_tests(self) -> None:
        limiter = RateLimiter(window_s=10)
        self.assertEqual(limiter._window_for("login"), 10)
        self.assertEqual(limiter._window_for("message"), 10)

    def test_fourth_login_is_blocked_for_the_full_hour(self) -> None:
        limiter = RateLimiter()
        uid = 1234
        with patch("core.rate_limit.time.time", return_value=1000):
            self.assertTrue(limiter.is_allowed(uid, "login"))
            self.assertTrue(limiter.is_allowed(uid, "login"))
            self.assertTrue(limiter.is_allowed(uid, "login"))
            self.assertFalse(limiter.is_allowed(uid, "login"))

        # Oddiy 60 soniyalik oyna o'tishi login limitini ochmasligi kerak.
        with patch("core.rate_limit.time.time", return_value=1061):
            self.assertFalse(limiter.is_allowed(uid, "login"))

        with patch("core.rate_limit.time.time", return_value=4601):
            self.assertTrue(limiter.is_allowed(uid, "login"))


class QrLoginLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        self.bot = SimpleNamespace(
            delete_message=AsyncMock(),
            send_message=AsyncMock(),
        )
        login.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        for uid in list(login.login_ctx):
            await login.cleanup_login(uid)
        login.user_states.clear()
        login.application = None

    async def test_cleanup_cancels_qr_waiter_and_disconnects(self) -> None:
        uid = 1001
        client = SimpleNamespace(disconnect=AsyncMock())
        waiter = asyncio.create_task(asyncio.Event().wait())
        ctx = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="",
            started_at=0,
            mode="qr",
            wait_task=waiter,
            qr_message_id=77,
        )
        login.login_ctx[uid] = ctx
        login.user_states[uid] = {"step": "qr"}

        await login.cleanup_login(uid)

        self.assertTrue(waiter.cancelled())
        client.disconnect.assert_awaited_once()
        self.bot.delete_message.assert_awaited_once_with(
            chat_id=uid, message_id=77
        )
        self.assertNotIn(uid, login.login_ctx)
        self.assertNotIn(uid, login.user_states)

    async def test_qr_success_rejects_a_different_telegram_user(self) -> None:
        uid = 1002
        client = SimpleNamespace(
            get_me=AsyncMock(return_value=SimpleNamespace(id=9999, phone="998900000000")),
            disconnect=AsyncMock(),
        )
        ctx = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="",
            started_at=0,
            mode="qr",
        )
        qr_login = SimpleNamespace(wait=AsyncMock())
        login.login_ctx[uid] = ctx
        login.user_states[uid] = {"step": "qr"}

        with patch.object(login, "finalize_login", new=AsyncMock()) as finalize:
            await login._wait_for_qr_login(uid, ctx, qr_login)

        finalize.assert_not_awaited()
        client.disconnect.assert_awaited_once()
        self.bot.send_message.assert_awaited_once()
        self.assertNotIn(uid, login.login_ctx)

    async def test_qr_success_updates_phone_and_finalizes(self) -> None:
        uid = 1003
        client = SimpleNamespace(
            get_me=AsyncMock(
                return_value=SimpleNamespace(id=uid, phone="998901112233")
            ),
            disconnect=AsyncMock(),
        )
        ctx = LoginCtx(
            client=client,
            phone="+998900000000",
            phone_code_hash="",
            started_at=0,
            mode="qr",
        )
        qr_login = SimpleNamespace(wait=AsyncMock())
        login.login_ctx[uid] = ctx
        login.user_states[uid] = {"step": "qr"}

        with (
            patch.object(login.db, "set_phone", new=AsyncMock()) as set_phone,
            patch.object(login, "finalize_login", new=AsyncMock()) as finalize,
        ):
            await login._wait_for_qr_login(uid, ctx, qr_login)

        set_phone.assert_awaited_once_with(uid, "+998901112233")
        finalize.assert_awaited_once_with(uid)
        self.assertEqual(ctx.phone, "+998901112233")


class RegistrationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        login.application = SimpleNamespace(bot=SimpleNamespace())

    async def asyncTearDown(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        login.application = None

    @staticmethod
    def _update(uid: int):
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=uid, username="test_user"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

    async def test_unapproved_user_is_sent_to_admin_before_code_request(self) -> None:
        uid = 2001
        update = self._update(uid)
        login.user_states[uid] = {"step": "phone", "full_name": "Test User"}

        with (
            patch.object(login.db, "set_phone", new=AsyncMock()),
            patch.object(login.db, "set_user_info", new=AsyncMock()),
            patch.object(login.db, "is_admin", new=AsyncMock(return_value=False)),
            patch.object(login.db, "set_awaiting_approval", new=AsyncMock()) as awaiting,
            patch.object(login, "notify_super_for_approval", new=AsyncMock()) as notify,
            patch.object(login, "request_code", new=AsyncMock()) as request_code,
        ):
            await login.handle_phone(update, "+998901234567")

        awaiting.assert_awaited_once_with(uid, True)
        notify.assert_awaited_once_with(uid)
        request_code.assert_not_awaited()
        self.assertEqual(
            update.message.reply_text.await_args.args[0],
            T.REGISTRATION_PENDING,
        )

    async def test_approved_user_requests_code_immediately(self) -> None:
        uid = 2002
        update = self._update(uid)
        login.user_states[uid] = {"step": "phone"}

        with (
            patch.object(login.db, "set_phone", new=AsyncMock()),
            patch.object(login.db, "is_admin", new=AsyncMock(return_value=True)),
            patch.object(login.db, "set_awaiting_approval", new=AsyncMock()) as awaiting,
            patch.object(login, "notify_super_for_approval", new=AsyncMock()) as notify,
            patch.object(login, "request_code", new=AsyncMock()) as request_code,
        ):
            await login.handle_phone(update, "+998901234567")

        request_code.assert_awaited_once_with(uid, "+998901234567")
        awaiting.assert_not_awaited()
        notify.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
