"""
Telegram API ulanish sozlamalari — bot "javob bermay qolmasligi" uchun.

Muammo: PTB standart `connection_pool_size=1` va `read_timeout=5s`.
Long-polling (`getUpdates`, serverda 10s kutadi) connection'ni band qiladi
va boshqa so'rovlar (javob yuborish) "pool timeout" bilan uziladi.
Natijada bot ishlayotgan bo'lishiga qaramay javob bermaydi.

Ushbu test sozlamalar to'g'ri qo'yilganini tekshiradi.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from config import config as C


class TelegramConnectionSettingsTests(unittest.TestCase):
    """Ulanish pool'i va timeout'lar mos kelishi kerak."""

    def test_connection_pool_is_large_enough(self) -> None:
        """Pool kamida 4 ta bo'lishi kerak (polling + javoblar)."""
        self.assertGreaterEqual(
            C.TELEGRAM_CONNECTION_POOL_SIZE,
            4,
            "connection pool too small — long-polling blocks other requests",
        )

    def test_read_timeout_exceeds_long_poll_duration(self) -> None:
        """getUpdates serverda 10 soniya kutadi — read timeout undan uzun bo'lishi kerak."""
        self.assertGreater(
            C.TELEGRAM_GET_UPDATES_READ_TIMEOUT,
            10,
            "get_updates read timeout must exceed the 10s long-poll window",
        )

    def test_pool_timeout_is_generous(self) -> None:
        """Pool timeout kichik bo'lsa, javob yuborish uzilib ketadi."""
        self.assertGreaterEqual(
            C.TELEGRAM_POOL_TIMEOUT,
            5,
            "pool timeout too small — replies fail while polling holds the connection",
        )
        self.assertGreaterEqual(
            C.TELEGRAM_GET_UPDATES_POOL_TIMEOUT,
            5,
            "get_updates pool timeout too small",
        )

    def test_general_timeouts_are_sane(self) -> None:
        self.assertGreaterEqual(C.TELEGRAM_READ_TIMEOUT, 10)
        self.assertGreaterEqual(C.TELEGRAM_WRITE_TIMEOUT, 10)
        self.assertGreaterEqual(C.TELEGRAM_CONNECT_TIMEOUT, 5)


class PollingSupervisorTests(unittest.IsolatedAsyncioTestCase):
    """Polling supervisor — polling o'lsa, qayta boshlaydi."""

    async def test_supervisor_restarts_polling_when_task_dies(self) -> None:
        import asyncio

        from main import polling_supervisor

        class FakeUpdater:
            def __init__(self) -> None:
                self.stopped = 0
                self.initialized = 0
                self.started = 0
                # Haqiqiy task — "o'lgan" polling task'ini simulyatsiya qiladi.
                # PTB ichki atribut nomi: _Updater__polling_task
                self._Updater__polling_task = asyncio.create_task(self._dead())

            async def _dead(self) -> None:
                raise RuntimeError("Bad Gateway")

            async def stop(self) -> None:
                self.stopped += 1

            async def initialize(self) -> None:
                self.initialized += 1

            async def start_polling(self, **kwargs) -> None:
                self.started += 1

        class FakeApp:
            def __init__(self) -> None:
                self.updater = FakeUpdater()

        app = FakeApp()
        stop_event = asyncio.Event()

        supervisor = asyncio.create_task(polling_supervisor(app, stop_event))
        await asyncio.sleep(1.5)
        stop_event.set()
        supervisor.cancel()
        try:
            await supervisor
        except asyncio.CancelledError:
            pass

        self.assertGreaterEqual(
            app.updater.started,
            1,
            "supervisor must restart polling when the polling task dies",
        )
        self.assertGreaterEqual(app.updater.stopped, 1)
        self.assertGreaterEqual(app.updater.initialized, 1)


if __name__ == "__main__":
    unittest.main()
