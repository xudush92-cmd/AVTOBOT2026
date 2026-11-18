"""Guruhdan chiqarilish / guruhga yetib borolmaslik oqimi testlari.

Qamlov:
- bot guruhdan chiqarilganda (ChatWriteForbidden) foydalanuvchi
  birinchi urinishda ogohlantiriladi;
- xato turi bo'yicha aniq sabab ko'rsatiladi;
- MAX_GROUP_FAILS urinishdan keyin guruh avtomatik o'chiriladi;
- ogohlantirishda hech qanday kiritish/session ma'lumoti ko'rsatilmaydi.
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

from worker import worker as W  # noqa: E402


class GroupUnreachableTests(unittest.IsolatedAsyncioTestCase):
    """Guruhga yetib borib bo'lmagan holat — foydalanuvchi ogohlantirilishi."""

    def test_error_reasons_cover_all_handled_errors(self) -> None:
        """Barcha qo'llanadigan xato turlari uchun sabab mavjud."""
        handled = {
            "ChatWriteForbiddenError",
            "ChannelPrivateError",
            "PeerIdInvalidError",
            "UsernameNotOccupiedError",
            "UsernameInvalidError",
        }
        for name in handled:
            self.assertIn(
                name,
                W._GROUP_ERROR_REASONS,
                f"{name} uchun sabab matni topilmadi",
            )

    def test_chat_write_forbidden_mentions_admin(self) -> None:
        """Bot chiqarilgan holatda admin qilib qo'yish tavsiya qilinadi."""
        reason = W._GROUP_ERROR_REASONS["ChatWriteForbiddenError"]
        self.assertIn("admin", reason.lower())

    def test_private_channel_reason(self) -> None:
        """Yopiq guruh uchun ogohlantirish bor."""
        reason = W._GROUP_ERROR_REASONS["ChannelPrivateError"]
        self.assertTrue(reason.strip())

    async def test_notify_sends_message_with_reason(self) -> None:
        """Foydalanuvchiga xabar yuboriladi va sabab ko'rsatiladi."""
        sent = []

        async def _send(chat_id, text, **kwargs):
            sent.append((chat_id, text, kwargs))

        bot = SimpleNamespace(send_message=_send)
        app = SimpleNamespace(bot=bot)

        with patch.object(W, "application", app):
            await W._notify_group_unreachable(
                5001, "-1001234567890", "ChatWriteForbiddenError"
            )

        self.assertEqual(len(sent), 1)
        chat_id, text, kwargs = sent[0]
        self.assertEqual(chat_id, 5001)
        self.assertIn("-1001234567890", text)
        self.assertIn("chiqarilgan", text)
        self.assertEqual(kwargs.get("parse_mode"), "HTML")

    async def test_notify_unknown_error_has_generic_reason(self) -> None:
        """Noma'lum xato uchun umumiy sabab ishlatiladi."""
        sent = []

        async def _send(chat_id, text, **kwargs):
            sent.append((chat_id, text, kwargs))

        app = SimpleNamespace(bot=SimpleNamespace(send_message=_send))

        with patch.object(W, "application", app):
            await W._notify_group_unreachable(5001, "-100999", "SomeOtherError")

        self.assertEqual(len(sent), 1)
        self.assertIn("Guruhga xabar yuborib bo'lmadi", sent[0][1])

    async def test_notify_failure_does_not_raise(self) -> None:
        """Xabar yuborish xatosi posting oqimini buzmasligi kerak."""

        async def _send(*args, **kwargs):
            raise RuntimeError("telegram xatosi")

        app = SimpleNamespace(bot=SimpleNamespace(send_message=_send))

        with patch.object(W, "application", app):
            await W._notify_group_unreachable(5001, "-100123", "ChatWriteForbiddenError")

    async def test_notify_message_does_not_leak_session(self) -> None:
        """Xabarda sessiya kaliti yoki boshqa maxfiy ma'lumot yo'q."""
        sent = []

        async def _send(chat_id, text, **kwargs):
            sent.append(text)

        app = SimpleNamespace(bot=SimpleNamespace(send_message=_send))

        with patch.object(W, "application", app):
            await W._notify_group_unreachable(5001, "-100123", "PeerIdInvalidError")

        text = sent[0]
        self.assertNotIn("session", text.lower().replace("sessiya", ""))
        self.assertNotIn("api_id", text.lower())
        self.assertNotIn("hash", text.lower())

    def test_max_group_fails_is_positive(self) -> None:
        """Guruh o'chirish chegarasi musbat bo'lishi kerak."""
        from config.config import MAX_GROUP_FAILS

        self.assertGreater(MAX_GROUP_FAILS, 0)


if __name__ == "__main__":
    unittest.main()
