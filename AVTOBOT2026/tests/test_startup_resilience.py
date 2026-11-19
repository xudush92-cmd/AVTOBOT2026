"""
Startup barqarorligi — bot bitta Telegram xatosi bilan o'lmasligi kerak.

Real muammo (server logida):
    main.py -> await app.bot.set_my_commands(...) -> telegram.error.TimedOut
    Natijada butun bot to'xtaydi (foydalanuvchilar javob olmaydi).

`set_my_commands` faqat menyu buyurqlarini ro'ylaydi — muvaffaqiyatsiz
bo'lsa ham bot ishlashda davom etishi kerak.

Ushbu test quyidagilarni tekshiradi:
- `_with_retry` — vaqtincha xatoni qayta urinib ko'radi;
- `set_bot_commands` — xato bo'lsa ham `False` qaytaradi (bot o'lmaydi).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from main import _with_retry, set_bot_commands


class WithRetryTests(unittest.IsolatedAsyncioTestCase):
    """``_with_retry`` — vaqtincha xatolarni qayta urinish."""

    async def test_returns_result_on_first_success(self) -> None:
        async def ok() -> str:
            return "natijа"

        self.assertEqual(await _with_retry(ok, attempts=3, delay=0), "natijа")

    async def test_retries_then_succeeds(self) -> None:
        calls = {"n": 0}

        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise TimeoutError("vaqtincha")
            return "muvaffaqiyat"

        result = await _with_retry(flaky, attempts=3, delay=0)
        self.assertEqual(result, "muvaffaqiyat")
        self.assertEqual(calls["n"], 3)

    async def test_raises_after_all_attempts(self) -> None:
        calls = {"n": 0}

        async def always_fail() -> None:
            calls["n"] += 1
            raise TimeoutError("doimiy")

        with self.assertRaises(TimeoutError):
            await _with_retry(always_fail, attempts=3, delay=0)
        self.assertEqual(calls["n"], 3)


class SetBotCommandsTests(unittest.IsolatedAsyncioTestCase):
    """``set_bot_commands`` — xato bo'lsa ham botni to'xtatmasligi kerak."""

    async def test_success_returns_true(self) -> None:
        class FakeBot:
            def __init__(self) -> None:
                self.commands: list = []

            async def set_my_commands(self, commands) -> None:
                self.commands = commands

        class FakeApp:
            def __init__(self) -> None:
                self.bot = FakeBot()

        app = FakeApp()
        ok = await set_bot_commands(app)
        self.assertTrue(ok)
        self.assertEqual(len(app.bot.commands), 3)

    async def test_failure_returns_false_and_does_not_raise(self) -> None:
        """Asosiy regressiya: set_my_commands xatosi botni o'ldirmasligi kerak."""

        class FakeBot:
            async def set_my_commands(self, commands) -> None:
                raise TimeoutError("Timed out")

        class FakeApp:
            def __init__(self) -> None:
                self.bot = FakeBot()

        app = FakeApp()
        # Xato raised bo'lmasligi kerak — aks holda butun bot to'xtaydi.
        ok = await set_bot_commands(app)
        self.assertFalse(ok)


class StartupFlowTests(unittest.TestCase):
    """main.py da startup qadamlari — himoyalangan bo'lishi kerak."""

    def test_set_my_commands_is_wrapped(self) -> None:
        """``set_my_commands`` to'g'ridan-to'g'ri awaited bo'lmasligi kerak."""
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "await set_bot_commands(app)",
            source,
            "set_my_commands must go through the safe wrapper",
        )
        self.assertNotIn(
            "await app.bot.set_my_commands(",
            source,
            "direct set_my_commands call would kill the bot on timeout",
        )

    def test_startup_uses_retry(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "main.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("await _with_retry(app.initialize)", source)
        self.assertIn("await _with_retry(", source)


if __name__ == "__main__":
    unittest.main()
