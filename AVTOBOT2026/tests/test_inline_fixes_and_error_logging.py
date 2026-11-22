"""Inline kontekstdagi xatolar va markaziy xato/kamchilik yozuvchi testlari.

Qamlov (VPS logida aniqlangan xatolar):
- X1: ``mg:find`` («🔍 Guruhlarni topish») inline callback'dan
      chaqirilganda ``update.message`` = None bo'ladi →
      ``AttributeError: 'NoneType' object has no attribute 'reply_text'``;
- X2/X3: ``tadm:rename`` / ``tadm:message`` — ``edit_message_text`` Reply
      klaviatura bilan chaqiriladi →
      ``BadRequest: Inline keyboard expected``;
- X4: ``mg:global`` (interval oynasi) inline kontekstda buziladi;
- X6: xatolar va kamchiliklar to'liq traceback bilan logga yoziladi.
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

from bot import keyboards as KB  # noqa: E402
from bot import teams as Tm  # noqa: E402
from bot import texts as T  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from core.errlog import log_error, log_event, log_gap  # noqa: E402
from core.utils import reply_text_safe  # noqa: E402

ADMIN_UID = 77001
MEMBER_UID = 77002
ADMIN_PHONE = "+998901110001"


class FakeMessage:
    def __init__(self) -> None:
        self.text = ""
        self.out: list[str] = []

    async def reply_text(self, text, reply_markup=None, **kwargs):
        self.out.append(text)
        return self

    async def edit_text(self, text, reply_markup=None, **kwargs):
        self.out.append(text)

    @property
    def last(self) -> str:
        return self.out[-1] if self.out else ""


class FakeQuery:
    def __init__(self) -> None:
        self.out: list[str] = []
        self.answers: list[str] = []
        self.markups: list = []

    async def answer(self, text="", show_alert=False, **kwargs):
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None, **kwargs):
        self.out.append(text)
        self.markups.append(reply_markup)


class FakeUpdate:
    """Inline kontekstni simulyatsiya qiladi: `message` = None."""

    def __init__(self, uid: int, *, inline: bool = True) -> None:
        self.effective_user = SimpleNamespace(
            id=uid, full_name=f"User {uid}", username=f"user{uid}"
        )
        self.callback_query = FakeQuery()
        if inline:
            # Inline kontekst: `update.message` mavjud EMAS.
            self.message = None
            self.callback_query.message = FakeMessage()
        else:
            self.message = FakeMessage()
            self.callback_query.message = self.message

    @property
    def effective_message(self):
        return self.message


class InlineFixTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "inline_fix.db"
        session_crypto._fernet = __import__(
            "cryptography.fernet", fromlist=["Fernet"]
        ).Fernet(
            __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key()
        )
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def _make_admin_with_team(self, name: str = "Jamoa") -> int:
        await db.upsert_user(
            ADMIN_UID, name="Admin", phone=ADMIN_PHONE, is_team_admin=1
        )
        team = await db.create_team_for_admin(
            ADMIN_UID, name, max_users=5, admin_expires_at=None
        )
        await db.set_team_admin(ADMIN_UID, int(team["id"]), max_users=5)
        return int(team["id"])

    # ── X1: skanerlash inline kontekstda ────────────────────────────
    async def test_discover_groups_works_in_inline_context(self) -> None:
        """«🔍 Guruhlarni topish» inline bosilganda xato bermasligi kerak.

        VPS logida: `data='mg:find' AttributeError: 'NoneType' object has
        no attribute 'reply_text'` (bot/groups.py:641).
        """
        from bot import groups as G

        await db.upsert_user(MEMBER_UID, name="Vali", is_admin=1)
        # Sessiya yo'q → `DISCOVER_NO_SESSION` xabari beriladi.
        up = FakeUpdate(MEMBER_UID, inline=True)
        await G.discover_groups(up)

        self.assertTrue(
            up.callback_query.message.out,
            "inline kontekstda xabar yuborilishi kerak (xato bermasligi kerak)",
        )
        self.assertIn(T.DISCOVER_NO_SESSION, up.callback_query.message.out[-1])

    async def test_discover_groups_no_session_does_not_raise(self) -> None:
        """Sessiya yo'q bo'lsa — istisno chiqmasligi kerak."""
        from bot import groups as G

        await db.upsert_user(MEMBER_UID, name="Vali", session="SESS")
        up = FakeUpdate(MEMBER_UID, inline=True)
        # Xato chiqsa test yiqiladi — bu asosiy maqsad.
        await G.discover_groups(up)

    # ── X4: interval oynasi inline kontekstda ───────────────────────
    async def test_begin_set_interval_works_in_inline_context(self) -> None:
        """«⏰ Vaqt» inline kontekstda xato bermasligi kerak."""
        from bot import timer as Tm

        await db.upsert_user(MEMBER_UID, name="Vali", session="SESS")
        up = FakeUpdate(MEMBER_UID, inline=True)
        await Tm.begin_set_interval(up)

        self.assertTrue(
            up.callback_query.message.out,
            "inline kontekstda xabar yuborilishi kerak",
        )

    # ── X2/X3: inline klaviatura ────────────────────────────────────
    async def test_kb_input_cancel_inline_is_inline_keyboard(self) -> None:
        """Inline bekor tugmasi — `InlineKeyboardMarkup` bo'lishi kerak."""
        from telegram import InlineKeyboardMarkup

        kb = KB.kb_input_cancel_inline()
        self.assertIsInstance(kb, InlineKeyboardMarkup)

    async def test_team_rename_uses_inline_keyboard(self) -> None:
        """`tadm:rename` inline klaviatura ishlatishi kerak.

        VPS logida: `data='tadm:rename' BadRequest: Inline keyboard expected`.
        """
        from telegram import InlineKeyboardMarkup

        await self._make_admin_with_team()
        up = FakeUpdate(ADMIN_UID, inline=True)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:rename")

        self.assertTrue(up.callback_query.out, "nomlash oynasi ochilishi kerak")
        markup = up.callback_query.markups[-1]
        self.assertIsInstance(
            markup,
            InlineKeyboardMarkup,
            "inline klaviatura bo'lishi kerak (Reply — BadRequest beradi)",
        )

    async def test_team_message_uses_inline_keyboard(self) -> None:
        """`tadm:message` inline klaviatura ishlatishi kerak.

        VPS logida: `data='tadm:message' BadRequest: Inline keyboard expected`.
        """
        from telegram import InlineKeyboardMarkup

        await self._make_admin_with_team()
        up = FakeUpdate(ADMIN_UID, inline=True)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:message")

        self.assertTrue(up.callback_query.out, "xabar yuborish oynasi ochilishi kerak")
        markup = up.callback_query.markups[-1]
        self.assertIsInstance(markup, InlineKeyboardMarkup)

    # ── reply_text_safe ─────────────────────────────────────────────
    async def test_reply_text_safe_inline_falls_back_to_query_message(self) -> None:
        """Inline kontekstda `update.message` None bo'lsa — callback xabariga yozadi."""
        up = FakeUpdate(MEMBER_UID, inline=True)
        ok = await reply_text_safe(up, " Salom")
        self.assertTrue(ok)
        self.assertEqual(up.callback_query.message.out[-1], " Salom")

    async def test_reply_text_safe_want_message_returns_message(self) -> None:
        """`want_message=True` — yuborilgan xabar obyektini qaytaradi."""
        up = FakeUpdate(MEMBER_UID, inline=True)
        sent = await reply_text_safe(up, "Salom", want_message=True)
        self.assertIsNotNone(sent)
        self.assertTrue(hasattr(sent, "edit_text"))

    async def test_reply_text_safe_want_message_none_when_failed(self) -> None:
        """Yuborib bo'lmasa — `None` qaytadi (AttributeError emas)."""
        up = FakeUpdate(MEMBER_UID, inline=True)
        up.callback_query.message = None
        sent = await reply_text_safe(up, "Salom", want_message=True)
        self.assertIsNone(sent)

    # ── X6: markaziy yozuvchi ───────────────────────────────────────
    async def test_log_error_writes_traceback(self) -> None:
        """`log_error` to'liq traceback yozishi kerak."""
        with patch("core.errlog.log") as fake_log:
            try:
                raise ValueError("test xatosi")
            except ValueError as exc:
                log_error(123, "Test kontekst", exc, action="tadm:stats")

        self.assertTrue(fake_log.called)
        args = fake_log.call_args[0]
        text = args[0]
        self.assertIn("XATO", text)
        self.assertIn("uid=123", text)
        self.assertIn("action=tadm:stats", text)
        self.assertIn("ValueError", text)
        self.assertIn("Traceback", text)

    async def test_log_gap_writes_warning(self) -> None:
        """`log_gap` warning darajasida yozishi kerak."""
        with patch("core.errlog.log") as fake_log:
            log_gap(123, "Foydalanuvchi topilmadi", action="tadm:member:1")

        args = fake_log.call_args[0]
        self.assertEqual(args[1], "warning")
        self.assertIn("KAMCHILIK", args[0])
        self.assertIn("uid=123", args[0])

    async def test_log_event_writes_info(self) -> None:
        """`log_event` info darajasida yozishi kerak."""
        with patch("core.errlog.log") as fake_log:
            log_event(123, "Jamoa ochildi", action="tadm:panel")

        args = fake_log.call_args[0]
        self.assertEqual(args[1], "info")
        self.assertIn("Jamoa ochildi", args[0])

    async def test_log_error_never_raises(self) -> None:
        """Yozuvchi o'zi xato bersa — ham yotib qolmasligi kerak."""
        with patch("core.errlog.log", side_effect=RuntimeError("log ishlamadi")):
            # Xato chiqmasligi kerak.
            try:
                raise ValueError("test")
            except ValueError as exc:
                log_error(1, "K", exc)

    async def test_log_gap_never_raises(self) -> None:
        """`log_gap` ham xato bermasligi kerak."""
        with patch("core.errlog.log", side_effect=RuntimeError("log ishlamadi")):
            log_gap(1, "K")

    # ── Jamoa admini callback xatolari ──────────────────────────────
    async def test_team_admin_callback_error_is_logged(self) -> None:
        """Jamoa admini callback xatosi — logga yozilishi kerak."""
        await self._make_admin_with_team()
        up = FakeUpdate(ADMIN_UID, inline=True)

        with patch("core.errlog.log") as fake_log:
            with patch.object(
                Tm, "_handle_team_admin_callback_inner", side_effect=RuntimeError("xato")
            ):
                await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:stats")

        self.assertTrue(fake_log.called, "xato logga yozilishi kerak")
        text = fake_log.call_args[0][0]
        self.assertIn("XATO", text)
        self.assertIn("Jamoa admini paneli", text)
        # Foydalanuvchi javob olishi kerak.
        self.assertTrue(up.callback_query.out)

    async def test_team_admin_permission_gap_is_logged(self) -> None:
        """Jamoa admini huquqi yo'q — kamchilik sifatida yozilishi kerak."""
        await db.upsert_user(MEMBER_UID, name="A'zo", phone="+998901110002")

        up = FakeUpdate(MEMBER_UID, inline=True)
        with patch("core.errlog.log") as fake_log:
            await Tm.handle_team_admin_callback(up, MEMBER_UID, "tadm:stats")

        self.assertTrue(fake_log.called, "kamchilik logga yozilishi kerak")
        self.assertEqual(fake_log.call_args[0][1], "warning")
        self.assertIn("KAMCHILIK", fake_log.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
