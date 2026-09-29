"""Oddiy foydalanuvchi registratsiyasi (pending session) regressiya testlari.

Qamrov:
- /start va 🔑 Login yangi userdan ism-familiyani darhol so'rashi;
- tasdiqlanmagan user telefon kiritgach kod darhol so'ralishi;
- UID va telefon bo'yicha login limitlari (/start orqali aylanib bo'lmaydi);
- telefon limiteri TelegramClient yaratilishidan oldin ishlashi;
- muvaffaqiyatli login pending sessiyani faqat bir marta saqlashi;
- pending owner validation: valid / mismatch / temporary;
- pending sessiyaning atomik promotion'i va admin tasdig'i;
- mismatch authorization'ning revoke qilinishi, temporary xatoda pending
  saqlanishi;
- birinchi tasdiqda 30 kun va 60 daqiqa; custom intervalning saqlanishi;
- yangi tasdiqlangan userga asosiy menyu yuborilishi.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from cryptography.fernet import Fernet  # noqa: E402
from telethon.errors import (  # noqa: E402
    AuthKeyUnregisteredError,
    FloodWaitError,
    PhoneCodeExpiredError,
    SessionRevokedError,
    UserDeactivatedError,
)

import main  # noqa: E402
from admin import admin_actions as AA  # noqa: E402
from bot import login  # noqa: E402
from bot import texts as T  # noqa: E402
from bot.keyboards import kb_login, kb_main  # noqa: E402
from bot.login import LoginCtx  # noqa: E402
from config.config import (  # noqa: E402
    DEFAULT_DURATION_DAYS,
    DEFAULT_INTERVAL_MIN,
    MAX_INTERVAL_MIN,
    MIN_INTERVAL_MIN,
)
from core import database as db  # noqa: E402
from core import session_crypto, session_manager  # noqa: E402
from core.session_manager import (  # noqa: E402
    INVALID,
    MISMATCH,
    TEMPORARY,
    VALID,
    validate_telegram_session_owner,
)
from core.utils import calc_expires  # noqa: E402


def reply_texts(markup) -> list[str]:
    return [button.text for row in markup.keyboard for button in row]


# ─────────────────────────────────────────────────────────────────────────
# /start VA 🔑 LOGIN KIRISH NUQTASI
# ─────────────────────────────────────────────────────────────────────────
class StartRegistrationEntryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        login.application = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock())
        )
        self.bot = login.application.bot

    async def asyncTearDown(self) -> None:
        for uid in list(login.login_ctx):
            await login.cleanup_login(uid)
        login.user_states.clear()
        login.application = None

    @staticmethod
    def _update(uid: int, text: str = "/start"):
        message = SimpleNamespace(reply_text=AsyncMock(), text=text)
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=uid, username="newbie"),
            effective_chat=SimpleNamespace(type="private"),
            message=message,
            callback_query=SimpleNamespace(edit_message_text=AsyncMock()),
        )

    def _patched_db(self, user):
        return (
            patch.object(main.db, "get_user", new=AsyncMock(return_value=user)),
            patch.object(main.db, "is_blocked", new=AsyncMock(return_value=False)),
        )

    async def test_start_asks_new_user_for_full_name_immediately(self) -> None:
        uid = 3001
        update = self._update(uid)
        get_user, is_blocked = self._patched_db(None)

        with (
            patch.object(main.rate_limiter, "is_allowed", return_value=True) as allowed,
            get_user,
            is_blocked,
        ):
            await main.cmd_start(update, SimpleNamespace(args=[]))

        self.assertEqual(update.message.reply_text.await_args.args[0], T.ASK_FULL_NAME)
        self.assertEqual(login.get_step(uid), "full_name")
        # Yangi user ham UID login limitiga tushadi.
        self.assertIn(((uid, "login")), [call.args for call in allowed.call_args_list])

    async def test_start_asks_unapproved_user_for_full_name_again(self) -> None:
        uid = 3002
        update = self._update(uid)
        user = {"uid": uid, "is_admin": 0, "awaiting_approval": 0, "session": ""}
        get_user, is_blocked = self._patched_db(user)

        with (
            patch.object(main.rate_limiter, "is_allowed", return_value=True),
            patch.object(main.db, "upsert_user", new=AsyncMock()),
            get_user,
            is_blocked,
        ):
            await main.cmd_start(update, SimpleNamespace(args=[]))

        self.assertEqual(update.message.reply_text.await_args.args[0], T.ASK_FULL_NAME)
        self.assertEqual(login.get_step(uid), "full_name")

    async def test_start_cannot_bypass_uid_login_rate_limit(self) -> None:
        uid = 3003
        update = self._update(uid)
        get_user, is_blocked = self._patched_db(None)

        with (
            patch.object(main.rate_limiter, "is_allowed", return_value=False),
            patch.object(main.rate_limiter, "get_wait_time", return_value=42),
            patch.object(main.Login, "begin_login", new=AsyncMock()) as begin_login,
            get_user,
            is_blocked,
        ):
            await main.cmd_start(update, SimpleNamespace(args=[]))

        begin_login.assert_not_awaited()
        self.assertEqual(
            update.message.reply_text.await_args.args[0], T.rate_limit_text(42)
        )
        self.assertIsNone(login.get_step(uid))

    async def test_login_button_cannot_bypass_uid_login_rate_limit(self) -> None:
        uid = 3004
        update = self._update(uid, T.BTN_LOGIN)
        get_user, is_blocked = self._patched_db(None)

        with (
            patch.object(main.rate_limiter, "is_allowed", return_value=False),
            patch.object(main.rate_limiter, "get_wait_time", return_value=17),
            patch.object(main.Login, "begin_login", new=AsyncMock()) as begin_login,
            get_user,
            is_blocked,
        ):
            from core.update_locks import user_update_lock

            async with user_update_lock(uid):
                await main._on_message_locked(update, SimpleNamespace())

        begin_login.assert_not_awaited()
        self.assertEqual(
            update.message.reply_text.await_args.args[0], T.rate_limit_text(17)
        )


# ─────────────────────────────────────────────────────────────────────────
# TELEFON → KOD DARHOL
# ─────────────────────────────────────────────────────────────────────────
class RegistrationPhoneStepTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        login.application = SimpleNamespace(
            bot=SimpleNamespace(send_message=AsyncMock())
        )

    async def asyncTearDown(self) -> None:
        login.user_states.clear()
        login.application = None

    @staticmethod
    def _update(uid: int):
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=uid, username="test_user"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

    async def test_unapproved_phone_requests_code_without_admin_approval(self) -> None:
        uid = 3101
        update = self._update(uid)
        login.user_states[uid] = {"step": "phone", "full_name": "Test User"}

        with (
            patch.object(
                login.db, "get_user_by_phone", new=AsyncMock(return_value=None)
            ),
            patch.object(login.db, "set_phone", new=AsyncMock(return_value=True)),
            patch.object(login.db, "set_user_info", new=AsyncMock()),
            patch.object(login.db, "is_admin", new=AsyncMock(return_value=False)),
            patch.object(
                login.db, "set_awaiting_approval", new=AsyncMock()
            ) as awaiting,
            patch.object(login, "notify_super_for_approval", new=AsyncMock()) as notify,
            patch.object(login, "request_code", new=AsyncMock()) as request_code,
        ):
            await login.handle_phone(update, "+998901234567")

        request_code.assert_awaited_once_with(uid, "+998901234567")
        awaiting.assert_not_awaited()
        notify.assert_not_awaited()
        self.assertEqual(
            update.message.reply_text.await_args.args[0],
            T.REGISTRATION_CODE_REQUEST.format(phone="+998901234567"),
        )

    async def test_approved_user_still_gets_code_immediately(self) -> None:
        uid = 3102
        update = self._update(uid)
        login.user_states[uid] = {"step": "phone"}

        with (
            patch.object(
                login.db, "get_user_by_phone", new=AsyncMock(return_value=None)
            ),
            patch.object(login.db, "set_phone", new=AsyncMock(return_value=True)),
            patch.object(login.db, "is_admin", new=AsyncMock(return_value=True)),
            patch.object(login, "request_code", new=AsyncMock()) as request_code,
        ):
            await login.handle_phone(update, "+998901234567")

        request_code.assert_awaited_once_with(uid, "+998901234567")
        self.assertEqual(
            update.message.reply_text.await_args.args[0],
            T.PHONE_ACCEPTED.format(phone="+998901234567"),
        )


# ─────────────────────────────────────────────────────────────────────────
# PENDING SESSIYANI SAQLASH (LOGIN YAKUNI)
# ─────────────────────────────────────────────────────────────────────────
class PendingSessionSaveTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        login.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        login.application = None

    async def test_unapproved_login_saves_pending_session_exactly_once(self) -> None:
        uid = 3201
        saved_session = "pending-string-session"
        client = SimpleNamespace(
            session=SimpleNamespace(save=lambda: saved_session),
            disconnect=AsyncMock(),
        )
        login.login_ctx[uid] = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="hash",
            started_at=time.time(),
        )

        with (
            patch.object(
                login,
                "_validate_signed_in_account",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                login.db,
                "get_user",
                new=AsyncMock(
                    return_value={
                        "uid": uid,
                        "is_admin": 0,
                        "is_blocked": 0,
                        "session": "",
                        "awaiting_approval": 0,
                    }
                ),
            ),
            patch.object(
                login.db, "set_pending_approval", new=AsyncMock(return_value=True)
            ) as set_pending_approval,
            patch.object(login.db, "set_pending", new=AsyncMock()) as set_pending,
            patch.object(login.db, "set_session", new=AsyncMock()) as set_session,
            patch.object(
                login.db, "set_awaiting_approval", new=AsyncMock()
            ) as awaiting,
            patch.object(login, "notify_super_for_approval", new=AsyncMock()) as notify,
            patch.object(
                login, "revoke_telegram_session", new=AsyncMock(return_value=True)
            ) as revoke,
        ):
            await login._finalize_login_locked(uid)

        # Sessiya faqat bir marta, atomik pending+awaiting yozuvi bilan saqlanadi.
        set_pending_approval.assert_awaited_once_with(uid, saved_session)
        set_pending.assert_not_awaited()
        set_session.assert_not_awaited()
        awaiting.assert_not_awaited()
        revoke.assert_not_awaited()
        notify.assert_awaited_once_with(uid)
        self.assertIsNone(login.get_step(uid))
        self.assertNotIn(uid, login.login_ctx)

        markup = self.bot.send_message.await_args.kwargs["reply_markup"]
        self.assertEqual(reply_texts(markup), [T.BTN_PENDING])

    async def test_failed_pending_save_revokes_fresh_authorization(self) -> None:
        uid = 3202
        client = SimpleNamespace(
            session=SimpleNamespace(save=lambda: "pending-string-session"),
            disconnect=AsyncMock(),
        )
        login.login_ctx[uid] = LoginCtx(
            client=client,
            phone="+998901234567",
            phone_code_hash="hash",
            started_at=time.time(),
        )

        with (
            patch.object(
                login,
                "_validate_signed_in_account",
                new=AsyncMock(return_value=True),
            ),
            patch.object(
                login.db, "get_user", new=AsyncMock(return_value={"uid": uid})
            ),
            patch.object(
                login.db, "set_pending_approval", new=AsyncMock(return_value=False)
            ),
            patch.object(
                login, "revoke_telegram_session", new=AsyncMock(return_value=True)
            ) as revoke,
            patch.object(login, "notify_super_for_approval", new=AsyncMock()) as notify,
        ):
            await login._finalize_login_locked(uid)

        revoke.assert_awaited_once_with("pending-string-session", uid)
        notify.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────
# TELEFON BO'YICHA KOD LIMITI
# ─────────────────────────────────────────────────────────────────────────
class PhoneCodeLimitTests(unittest.IsolatedAsyncioTestCase):
    PHONE = "+998901234567"

    async def asyncSetUp(self) -> None:
        login.phone_limiter.reset(login.phone_rate_key(self.PHONE))
        self.bot = SimpleNamespace(send_message=AsyncMock())
        login.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        login.phone_limiter.reset(login.phone_rate_key(self.PHONE))
        login.application = None

    def test_phone_key_uses_digits_only(self) -> None:
        self.assertEqual(login.phone_rate_key(self.PHONE), 998901234567)
        self.assertEqual(login.phone_rate_key("+998 90 123-45-67"), 998901234567)
        self.assertEqual(login.phone_rate_key(""), 0)

    def test_phone_limiter_is_separate_from_uid_limiter(self) -> None:
        self.assertIsNot(login.phone_limiter, main.rate_limiter)
        self.assertEqual(login.phone_limiter._window_for("phone"), 3600)

    async def test_fourth_request_is_blocked_before_telegram_client(self) -> None:
        for _ in range(3):
            self.assertTrue(login.take_phone_code_slot(self.PHONE)[0])

        with patch("bot.login.TelegramClient") as telegram_client:
            await login.request_code(4001, self.PHONE)

        telegram_client.assert_not_called()
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(
            self.bot.send_message.await_args.args[1],
            T.PHONE_CODE_LIMIT_REACHED.format(
                minutes=login.phone_limiter.get_wait_time(
                    login.phone_rate_key(self.PHONE), "phone"
                )
            ),
        )

    async def test_third_request_is_still_allowed(self) -> None:
        for _ in range(2):
            self.assertTrue(login.take_phone_code_slot(self.PHONE)[0])
        self.assertTrue(login.take_phone_code_slot(self.PHONE)[0])

        # Shundan keyingina limit tugaydi.
        allowed, wait_min = login.take_phone_code_slot(self.PHONE)
        self.assertFalse(allowed)
        self.assertGreaterEqual(wait_min, 1)

    async def test_janitor_cleans_phone_limiter_and_uid_limiter(self) -> None:
        with (
            patch.object(main, "expire_stale_logins", new=AsyncMock(return_value=0)),
            patch.object(main.rate_limiter, "cleanup_all", MagicMock()) as uid_cleanup,
            patch.object(main.Login, "cleanup_sms_attempts", MagicMock()),
            patch.object(
                login.phone_limiter, "cleanup_all", MagicMock()
            ) as phone_cleanup,
        ):
            await main.janitor_tick()

        uid_cleanup.assert_called_once()
        phone_cleanup.assert_called_once()

    async def test_expired_code_resend_is_blocked_before_send_code_request(
        self,
    ) -> None:
        uid = 4101
        for _ in range(3):
            login.take_phone_code_slot(self.PHONE)

        client = SimpleNamespace(
            is_connected=lambda: True,
            sign_in=AsyncMock(side_effect=PhoneCodeExpiredError(None)),
            send_code_request=AsyncMock(),
            disconnect=AsyncMock(),
        )
        login.login_ctx[uid] = LoginCtx(
            client=client,
            phone=self.PHONE,
            phone_code_hash="hash",
            started_at=time.time(),
        )
        login.sms_attempts.pop(uid, None)

        try:
            await login.attempt_signin(uid, "12345")
        finally:
            login.login_ctx.pop(uid, None)
            login.sms_attempts.pop(uid, None)

        client.send_code_request.assert_not_awaited()
        self.bot.send_message.assert_awaited_once()
        self.assertEqual(
            self.bot.send_message.await_args.args[1],
            T.PHONE_CODE_LIMIT_REACHED.format(
                minutes=login.phone_limiter.get_wait_time(
                    login.phone_rate_key(self.PHONE), "phone"
                )
            ),
        )

    async def test_cleanup_phone_requests_drops_expired_records(self) -> None:
        login.take_phone_code_slot(self.PHONE)
        key = login.phone_rate_key(self.PHONE)
        self.assertIn(key, login.phone_limiter._records)

        with patch("core.rate_limit.time.time", return_value=time.time() + 7200):
            self.assertEqual(login.cleanup_phone_requests(), 1)
        self.assertNotIn(key, login.phone_limiter._records)


# ─────────────────────────────────────────────────────────────────────────
# PENDING SESSION EGASI (session_manager)
# ─────────────────────────────────────────────────────────────────────────
class FakeOwnerClient:
    instances: ClassVar[list[FakeOwnerClient]] = []
    me_id: int | None = 42
    error: Exception | None = None

    def __init__(self, *_args, **_kwargs):
        self.disconnected = False
        self.__class__.instances.append(self)

    async def connect(self) -> None:
        return None

    async def disconnect(self) -> None:
        self.disconnected = True

    async def get_me(self):
        if self.__class__.error:
            raise self.__class__.error
        if self.__class__.me_id is None:
            return None
        return SimpleNamespace(id=self.__class__.me_id)


class PendingOwnerValidationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        FakeOwnerClient.instances.clear()
        FakeOwnerClient.me_id = 42
        FakeOwnerClient.error = None

    async def _validate(self, session: str = "session", uid: int = 42) -> str:
        with (
            patch.object(session_manager, "TelegramClient", FakeOwnerClient),
            patch.object(
                session_manager, "StringSession", side_effect=lambda value: value
            ),
        ):
            return await validate_telegram_session_owner(session, uid)

    async def test_matching_uid_is_valid(self) -> None:
        self.assertEqual(await self._validate("session", 42), VALID)
        self.assertTrue(FakeOwnerClient.instances[-1].disconnected)

    async def test_other_uid_is_mismatch(self) -> None:
        FakeOwnerClient.me_id = 777
        self.assertEqual(await self._validate("session", 42), MISMATCH)
        self.assertTrue(FakeOwnerClient.instances[-1].disconnected)

    async def test_missing_authorization_is_invalid(self) -> None:
        FakeOwnerClient.me_id = None
        self.assertEqual(await self._validate("session", 42), INVALID)

    async def test_empty_session_is_invalid(self) -> None:
        self.assertEqual(await validate_telegram_session_owner("", 42), INVALID)

    async def test_definitive_errors_are_invalid(self) -> None:
        for error in (
            AuthKeyUnregisteredError(None),
            SessionRevokedError(None),
            UserDeactivatedError(None),
        ):
            with self.subTest(error=type(error).__name__):
                FakeOwnerClient.error = error
                self.assertEqual(await self._validate("session", 42), INVALID)
        FakeOwnerClient.error = None

    async def test_temporary_errors_are_not_invalid(self) -> None:
        for error in (
            FloodWaitError(None, 90),
            asyncio.TimeoutError(),
            OSError("network down"),
            RuntimeError("telegram api hiccup"),
        ):
            with self.subTest(error=type(error).__name__):
                FakeOwnerClient.error = error
                self.assertEqual(await self._validate("session", 42), TEMPORARY)
                self.assertTrue(FakeOwnerClient.instances[-1].disconnected)
        FakeOwnerClient.error = None

    async def test_malformed_session_is_invalid(self) -> None:
        with patch.object(
            session_manager, "StringSession", side_effect=ValueError("bad session")
        ):
            self.assertEqual(
                await validate_telegram_session_owner("not-a-session", 42), INVALID
            )

    async def test_revoke_treats_definitive_invalid_as_cleanup(self) -> None:
        for error in (AuthKeyUnregisteredError(None), SessionRevokedError(None)):
            with self.subTest(error=type(error).__name__):
                FakeOwnerClient.error = error
                with (
                    patch.object(session_manager, "TelegramClient", FakeOwnerClient),
                    patch.object(
                        session_manager,
                        "StringSession",
                        side_effect=lambda value: value,
                    ),
                ):
                    self.assertTrue(
                        await session_manager.revoke_telegram_session("session", 42)
                    )
        FakeOwnerClient.error = None

    async def test_revoke_keeps_flood_as_failure(self) -> None:
        FakeOwnerClient.error = FloodWaitError(None, 30)
        with (
            patch.object(session_manager, "TelegramClient", FakeOwnerClient),
            patch.object(
                session_manager, "StringSession", side_effect=lambda value: value
            ),
        ):
            self.assertFalse(
                await session_manager.revoke_telegram_session("session", 42)
            )
        FakeOwnerClient.error = None


# ─────────────────────────────────────────────────────────────────────────
# BAZA: ATOMIK PENDING → SESSION
# ─────────────────────────────────────────────────────────────────────────
class PendingApprovalDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.old_path = db.DB_PATH
        db.DB_PATH = self.db_path
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_set_pending_approval_stores_encrypted_secret_and_flag(self) -> None:
        uid = 7001
        await db.upsert_user(uid, name="Ali Valiyev")
        self.assertTrue(await db.set_pending_approval(uid, "pending-secret"))

        user = await db.get_user(uid)
        self.assertEqual(user["pending_session"], "pending-secret")
        self.assertEqual(user["session"], "")
        self.assertTrue(user["awaiting_approval"])

        async with db._conn().execute(
            "SELECT session, pending_session FROM users WHERE uid = ?", (uid,)
        ) as cursor:
            raw = await cursor.fetchone()
        self.assertTrue(raw["pending_session"].startswith("enc:v1:"))
        self.assertNotIn("pending-secret", raw["pending_session"])

    async def test_approve_pending_user_promotes_atomically(self) -> None:
        uid = 7002
        expires = calc_expires(DEFAULT_DURATION_DAYS)
        await db.upsert_user(uid, name="Vali Aliyev")
        await db.set_pending_approval(uid, "pending-secret")

        self.assertTrue(await db.approve_pending_user(uid, expires))

        user = await db.get_user(uid)
        self.assertEqual(user["session"], "pending-secret")
        self.assertEqual(user["pending_session"], "")
        self.assertFalse(user["awaiting_approval"])
        self.assertTrue(user["is_admin"])
        self.assertEqual(user["tariff_expires_at"], expires)
        self.assertEqual(user["interval_min"], DEFAULT_INTERVAL_MIN)

        # Pending yo'q — ikkinchi marta promotion bo'lmaydi va session tegilmaydi.
        self.assertFalse(await db.approve_pending_user(uid, expires))
        self.assertEqual((await db.get_user(uid))["session"], "pending-secret")

    async def test_approve_pending_user_keeps_existing_interval(self) -> None:
        uid = 7003
        await db.upsert_user(uid, name="Hasan Aliyev", is_admin=1, interval_min=25)
        await db.set_pending_approval(uid, "pending-secret")

        self.assertTrue(await db.approve_pending_user(uid, calc_expires(30)))
        self.assertEqual((await db.get_user(uid))["interval_min"], 25)
        self.assertEqual(await db.get_interval(uid), 25)

    async def test_clear_pending_approval_wipes_secret_and_flag(self) -> None:
        uid = 7004
        await db.upsert_user(uid, name="Husan Aliyev")
        await db.set_pending_approval(uid, "pending-secret")

        self.assertTrue(await db.clear_pending_approval(uid))
        user = await db.get_user(uid)
        self.assertEqual(user["pending_session"], "")
        self.assertFalse(user["awaiting_approval"])
        self.assertEqual(user["session"], "")

    async def test_first_approval_sets_expiry_and_default_interval(self) -> None:
        uid = 7005
        expires = calc_expires(DEFAULT_DURATION_DAYS)
        await db.upsert_user(uid, name="Sardor Aliyev", awaiting_approval=1)

        self.assertTrue(await db.approve_user(uid, expires))
        user = await db.get_user(uid)
        self.assertEqual(user["tariff_expires_at"], expires)
        self.assertEqual(user["interval_min"], DEFAULT_INTERVAL_MIN)

    async def test_reapproval_keeps_manual_interval_and_expiry(self) -> None:
        uid = 7006
        first_expires = calc_expires(DEFAULT_DURATION_DAYS)
        await db.upsert_user(uid, name="Nodir Aliyev", awaiting_approval=1)
        await db.approve_user(uid, first_expires)
        await db.set_interval(uid, 15)

        await db.upsert_user(uid, awaiting_approval=1)
        await db.approve_user(uid, calc_expires(90))

        user = await db.get_user(uid)
        self.assertEqual(user["interval_min"], 15)
        self.assertEqual(user["tariff_expires_at"], first_expires)

    def test_default_interval_config_is_60_and_clamped(self) -> None:
        import config.config as cfg

        self.assertEqual(DEFAULT_INTERVAL_MIN, 60)
        self.assertEqual(MIN_INTERVAL_MIN, cfg.MIN_INTERVAL_MIN)
        self.assertLessEqual(cfg.MIN_INTERVAL_MIN, cfg.DEFAULT_INTERVAL_MIN)
        self.assertLessEqual(cfg.DEFAULT_INTERVAL_MIN, cfg.MAX_INTERVAL_MIN)

        try:
            for raw, expected in (
                ("999999", cfg.MAX_INTERVAL_MIN),
                ("1", cfg.MIN_INTERVAL_MIN),
                ("60", 60),
            ):
                with patch.dict(os.environ, {"DEFAULT_INTERVAL_MIN": raw}):
                    importlib.reload(cfg)
                    self.assertEqual(cfg.DEFAULT_INTERVAL_MIN, expected)
        finally:
            os.environ.pop("DEFAULT_INTERVAL_MIN", None)
            importlib.reload(cfg)
        self.assertEqual(cfg.DEFAULT_INTERVAL_MIN, 60)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN TASDIG'I
# ─────────────────────────────────────────────────────────────────────────
class AdminApprovalFlowTests(unittest.IsolatedAsyncioTestCase):
    UID = 8001

    async def asyncSetUp(self) -> None:
        self.bot = SimpleNamespace(send_message=AsyncMock())
        AA.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        AA.application = None

    @staticmethod
    def _update():
        return SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )

    def _enter_common(
        self, stack, *, pending: str, verdict: str, revoke_ok: bool = True
    ):
        """Umumiy patchlarni ExitStack'ga kiradiradi va mocklarni qaytaradi."""
        stack.enter_context(
            patch.object(
                AA.db,
                "get_user",
                new=AsyncMock(
                    return_value={
                        "uid": self.UID,
                        "is_admin": 0,
                        "awaiting_approval": 1,
                        "session": "",
                        "running": 0,
                    }
                ),
            )
        )
        stack.enter_context(
            patch.object(AA.db, "get_pending", new=AsyncMock(return_value=pending))
        )
        validate = stack.enter_context(
            patch.object(
                AA,
                "validate_telegram_session_owner",
                new=AsyncMock(return_value=verdict),
            )
        )
        revoke = stack.enter_context(
            patch.object(
                AA,
                "revoke_telegram_session",
                new=AsyncMock(return_value=revoke_ok),
            )
        )
        stack.enter_context(
            patch.object(AA, "user_card_markup", new=AsyncMock(return_value="card"))
        )
        return validate, revoke

    async def test_valid_pending_is_promoted_without_revoking(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            validate, revoke = self._enter_common(
                stack, pending="pending-session", verdict=VALID
            )
            promote = stack.enter_context(
                patch.object(
                    AA.db, "approve_pending_user", new=AsyncMock(return_value=True)
                )
            )
            legacy_approve = stack.enter_context(
                patch.object(AA.db, "approve_user", new=AsyncMock())
            )
            clear = stack.enter_context(
                patch.object(AA.db, "clear_pending_approval", new=AsyncMock())
            )
            del_pending = stack.enter_context(
                patch.object(AA.db, "del_pending", new=AsyncMock())
            )

            await AA._action_approve_locked(update, 999, self.UID)

        validate.assert_awaited_once_with("pending-session", self.UID)
        promote.assert_awaited_once_with(self.UID, calc_expires(DEFAULT_DURATION_DAYS))
        revoke.assert_not_awaited()
        clear.assert_not_awaited()
        del_pending.assert_not_awaited()
        legacy_approve.assert_not_awaited()

        # Foydalanuvchiga to'g'ridan-to'g'ri asosiy menyu yuboriladi.
        self.bot.send_message.assert_awaited_once()
        args, kwargs = self.bot.send_message.await_args
        self.assertEqual(args[0], self.UID)
        self.assertEqual(args[1], T.USER_APPROVED_ACTIVE)
        self.assertEqual(
            set(reply_texts(kwargs["reply_markup"])),
            set(reply_texts(kb_main())),
        )
        # Sessiya qiymati hech qanday xabarda oshkor qilinmaydi.
        admin_text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertNotIn("pending-session", admin_text)
        self.assertNotIn("pending-session", args[1])

    async def test_mismatch_revokes_and_clears_pending_state(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            _, revoke = self._enter_common(
                stack, pending="pending-session", verdict=MISMATCH
            )
            promote = stack.enter_context(
                patch.object(AA.db, "approve_pending_user", new=AsyncMock())
            )
            legacy_approve = stack.enter_context(
                patch.object(AA.db, "approve_user", new=AsyncMock())
            )
            clear = stack.enter_context(
                patch.object(AA.db, "clear_pending_approval", new=AsyncMock())
            )

            await AA._action_approve_locked(update, 999, self.UID)

        revoke.assert_awaited_once_with("pending-session", self.UID)
        clear.assert_awaited_once_with(self.UID)
        promote.assert_not_awaited()
        legacy_approve.assert_not_awaited()
        args, kwargs = self.bot.send_message.await_args
        self.assertEqual(args[1], T.PENDING_SESSION_MISMATCH)
        self.assertEqual(
            set(reply_texts(kwargs["reply_markup"])),
            set(reply_texts(kb_login())),
        )

    async def test_mismatch_keeps_pending_when_revoke_fails(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            self._enter_common(
                stack, pending="pending-session", verdict=MISMATCH, revoke_ok=False
            )
            promote = stack.enter_context(
                patch.object(AA.db, "approve_pending_user", new=AsyncMock())
            )
            legacy_approve = stack.enter_context(
                patch.object(AA.db, "approve_user", new=AsyncMock())
            )
            clear = stack.enter_context(
                patch.object(AA.db, "clear_pending_approval", new=AsyncMock())
            )

            await AA._action_approve_locked(update, 999, self.UID)

        clear.assert_not_awaited()
        promote.assert_not_awaited()
        legacy_approve.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()
        self.assertIn(
            "bekor qilinmadi",
            update.callback_query.edit_message_text.await_args.args[0],
        )

    async def test_temporary_error_keeps_pending_session(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            _, revoke = self._enter_common(
                stack, pending="pending-session", verdict=TEMPORARY
            )
            promote = stack.enter_context(
                patch.object(AA.db, "approve_pending_user", new=AsyncMock())
            )
            legacy_approve = stack.enter_context(
                patch.object(AA.db, "approve_user", new=AsyncMock())
            )
            clear = stack.enter_context(
                patch.object(AA.db, "clear_pending_approval", new=AsyncMock())
            )
            del_pending = stack.enter_context(
                patch.object(AA.db, "del_pending", new=AsyncMock())
            )

            await AA._action_approve_locked(update, 999, self.UID)

        revoke.assert_not_awaited()
        clear.assert_not_awaited()
        del_pending.assert_not_awaited()
        promote.assert_not_awaited()
        legacy_approve.assert_not_awaited()
        self.bot.send_message.assert_not_awaited()
        self.assertIn(
            "saqlab qolindi",
            update.callback_query.edit_message_text.await_args.args[0],
        )

    async def test_invalid_pending_is_cleared_then_legacy_approval(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            self._enter_common(stack, pending="pending-session", verdict=INVALID)
            promote = stack.enter_context(
                patch.object(AA.db, "approve_pending_user", new=AsyncMock())
            )
            legacy_approve = stack.enter_context(
                patch.object(AA.db, "approve_user", new=AsyncMock(return_value=True))
            )
            del_pending = stack.enter_context(
                patch.object(AA.db, "del_pending", new=AsyncMock())
            )

            await AA._action_approve_locked(update, 999, self.UID)

        del_pending.assert_awaited_once_with(self.UID)
        promote.assert_not_awaited()
        legacy_approve.assert_awaited_once_with(
            self.UID, calc_expires(DEFAULT_DURATION_DAYS)
        )
        args, kwargs = self.bot.send_message.await_args
        self.assertEqual(args[1], T.USER_APPROVED)
        self.assertEqual(
            set(reply_texts(kwargs["reply_markup"])),
            set(reply_texts(kb_login())),
        )

    async def test_legacy_approval_without_pending_asks_one_login(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            validate, _ = self._enter_common(stack, pending="", verdict=VALID)
            promote = stack.enter_context(
                patch.object(AA.db, "approve_pending_user", new=AsyncMock())
            )
            legacy_approve = stack.enter_context(
                patch.object(AA.db, "approve_user", new=AsyncMock(return_value=True))
            )

            await AA._action_approve_locked(update, 999, self.UID)

        validate.assert_not_awaited()
        promote.assert_not_awaited()
        legacy_approve.assert_awaited_once_with(
            self.UID, calc_expires(DEFAULT_DURATION_DAYS)
        )
        args, kwargs = self.bot.send_message.await_args
        self.assertEqual(args[1], T.USER_APPROVED)
        self.assertEqual(
            set(reply_texts(kwargs["reply_markup"])),
            set(reply_texts(kb_login())),
        )

    async def test_approval_messages_show_tariff_and_interval(self) -> None:
        update = self._update()
        with contextlib.ExitStack() as stack:
            self._enter_common(stack, pending="pending-session", verdict=VALID)
            stack.enter_context(
                patch.object(
                    AA.db, "approve_pending_user", new=AsyncMock(return_value=True)
                )
            )

            await AA._action_approve_locked(update, 999, self.UID)

        admin_text = update.callback_query.edit_message_text.await_args.args[0]
        for fragment in (
            f"{DEFAULT_DURATION_DAYS} kun",
            f"{DEFAULT_INTERVAL_MIN} daqiqa",
            "qayta so'ralmaydi",
        ):
            self.assertIn(fragment, admin_text)
        user_text = self.bot.send_message.await_args.args[1]
        self.assertIn(f"{DEFAULT_DURATION_DAYS} kun", user_text)
        self.assertIn(f"{DEFAULT_INTERVAL_MIN} daqiqa", user_text)

    async def test_approval_notification_promises_no_second_code(self) -> None:
        text = T.new_user_notification("Ali Valiyev", "+998901234567", "ali", 8002)
        self.assertIn(f"{DEFAULT_DURATION_DAYS} kun", text)
        self.assertIn(f"{DEFAULT_INTERVAL_MIN} daqiqa", text)
        self.assertIn("qayta kiritish shart emas", text)


if __name__ == "__main__":
    unittest.main()
