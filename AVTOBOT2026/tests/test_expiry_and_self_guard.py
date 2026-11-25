"""🛡️ Muddat va jamoa xavfsizligi — PR #49.

Auditning qolgan to'rt bandi:

1. **Muddat eslatmasi takrorlanardi** — jamoa admini muddati tugagani
   haqida xabar **har daqiqada** yuborilardi (janitor har daqiqada
   ishga tushadi, xabar yuborilganini belgilamagan).

2. **Jamoadan chiqishda muddat cheksiz bo'lib qolardi** — «uning
   muddati ham tugdi» degan xabar yuborilardi, lekin bazada muddat
   ``NULL`` (chekisiz) qilib qo'yilardi — ya'ni muddat **tugamaydi**.

3. **``shift_expires(None, -1)``** — cheksiz muddatni «kamaytirish»
   o'rniga **darhol tugatardi** (``calc_expires(0)``).

4. **Jamoa admini o'zini bloklay olardi** — jamoa egasining
   ``owner_admin_uid`` o'zining qiymatiga teng, shuning uchun
   ``block``/``unblock``/``term`` o'ziga nisbatan ishlagan.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from bot import teams as Tm
from config.config import SUPER_ADMIN
from core import database as db
from core.utils import calc_expires, is_expired, shift_expires

SUPER = SUPER_ADMIN
ADMIN = 88001
MEMBER = 88002


class _Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name) / "t.db"
        await db.init_db()
        await db.upsert_user(SUPER, name="Super", is_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self._old_db
        self._tmp.cleanup()


class AdminExpiryNotificationTests(_Base):
    """Band 1 — muddat eslatmasi faqat bir marta."""

    async def test_notified_flag_exists(self) -> None:
        await db.upsert_user(ADMIN, name="Jamoa admini", is_admin=1,
                             is_team_admin=1)
        self.assertFalse(await db.is_admin_expiry_notified(ADMIN))

    async def test_mark_notified(self) -> None:
        await db.upsert_user(ADMIN, name="Jamoa admini", is_admin=1,
                             is_team_admin=1)
        await db.mark_admin_expiry_notified(ADMIN)
        self.assertTrue(await db.is_admin_expiry_notified(ADMIN))

    async def test_set_admin_expires_clears_flag(self) -> None:
        """Muddat yangilanganda ogohlantirish qayta yuborilishi kerak."""
        await db.upsert_user(ADMIN, name="Jamoa admini", is_admin=1,
                             is_team_admin=1)
        await db.mark_admin_expiry_notified(ADMIN)
        self.assertTrue(await db.is_admin_expiry_notified(ADMIN))

        await db.set_admin_expires(ADMIN, calc_expires(30))
        self.assertFalse(
            await db.is_admin_expiry_notified(ADMIN),
            "muddat yangilanganda belgi tozalanishi kerak",
        )

    async def test_set_team_admin_clears_flag(self) -> None:
        """Yangi jamoa admini tayinlanganda belgi tozalanadi."""
        await db.upsert_user(ADMIN, name="Jamoa admini", is_admin=1)
        await db.mark_admin_expiry_notified(ADMIN)
        team = await db.create_team("Jamoa", ADMIN, max_users=5)
        await db.set_team_admin(ADMIN, int(team["id"]), max_users=5)
        self.assertFalse(await db.is_admin_expiry_notified(ADMIN))


class LeaveTeamExpiryTests(_Base):
    """Band 2 — jamoadan chiqishda muddat cheksiz bo'lmaydi."""

    async def _make_member(self) -> None:
        team = await db.create_team("Jamoa", ADMIN, max_users=5)
        await db.set_team_admin(
            ADMIN, int(team["id"]), max_users=5, admin_expires_at=calc_expires(30)
        )
        await db.upsert_user(
            MEMBER,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN,
            tariff_expires_at=calc_expires(30),
        )

    async def test_muddat_tugadi_cheksiz_emas(self) -> None:
        """Chiqishdan keyin muddat **bugun tugagan** bo'lishi kerak."""
        await self._make_member()
        await db.leave_team(MEMBER)
        user = await db.get_user(MEMBER)
        expires = user["tariff_expires_at"]
        self.assertIsNotNone(
            expires, "muddat cheksiz (NULL) qilinmashi kerak"
        )
        self.assertTrue(
            is_expired(expires),
            "chiqishdan keyin muddat tugagan bo'lishi kerak",
        )

    async def test_super_admin_expiry_kept(self) -> None:
        """Super admin bergan muddat saqlanadi."""
        await self._make_member()
        await db.upsert_user(
            MEMBER,
            name="A'zo",
            team_id=int((await db.get_team_by_name(ADMIN, "Jamoa"))["id"]),
            owner_admin_uid=SUPER_ADMIN,
            tariff_expires_at=calc_expires(30),
        )
        await db.leave_team(MEMBER)
        user = await db.get_user(MEMBER)
        self.assertIsNotNone(user["tariff_expires_at"])
        self.assertFalse(is_expired(user["tariff_expires_at"]))


