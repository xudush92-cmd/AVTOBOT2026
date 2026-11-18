"""Do'st qo'shish va taklif orqali jamoaga biriktirish testlari.

Qamlov:
- admin do'stning telefon raqamini kiritadi — jamoaga biriktiriladi;
- telefon raqami validatsiyasi: faqat to'g'ri format qabul qilinadi;
- ro'yxatdan o'tayotgan do'st avtomatik jamoaga biriktiriladi;
- super admin taklif qilgan raqam — jamoa admini bo'ladi;
- boshqa yangi foydalanuvchilar to'g'ridan-to'g'ri ro'yxatdan o'tadi.
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

from bot import keyboards as KB  # noqa: E402
from bot import login as Login  # noqa: E402
from bot import teams as Tm  # noqa: E402
from bot import texts as T  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from core.utils import calc_expires, normalize_phone  # noqa: E402

ADMIN_A = 7001
USER_1 = 7002
USER_2 = 7003
SUPER = 123456789


class InviteBaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        from cryptography.fernet import Fernet

        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def _make_team_admin(self) -> int:
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        return int(team["id"])


class PhoneNormalizeTests(unittest.TestCase):
    """Telefon raqam normalizatsiyasi."""

    def test_valid_format_kept(self) -> None:
        self.assertEqual(normalize_phone("+998123456789"), "+998123456789")

    def test_spaces_and_dashes_removed(self) -> None:
        self.assertEqual(
            normalize_phone("+998 123-456-789"), "+998123456789"
        )

    def test_uzbek_format_normalized(self) -> None:
        self.assertEqual(normalize_phone("998123456789"), "+998123456789")

    def test_invalid_returns_empty(self) -> None:
        self.assertEqual(normalize_phone("12345"), "")
        self.assertEqual(normalize_phone("abc"), "")
        self.assertEqual(normalize_phone(""), "")


class InviteDbTests(InviteBaseTest):
    """Takliflar jadvali bilan ishlash."""

    async def test_add_and_get_invite(self) -> None:
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        invite = await db.get_team_invite("+998123456789", kind="member")
        self.assertIsNotNone(invite)
        self.assertEqual(int(invite["owner_admin_uid"]), ADMIN_A)
        self.assertEqual(int(invite["team_id"]), team_id)
        self.assertEqual(invite["status"], "pending")

    async def test_invite_replaced_on_re_add(self) -> None:
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        invites = await db.get_team_invites(ADMIN_A)
        self.assertEqual(len(invites), 1)

    async def test_invite_status_updated(self) -> None:
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        await db.set_team_invite_status("+998123456789", "used", kind="member")
        invite = await db.get_team_invite("+998123456789", kind="member")
        self.assertEqual(invite["status"], "used")

    async def test_invite_deleted(self) -> None:
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        self.assertTrue(await db.delete_team_invite("+998123456789"))
        self.assertIsNone(await db.get_team_invite("+998123456789"))

    async def test_admin_kind_separate_from_member(self) -> None:
        """Admin taklifi va member taklifi alohida saqlanadi."""
        await db.add_team_invite("+998123456789", ADMIN_A, kind="admin")
        self.assertIsNone(
            await db.get_team_invite("+998123456789", kind="member")
        )
        self.assertIsNotNone(
            await db.get_team_invite("+998123456789", kind="admin")
        )


class AddFriendFlowTests(InviteBaseTest):
    """Admin do'st qo'shish oqimi."""

    async def test_admin_adds_friend_by_phone(self) -> None:
        """Do'st telefon raqami bilan qo'shiladi."""
        team_id = await self._make_team_admin()
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=ADMIN_A),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_add_friend_phone(
                update, ADMIN_A, "+998123456789"
            )

        invite = await db.get_team_invite("+998123456789", kind="member")
        self.assertIsNotNone(invite, "do'st qo'shilmishi kerak")
        self.assertEqual(int(invite["team_id"]), team_id)

        text = update.message.reply_text.await_args.args[0]
        self.assertIn("+998123456789", text)
        self.assertIn("t.me", text)

    async def test_invalid_phone_rejected(self) -> None:
        """Noto'g'ri format rad etiladi."""
        await self._make_team_admin()
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=ADMIN_A),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_add_friend_phone(update, ADMIN_A, "12345")

        self.assertIsNone(await db.get_team_invite("12345"))
        text = update.message.reply_text.await_args.args[0]
        self.assertIn("noto'g'ri", text.lower())

    async def test_add_friend_panel_has_button(self) -> None:
        """Jamoa admini panelida '+ Do'st qo'shish' tugmasi bor."""
        kb = KB.kb_team_admin_panel()
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn("tadm:addfriend", callbacks)

    async def test_invites_list_shown(self) -> None:
        """Admin qo'shgan do'stlar ro'yxati ko'rsatiladi."""
        await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=1)
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=ADMIN_A),
        )
        with patch.object(Tm, "application", None):
            await Tm.show_team_invites(update, ADMIN_A)

        markup = update.message.reply_text.await_args.kwargs.get("reply_markup")
        labels = [b.text for row in markup.inline_keyboard for b in row]
        self.assertTrue(
            any("+998123456789" in label for label in labels),
            f"telefon inline tugmalarda ko'rinishi kerak: {labels}",
        )


class AutoBindTests(InviteBaseTest):
    """Ro'yxatdan o'tganda avtomatik jamoaga biriktirish."""

    async def test_friend_auto_binds_to_team(self) -> None:
        """Do'st ro'yxatdan o'tsa — jamoaga biriktiriladi."""
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_1, full_name="Vali", username="vali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            ok = await Login._auto_bind_team_invite(update, USER_1, "+998123456789")

        self.assertTrue(ok, "do'st jamoaga biriktirilishi kerak")
        user = await db.get_user(USER_1)
        self.assertEqual(int(user["team_id"]), team_id)
        self.assertEqual(int(user["owner_admin_uid"]), ADMIN_A)
        self.assertTrue(user["awaiting_approval"])

    async def test_invite_marked_used(self) -> None:
        """Taklif ishlatilgan deb belgilanadi."""
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_1, full_name="Vali", username="vali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            await Login._auto_bind_team_invite(update, USER_1, "+998123456789")

        invite = await db.get_team_invite("+998123456789", kind="member")
        self.assertEqual(invite["status"], "used")

    async def test_no_invite_no_bind(self) -> None:
        """Taklif yo'q — biriktirilmaydi."""
        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_1, full_name="Vali", username="vali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            ok = await Login._auto_bind_team_invite(update, USER_1, "+998999999999")
        self.assertFalse(ok)

    async def test_used_invite_not_reused(self) -> None:
        """Ishlatilgan taklif qayta ishlatilmaydi."""
        team_id = await self._make_team_admin()
        await db.add_team_invite("+998123456789", ADMIN_A, team_id=team_id)
        await db.set_team_invite_status("+998123456789", "used", kind="member")

        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_1, full_name="Vali", username="vali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            ok = await Login._auto_bind_team_invite(update, USER_1, "+998123456789")
        self.assertFalse(ok)

    async def test_expired_team_admin_no_bind(self) -> None:
        """Muddati tugagan jamoa admini — biriktirilmaydi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(-1)
        )
        await db.add_team_invite(
            "+998123456789", ADMIN_A, team_id=int(team["id"])
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_1, full_name="Vali", username="vali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            ok = await Login._auto_bind_team_invite(update, USER_1, "+998123456789")
        self.assertFalse(ok, "muddati tugagan admin jamoasiga qabul qilmasligi kerak")

    async def test_admin_invite_makes_team_admin(self) -> None:
        """Super admin taklif qilgan raqam — jamoa admini bo'ladi."""
        await db.add_team_invite("+998555555555", SUPER, kind="admin")

        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_2, full_name="Alisher", username="ali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            ok = await Login._auto_bind_team_invite(update, USER_2, "+998555555555")

        self.assertTrue(ok, "taklif qilingan user jamoa admini bo'lishi kerak")
        user = await db.get_user(USER_2)
        self.assertTrue(user["is_team_admin"])

    async def test_regular_user_not_bound(self) -> None:
        """Taklif qilinmagan user — jamoasiz qoladi."""
        update = SimpleNamespace(
            effective_user=SimpleNamespace(
                id=USER_2, full_name="Alisher", username="ali"
            ),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Login, "application", None):
            await Login._auto_bind_team_invite(update, USER_2, "+998777777777")

        user = await db.get_user(USER_2)
        if user:
            self.assertIsNone(user["team_id"])
            self.assertFalse(user["is_team_admin"])


