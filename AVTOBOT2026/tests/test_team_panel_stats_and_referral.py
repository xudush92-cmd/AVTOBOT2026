"""Jamoa paneli, statistikasi va referali tuzatishlarining regressiya testlari.

Qamlov:
- Statistika hisobi ``await`` async generator'da ishlatilmaydi
  (TypeError: 'async_generator' object is not iterable — live "Xatolik yuz berdi"
  sababi);
- Jamoa asosi (admin) o'z ro'yxatida ko'rinmaydi, lekin sig'im hisobida
  hisobga olinadi;
- Jamoa admini ichki oynalardan «Orqaga» bosilsa — jamoa admini
  paneliga qaytadi (asosiy menyuga emas);
- Panel va asosiy menyu inline kontekstda o'z xabarini tahrirlaydi
  (yangi xabar yubormaydi);
- Jamoa admini referal oynasida faqat umumiy jamoa havolasi chiqadi —
  shaxsiy referal tugmalari va statistikasi yo'q.
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
from bot import referral as Rf  # noqa: E402
from bot import teams as Tm  # noqa: E402
from bot import texts as T  # noqa: E402
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

ADMIN_UID = 99001
MEMBER_UID = 99002
ADMIN_PHONE = "+998901119900"
MEMBER_PHONE = "+998901119901"


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
        self.markups: list = []

    async def answer(self, text="", show_alert=False, **kwargs) -> None:
        self.answers.append(text)

    async def edit_message_text(self, text, reply_markup=None, **kwargs) -> None:
        self.out.append(text)
        self.markups.append(reply_markup)


class FakeUpdate:
    def __init__(self, uid: int, text: str = "") -> None:
        self.effective_user = SimpleNamespace(
            id=uid, full_name=f"User {uid}", username=f"user{uid}"
        )
        self.message = FakeMessage()
        self.message.text = text
        self.callback_query = FakeQuery()


class TeamPanelStatsReferralTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "panel_stats.db"
        session_crypto._fernet = __import__(
            "cryptography.fernet", fromlist=["Fernet"]
        ).Fernet(
            __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key()
        )
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def _make_admin_with_team(self, name: str = "Jamoa") -> int:
        await db.upsert_user(
            ADMIN_UID, name="Admin", phone=ADMIN_PHONE, is_team_admin=1
        )
        team = await db.create_team_for_admin(
            ADMIN_UID, name, max_users=5, admin_expires_at=None
        )
        self.assertIsNotNone(team)
        await db.set_team_admin(ADMIN_UID, int(team["id"]), max_users=5)
        return int(team["id"])

    # ── Statistikadagi async xato ───────────────────────────────────
    async def test_team_stats_does_not_raise(self) -> None:
        """Statistika oynasi xatosiz ochilishi kerak.

        Avvalgi kodda ``sum(await db.count_chats(...) for m in members)``
        ishlatilgan — bu async generator yaratadi va ``TypeError``
        beradi (live "Xatolik yuz berdi" sababi).
        """
        await self._make_admin_with_team()
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        await db.set_team_pending(MEMBER_UID, 1, ADMIN_UID, name="A'zo")

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:stats")

        self.assertTrue(
            up.callback_query.out,
            "statistika oynasi ochilishi kerak (xato bermasligi kerak)",
        )
        self.assertIn("JAMOA STATISTIKASI", up.callback_query.out[-1])

    async def test_team_stats_counts_are_numeric(self) -> None:
        """Statistikadagi guruh/post sonlari raqam bo'lishi kerak."""
        await self._make_admin_with_team()
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        await db.set_team_pending(MEMBER_UID, 1, ADMIN_UID, name="A'zo")

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:stats")
        text = up.callback_query.out[-1]

        self.assertIn("Jami guruhlar: 0 ta", text)
        self.assertIn("Jami postlar: 0 ta", text)

    async def test_team_stats_excludes_admin_from_total(self) -> None:
        """Admin statistikadagi foydalanuvchilar soniga kirmasligi kerak."""
        await self._make_admin_with_team()
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        await db.set_team_pending(MEMBER_UID, 1, ADMIN_UID, name="A'zo")

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:stats")
        text = up.callback_query.out[-1]

        self.assertIn("Foydalanuvchilar: 1 ta", text)

    async def test_team_stats_back_button_returns_to_panel(self) -> None:
        """Statistikadan «Orqaga» — jamoa admini paneli."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:stats")

        markup = up.callback_query.markups[-1]
        data = [b.callback_data for row in markup.inline_keyboard for b in row]
        self.assertIn("tadm:panel", data)

    # ── A1: admin ro'yxatda ko'rinmaydi ─────────────────────────────
    async def test_count_team_members_include_admin_flag(self) -> None:
        """`include_admin=False` adminni hisobdan chiqaradi."""
        await self._make_admin_with_team()
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        await db.set_team_pending(MEMBER_UID, 1, ADMIN_UID, name="A'zo")

        team = await Tm.primary_team(ADMIN_UID)
        with_admin = await db.count_team_members(int(team["id"]))
        without_admin = await db.count_team_members(
            int(team["id"]), include_admin=False
        )

        self.assertEqual(with_admin, 2, "sig'im hisobida admin hisobda bo'lishi kerak")
        self.assertEqual(
            without_admin, 1, "ko'rsatiladigan ro'yxatda admin bo'lmasligi kerak"
        )

    async def test_team_capacity_still_counts_admin(self) -> None:
        """Sig'im (capacity) hisobiga admin kirishi davom etishi kerak."""
        await self._make_admin_with_team()

        team = await Tm.primary_team(ADMIN_UID)
        self.assertTrue(
            await db.team_has_free_slot(int(team["id"])),
            "jamoa sig'imi adminni hisobga olgan holda bo'sh bo'lishi kerak",
        )

    async def test_team_admin_panel_count_matches_member_list(self) -> None:
        """Paneldagi son — ro'yxatdagi son bilan mos kelishi kerak."""
        team_id = await self._make_admin_with_team()
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)
        await db.set_team_pending(MEMBER_UID, 1, ADMIN_UID, name="A'zo")

        members = [
            m
            for m in await db.get_team_members(team_id)
            if int(m.get("uid") or 0) != ADMIN_UID
        ]

        up = FakeUpdate(ADMIN_UID)
        await Tm.show_team_admin_panel(up, ADMIN_UID)
        panel_text = up.callback_query.out[-1]

        self.assertIn(f"Foydalanuvchilar: {len(members)}/5 ta", panel_text)

    async def test_team_admin_hidden_from_member_list(self) -> None:
        """Admin o'z a'zolar ro'yxatida ko'rinmasligi kerak."""
        team_id = await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:users")
        shown = up.callback_query.out[-1]

        self.assertNotIn("Admin", shown, "admin o'z ro'yxatida ko'rinmasligi kerak")

    # ── Navigatsiya: ichki oynalar → jamoa admini paneli ────────────
    async def test_panel_action_returns_to_panel(self) -> None:
        """`tadm:panel` jamoa admini panelini ochishi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:panel")

        self.assertTrue(up.callback_query.out, "panel ochilishi kerak")
        self.assertIn("JAMOA ADMINI PANELI", up.callback_query.out[-1])

    async def test_panel_action_does_not_send_new_message(self) -> None:
        """Panel ochilganda yangi xabar yuborilmasligi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:panel")

        self.assertEqual(
            up.message.out, [], "inline kontekstda yangi xabar yuborilmasligi kerak"
        )

    async def test_members_back_goes_to_panel(self) -> None:
        """A'zolar ro'yxatidan «Orqaga» — jamoa admini paneli."""
        await self._make_admin_with_team()

        kb = KB.kb_team_members([])
        data = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("tadm:panel", data)
        self.assertNotIn("tadm:back", data)

    async def test_invites_back_goes_to_panel(self) -> None:
        """Takliflar ro'yxatidan «Orqaga» — jamoa admini paneli."""
        kb = KB.kb_team_invites([])
        data = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("tadm:panel", data)
        self.assertNotIn("tadm:back", data)

    async def test_team_admin_back_still_goes_to_main_menu(self) -> None:
        """Panelning «Orqaga» tugmasi asosiy menyuga qaytishida qoladi."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        with patch("bot.menu.show_home", new=AsyncMock()) as home:
            await Tm.handle_team_admin_callback(up, ADMIN_UID, "tadm:back")
        home.assert_awaited_once()

    # ── Inline xabarni o'zida tahrirlash ────────────────────────────
    async def test_show_home_in_place_edits_message(self) -> None:
        """`show_home(in_place=True)` mavjud xabarni tahrirlashi kerak."""
        from bot import menu as M

        up = FakeUpdate(ADMIN_UID)
        await M.show_home(up, ADMIN_UID, in_place=True)

        self.assertTrue(up.callback_query.out, "xabar tahrirlanishi kerak")
        self.assertEqual(up.message.out, [], "yangi xabar yuborilmasligi kerak")
        self.assertIn("Asosiy menyu", up.callback_query.out[-1])

    async def test_show_home_default_still_replies(self) -> None:
        """Standart `show_home` yangi xabar yuborishiga davom etishi kerak."""
        from bot import menu as M

        up = FakeUpdate(ADMIN_UID)
        await M.show_home(up, ADMIN_UID)

        self.assertTrue(up.message.out, "oddiy xabar yuborilishi kerak")

    async def test_reply_text_safe_in_place_flag(self) -> None:
        """`reply_text_safe(in_place=True)` inline kontekstda tahrirlaydi."""
        from core.utils import reply_text_safe

        up = FakeUpdate(ADMIN_UID)
        ok = await reply_text_safe(up, "matn", in_place=True)
        self.assertTrue(ok)
        self.assertEqual(up.callback_query.out[-1], "matn")
        self.assertEqual(up.message.out, [])

    # ── Referal: jamoa adminida faqat jamoa havolasi ────────────────
    async def test_team_admin_referral_shows_only_team_link(self) -> None:
        """Jamoa admini referal oynasida faqat jamoa havolasi bo'lishi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        await Rf.show_referral(up)

        shown = up.message.last
        self.assertIn("start=team_", shown)
        self.assertNotIn("start=ref_", shown, "shaxsiy havola chiqmasligi kerak")
        self.assertNotIn("Faol referallar", shown, "referal statistikasi chiqmasligi kerak")

    async def test_team_admin_referral_keyboard_has_single_button(self) -> None:
        """Jamoa admini referal klaviaturasida bitta tugma bo'lishi kerak."""
        await self._make_admin_with_team()

        up = FakeUpdate(ADMIN_UID)
        with patch.object(
            up.message, "reply_text", new=AsyncMock()
        ) as reply:
            await Rf.show_referral(up)

        markup = reply.await_args.kwargs.get("reply_markup")
        buttons = [b for row in markup.inline_keyboard for b in row]
        self.assertEqual(len(buttons), 1, "faqat bitta tugma bo'lishi kerak")
        self.assertIsNotNone(buttons[0].url, "tugma havola bo'lishi kerak")
        self.assertIn("start=team_", buttons[0].url)

    async def test_ordinary_user_referral_unchanged(self) -> None:
        """Oddiy foydalanuvchi referali o'zgarmasligi kerak."""
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)

        up = FakeUpdate(MEMBER_UID)
        await Rf.show_referral(up)

        shown = up.message.last
        self.assertIn(f"start=ref_{MEMBER_UID}", shown)
        self.assertIn("Faol referallar", shown)

    async def test_team_admin_share_message_uses_team_link(self) -> None:
        """Jamoa admini «do'stlarga yuborish» matni jamoa havolasi bilan."""
        await self._make_admin_with_team()

        text = await Rf.share_referral_message(ADMIN_UID)
        self.assertIn("start=team_", text)
        self.assertNotIn("start=ref_", text)

    async def test_ordinary_user_share_message_uses_personal_link(self) -> None:
        """Oddiy foydalanuvchi shaxsiy havola matnini oladi."""
        await db.upsert_user(MEMBER_UID, name="A'zo", phone=MEMBER_PHONE)

        text = await Rf.share_referral_message(MEMBER_UID)
        self.assertIn(f"start=ref_{MEMBER_UID}", text)

    async def test_team_link_text_has_no_personal_stats(self) -> None:
        """`team_link_text` shaxsiy statistika ko'rsatmasligi kerak."""
        text = T.team_link_text("https://t.me/Bot?start=team_2")
        self.assertIn("start=team_2", text)
        self.assertNotIn("referal", text.lower())
        self.assertNotIn("Faol referallar", text)

    async def test_kb_team_link_only_single_button(self) -> None:
        """`kb_team_link_only` — bitta havola tugmasi."""
        kb = KB.kb_team_link_only("https://t.me/Bot?start=team_2")
        buttons = [b for row in kb.inline_keyboard for b in row]
        self.assertEqual(len(buttons), 1)
        self.assertIn("start=team_2", buttons[0].url)


if __name__ == "__main__":
    unittest.main()
