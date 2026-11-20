"""🧪 Restartda posting to'xtamasligi va holat ko'rinishi.

Muammo: VPS da kod yangilanganda (``systemctl restart``) foydalanuvchining
ishlayotgan worker'i to'xtardi va ``running`` bayrog'i ``False`` bo'lib
qolardi. Natijada:

* foydalanuvchining e'lonlari to'xtab qolardi;
* u qaytadan ``▶️ Start`` bosishi kerak edi;
* lekin ``⛔ Stop`` bosgan foydalanuvchilar ham avtomatik tiklanmasin
  edi (ular to'xtab tursin).

Tuzatish:

* ``worker/worker.py`` — jarayon to'xtayotganda (``SIGTERM``) ``running``
  **saqlanadi**; foydalanuvchi o'zi ``⛔ Stop`` bosgan bo'lsa esa
  ``running`` ``False`` qilinadi;
* ``bot/menu.py`` — asosiy menyu ustida holat qatori ko'rsatiladi
  (``▶️ Start`` va ``⛔ Stop`` tugmalari **doimiy va alohida** qoladi).
"""

from __future__ import annotations

import asyncio
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

from bot import menu as Menu  # noqa: E402
from bot import texts as T  # noqa: E402
from worker import worker as W  # noqa: E402


class ShutdownFlagTests(unittest.TestCase):
    """Jarayon to'xtash bayrog'i."""

    def setUp(self) -> None:
        W.set_process_shutting_down(False)

    def tearDown(self) -> None:
        W.set_process_shutting_down(False)

    def test_flag_defaults_false(self) -> None:
        self.assertFalse(W._is_process_shutdown())

    def test_flag_can_be_set(self) -> None:
        W.set_process_shutting_down(True)
        self.assertTrue(W._is_process_shutdown())


class PostingLoopRunningFlagTests(unittest.IsolatedAsyncioTestCase):
    """``posting_loop`` ning ``finally`` bloki."""

    def setUp(self) -> None:
        W.set_process_shutting_down(False)

    def tearDown(self) -> None:
        W.set_process_shutting_down(False)

    async def test_user_stop_clears_running(self) -> None:
        """Foydalanuvchi o'zi Stop bosgan — ``running`` o'chiriladi."""
        stop = asyncio.Event()
        stop.set()  # ← foydalanuvchining Stop tugmasi

        with (
            patch.object(W.db, "set_running", new=AsyncMock()) as set_running,
            patch.object(W.db, "get_user", new=AsyncMock(return_value=None)),
            patch.object(W.db, "get_chats", new=AsyncMock(return_value=[])),
            patch.object(W.db, "get_posts", new=AsyncMock(return_value=[])),
            patch.object(W, "sleep_or_stop", new=AsyncMock(return_value=True)),
        ):
            await W.posting_loop(999, stop)

        set_running.assert_awaited_with(999, False)

    async def test_process_shutdown_keeps_running(self) -> None:
        """Jarayon to'xtayotgan (restart) — ``running`` SAQLANADI."""
        stop = asyncio.Event()
        stop.set()  # stop_all() ham stop_event ni set qiladi
        W.set_process_shutting_down(True)

        with (
            patch.object(W.db, "set_running", new=AsyncMock()) as set_running,
            patch.object(W.db, "get_user", new=AsyncMock(return_value=None)),
            patch.object(W.db, "get_chats", new=AsyncMock(return_value=[])),
            patch.object(W.db, "get_posts", new=AsyncMock(return_value=[])),
            patch.object(W, "sleep_or_stop", new=AsyncMock(return_value=True)),
        ):
            await W.posting_loop(999, stop)

        set_running.assert_not_awaited()


