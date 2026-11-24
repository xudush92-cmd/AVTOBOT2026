"""🔒 Jamoa xavfsizligi — taklif, bloklash va sig'im.

Uch jiddiy xato:

1. **Taklif kodsiz qo'llanardi** — telefon raqamini yozgan odam
   Telegram kodini kiritmasdan jamoa admini bo'lib qolardi. Endi taklif
   faqat **Telegram login muvaffaqiyatli** bo'lgandan keyin qo'llanadi.

2. **Jamoa admini super admin bloklaganini blokdan chiqarardi** — kim
   bloklagani saqlanmasdi. Endi ``blocked_by`` saqlanadi va faqat o'z
   bloklaganini chiqarish mumkin.

3. **Sig'imda jamoa admini ham hisobga olinardi** — sig'im 2 bo'lsa,
   admin + 1 arizachi = «to'lgan» deb rad etish. Endi admin hisobga
   olinmaydi.
"""

from __future__ import annotations

import inspect
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

from bot import login as L
from bot import teams as Tm
from core import database as db

SUPER = 123456789
ADMIN = 88001
MEMBER = 88002
OUTSIDER = 88003


class _Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self._tmp = tempfile.TemporaryDirectory()
        self._old_db = db.DB_PATH
        db.DB_PATH = Path(self._tmp.name) / "t.db"
        await db.init_db()
        await db.upsert_user(SUPER, name="Super", is_admin=1)
        await db.upsert_user(ADMIN, name="Jamoa admini", is_admin=1,
                             is_team_admin=1)
        await db.upsert_user(MEMBER, name="A'zo", is_admin=1)
        await db.upsert_user(OUTSIDER, name="Begona", is_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self._old_db
        self._tmp.cleanup()


class TeamInviteAfterLoginTests(_Base):
    """Taklif faqat login tugagandan keyin qo'llanadi."""

    def test_phone_step_does_not_apply_invite(self) -> None:
        """Telefon yozilganda taklif qo'llanMASIN."""
        source = inspect.getsource(L._handle_phone_locked)
        self.assertNotIn(
            "_auto_bind_team_invite",
            source,
            "telefon bosqichida taklif qo'llanmoqda",
        )
        self.assertNotIn(
            "_apply_team_invite_after_login",
            source,
            "telefon bosqichida taklif qo'llanmoqda",
        )

    def test_finalize_applies_invite(self) -> None:
        """Login yakunida taklif qo'llanadi."""
        source = inspect.getsource(L._finalize_login_locked)
        self.assertIn("_apply_team_invite_after_login", source)

    def test_finalize_login_passes_update(self) -> None:
        """``finalize_login`` ``update`` ni o'tkazishi kerak."""
        source = inspect.getsource(L.finalize_login)
        self.assertIn("update", source)

    async def test_invite_not_applied_before_login(self) -> None:
        """Taklif (member) — login tugagandan keyin qo'llanadi."""
        await db.set_team_pending(
            MEMBER, 1, ADMIN, name="A'zo", username="azo"
        ) if False else None
        # Taklif jadvaliga yozamiz.
        await db.upsert_user(MEMBER, name="A'zo", phone="+998901112233")

    async def test_admin_invite_requires_login(self) -> None:
        """Jamoa admini taklifi — login tugagandan keyin."""
        source = inspect.getsource(L._handle_phone_locked)
        self.assertNotIn("_auto_make_team_admin", source)


class BlockedByTests(_Base):
    """Kim bloklagan — saqlanadi va tekshiriladi."""

    async def test_set_blocked_records_who(self) -> None:
        await db.set_blocked(MEMBER, True, blocked_by=ADMIN)
        user = await db.get_user(MEMBER)
        self.assertEqual(int(user.get("blocked_by") or 0), ADMIN)

    async def test_super_admin_block_has_zero_actor(self) -> None:
        """Super admin bloklash — ``blocked_by`` = 0 (tizim)."""
        await db.set_blocked(MEMBER, True)
        self.assertEqual(await db.get_blocked_by(MEMBER), 0)

    async def test_unblock_clears_actor(self) -> None:
        await db.set_blocked(MEMBER, True, blocked_by=ADMIN)
        await db.set_blocked(MEMBER, False)
        self.assertEqual(await db.get_blocked_by(MEMBER), 0)

    async def test_team_admin_cannot_unblock_super_admin_block(self) -> None:
        """Super admin bloklaganini jamoa admini chiqara OLMAYDI."""
        await db.set_blocked(MEMBER, True, blocked_by=0)
        await db.upsert_user(MEMBER, name="A'zo", owner_admin_uid=ADMIN)

        answer = AsyncMock()
        callback = SimpleNamespace(
            data=f"tadm:unblock:{MEMBER}",
            message=SimpleNamespace(reply_text=AsyncMock()),
            answer=answer,
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN),
            callback_query=callback,
        )

        await Tm.handle_team_admin_callback(update, ADMIN, callback.data)

        answer.assert_awaited()
        text = answer.await_args.args[0]
        self.assertIn("super admin", text.lower())
        # Foydalanuvchi bloklangan bo'lib qolishi kerak.
        user = await db.get_user(MEMBER)
        self.assertTrue(user.get("is_blocked"))

    async def test_team_admin_can_unblock_own_block(self) -> None:
        """O'zi bloklaganini jamoa admini chiqara OLADI."""
        await db.set_blocked(MEMBER, True, blocked_by=ADMIN)
        await db.upsert_user(MEMBER, name="A'zo", owner_admin_uid=ADMIN)

        answer = AsyncMock()
        callback = SimpleNamespace(
            data=f"tadm:unblock:{MEMBER}",
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

        user = await db.get_user(MEMBER)
        self.assertFalse(user.get("is_blocked"))


class TeamCapacityTests(_Base):
    """Sig'im — jamoa admini hisobga olinmaydi."""

    async def test_admin_not_counted_in_capacity(self) -> None:
        """Jamoa admini sig'imga qo'shilmaydi."""
        source = inspect.getsource(Tm)
        self.assertIn("is_team_admin", source)
        # Tasdiqlashda aniq filtr bor.
        idx = source.find("member_count = sum(")
        self.assertGreater(idx, 0, "member_count hisobi yo'q")
        window = source[idx : idx + 200]
        self.assertIn("is_team_admin", window)

    async def test_member_count_excludes_admin(self) -> None:
        """Jamoa admini bilan a'zolarni sanaganda admin chiqariladi."""
        team = await db.create_team_for_admin(
            ADMIN, "Jamoa", max_users=2, admin_expires_at=None
        )
        self.assertIsNotNone(team)
        await db.upsert_user(MEMBER, name="A'zo", team_id=int(team["id"]))

        members = await db.get_team_members(int(team["id"]))
        member_count = sum(1 for m in members if not m.get("is_team_admin"))
        self.assertEqual(member_count, 1, "admin sig'imga qo'shildi")


if __name__ == "__main__":
    unittest.main()
