"""Login yakunidagi **tasdiqlash kontakti** regressiya testlari.

Qamlov (A7):
- jamoa a'zosi (havola orqali kelgan) — jamoa adminining telefon raqami
  ko'rsatiladi, super adminning raqami emas;
- jamoa asosi (jamoa admini) — tasdiq kutilmaydi, super admin raqami
  ko'rsatilmaydi, jamoa asosi xabari yuboriladi;
- jamoasiz foydalanuvchi — super adminning telefon raqami ko'rsatiladi.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from bot import login  # noqa: E402
from bot import texts as T  # noqa: E402
from bot.login import LoginCtx  # noqa: E402

SUPER_ADMIN = 123456789
ADMIN_UID = 99001
MEMBER_UID = 99002
ADMIN_PHONE = "+998901230001"
MEMBER_PHONE = "+998901230002"


class PendingContactTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        self.bot = SimpleNamespace(send_message=AsyncMock())
        login.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        login.login_ctx.clear()
        login.user_states.clear()
        login.application = None

    def _ctx(self, uid: int) -> None:
        client = SimpleNamespace(
            session=SimpleNamespace(save=lambda: "sess"), disconnect=AsyncMock()
        )
        login.login_ctx[uid] = LoginCtx(
            client=client,
            phone=MEMBER_PHONE,
            phone_code_hash="hash",
            started_at=time.time(),
        )

    async def _finalize(self, uid: int, user_row: dict) -> str:
        """Login yakunini bajaradi va yuborilgan matnni qaytaradi."""
        self._ctx(uid)
        with (
            patch.object(
                login, "_validate_signed_in_account", new=AsyncMock(return_value=True)
            ),
            patch.object(login.db, "get_user", new=AsyncMock(return_value=user_row)),
            patch.object(
                login.db, "set_pending_approval", new=AsyncMock(return_value=True)
            ),
            patch.object(login.db, "get_phone", new=AsyncMock(return_value=ADMIN_PHONE)),
            patch.object(
                login.db,
                "get_team",
                new=AsyncMock(return_value={"id": 5, "name": "Jamoa"}),
            ),
            patch.object(
                login, "schedule_notify_super_for_approval", new=MagicMock()
            ),
            patch.object(
                login, "revoke_telegram_session", new=AsyncMock(return_value=True)
            ),
        ):
            await login._finalize_login_locked(uid)
        # Oxirgi yuborilgan xabar — foydalanuvchiga tegishli.
        # ``send_message(chat_id, text, ...)`` — matn ikkinchi argumentda.
        return self.bot.send_message.await_args.args[1]

    async def test_team_member_sees_team_admin_phone(self) -> None:
        """Jamoa a'zosiga jamoa adminining raqami ko'rsatiladi."""
        text = await self._finalize(
            MEMBER_UID,
            {
                "uid": MEMBER_UID,
                "is_admin": 0,
                "is_blocked": 0,
                "session": "",
                "awaiting_approval": 0,
                "is_team_admin": 0,
                "owner_admin_uid": ADMIN_UID,
                "team_id": 5,
            },
        )
        self.assertIn(ADMIN_PHONE, text)
        self.assertNotIn(
            T.ADMIN_CONTACT_PHONE,
            text,
            "jamoa a'zosiga super admin raqami chiqmasligi kerak",
        )

    async def test_team_admin_ready_has_no_super_admin_phone(self) -> None:
        """Jamoa asosiga super admin raqami chiqmasligi kerak.

        Jamoa asosi super admin taklifi bilan birinchi marta ro'yxatdan
        o'tganda hali ``is_admin`` emas (u tasdiqlanmagan holda keladi),
        ammo ``is_team_admin`` allaqachon 1 — shuning uchun o'ziga
        "jamoa admini bo'ldingiz" xabarini olishi kerak.
        """
        with patch(
            "bot.teams.team_link", new=lambda tid: f"https://t.me/bot?start=team_{tid}"
        ):
            text = await self._finalize(
                ADMIN_UID,
                {
                    "uid": ADMIN_UID,
                    "is_admin": 0,
                    "is_blocked": 0,
                    "session": "",
                    "awaiting_approval": 0,
                    "is_team_admin": 1,
                    "owner_admin_uid": ADMIN_UID,
                    "team_id": 5,
                },
            )
        self.assertNotIn(
            T.ADMIN_CONTACT_PHONE,
            text,
            "jamoa asosiga super admin raqami chiqmasligi kerak",
        )
        self.assertIn("jamoa admini bo'ldingiz", text.lower())
        self.assertIn("start=team_5", text)

    async def test_plain_user_sees_super_admin_phone(self) -> None:
        """Jamoasiz foydalanuvchiga super admin raqami ko'rsatiladi."""
        text = await self._finalize(
            MEMBER_UID,
            {
                "uid": MEMBER_UID,
                "is_admin": 0,
                "is_blocked": 0,
                "session": "",
                "awaiting_approval": 0,
                "is_team_admin": 0,
                "owner_admin_uid": 0,
                "team_id": 0,
            },
        )
        self.assertIn(T.ADMIN_CONTACT_PHONE, text)

    async def test_team_admin_gets_no_approval_request(self) -> None:
        """Jamoa asosiga «yangi ariza» xabari yuborilmasligi kerak.

        Jamoa asosi allaqachon tasdiqlangan — u o'ziga o'zi ariza
        yubormasligi kerak (va tasdiqlash kutilmasligi kerak).
        """
        with (
            patch.object(
                login.db,
                "get_user_info",
                new=AsyncMock(return_value={"name": "Admin"}),
            ),
            patch.object(login.db, "get_user", new=AsyncMock(return_value={
                "uid": ADMIN_UID,
                "is_team_admin": 1,
                "owner_admin_uid": ADMIN_UID,
                "team_id": 5,
            })),
            patch.object(login.db, "get_phone", new=AsyncMock(return_value=ADMIN_PHONE)),
            patch.object(
                login.db, "get_team", new=AsyncMock(return_value={"id": 5, "name": "J"})
            ),
        ):
            await login.notify_super_for_approval(ADMIN_UID)

        self.bot.send_message.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