class ShiftExpiresTests(unittest.TestCase):
    """Band 3 — cheksiz muddatni kamaytirib bo'lmaydi."""

    def test_none_minus_returns_none(self) -> None:
        """``None`` + manfiy → ``None`` (rad etiladi)."""
        self.assertIsNone(shift_expires(None, -1))
        self.assertIsNone(shift_expires(None, -30))

    def test_none_plus_sets_date(self) -> None:
        """``None`` + musbat → bugundan keyingi sana."""
        result = shift_expires(None, 30)
        self.assertIsNotNone(result)
        self.assertFalse(is_expired(result))

    def test_existing_minus_reduces(self) -> None:
        """Mavjud muddat manfiy bilan kamayadi."""
        before = calc_expires(30)
        after = shift_expires(before, -10)
        self.assertIsNotNone(after)
        self.assertTrue(after < before)


class TeamAdminExpiryRunTests(_Base):
    """Band 1 — xabar faqat bir marta yuboriladi (janitor tez-tez ishlaydi)."""

    async def _make_expired_admin(self) -> None:
        """Muddati tugagan jamoa admini."""
        team = await db.create_team("Jamoa", ADMIN, max_users=5)
        await db.set_team_admin(
            ADMIN,
            int(team["id"]),
            max_users=5,
            admin_expires_at=calc_expires(-1),
        )
        await db.upsert_user(
            ADMIN,
            name="Jamoa admini",
            is_admin=1,
            is_team_admin=1,
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN,
            admin_expires_at=calc_expires(-1),
        )

    async def test_expiry_notice_sent_once(self) -> None:
        """Ikki marta chaqirilganda xabar faqat bir marta yuboriladi."""
        import main as M

        await self._make_expired_admin()

        sent: list[tuple[int, str]] = []

        async def fake_send(chat_id, text, **kwargs):
            sent.append((int(chat_id), str(text)))
            return True

        class _Bot:
            async def send_message(self, chat_id, text, **kwargs):
                return await fake_send(chat_id, text, **kwargs)

        old_bot = M.application
        old_worker = M.worker_manager
        old_pool = M.client_pool
        try:
            M.application = SimpleNamespace(bot=_Bot())
            M.worker_manager = None
            M.client_pool = None
            await M.check_team_admin_expiry()
            first_count = len(sent)
            # Ikkinchi chaqiruv — janitor yana ishladi.
            await M.check_team_admin_expiry()
        finally:
            M.application = old_bot
            M.worker_manager = old_worker
            M.client_pool = old_pool

        self.assertGreater(first_count, 0, "xabar yuborilishi kerak")
        self.assertEqual(
            len(sent),
            first_count,
            "xabar takrorlanmashi kerak (har daqiqada yuborilmasin)",
        )

    async def test_flag_set_after_notification(self) -> None:
        """Xabar yuborilgandan keyin belgi qo'yiladi."""
        import main as M

        await self._make_expired_admin()

        class _Bot:
            async def send_message(self, chat_id, text, **kwargs):
                return True

        old_bot = M.application
        old_worker = M.worker_manager
        old_pool = M.client_pool
        try:
            M.application = SimpleNamespace(bot=_Bot())
            M.worker_manager = None
            M.client_pool = None
            await M.check_team_admin_expiry()
        finally:
            M.application = old_bot
            M.worker_manager = old_worker
            M.client_pool = old_pool

        self.assertTrue(
            await db.is_admin_expiry_notified(ADMIN),
            "xabar yuborilgachan belgi qo'yilishi kerak",
        )


class SelfBlockTests(_Base):
    """Band 4 — jamoa admini o'ziga amal bajar olmaydi."""

    async def _make_admin_with_team(self) -> int:
        team = await db.create_team("Jamoa", ADMIN, max_users=5)
        await db.set_team_admin(
            ADMIN, int(team["id"]), max_users=5, admin_expires_at=calc_expires(30)
        )
        await db.upsert_user(
            ADMIN,
            name="Jamoa admini",
            is_admin=1,
            is_team_admin=1,
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN,
        )
        return int(team["id"])

    async def _run(self, action: str) -> AsyncMock:
        answer = AsyncMock()
        callback = SimpleNamespace(
            data=f"tadm:{action}:{ADMIN}",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=answer,
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )
        with patch.object(Tm, "_send", AsyncMock()):
            await Tm.handle_team_admin_callback(update, ADMIN, callback.data)
        return answer

    async def test_cannot_block_self(self) -> None:
        await self._make_admin_with_team()
        answer = await self._run("block")
        user = await db.get_user(ADMIN)
        self.assertFalse(
            user.get("is_blocked"),
            "jamoa admini o'zini bloklamasligi kerak",
        )
        answer.assert_awaited()

    async def test_cannot_unblock_self(self) -> None:
        await self._make_admin_with_team()
        await db.set_user_limits(ADMIN, is_blocked=1, blocked_by=ADMIN)
        answer = await self._run("unblock")
        user = await db.get_user(ADMIN)
        self.assertTrue(
            user.get("is_blocked"),
            "jamoa admini o'zini blokdan chiqara olmasligi kerak",
        )
        answer.assert_awaited()

    async def test_cannot_set_own_term(self) -> None:
        await self._make_admin_with_team()
        answer = await self._run("term")
        answer.assert_awaited()


if __name__ == "__main__":
    unittest.main()
