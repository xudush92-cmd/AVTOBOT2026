"""🧪 Polling supervisor qayta ishga tushirish logikasi.

VPS da kuzatilgan muammo: bot polling to'xtaganida supervisor uni
qayta ishga tushirishga uringan, lekin:

* ``stop()`` ning "This Updater is not running!" xatosi
  ``contextlib.suppress`` bilan **yashirilgan**;
* shuning uchun ``_running`` ``True`` bo'lib qolgan;
* ``start_polling()`` "This Updater is already running!" xatosi bilan
  urilgan;
* supervisor har siklda "Polling qayta boshlandi" deb yozgan, lekin
  polling **haqiqatan ishga tushmagan** — bot javob bermagan.

Qamlov:
- xato matni logda **ko'rinadi** (faqat klassi emas);
- ``_running`` qoldig'i tozalanadi;
- ``start_polling`` xatosi **yashirilmaydi**.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

import main as M  # noqa: E402


class FakeUpdater:
    """PTB ``Updater`` ning muhim qismini takrorlaydi."""

    def __init__(self, *, running: bool = False, initialized: bool = True) -> None:
        self._running = running
        self._initialized = initialized
        self.started = 0
        self.stopped = 0
        self.start_error: Exception | None = None

    @property
    def running(self) -> bool:
        return self._running

    async def stop(self) -> None:
        if not self._running:
            raise RuntimeError("This Updater is not running!")
        self._running = False
        self.stopped += 1

    async def initialize(self) -> None:
        if not self._initialized:
            self._initialized = True

    async def start_polling(self, **_kw) -> None:
        if self.start_error is not None:
            raise self.start_error
        if self._running:
            raise RuntimeError("This Updater is already running!")
        self._running = True
        self.started += 1


class FakeApp:
    def __init__(self, updater: FakeUpdater) -> None:
        self.updater = updater


class RestartPollingTests(unittest.IsolatedAsyncioTestCase):
    """``_restart_polling`` to'g'ri ishlashi kerak."""

    async def test_restarts_when_running(self) -> None:
        """Ishlayotgan polling to'xtatilib, qayta boshladi."""
        up = FakeUpdater(running=True)
        app = FakeApp(up)

        await M._restart_polling(app)

        self.assertEqual(up.stopped, 1)
        self.assertEqual(up.started, 1)
        self.assertTrue(up.running)

    async def test_restarts_when_already_stopped(self) -> None:
        """``stop()`` xatasi bo'lsa ham qayta boshlashi kerak."""
        up = FakeUpdater(running=False)
        app = FakeApp(up)

        await M._restart_polling(app)

        # `stop()` chaqiriladi va xatoni yashiriladi, lekin `start_polling`
        # **albatta** chaqirilishi kerak.
        self.assertEqual(up.started, 1)
        self.assertTrue(up.running)

    async def test_clears_stale_running_flag(self) -> None:
        """``_running`` qoldig'i True bo'lsa ham tozalanishi kerak."""
        up = FakeUpdater(running=True)
        app = FakeApp(up)

        # `stop()` xato beradi va `_running` ni o'zgartirmaydi.
        async def bad_stop() -> None:
            raise RuntimeError("This Updater is not running!")

        up.stop = bad_stop  # type: ignore[assignment]

        await M._restart_polling(app)

        self.assertEqual(up.started, 1, "start_polling chaqirilishi kerak edi")

    async def test_start_polling_error_is_not_hidden(self) -> None:
        """``start_polling`` xatosi yashirilmasligi kerak."""
        up = FakeUpdater(running=False)
        up.start_error = RuntimeError("This Updater is already running!")
        app = FakeApp(up)

        with self.assertRaises(RuntimeError):
            await M._restart_polling(app)


class PollingSupervisorLoggingTests(unittest.IsolatedAsyncioTestCase):
    """Supervisor xato matnini logga yozishi kerak."""

    async def test_error_message_includes_text(self) -> None:
        """Logda faqat klassi emas, xato matni ham ko'rinishi kerak."""
        up = FakeUpdater(running=False)
        app = FakeApp(up)

        async def bad_start(**_kw) -> None:
            raise RuntimeError("Bu aniq xato matni")

        up.start_polling = bad_start  # type: ignore[assignment]

        messages: list[str] = []
        with patch.object(M, "log", side_effect=lambda m, *_a, **_k: messages.append(m)):
            with self.assertRaises(RuntimeError):
                await M._restart_polling(app)

        self.assertTrue(
            any("Polling qayta ishga tushmadi" in m for m in messages),
            f"start_polling xatosi loglanmadi: {messages}",
        )
        self.assertTrue(
            any("Bu aniq xato matni" in m for m in messages),
            f"xato matni logda yo'q: {messages}",
        )


if __name__ == "__main__":
    unittest.main()