class SuperAdminAddTests(InviteBaseTest):
    """Super admin yangi jamoa admini qo'shish."""

    async def test_new_phone_saved_as_invite(self) -> None:
        """Yangi raqam — admin taklifi sifatida saqlanadi."""
        from admin import admin_panel as AP

        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=SUPER),
        )
        with patch.object(AP, "application", None):
            await AP.handle_add_team_admin_phone(update, SUPER, "+998999888777")

        invite = await db.get_team_invite("+998999888777", kind="admin")
        self.assertIsNotNone(invite)
        self.assertEqual(int(invite["owner_admin_uid"]), SUPER)

    async def test_invalid_phone_rejected(self) -> None:
        """Noto'g'ri format rad etiladi."""
        from admin import admin_panel as AP

        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=SUPER),
        )
        with patch.object(AP, "application", None):
            await AP.handle_add_team_admin_phone(update, SUPER, "abc")

        self.assertIsNone(await db.get_team_invite("abc", kind="admin"))

    async def test_existing_user_promoted_to_team_admin(self) -> None:
        """Allaqachon ro'yxatdan o'tgan user — jamoa admini qilinadi."""
        from admin import admin_panel as AP

        await db.upsert_user(USER_1, name="Vali", phone="+998123456789")
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=SUPER),
        )
        with patch.object(AP, "application", None):
            await AP.handle_add_team_admin_phone(update, SUPER, "+998123456789")

        user = await db.get_user(USER_1)
        self.assertTrue(user["is_team_admin"], "ro'yxatdan o'tgan user admin qilinishi kerak")

    async def test_panel_has_add_admin_button(self) -> None:
        """Jamoa adminlari ro'yxatida '+ Admin qo'shish' tugmasi bor."""
        kb = KB.kb_team_admins([])
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn("adm:addteamadmin", callbacks)


