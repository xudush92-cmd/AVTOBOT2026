"""Jamoa aloqa va nomlash tuzatishlarining regressiya testlari.

Qamlov:
- A2: jamoa admini panelidagi «Orqaga» tugmasi o'z-o'ziga qaytmaydi;
- A3: super admin oddiy foydalanuvchini jamoaga yo'naltira oladi
      (tasdiqlash jamoa adminida qoladi);
- A6: jamoalarda faqat **umumiy** havolа qoladi — shaxsiy havola yo'q;
- A7: ro'yxatdan o'tgandan keyin to'g'ri telefon raqami ko'rsatiladi
      (jamoa a'zosiga — jamoa adminining, jamoasizga — super admin);
- A8: jamoa admini o'z jamoasining nomini o'zgartira oladi.
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
from bot import teams as Tm  # noqa: E402
from bot import texts as T  # noqa: E402
from bot.login import _team_admin_contact  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

ADMIN_UID = 88001
MEMBER_UID = 88002
ADMIN_PHONE = "+998901112244"
MEMBER_PHONE = "+998901112255"


class FakeMessage:
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
    def __init__(self) -> None:
        self.out: list[str] = []
        self.answers: list[str] = []

    async def answer(self, text="", show_alert=False, **kwargs) -> None:
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None, **kwargs) -> None:
        self.out.append(text)


class FakeUpdate:
    def __init__(self, uid: int, text: str = "") -> None:
        self.effective_user = SimpleNamespace(
            id=uid, full_name=f"User {uid}", username=f"user{uid}"
        )
        self.message = FakeMessage()
        self.message.text = text
        self.callback_query = FakeQuery()


class TeamContactNamingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "contact_naming.db"
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

    async def _make_admin_with_team(self, name: str = "Jamoa") -> int:
        """Jamoa admini yaratadi (telefoni bilan) va jamoani qaytaradi."""
        await db.upsert_user(
            ADMIN_UID, name="Admin", phone=ADMIN_PHONE, is_team_admin=1
        )
        team = await db.create_team_for_admin(
            ADMIN_UID, name, max_users=5, admin_expires_at=None
        )
        self.assertIsNotNone(team)
        await db.set_team_admin(ADMIN_UID, int(team["id"]), max_users=5)
        return int(team["id"])

    # ── A2: «Orqaga» o'z-o'ziga qaytmasligi kerak ──────────────────
    async def test_team_admin_back_goes_to_main_menu(self) -> None:
        """Jamoa admini panelidagi «Orqaga» asosiy menyuga qaytaradi."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        with patch("bot.menu.show_home", new=AsyncMock()) as home:
            await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:back")
        home.assert_awaited_once()
        self.assertEqual(home.await_args.args[1], ADMIN_UID)

    async def test_show_home_works_without_update_message(self) -> None:
        """`show_home` inline callback'da ham ishlashi kerak.

        Inline tugma bosilganda ``update.message`` bo'lmasligi mumkin —
        funksiya ``reply_text_safe`` ishlatishi kerak.
        """
        import inspect

        from bot import menu as M

        src = inspect.getsource(M.show_home)
        self.assertIn(
            "reply_text_safe",
            src,
            "show_home xavfsiz reply ishlatishi kerak (inline callback)",
        )

    async def test_team_admin_panel_back_callback_exists(self) -> None:
        """Panel tugmalarida «Orqaga» bor va u `tadm:back` ga ishlaydi."""
        kb = KB.kb_team_admin_panel()
        data = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("tadm:back", data)

    # ── A6: faqat umumiy jamoa havolasi ─────────────────────────────
    async def test_team_link_screen_has_no_personal_link(self) -> None:
        """«🔗 Havola» oynasida shaxsiy havola chiqmasligi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:link")
        shown = up.callback_query.out[-1]

        self.assertIn("start=team_", shown, "umumiy jamoa havolasi bo'lishi kerak")
        self.assertNotIn(
            "start=adm_", shown, "shaxsiy jamoa havolasi chiqmasligi kerak"
        )

    async def test_admin_link_helper_removed(self) -> None:
        """Shaxsiy jamoa havolasi yordamchi funksiyasi mavjud bo'lmasligi kerak."""
        self.assertFalse(
            hasattr(Tm, "admin_link"),
            "admin_link() olib tashlangan bo'lishi kerak",
        )

    async def test_add_friend_message_has_no_personal_link(self) -> None:
        """Do'st qo'shish xabarida faqat umumiy havola bo'lishi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_add_friend_phone(up, ADMIN_UID, MEMBER_PHONE)
        shown = up.message.last

        self.assertIn("start=team_", shown)
        self.assertNotIn("start=adm_", shown)
        self.assertNotIn("Shaxsiy havola", shown)

    async def test_adm_deep_link_no_longer_assigns_team(self) -> None:
        """`adm_<uid>` deep link endi jamoaga biriktirmasligi kerak."""
        import main as M

        await self._make_admin_with_team()
        up = FakeUpdate(MEMBER_UID)
        ok = await M._auto_assign_team_from_link(up, MEMBER_UID, f"adm_{ADMIN_UID}")
        self.assertFalse(ok, "adm_ deep link o'chirilishi kerak")

        user = await db.get_user(MEMBER_UID) or {}
        self.assertFalse(user.get("team_id"), "a'zo jamoaga biriktirilmasligi kerak")

    # ── A7: to'g'ri telefon raqami ──────────────────────────────────
    async def test_team_admin_contact_returns_admin_phone(self) -> None:
        """Jamoa adminining telefon raqami olinadi."""
        await db.upsert_user(ADMIN_UID, name="Admin", phone=ADMIN_PHONE)
        contact = await _team_admin_contact(ADMIN_UID)
        self.assertEqual(contact, ADMIN_PHONE)

    async def test_team_admin_contact_falls_back_to_admin(self) -> None:
        """Raqam topilmasa — zaxira sifatida umumiy admin kontakti."""
        await db.upsert_user(ADMIN_UID, name="Admin")
        contact = await _team_admin_contact(ADMIN_UID)
        self.assertEqual(contact, T.ADMIN_CONTACT_PHONE)

    async def test_team_member_pending_message_uses_admin_phone(self) -> None:
        """Jamoa a'zosiga jamoa adminining raqami ko'rsatiladi."""
        await self._make_admin_with_team()
        contact = await _team_admin_contact(ADMIN_UID)
        text = T.LOGIN_SUCCESS_PENDING_TEAM.format(contact=contact)

        self.assertIn(ADMIN_PHONE, text)
        self.assertNotIn(
            T.ADMIN_CONTACT_PHONE,
            text,
            "jamoa a'zosiga super admin raqami chiqmasligi kerak",
        )

    async def test_plain_pending_message_keeps_admin_phone(self) -> None:
        """Jamoasiz foydalanuvchiga super admin raqami ko'rsatiladi."""
        self.assertIn(T.ADMIN_CONTACT_PHONE, T.LOGIN_SUCCESS_PENDING)

    async def test_team_admin_ready_has_no_admin_phone(self) -> None:
        """Jamoa asosiga super admin raqami chiqmasligi kerak."""
        text = T.TEAM_ADMIN_READY.format(name="Jamoa", link="https://t.me/bot?start=team_1")
        self.assertNotIn(T.ADMIN_CONTACT_PHONE, text)
        self.assertIn("start=team_1", text)

    # ── A8: jamoa nomini o'zgartirish ────────────────────────────────
    async def test_team_admin_can_rename_team(self) -> None:
        """Jamoa admini o'z jamoasining nomini o'zgartira oladi."""
        team_id = await self._make_admin_with_team("Jamoa #88001")

        up = FakeUpdate(ADMIN_UID, "Avtoelon Toshkent")
        await Tm.handle_team_admin_rename(up, ADMIN_UID, "Avtoelon Toshkent")

        team = await db.get_team(team_id)
        self.assertEqual(team["name"], "Avtoelon Toshkent")
        self.assertIn("Avtoelon Toshkent", up.message.last)
        self.assertIsNone(
            self.user_states.get(ADMIN_UID),
            "state to'g'rilanmagan bo'lishi kerak",
        )

    async def test_rename_rejects_too_short_name(self) -> None:
        """1 belgili nom qabul qilinmasligi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID, "A")
        await Tm.handle_team_admin_rename(up, ADMIN_UID, "A")
        self.assertIn("2", up.message.last)

    async def test_rename_rejects_duplicate_name(self) -> None:
        """Boshqa jamoa bilan bir xil nomga o'tkazib bo'lmasligi kerak.

        Bazada ``UNIQUE(owner_admin_uid, name)`` bor, lekin kod ham
        alohida tekshiradi (eski bazalarda constraint bo'lmasligi mumkin).
        """
        await self._make_admin_with_team("Bitta")
        # Ikkinchi jamoa — boshqa nom bilan (UNIQUE constraint'ga tegilmasin).
        second = await db.create_team("Ikkinchi", ADMIN_UID, max_users=5)
        self.assertIsNotNone(second)

        # Endi "Ikkinchi" nomi band — biriktirish uchun ishlatilmaydi.
        with patch(
            "bot.teams.db.get_team_by_name", new=AsyncMock(return_value=second)
        ):
            up = FakeUpdate(ADMIN_UID, "Ikkinchi")
            await Tm.handle_team_admin_rename(up, ADMIN_UID, "Ikkinchi")

        self.assertIn("allaqachon bor", up.message.last)
        team = await db.get_team(int(second["id"]))
        self.assertEqual(team["name"], "Ikkinchi", "nomi o'zgartirilmasligi kerak")

    async def test_rename_keeps_same_name_allowed(self) -> None:
        """Jamoa o'z nomini qayta yozsa ham xato bermasligi kerak."""
        team_id = await self._make_admin_with_team("Birinchi")

        up = FakeUpdate(ADMIN_UID, "Birinchi")
        await Tm.handle_team_admin_rename(up, ADMIN_UID, "Birinchi")
        team = await db.get_team(team_id)
        self.assertEqual(team["name"], "Birinchi")

    async def test_rename_button_present_in_panel(self) -> None:
        """Jamoa admini panelida nomni o'zgartirish tugmasi bo'lishi kerak."""
        kb = KB.kb_team_admin_panel()
        data = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("tadm:rename", data)

    async def test_rename_state_is_routed(self) -> None:
        """`team_admin_rename` holati FSM ro'yxatida bo'lishi kerak.

        Aks holda admin nom kiritganda bot javob bermaydi.
        """
        import inspect

        import main as M

        src = inspect.getsource(M._on_message_locked)
        self.assertIn(
            '"team_admin_rename"',
            src,
            "team_admin_rename holati FSM'ga qo'shilmagan bo'lishi mumkin",
        )

    async def test_rename_flow_button_then_text(self) -> None:
        """Tugma bosiladi → matn kiritiladi → nom o'zgaradi (to'liq oqim)."""
        team_id = await self._make_admin_with_team("Jamoa #88001")

        # 1) «✏️ Jamoa nomi» tugmasi bosiladi.
        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:rename")
        self.assertEqual(
            self.user_states.get(ADMIN_UID, {}).get("step"),
            "team_admin_rename",
        )
        self.assertIn("nomini kiriting", up.callback_query.out[-1])

        # 2) Yangi nom kiritiladi.
        up = FakeUpdate(ADMIN_UID, "Yangi Jamoa")
        await Tm.handle_team_admin_rename(up, ADMIN_UID, "Yangi Jamoa")

        team = await db.get_team(team_id)
        self.assertEqual(team["name"], "Yangi Jamoa")

    # ── A1: jamoa admini o'z ro'yxatida ko'rinmasin ────────────────
    async def test_team_admin_hidden_from_own_member_list(self) -> None:
        """Jamoa asosi o'z foydalanuvchilar ro'yxatida ko'rinmasin."""
        await self._make_admin_with_team("Jamoa")
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        await db.set_team_pending(MEMBER_UID, 1, ADMIN_UID, name="A'zo")

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:users")

        shown = up.callback_query.out[-1]
        self.assertNotIn(
            "Admin",
            shown,
            "jamoa asosi o'z ro'yxatida ko'rinmasligi kerak",
        )
        self.assertIn("A'zo", shown, "a'zo ro'yxatda ko'rinishi kerak")

    # ── A3: super admin a'zoni jamoaga yo'naltiradi ─────────────────
    async def test_super_admin_can_route_user_to_team(self) -> None:
        """Super admin oddiy foydalanuvchini jamoa adminiga yo'naltiradi."""
        from admin import admin_actions as AA

        team_id = await self._make_admin_with_team("Jamoa")
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)

        bot = SimpleNamespace(send_message=AsyncMock())
        up = FakeUpdate(MEMBER_UID)
        with patch.object(AA, "application", SimpleNamespace(bot=bot)):
            await AA.action_team_bind_go(up, MEMBER_UID, ADMIN_UID)

        member = await db.get_user(MEMBER_UID)
        self.assertEqual(int(member["team_id"]), team_id)
        self.assertEqual(int(member["owner_admin_uid"]), ADMIN_UID)
        self.assertTrue(
            member.get("awaiting_approval"),
            "jamoa admini tasdiqlashi uchun ariza holati bo'lishi kerak",
        )
        self.assertIn("yo'naltirildi", up.callback_query.out[-1])

        # Foydalanuvchiga ham xabar boradi — jamoa adminining raqami bilan.
        sent = bot.send_message.await_args
        self.assertEqual(sent.args[0], MEMBER_UID)
        self.assertIn(ADMIN_PHONE, sent.args[1])
        self.assertNotIn(
            T.ADMIN_CONTACT_PHONE,
            sent.args[1],
            "a'zoga super admin raqami chiqmasligi kerak",
        )

    async def test_super_admin_cannot_route_user_to_full_team(self) -> None:
        """To'lgan jamoaga yo'naltirilmasligi kerak.

        Sig'im — jamoaning **a'zolar** soni (admin hisobga olinmaydi),
        shuning uchun to'ldirish uchun avval a'zo qo'shilishi kerak.
        """
        from admin import admin_actions as AA

        team_id = await self._make_admin_with_team("Jamoa")
        await db.update_team(team_id, max_users=1)
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)

        # Sig'im 1 — jamoada birinchi a'zo bor (admin hisobga olinmaydi).
        await db.set_team_pending(MEMBER_UID, team_id, ADMIN_UID, name="A'zo")

        # Endi jamoa to'lgan — ikkinchisi biriktirilmaydi.
        await db.upsert_user(777222333, name="Ikkinchi", phone="+998907070707")
        up = FakeUpdate(777222333)
        await AA.action_team_bind_go(up, 777222333, ADMIN_UID)

        member = await db.get_user(777222333)
        self.assertFalse(member.get("team_id"), "jamoaga biriktirilmasligi kerak")
        self.assertIn("sig'imi to'lgan", up.callback_query.out[-1])

    async def test_user_card_has_team_bind_button(self) -> None:
        """Foydalanuvchi kartasida jamoaga biriktirish tugmasi bo'lishi kerak."""
        kb = KB.kb_user_card(MEMBER_UID, has_session=True)
        data = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn(f"uc:teambind:{MEMBER_UID}", data)


if __name__ == "__main__":
    unittest.main()
