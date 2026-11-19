"""👑 Jamoa admini oqimi — foydalanuvchi bloklanmasligi.

Qamlov:
- super admin'ga xabar **fon task**'ida yuboriladi — foydalanuvchi
  javobni darhol oladi;
- xabar yuborish sekin bo'lsa ham foydalanuvchi kutib qolmaydi;
- xabar yetkazilmasa (xato/timeout) jamoa oqimi buzilmaydi;
- jamoa admini o'z jamoasi yaratilgandan keyin **darhol** tasdiqlanadi.
"""

from __future__ import annotations

import asyncio
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

from cryptography.fernet import Fernet

from bot import teams as Tm
from core import database as db
from core import session_crypto

UID = 3601


class TeamNotifyNonBlockingTests(unittest.IsolatedAsyncioTestCase):
    """Super admin'ga xabar foydalanuvchini kechiktirmasligi kerak."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(UID, name="Vali", is_admin=1, session="SESS")

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _update(self):
        status = SimpleNamespace(edit_text=AsyncMock())
        message = SimpleNamespace(reply_text=AsyncMock(return_value=status))
        return (
            SimpleNamespace(
                effective_user=SimpleNamespace(id=UID),
                message=message,
            ),
            message,
        )

    async def test_notify_is_scheduled_as_background_task(self) -> None:
        """Xabar fon task'ida yuboriladi — darhol qaytadi."""
        called = asyncio.Event()

        async def _slow_notify(uid, name, size):
            called.set()

        with patch.object(Tm, "notify_super_team_admin", new=_slow_notify):
            Tm.schedule_notify_super_team_admin(UID, "Jamoa", 10)
            # Vaqtni kutamiz — task boshlanishi uchun.
            await asyncio.wait_for(called.wait(), timeout=2)

        self.assertTrue(called.is_set(), "xabar yuborilmadi")

    async def test_notify_does_not_block_caller(self) -> None:
        """Sekin xabar yuborish chaqiruvchini bloklamasligi kerak."""
        release = asyncio.Event()

        async def _blocking_notify(uid, name, size):
            await release.wait()

        with patch.object(Tm, "notify_super_team_admin", new=_blocking_notify):
            # Chaqiruv darhol qaytishi kerak (bloklanmasligi).
            await asyncio.wait_for(
                asyncio.get_running_loop().run_in_executor(
                    None,
                    lambda: Tm.schedule_notify_super_team_admin(UID, "J", 5),
                ),
                timeout=1.0,
            )
            release.set()

    async def test_notify_failure_does_not_break_flow(self) -> None:
        """Xabar yuborish xatosi jamoa oqimini buzmasligi kerak."""
        async def _failing_notify(uid, name, size):
            raise RuntimeError("Telegram timeout")

        with patch.object(Tm, "notify_super_team_admin", new=_failing_notify):
            Tm.schedule_notify_super_team_admin(UID, "Jamoa", 10)
            # Task xato bilan tugashi kerak — oqimga ta'sir qilmasin.
            await asyncio.sleep(0.05)

    async def test_notify_helper_swallows_errors(self) -> None:
        """``notify_super_team_admin`` o'z ichida xatoni yutadi."""
        bot = SimpleNamespace(
            send_message=AsyncMock(side_effect=RuntimeError("timeout"))
        )
        app = SimpleNamespace(bot=bot)
        old_app = Tm.application
        Tm.application = app
        try:
            await Tm.notify_super_team_admin(UID, "Jamoa", 10)
        finally:
            Tm.application = old_app

    async def test_team_admin_registration_replies_before_notify(self) -> None:
        """Foydalanuvchi avval tasdiqlanadi, keyin xabar yuboriladi.

        ``notify_super_team_admin`` **sekin** bo'lsa ham, foydalanuvchining
        javobi **darhol** yuborilishi kerak — ya'ni ro'yxatdan o'tkazish
        xabar yuborilishini **kutmaydi**.
        """
        notify_started = asyncio.Event()
        release = asyncio.Event()

        async def _blocking_notify(uid, name, size):
            notify_started.set()
            await release.wait()

        update, message = self._update()
        with patch.object(Tm, "notify_super_team_admin", new=_blocking_notify):
            await Tm.handle_team_admin_name(update, UID, "Test Jamoa")

            # Foydalanuvchi javob bergan bo'lishi kerak — xabar yuborilishini
            # kutmasdan.
            self.assertTrue(message.reply_text.await_count >= 1)

            # Xabar **fon task**'ida boshlanadi (bloklamaydi).
            await asyncio.wait_for(notify_started.wait(), timeout=2)

            # Xabar tugamagan — foydalanuvchi esa allaqon javob oldi.
            self.assertFalse(release.is_set())

            release.set()


if __name__ == "__main__":
    unittest.main()