class StateLineTests(unittest.IsolatedAsyncioTestCase):
    """Menyu ustidagi holat qatori."""

    async def test_state_on_when_worker_running(self) -> None:
        """Worker ishlayotganda ``🟢`` holati."""
        with patch.object(Menu, "worker_manager", new=SimpleNamespace(is_running=lambda _u: True)):
            self.assertEqual(Menu.state_line(1), T.STATE_ON)

    async def test_state_off_when_worker_stopped(self) -> None:
        """Worker ishlamayotganda ``🔴`` holati."""
        with patch.object(Menu, "worker_manager", new=SimpleNamespace(is_running=lambda _u: False)):
            self.assertEqual(Menu.state_line(1), T.STATE_OFF)

    async def test_state_off_without_manager(self) -> None:
        """Worker manager yo'q bo'lsa — ``🔴``."""
        with patch.object(Menu, "worker_manager", new=None):
            self.assertEqual(Menu.state_line(1), T.STATE_OFF)

    async def test_show_home_includes_state_and_main_menu(self) -> None:
        """Asosiy menyu holat qatori bilan chiqishi kerak."""
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(message=message)

        with (
            patch.object(Menu, "worker_manager", new=SimpleNamespace(is_running=lambda _u: True)),
            patch.object(Menu.KB, "kb_main_for", new=AsyncMock(return_value="KB")),
        ):
            await Menu.show_home(update, 42)

        text = message.reply_text.await_args.args[0]
        self.assertIn(T.STATE_ON, text)
        self.assertIn("Asosiy menyu", text)


class RestoreWorkersTests(unittest.IsolatedAsyncioTestCase):
    """Restartdan keyin worker tiklanishi."""

    async def test_running_user_is_restored(self) -> None:
        """``running=True`` bo'lgan foydalanuvchi tiklanadi."""
        import main as M

        user = {
            "uid": 42,
            "running": 1,
            "is_admin": 1,
            "is_blocked": 0,
            "session": "sess",
            "tariff_expires_at": None,
        }
        start_worker = AsyncMock(return_value=True)

        with (
            patch.object(M.db, "get_all_running", new=AsyncMock(return_value=[42])),
            patch.object(M.db, "get_user", new=AsyncMock(return_value=user)),
            patch.object(M.db, "get_chats", new=AsyncMock(return_value=[{"id": 1}])),
            patch.object(M.db, "get_posts", new=AsyncMock(return_value=[{"id": 1}])),
            patch.object(M.db, "is_tariff_expired", new=AsyncMock(return_value=False)),
            patch.object(M.db, "set_running", new=AsyncMock()) as set_running,
            patch.object(M, "worker_manager", new=SimpleNamespace(start_worker=start_worker)),
        ):
            await M.restore_running_workers()

        start_worker.assert_awaited_once_with(42)
        set_running.assert_not_awaited()

    async def test_stopped_user_is_not_restored(self) -> None:
        """``running=False`` bo'lgan foydalanuvchi tiklanmaydi."""
        import main as M

        user = {
            "uid": 43,
            "running": 0,
            "is_admin": 1,
            "is_blocked": 0,
            "session": "sess",
            "tariff_expires_at": None,
        }
        start_worker = AsyncMock(return_value=True)

        with (
            patch.object(M.db, "get_all_running", new=AsyncMock(return_value=[43])),
            patch.object(M.db, "get_user", new=AsyncMock(return_value=user)),
            patch.object(M.db, "get_chats", new=AsyncMock(return_value=[{"id": 1}])),
            patch.object(M.db, "get_posts", new=AsyncMock(return_value=[{"id": 1}])),
            patch.object(M.db, "is_tariff_expired", new=AsyncMock(return_value=False)),
            patch.object(M.db, "set_running", new=AsyncMock()),
            patch.object(M, "worker_manager", new=SimpleNamespace(start_worker=start_worker)),
        ):
            await M.restore_running_workers()

        start_worker.assert_not_awaited()


class StartStopButtonsStaySeparateTests(unittest.TestCase):
    """``▶️ Start`` va ``⛔ Stop`` — doimiy va alohida tugmalar."""

    def test_buttons_are_separate_and_always_present(self) -> None:
        from bot import keyboards as KB

        for running in (True, False):
            rows = KB.kb_main(running=running).keyboard
            flat = [b.text for r in rows for b in r]
            self.assertIn(T.BTN_START, flat)
            self.assertIn(T.BTN_STOP, flat)
            # Ikkalasi bitta qatorda, lekin alohida tugmalar.
            first = [b.text for b in rows[0]]
            self.assertEqual(first, [T.BTN_START, T.BTN_STOP])

    def test_buttons_do_not_change_with_state(self) -> None:
        """Holat o'zgarganda tugma matnlari o'zgarmasligi kerak."""
        from bot import keyboards as KB

        on = [b.text for r in KB.kb_main(running=True).keyboard for b in r]
        off = [b.text for r in KB.kb_main(running=False).keyboard for b in r]
        self.assertEqual(on, off)


if __name__ == "__main__":
    unittest.main()
