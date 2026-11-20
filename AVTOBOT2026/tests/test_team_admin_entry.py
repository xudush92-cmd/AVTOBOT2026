"""«👑 Admin bo'lish» tugmasi: login'dan oldin ham jamoa yaratishni boshlashi."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from cryptography.fernet import Fernet

from bot import texts as T
from core import database as db
from core import session_crypto

USER_ID = 77001


class TeamAdminEntryTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa admini bo'lish tugmasi login'dan mustaqil ishlashi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    def _update(self, text: str = "") -> SimpleNamespace:
        return SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_ID),
            message=SimpleNamespace(text=text, reply_text=AsyncMock()),
        )

    async def test_admin_button_is_rejected_for_new_user(self) -> None:
        """Ro'yxatdan o'tmagan user «👑 Admin bo'lish» bosolmaydi.

        Jamoa adminini **faqat super admin** yaratadi (telefon orqali
        tayyorlaydi). Oddiy foydalanuvchiga rad javobi beriladi.
        """
        import main as app_main

        update = self._update(T.BTN_TEAM_ADMIN)

        # Foydalanuvchi umuman ro'yxatda yo'q.
        self.assertIsNone(await db.get_user(USER_ID))

        await app_main.on_message(update, SimpleNamespace())

        update.message.reply_text.assert_awaited()

        # Jamoa yaratish oqimi boslanMAMALIGI kerak.
        from bot.login import user_states

        self.assertIsNone(
            user_states.get(USER_ID),
            "oddiy user uchun jamoa yaratish oqimi boshlanmasligi kerak",
        )

    async def test_admin_button_is_rejected_for_unapproved_user(self) -> None:
        """Tasdiqlanmagan user ham jamoa admini bo'la olmaydi."""
        import main as app_main

        await db.upsert_user(
            USER_ID, name="Otkazilgan", is_admin=0, awaiting_approval=1
        )

        update = self._update(T.BTN_TEAM_ADMIN)
        await app_main.on_message(update, SimpleNamespace())

        from bot.login import user_states

        self.assertIsNone(
            user_states.get(USER_ID),
            "tasdiqlanmagan user uchun jamoa yaratish oqimi boshlanmasligi kerak",
        )

    async def test_admin_button_starts_team_flow_for_team_admin(self) -> None:
        """Super admin tomonidan tayyorlangan jamoa admini jamoani yaratadi."""
        import main as app_main

        await db.upsert_user(
            USER_ID, name="Jamoa admini", is_admin=1, is_team_admin=1
        )

        update = self._update(T.BTN_TEAM_ADMIN)
        await app_main.on_message(update, SimpleNamespace())

        from bot.login import user_states

        self.assertEqual(
            user_states.get(USER_ID, {}).get("step"),
            "team_admin_size",
            "jamoa admini uchun jamoa yaratish oqimi boshlanishi kerak",
        )


class TeamAdminButtonRoutingTests(unittest.IsolatedAsyncioTestCase):
    """Kirish oynasida menyu tugmasi bosilsa, «Admin bo'lish» ishlashi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_admin_button_is_in_menu_buttons_set(self) -> None:
        """`BTN_TEAM_ADMIN` kirish oynasi ro'yxatida bo'lishi kerak.

        Eski klaviaturadagi foydalanuvchilar uchun matn o'zgarmaydi —
        tugma bosilganda jamoa admini uchun jamoa yaratish oqimi
        boshlanadi, oddiy user uchun esa rad javobi beriladi.
        """
        import main as app_main
        from bot import login as Login

        await db.upsert_user(
            USER_ID, name="Kirish oynasida", is_admin=0, awaiting_approval=0
        )

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_ID),
            message=SimpleNamespace(
                text=T.BTN_TEAM_ADMIN, reply_text=AsyncMock()
            ),
        )

        # Login oynasi holatiga o'tamiz.
        Login.user_states[USER_ID] = {"step": "phone"}

        await app_main.on_message(update, SimpleNamespace())

        from bot.login import user_states

        self.assertIsNone(
            user_states.get(USER_ID),
            "oddiy user uchun jamoa oqimi boshlanmasligi kerak",
        )
        self.assertEqual(
            T.BTN_TEAM_ADMIN,
            "👑 Admin bo'lish",
            "tugma matni o'zgarmasligi kerak",
        )


if __name__ == "__main__":
    unittest.main()
