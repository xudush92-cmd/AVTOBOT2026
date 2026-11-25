"""Jamoa (team) tizimi — integratsion testlari.

Ushbu faylda jamoa tizimining butun hayot sikli bitta test oqimida
tekshiriladi: admin jamoa yaratadi → a'zo qo'shadi → a'zo ro'yxatdan
o'tadi → admin tasdiqlaydi → muddat beriladi → jamoaga xabar yuboriladi
→ a'zo chiqadi → jamoa to'xtaydi.

Maqsad: modullararo o'zaro ta'sir (bot/teams.py + core/database.py +
bot/login.py + bot/menu.py) buzilsa, xato bir yerda ko'rinib qolsin.

Qamlov:
- ro'yxatdan o'tmagan user jamoa yarata oladi (login'dan oldin);
- a'zo telefoni orqali jamoaga arizani yuboradi;
- jamoa admini faqat o'z a'zosini tasdiqlaydi;
- muddat beriladi va tarifga saqlanadi;
- jamoaga xabar barcha a'zolarga yetib boradi;
- a'zo chiqqach jamoa va admin to'xtaydi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from bot import teams as Tm
from core import database as db
from core import session_crypto
from core.utils import calc_expires

ADMIN_UID = 77001
MEMBER_UID = 77002
MEMBER_PHONE = "+998901112233"


class FakeMessage:
    """`update.message` o'rnini bosadi — reply_text larni yig'adi."""

    def __init__(self) -> None:
        self.text = ""
        self.out: list[str] = []

    async def reply_text(self, text, reply_markup=None, **kwargs) -> None:
        self.out.append(text)

    async def edit_text(self, text, reply_markup=None, **kwargs) -> None:
        self.out.append(text)

    @property
    def last(self) -> str:
        return self.out[-1] if self.out else ""


class FakeQuery:
    """`update.callback_query` o'rnini bosadi."""

    def __init__(self) -> None:
        self.out: list[str] = []
        self.answers: list[str] = []

    async def answer(self, text, show_alert=False, **kwargs) -> None:
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None, **kwargs) -> None:
        self.out.append(text)


class FakeUpdate:
    def __init__(self, uid: int, text: str = "") -> None:
        self.effective_user = SimpleNamespace(
            id=uid,
            full_name=f"User {uid}",
            username=f"user{uid}",
        )
        self.message = FakeMessage()
        self.message.text = text
        self.callback_query = FakeQuery()


class TeamLifecycleTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa tizimining to'liq hayot sikli."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "lifecycle.db"
        session_crypto._fernet = __import__(
            "cryptography.fernet", fromlist=["Fernet"]
        ).Fernet(
            __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key()
        )
        await db.init_db()
        from bot.login import user_states

        self.user_states = user_states

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_full_jamoa_lifecycle(self) -> None:
        """Admin jamoa yaratadi → a'zo qo'shiladi → tasdiqlanadi → chiqadi.

        Jamoa adminini super admin panelidan tayyorlaydi; admin ro'yxatdan
        o'tgach o'z jamoasini o'zi yaratadi.
        """
        # ── 1. Super admin tomonidan tayyorlangan jamoa admini jamoa yaratadi
        await db.upsert_user(ADMIN_UID, name="Admin", is_team_admin=1)
        up = FakeUpdate(ADMIN_UID)
        await Tm.begin_team_admin_register(up, ADMIN_UID)
        self.assertEqual(
            self.user_states.get(ADMIN_UID, {}).get("step"),
            "team_admin_size",
            "jamoa yaratish oqimi boshlanishi kerak",
        )

        up = FakeUpdate(ADMIN_UID, "5")
        await Tm.handle_team_admin_size(up, ADMIN_UID, "5")
        self.assertEqual(
            self.user_states.get(ADMIN_UID, {}).get("step"),
            "team_admin_name",
        )

        up = FakeUpdate(ADMIN_UID, "Test Jamoasi")
        await Tm.handle_team_admin_name(up, ADMIN_UID, "Test Jamoasi")
        self.assertIn("yaratildi", up.message.last.lower())

        teams = await db.get_teams(ADMIN_UID)
        self.assertEqual(len(teams), 1, "jamoa yaratilishi kerak")
        team_id = int(teams[0]["id"])
        self.assertEqual(int(teams[0]["max_users"]), 5)

        admin = await db.get_user(ADMIN_UID)
        self.assertTrue(admin.get("is_team_admin"), "admin roli berilishi kerak")
        self.assertFalse(
            admin.get("awaiting_approval"),
            "jamoa admini darhol tasdiqlangan bo'lishi kerak",
        )

        # ── 2. Admin a'zo telefon raqamini qo'shadi ─────────────────────
        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_add_friend_phone(up, ADMIN_UID, MEMBER_PHONE)
        invites = await db.get_team_invites(ADMIN_UID)
        self.assertEqual(len(invites), 1, "taklif saqlanishi kerak")
        self.assertEqual(invites[0]["phone"], MEMBER_PHONE)

        # ── 3. A'zo ro'yxatdan o'tadi va jamoaga ariza yuboradi ────────
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        invite = await db.get_team_invite(MEMBER_PHONE, kind="member")
        self.assertIsNotNone(invite)
        saved = await db.set_team_pending(
            MEMBER_UID,
            int(invite["team_id"]),
            int(invite["owner_admin_uid"]),
            name="A'zo",
        )
        self.assertTrue(saved, "a'zo jamoaga biriktirilishi kerak")

        member = await db.get_user(MEMBER_UID)
        self.assertEqual(int(member["team_id"]), team_id)
        self.assertEqual(int(member["owner_admin_uid"]), ADMIN_UID)
        self.assertTrue(member.get("awaiting_approval"), "ariza kutilmoqda")

        # ── 4. Admin a'zoni tasdiqlaydi va muddat beradi ──────────────
        up = FakeUpdate(ADMIN_UID)
        await Tm.approve_team_member(up, ADMIN_UID, MEMBER_UID, days=30)

        member = await db.get_user(MEMBER_UID)
        self.assertFalse(
            member.get("awaiting_approval"),
            "a'zo tasdiqlangan bo'lishi kerak",
        )
        self.assertTrue(member.get("is_admin"), "a'zo tasdiqlangan bo'lishi kerak")
        self.assertIsNotNone(
            member.get("tariff_expires_at"),
            "a'zoga muddat berilishi kerak",
        )

        # ── 5. Jamoa admini jamoaga xabar yuboradi ─────────────────────
        sent: list[int] = []

        async def fake_send(chat_id: int, text: str, markup=None) -> bool:
            sent.append(int(chat_id))
            return True

        original_send = Tm._send
        Tm._send = fake_send
        try:
            up = FakeUpdate(ADMIN_UID)
            await Tm.send_team_message(up, ADMIN_UID, "Jamoa xabari")
        finally:
            Tm._send = original_send

        self.assertIn(MEMBER_UID, sent, "xabar a'zoga yetib borishi kerak")
        self.assertNotIn(
            ADMIN_UID, sent, "admin o'ziga xabar yubormasligi kerak"
        )

        # ── 6. A'zo jamoadan chiqadi ───────────────────────────────────
        result = await db.leave_team(MEMBER_UID)
        self.assertIsNotNone(result, "a'zo jamoadan chiqishi kerak")

        member = await db.get_user(MEMBER_UID)
        self.assertFalse(member.get("team_id"), "team_id tozalanishi kerak")
        self.assertFalse(
            member.get("owner_admin_uid"), "owner_admin_uid tozalanishi kerak"
        )
        self.assertIsNone(
            member.get("tariff_expires_at"),
            "jamoa muddati a'zo bilan birga tugashi kerak",
        )

        # ── 7. Jamoa admini o'z jamoasidan chiqmaydi ───────────────────
        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_member_callback(
            up, ADMIN_UID, "team:leaveconfirm"
        )
        admin = await db.get_user(ADMIN_UID)
        self.assertEqual(
            int(admin.get("team_id") or 0),
            team_id,
            "jamoa egasi jamoasidan chiqmasligi kerak",
        )

    async def test_member_cannot_touch_other_team(self) -> None:
        """Jamoa admini boshqa jamoaning a'zosiga amal qila olmaydi."""
        # Boshqa jamoa
        other_team = await db.create_team("Boshqa jamoa", 88001, max_users=5)
        await db.set_team_admin(
            88001, int(other_team["id"]), max_users=5, admin_expires_at=calc_expires(30)
        )
        await db.upsert_user(
            88002, name="Begona", team_id=int(other_team["id"]), owner_admin_uid=88001
        )

        # Bizning jamoa
        my_team = await db.create_team("Mening jamoam", ADMIN_UID, max_users=5)
        await db.set_team_admin(
            ADMIN_UID,
            int(my_team["id"]),
            max_users=5,
            admin_expires_at=calc_expires(30),
        )

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:member:88002")
        self.assertTrue(
            up.callback_query.answers,
            "begona a'zoga murojaat qilinganda rad etilishi kerak",
        )
        self.assertIn(
            "jamoangizda emas",
            up.callback_query.answers[-1],
        )

    async def test_jamoa_admin_cannot_be_super_admin(self) -> None:
        """Jamoa admini super admin bo'la olmaydi.

        Super admin — yagona oliq daraja; jamoa adminlari o'z jamoalari
        bilan cheklangan. `SUPER_ADMIN` boshqa roldagi user bo'lib qolishi
        kerak.
        """
        from config.config import SUPER_ADMIN

        await db.upsert_user(SUPER_ADMIN, name="Super", is_admin=1)
        user = await db.get_user(SUPER_ADMIN)
        self.assertIsNotNone(user, "super admin bazada bo'lishi kerak")
        self.assertFalse(
            user.get("is_team_admin"),
            "super admin jamoa admini bo'lmasligi kerak",
        )

        # Jamoa yaratilgandan keyin ham super admin jamoa adminiga
        # aylanmasligi kerak.
        team = await db.create_team("Jamoa", ADMIN_UID, max_users=5)
        await db.set_team_admin(
            ADMIN_UID, int(team["id"]), max_users=5, admin_expires_at=calc_expires(30)
        )
        user = await db.get_user(SUPER_ADMIN)
        self.assertFalse(user.get("is_team_admin"))

    async def test_expired_team_admin_stops_team(self) -> None:
        """Admin muddati tugasa — jamoa a'zosi ham to'xtaydi."""
        team = await db.create_team("Muddati tugagan", ADMIN_UID, max_users=5)
        await db.set_team_admin(
            ADMIN_UID,
            int(team["id"]),
            max_users=5,
            admin_expires_at="2020-01-01 00:00:00",  # o'tgan muddat
        )
        await db.upsert_user(
            MEMBER_UID,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_UID,
        )

        self.assertTrue(
            await db.team_admin_expired(ADMIN_UID),
            "admin muddati tugagan bo'lishi kerak",
        )
        self.assertTrue(
            await db.team_owner_expired(MEMBER_UID),
            "jamoa a'zosi ham muddati tugagan jamoani sezishi kerak",
        )

    async def test_team_message_reaches_all_members(self) -> None:
        """Jamoa xabari barcha a'zolarga yetib boradi."""
        team = await db.create_team("Keng jamoa", ADMIN_UID, max_users=10)
        await db.set_team_admin(
            ADMIN_UID,
            int(team["id"]),
            max_users=10,
            admin_expires_at=calc_expires(30),
        )
        for index in range(3):
            await db.upsert_user(
                88010 + index,
                name=f"A'zo {index}",
                team_id=int(team["id"]),
                owner_admin_uid=ADMIN_UID,
            )

        sent: list[int] = []

        async def fake_send(chat_id: int, text: str, markup=None) -> bool:
            sent.append(int(chat_id))
            return True

        original_send = Tm._send
        Tm._send = fake_send
        try:
            up = FakeUpdate(ADMIN_UID)
            await Tm.send_team_message(up, ADMIN_UID, "Salom")
        finally:
            Tm._send = original_send

        for index in range(3):
            self.assertIn(88010 + index, sent, "barcha a'zolar xabar olishi kerak")

    async def test_referral_user_joins_referrer_team(self) -> None:
        """Referal havolasi orqali kelgan user referrer jamoasiga biriktiriladi.

        Bu sizning talabbingiz: «Referal orqali kirsa user darhol o'sha
        jamoaga biriktiriladi».
        """
        from bot import referral as Ref

        team = await db.create_team("Referal jamoasi", ADMIN_UID, max_users=5)
        await db.set_team_admin(
            ADMIN_UID,
            int(team["id"]),
            max_users=5,
            admin_expires_at=calc_expires(30),
        )

        # Referrer — jamoa admini.
        await db.upsert_user(
            ADMIN_UID, name="Referrer", is_admin=1, is_team_admin=1,
            team_id=int(team["id"]),
        )

        # Yangi user referal havolasi orqali keldi.
        ok = await Ref.register_referral(MEMBER_UID, f"ref_{ADMIN_UID}")
        self.assertTrue(ok, "referal qayd etilishi kerak")

        member = await db.get_user(MEMBER_UID)
        self.assertEqual(
            int(member.get("team_id") or 0),
            int(team["id"]),
            "referral user referrer jamoasiga biriktirilishi kerak",
        )
        self.assertEqual(
            int(member.get("owner_admin_uid") or 0),
            ADMIN_UID,
            "jamoa egasi referrer bo'lishi kerak",
        )
        self.assertTrue(
            member.get("awaiting_approval"),
            "jamoa admini tasdiqlashi uchun ariza kutilmoqda",
        )

    async def test_referral_to_full_team_is_rejected(self) -> None:
        """Jamoa to'lgan bo'lsa, referal orqali kelgan user qo'shilmaydi.

        Sig'im — jamoaning **a'zolar** soni (jamoa admini hisobga
        olinmaydi). Limit 2 = ikkita a'zo mumkin.
        """
        from bot import referral as Ref

        team = await db.create_team("To'lgan jamoa", ADMIN_UID, max_users=2)
        await db.set_team_admin(
            ADMIN_UID,
            int(team["id"]),
            max_users=2,
            admin_expires_at=calc_expires(30),
        )
        await db.upsert_user(
            ADMIN_UID, name="Referrer", is_admin=1, is_team_admin=1,
            team_id=int(team["id"]),
        )
        # Jamoa to'lgan: 2 ta a'zo = limit 2 (admin hisobga olinmaydi).
        await db.upsert_user(
            88050, name="A'zo", team_id=int(team["id"]), owner_admin_uid=ADMIN_UID
        )
        await db.upsert_user(
            88051, name="Ikkinchi", team_id=int(team["id"]), owner_admin_uid=ADMIN_UID
        )

        ok = await Ref.register_referral(MEMBER_UID, f"ref_{ADMIN_UID}")
        self.assertTrue(ok, "referal ro'yxatdan o'tishi kerak")

        member = await db.get_user(MEMBER_UID)
        self.assertFalse(
            member.get("team_id"),
            "to'lgan jamoaga referal user qo'shilmasligi kerak",
        )

    async def test_add_friend_rejects_invalid_phone(self) -> None:
        """Noto'g'ri telefon formati rad etiladi."""
        team = await db.create_team("Jamoa", ADMIN_UID, max_users=5)
        await db.set_team_admin(
            ADMIN_UID,
            int(team["id"]),
            max_users=5,
            admin_expires_at=calc_expires(30),
        )

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_add_friend_phone(up, ADMIN_UID, "12345")
        self.assertIn("noto'g'ri", up.message.last.lower())
        self.assertEqual(
            len(await db.get_team_invites(ADMIN_UID)),
            0,
            "noto'g'ri raqam saqlanmamasligi kerak",
        )

    async def test_add_friend_rejects_other_team_duplicate(self) -> None:
        """Boshqa jamoa admini shu raqamni qo'shgan bo'lsa — rad etiladi."""
        # Boshqa jamoa admini raqamni qo'shadi
        other_team = await db.create_team("Boshqa", 88001, max_users=5)
        await db.set_team_admin(
            88001, int(other_team["id"]), max_users=5, admin_expires_at=calc_expires(30)
        )
        await db.add_team_invite(
            MEMBER_PHONE, 88001, team_id=int(other_team["id"]), kind="member"
        )

        # Bizning adminimiz xuddi shu raqamni qo'shmoqchi
        my_team = await db.create_team("Mening jamoam", ADMIN_UID, max_users=5)
        await db.set_team_admin(
            ADMIN_UID,
            int(my_team["id"]),
            max_users=5,
            admin_expires_at=calc_expires(30),
        )

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_add_friend_phone(up, ADMIN_UID, MEMBER_PHONE)
        self.assertIn(
            "allaqachon qo'shilgan",
            up.message.last.lower(),
            "boshqa jamoaga tegishli raqam rad etilishi kerak",
        )
        self.assertIn(
            "boshqa",
            up.message.last.lower(),
            "rad etilishda jamoa nomi ko'rsatilishi kerak",
        )
        # Taklif o'zgarmasligi kerak — boshqa jamoaning taklifi saqlanadi.
        invites = await db.get_team_invites(ADMIN_UID)
        self.assertEqual(
            len(invites),
            0,
            "rad etilgan raqam bizning taklifimizga qo'shilmasligi kerak",
        )


if __name__ == "__main__":
    unittest.main()
