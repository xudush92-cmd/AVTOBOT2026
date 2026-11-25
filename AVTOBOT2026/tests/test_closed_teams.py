"""🔒 Jamoa tizimi — jamoalar yopiq, jamoa adminini faqat super admin.

Qamlov:
- oddiy foydalanuvchi jamoalarni **ko'ra olmaydi**;
- oddiy foydalanuvchi jamoaga **qo'shila olmaydi**;
- oddiy foydalanuvchi jamoa admini **bo'la olmaydi**;
- super admin jamoa adminlarini telefon orqali tayyorlaydi;
- jamoa admini birinchi marta «👥 Jamoam» bosganda jamoani yaratadi;
- jamoa admini faqat **o'z** jamoasini ko'radi;
- tasdiqlash: jamoasiz → super admin, jamoa a'zosi → jamoa admini.
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

from cryptography.fernet import Fernet

from bot import teams as Tm
from core import database as db
from core import session_crypto

USER_1 = 111000222
ADMIN_A = 333000444
ADMIN_B = 555000666


class ClosedTeamsTests(unittest.IsolatedAsyncioTestCase):
    """Jamoalar yopiq — foydalanuvchilar boshqa jamoalarni ko'rmaydi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()
        await db.upsert_user(USER_1, name="Oddiy", is_admin=1)
        await db.upsert_user(ADMIN_A, name="Admin A", is_admin=1, is_team_admin=1)
        await db.upsert_user(ADMIN_B, name="Admin B", is_admin=1, is_team_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    # ── Jamoalar yopiq ────────────────────────────────────────────────

    async def test_ordinary_user_cannot_see_teams(self) -> None:
        """Oddiy foydalanuvchi jamoalarni ko'ra olmaydi."""
        await db.create_team("Maxfiy Jamoa", ADMIN_A, max_users=5)

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_1),
            message=message,
        )
        await Tm.show_team_picker(update, USER_1)

        reply = message.reply_text.await_args.args[0]
        self.assertIn("yopiq", reply.lower())
        self.assertNotIn("Maxfiy Jamoa", reply)

    async def test_ordinary_user_cannot_join_team_by_callback(self) -> None:
        """Oddiy foydalanuvchi ``team:pick`` bilan jamoaga qo'shila olmaydi."""
        team = await db.create_team("Maxfiy Jamoa", ADMIN_A, max_users=5)
        q = SimpleNamespace(
            data=f"team:pick:{int(team['id'])}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=USER_1, full_name="Vali"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_pick_callback(
                update, USER_1, f"team:pick:{int(team['id'])}"
            )

        user = await db.get_user(USER_1)
        self.assertIsNone(user.get("team_id"))
        q.answer.assert_awaited()

    async def test_team_admin_sees_only_own_team(self) -> None:
        """Jamoa admini faqat o'z jamoasini ko'radi."""
        mine = await db.create_team("Mening Jamoam", ADMIN_A, max_users=5)
        await db.create_team("Boshqa Jamoa", ADMIN_B, max_users=5)

        teams = await Tm.admin_teams(ADMIN_A)
        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0]["name"], "Mening Jamoam")
        self.assertEqual(int(teams[0]["id"]), int(mine["id"]))

    async def test_team_admin_members_are_own_only(self) -> None:
        """Jamoa admini faqat o'z jamoasining a'zolarini ko'radi."""
        team_a = await db.create_team("Jamoa A", ADMIN_A, max_users=5)
        team_b = await db.create_team("Jamoa B", ADMIN_B, max_users=5)
        await db.upsert_user(
            USER_1, name="A'zo", team_id=int(team_a["id"]), owner_admin_uid=ADMIN_A
        )
        other = await db.get_team_members(int(team_b["id"]))
        self.assertNotIn(
            USER_1, [int(u["uid"]) for u in other], "boshqa jamoaning a'zosi ko'rinmasligi kerak"
        )

    # ── Jamoa admini faqat super admin tomonidan ──────────────────────

    async def test_ordinary_user_cannot_become_team_admin(self) -> None:
        """Oddiy foydalanuvchi jamoa admini bo'la olmaydi."""
        from bot.login import user_states

        user_states.pop(USER_1, None)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_1),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        await Tm.begin_team_admin_register(update, USER_1)

        self.assertIsNone(user_states.get(USER_1))
        reply = update.message.reply_text.await_args.args[0]
        self.assertIn("super admin", reply.lower())

    async def test_team_admin_creates_own_team(self) -> None:
        """Jamoa admini birinchi marta jamoani o'zi yaratadi."""
        from bot.login import user_states

        user_states.pop(ADMIN_A, None)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        await Tm.begin_team_admin_register(update, ADMIN_A)

        self.assertEqual(user_states.get(ADMIN_A, {}).get("step"), "team_admin_size")

    async def test_team_admin_panel_starts_team_creation(self) -> None:
        """Jamoasi yo'q jamoa admini «👥 Jamoam» bosganda yaratishni boshlaydi."""
        from bot.login import user_states

        user_states.pop(ADMIN_A, None)

        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=message,
        )
        await Tm.show_team_admin_panel(update, ADMIN_A)

        self.assertEqual(user_states.get(ADMIN_A, {}).get("step"), "team_admin_size")
        message.reply_text.assert_awaited()

    async def test_existing_team_panel_shows_team(self) -> None:
        """Jamoasi bor admin paneli jamoa ma'lumotini ko'rsatadi."""
        await db.create_team("Jamoa A", ADMIN_A, max_users=5)
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=message,
        )
        await Tm.show_team_admin_panel(update, ADMIN_A)

        reply = message.reply_text.await_args.args[0]
        self.assertIn("Jamoa A", reply)
        self.assertNotIn("team_admin_size", reply)

    # ── Tasdiqlash ────────────────────────────────────────────────────

    async def test_ordinary_user_is_notified_to_super_admin(self) -> None:
        """Jamoasiz foydalanuvchi → tasdiqlash xabari super admin'ga."""
        from bot import login as Login

        sent: list[int] = []

        class FakeApp:
            class bot:
                @staticmethod
                async def send_message(chat_id, text, **kwargs):
                    sent.append(chat_id)

        with patch.object(Login, "application", FakeApp):
            await Login.notify_super_for_approval(USER_1)

        from config.config import SUPER_ADMIN

        self.assertIn(SUPER_ADMIN, sent)

    async def test_team_member_is_notified_to_team_admin(self) -> None:
        """Jamoa a'zosi → tasdiqlash xabari jamoa adminiga boradi."""
        team = await db.create_team("Jamoa A", ADMIN_A, max_users=5)
        member = 888000999
        await db.upsert_user(
            member,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )

        from bot import login as Login

        sent: list[int] = []

        class FakeApp:
            class bot:
                @staticmethod
                async def send_message(chat_id, text, **kwargs):
                    sent.append(chat_id)

        with patch.object(Login, "application", FakeApp):
            await Login.notify_super_for_approval(member)

        self.assertIn(ADMIN_A, sent)

        from config.config import SUPER_ADMIN

        self.assertNotIn(SUPER_ADMIN, sent)

    # ── Sig'im nazorati ───────────────────────────────────────────────

    async def test_team_capacity_never_exceeded(self) -> None:
        """Jamoa sig'imi hech qachon oshmasligi kerak.

        Sig'im — jamoaning **a'zolar** soni. Jamoa admini (jamoa egasi)
        hisobga olinmaydi.
        """
        team = await db.create_team("Jamoa A", ADMIN_A, max_users=2)
        team_id = int(team["id"])
        # Jamoa admini jamoaning egasi — sig'imga hisoblanmaydi.
        await db.set_team_pending(ADMIN_A, team_id, ADMIN_A)

        ok1 = await db.set_team_pending(USER_1, team_id, ADMIN_A)
        self.assertTrue(ok1)
        self.assertTrue(
            await db.team_has_free_slot(team_id),
            "1 a'zo < limit 2 — yana joy bo'lishi kerak",
        )

        # Ikkinchi a'zo — sig'im to'ladi.
        ok2 = await db.set_team_pending(777000888, team_id, ADMIN_A)
        self.assertTrue(ok2)
        self.assertFalse(
            await db.team_has_free_slot(team_id),
            "sig'im to'lgan jamoaga yangi a'zo qo'shilmasligi kerak",
        )

        # Uchinchi a'zo — rad etiladi.
        other = 777000999
        await db.upsert_user(other, name="Uchinchi")
        self.assertFalse(await db.set_team_pending(other, team_id, ADMIN_A))


if __name__ == "__main__":
    unittest.main()