class TeamPickOptionalTests(InviteBaseTest):
    """Jamoani tanlash — ixtiyoriy, menyudan ochiladi."""

    async def test_plain_user_menu_has_pick_button(self) -> None:
        """Jamoasiz user menyusida 'Jamoani tanlash' tugmasi bor."""
        kb = KB.kb_main(running=False)
        labels = {b.text for row in kb.keyboard for b in row}
        self.assertIn(T.BTN_TEAM_PICK, labels)

    async def test_team_member_menu_has_team_menu(self) -> None:
        """Jamoa a'zosi menyusida 'Jamoam' tugmasi bor."""
        kb = KB.kb_main(running=False, team_member=True)
        labels = {b.text for row in kb.keyboard for b in row}
        self.assertIn(T.BTN_TEAM_MENU, labels)
        self.assertNotIn(T.BTN_TEAM_PICK, labels)

    async def test_team_admin_menu_has_team_menu(self) -> None:
        """Jamoa admini menyusida 'Jamoam' tugmasi bor."""
        kb = KB.kb_main(running=False, team_admin=True)
        labels = {b.text for row in kb.keyboard for b in row}
        self.assertIn(T.BTN_TEAM_MENU, labels)
        self.assertNotIn(T.BTN_TEAM_PICK, labels)


if __name__ == "__main__":
    unittest.main()
