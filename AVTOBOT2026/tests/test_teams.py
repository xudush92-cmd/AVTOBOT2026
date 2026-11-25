"""Jamoa (team) tizimi testlari.

Qamlov:
- jamoa yaratish: admin jamoani nom va sig'im bilan yaratadi;
- sig'im chegarasi: limit to'lgan jamoaga yangi user qo'shilmaydi;
- izolyatsiya: jamoa admini faqat o'z jamoasidagi userlarni boshqaradi;
- jamoa admini muddati tugasa — uning jamoasi ham to'xtaydi;
- super admin jamoa adminining muddati va sig'imini o'zgartiradi;
- video rad etiladi, rasm limiti 4 ta.
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
from bot import media_ingest  # noqa: E402
from bot import callbacks as Cb  # noqa: E402
from bot import teams as Tm  # noqa: E402
from bot import texts as T  # noqa: E402
from core.utils import calc_expires  # noqa: E402


def assert_expires_in_days(testcase, actual, days, msg=""):
    """Muddat ``days`` kunlik ekanini tekshiradi — **vaqt chegarasiga bog'liq emas**.

    ``calc_expires()`` vaqtni darhol hisoblaydi, shuning uchun kod ham
    darhol hisoblaganda ikkita ``now()`` chaqiruvi orasida bir necha soniya
    o'tishi mumkin (sekin serverda 1+ soniya). Aniq sanani solishtirish
    shu sababdan "flaky" test yaratadi — biz faqat intervalni tekshiramiz.
    """
    from datetime import datetime, timezone

    testcase.assertIsNotNone(actual, msg or "muddat belgilanmagan")
    expires = datetime.strptime(actual, "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=timezone.utc
    )
    delta = expires - datetime.now(timezone.utc)
    testcase.assertLessEqual(
        delta.total_seconds(),
        days * 86400 + 5,
        msg or f"muddat {days} kundan ko'p bo'lmasligi kerak",
    )
    testcase.assertGreater(
        delta.total_seconds(),
        (days - 1) * 86400,
        msg or f"muddat taxminan {days} kun bo'lishi kerak",
    )
from config.config import (  # noqa: E402
    MAX_ALBUM_FILES,
    SUPER_ADMIN,
    TEAM_MIN_MEMBERS,
)
from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

ADMIN_A = 5001
ADMIN_B = 5002
USER_1 = 6001
USER_2 = 6002


class TeamDatabaseTests(unittest.IsolatedAsyncioTestCase):
    """Baza darajasidagi jamoa mantiqi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_create_team_and_read_back(self) -> None:
        team = await db.create_team("Avtoelon TZ", ADMIN_A, max_users=5)
        self.assertIsNotNone(team)
        self.assertEqual(team["name"], "Avtoelon TZ")
        self.assertEqual(int(team["owner_admin_uid"]), ADMIN_A)
        self.assertEqual(int(team["max_users"]), 5)

        fetched = await db.get_team(int(team["id"]))
        self.assertEqual(fetched["name"], "Avtoelon TZ")

        by_name = await db.get_team_by_name(ADMIN_A, "Avtoelon TZ")
        self.assertIsNotNone(by_name)

    async def test_team_limit_is_enforced(self) -> None:
        team = await db.create_team("Kichik jamoa", ADMIN_A, max_users=2)
        team_id = int(team["id"])

        self.assertTrue(await db.team_has_free_slot(team_id))
        await db.upsert_user(USER_1, name="Birinchi", team_id=team_id)
        self.assertTrue(await db.team_has_free_slot(team_id))
        await db.upsert_user(USER_2, name="Ikkinchi", team_id=team_id)
        self.assertFalse(
            await db.team_has_free_slot(team_id),
            "limit to'lganda bo'sh joy qolmasligi kerak",
        )

    async def test_assign_team_member_respects_limit(self) -> None:
        """Sig'im to'lgan jamoaga yangi a'zo biriktirilmaydi.

        `assign_team_member` — jamoaga biriktirishning yagona yozuv
        nuqtasi. U sig'imi tekshirmasa, limit oshib ketishi mumkin.

        Sig'im — jamoaning **a'zolar** soni. Jamoa admini (jamoa egasi)
        hisobga **olinmaydi**: u jamoani yaratgan, u a'zo emas.
        """
        team = await db.create_team("Kichik jamoa", ADMIN_A, max_users=2)
        team_id = int(team["id"])
        await db.set_team_admin(
            ADMIN_A, team_id, max_users=2, admin_expires_at=calc_expires(30)
        )
        self.assertEqual(
            await db.count_team_members(team_id),
            0,
            "jamoa admini sig'imga hisoblanmasligi kerak",
        )

        # Bo'sh joy bor (0 < 2) — birinchi a'zo qo'shiladi.
        await db.upsert_user(USER_1, name="Birinchi")
        ok = await db.assign_team_member(USER_1, team_id, ADMIN_A)
        self.assertTrue(ok, "bo'sh joy bo'lsa biriktirilishi kerak")

        # Endi jamoa to'ldi (1 a'zo = limit 2? yo'q — 1 < 2, bo'sh joy bor).
        await db.upsert_user(6003, name="Ikkinchi")
        ok = await db.assign_team_member(6003, team_id, ADMIN_A)
        self.assertTrue(ok, "1 a'zo < limit 2 — ikkinchisi ham kirishi kerak")

        # Uchinchi a'zo — endi jamoa to'lgan (2 a'zo = limit 2).
        await db.upsert_user(6004, name="Uchinchi")
        ok = await db.assign_team_member(6004, team_id, ADMIN_A)
        self.assertFalse(
            ok,
            "limit to'lganda yangi a'zo biriktirilmasligi kerak",
        )
        u = await db.get_user(6004)
        self.assertIsNone(
            u.get("team_id"),
            "rad etilgan a'zo jamoaga biriktirilmasligi kerak",
        )

    async def test_unlimited_team_always_has_slot(self) -> None:
        team = await db.create_team("Cheksiz jamoa", ADMIN_A, max_users=0)
        for index in range(5):
            await db.upsert_user(7000 + index, name=f"U{index}", team_id=int(team["id"]))
        self.assertTrue(await db.team_has_free_slot(int(team["id"])))

    async def test_members_are_scoped_to_owner(self) -> None:
        team_a = await db.create_team("Jamoa A", ADMIN_A, max_users=10)
        team_b = await db.create_team("Jamoa B", ADMIN_B, max_users=10)

        await db.upsert_user(
            USER_1, name="A user", team_id=int(team_a["id"]), owner_admin_uid=ADMIN_A
        )
        await db.upsert_user(
            USER_2, name="B user", team_id=int(team_b["id"]), owner_admin_uid=ADMIN_B
        )

        members_a = await db.get_users_by_owner(ADMIN_A)
        self.assertEqual([int(m["uid"]) for m in members_a], [USER_1])
        members_b = await db.get_users_by_owner(ADMIN_B)
        self.assertEqual([int(m["uid"]) for m in members_b], [USER_2])

        team_a_members = await db.get_team_members(int(team_a["id"]))
        self.assertEqual([int(m["uid"]) for m in team_a_members], [USER_1])

    async def test_team_admin_expiry_detection(self) -> None:
        await db.upsert_user(ADMIN_A, name="Admin A", is_team_admin=1)
        self.assertFalse(await db.team_admin_expired(ADMIN_A))

        await db.set_admin_expires(ADMIN_A, "2020-01-01 00:00:00")
        self.assertTrue(await db.team_admin_expired(ADMIN_A))
        self.assertIn(ADMIN_A, await db.get_expired_team_admins())

    async def test_set_team_admin_and_limits(self) -> None:
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at="2030-01-01 00:00:00"
        )
        admin = await db.get_user(ADMIN_A)
        self.assertTrue(admin["is_team_admin"])
        self.assertEqual(int(admin["admin_max_users"]), 5)

        await db.set_admin_max_users(ADMIN_A, 12)
        admin = await db.get_user(ADMIN_A)
        self.assertEqual(int(admin["admin_max_users"]), 12)

    async def test_update_team_limit_keeps_existing_members(self) -> None:
        team = await db.create_team("Jamoa", ADMIN_A, max_users=10)
        team_id = int(team["id"])
        await db.upsert_user(USER_1, name="U1", team_id=team_id)
        await db.upsert_user(USER_2, name="U2", team_id=team_id)

        await db.update_team(team_id, max_users=1)
        updated = await db.get_team(team_id)
        self.assertEqual(int(updated["max_users"]), 1)
        # Kamaytirilganda ham a'zolar saqlanadi.
        self.assertEqual(len(await db.get_team_members(team_id)), 2)
        # Yangi user qabul qilinmaydi.
        self.assertFalse(await db.team_has_free_slot(team_id))


class TeamUiTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa klaviaturasi va matnlari."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_team_pick_keyboard_lists_teams(self) -> None:
        team = await db.create_team("Jamoa One", ADMIN_A, max_users=5)
        teams = await db.get_all_teams()
        kb = KB.kb_team_pick(teams)

        buttons = [b for row in kb.inline_keyboard for b in row]
        labels = [b.text for b in buttons]
        self.assertTrue(any("Jamoa One" in label for label in labels))

        callbacks = [b.callback_data for b in buttons if b.callback_data]
        self.assertIn(f"team:pick:{int(team['id'])}", callbacks)

    async def test_team_admin_menu_has_expected_sections(self) -> None:
        kb = KB.kb_team_admin_panel()
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn("tadm:users", callbacks)
        self.assertIn("tadm:stats", callbacks)
        self.assertIn("tadm:message", callbacks)

    async def test_team_texts_render(self) -> None:
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        text = T.team_admin_menu_text(team, members=2, expires="2026-12-01")
        self.assertIn("Jamoa", text)
        self.assertIn("2/5 ta", text)

        members_text = T.team_members_text(
            [{"uid": 1, "name": "Ali", "running": 1}, {"uid": 2, "name": "Vali"}]
        )
        self.assertIn("Ali", members_text)
        self.assertIn("Vali", members_text)

    async def test_team_pick_text_paginates(self) -> None:
        teams = [
            {"id": i, "name": f"Jamoa {i}", "max_users": 0} for i in range(1, 13)
        ]
        page0 = T.team_pick_text(teams, page=0, page_size=10)
        page1 = T.team_pick_text(teams, page=1, page_size=10)
        self.assertIn("Sahifa 1/2", page0)
        self.assertIn("Sahifa 2/2", page1)
        self.assertIn("Jamoa 11", page1)

    async def test_video_is_rejected(self) -> None:
        """Video yuborilsa — rad etiladi (faqat surat qabul qilinadi)."""
        video_msg = SimpleNamespace(
            photo=None,
            video=SimpleNamespace(
                mime_type="video/mp4", file_size=1024, get_file=AsyncMock()
            ),
            document=None,
        )
        items, errors = await media_ingest.download_message_media(video_msg, USER_1)
        self.assertEqual(items, [])
        self.assertTrue(errors)
        self.assertIn("Video", errors[0])

    async def test_photo_limit_is_four(self) -> None:
        self.assertEqual(MAX_ALBUM_FILES, 4)

    async def test_admin_registration_flow(self) -> None:
        """Jamoa admini o'z jamoasini yaratadi: sig'im → nom → jamoa.

        Jamoa adminini faqat super admin yaratadi (telefon orqali
        tayyorlaydi). Admin ro'yxatdan o'tgach, birinchi marta
        «👥 Jamoam» bosganda jamoani o'zi shakllantiradi.
        """
        await db.upsert_user(ADMIN_A, name="Admin A", is_team_admin=1)

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_A, username="admina"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

        await Tm.begin_team_admin_register(update, ADMIN_A)
        # FSM login modulida saqlanadi:
        from bot.login import user_states

        self.assertEqual(user_states.get(ADMIN_A)["step"], "team_admin_size")

        await Tm.handle_team_admin_size(update, ADMIN_A, "5")
        self.assertEqual(user_states.get(ADMIN_A)["step"], "team_admin_name")

        await Tm.handle_team_admin_name(update, ADMIN_A, "Avtoelon TJ")
        teams = await db.get_teams(ADMIN_A)
        self.assertEqual(len(teams), 1)
        self.assertEqual(teams[0]["name"], "Avtoelon TJ")
        self.assertEqual(int(teams[0]["max_users"]), 5)

        admin = await db.get_user(ADMIN_A)
        self.assertTrue(admin["is_team_admin"])

    async def test_non_admin_cannot_register_team(self) -> None:
        """Oddiy foydalanuvchi jamoa admini bo'la olmaydi.

        Jamoa adminini faqat super admin panelidan qo'shish mumkin.
        """
        from bot.login import user_states

        # ``user_states`` global — boshqa testdan qolgan state bo'lishi
        # mumkin. O'z holatimizni tozalab boshlaymiz.
        user_states.pop(USER_1, None)

        await db.upsert_user(USER_1, name="Oddiy")
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_1, username="oddiy"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        await Tm.begin_team_admin_register(update, USER_1)

        self.assertIsNone(user_states.get(USER_1))
        reply = update.message.reply_text.await_args.args[0]
        self.assertIn("super admin", reply.lower())

    async def test_admin_registration_rejects_small_size(self) -> None:
        await db.upsert_user(ADMIN_B, name="Admin B", is_team_admin=1)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_B, username="adminb"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        await Tm.begin_team_admin_register(update, ADMIN_B)
        await Tm.handle_team_admin_size(update, ADMIN_B, "1")
        from bot.login import user_states

        self.assertEqual(
            user_states.get(ADMIN_B)["step"], "team_admin_size",
            "minimal jamoa hajmi qabul qilinmali",
        )
        self.assertGreaterEqual(TEAM_MIN_MEMBERS, 2)

    async def test_team_admin_cannot_touch_other_team(self) -> None:
        """Jamoa admini boshqa jamoaning a'zosiga kira olmaydi."""
        team_a = await db.create_team("Jamoa A", ADMIN_A, max_users=10)
        team_b = await db.create_team("Jamoa B", ADMIN_B, max_users=10)
        await db.upsert_user(
            USER_2, name="B user", team_id=int(team_b["id"]), owner_admin_uid=ADMIN_B
        )
        await db.upsert_user(ADMIN_A, name="Admin A", is_team_admin=1)

        update = SimpleNamespace(
            callback_query=SimpleNamespace(
                data=f"tadm:member:{USER_2}",
                answer=AsyncMock(),
                edit_message_text=AsyncMock(),
                message=SimpleNamespace(reply_text=AsyncMock()),
            )
        )
        await Tm.handle_team_admin_callback(update, ADMIN_A, f"tadm:member:{USER_2}")
        update.callback_query.answer.assert_awaited()
        args = update.callback_query.answer.await_args
        self.assertIn("jamoangizda emas", str(args.args[0]))

    async def test_team_link_format(self) -> None:
        link = Tm.team_link(42)
        self.assertIn("start=team_42", link)
        self.assertTrue(link.startswith("https://t.me/"))


if __name__ == "__main__":
    unittest.main()


class TeamExpiryTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa admini muddati tugaganda jamoasi ham to'xtashi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_expired_admin_team_members_are_listed(self) -> None:
        """Muddati tugagan adminning jamoasi aniqlanadi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=10)
        await db.upsert_user(
            ADMIN_A,
            name="Admin A",
            is_team_admin=1,
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            admin_expires_at="2020-01-01 00:00:00",
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )

        expired = await db.get_expired_team_admins()
        self.assertIn(ADMIN_A, expired)

        # Jamoa a'zolari admin orqali ko'rinadi (to'xtatish uchun).
        members = await db.get_users_by_owner(ADMIN_A)
        self.assertIn(USER_1, [int(m["uid"]) for m in members])

    async def test_active_admin_is_not_expired(self) -> None:
        await db.upsert_user(
            ADMIN_A,
            name="Admin A",
            is_team_admin=1,
            admin_expires_at="2099-01-01 00:00:00",
        )
        self.assertNotIn(ADMIN_A, await db.get_expired_team_admins())
        self.assertFalse(await db.team_admin_expired(ADMIN_A))

    async def test_admin_without_expiry_never_expires(self) -> None:
        await db.upsert_user(ADMIN_A, name="Admin A", is_team_admin=1)
        self.assertFalse(await db.team_admin_expired(ADMIN_A))

    async def test_referral_auto_joins_referrer_team(self) -> None:
        """Referal orqali kelgan user referrer'ning jamoasiga biriktiriladi."""
        from bot import referral as RF

        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.upsert_user(
            ADMIN_A,
            name="Admin A",
            is_admin=1,
            is_team_admin=1,
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )

        self.assertTrue(await RF.register_referral(USER_1, f"ref_{ADMIN_A}"))
        user = await db.get_user(USER_1)
        self.assertEqual(int(user["team_id"]), int(team["id"]))
        self.assertEqual(int(user["owner_admin_uid"]), ADMIN_A)

    async def test_referral_does_not_join_full_team(self) -> None:
        """Jamoa to'ldiq bo'lsa — referal biriktirilmaydi.

        Sig'im — jamoaning **a'zolar** soni (jamoa admini hisobga
        olinmaydi). Sig'im 1 = bitta a'zo mumkin.
        """
        from bot import referral as RF

        team = await db.create_team("Jamoa", ADMIN_A, max_users=1)
        await db.upsert_user(
            ADMIN_A,
            name="Admin A",
            is_admin=1,
            is_team_admin=1,
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )

        # Birinchi a'zo — sig'im 1 bo'lgan jamoaga sig'adi.
        self.assertTrue(await RF.register_referral(USER_1, f"ref_{ADMIN_A}"))
        user = await db.get_user(USER_1)
        self.assertEqual(
            int(user["team_id"]),
            int(team["id"]),
            "birinchi a'zo jamoaga biriktirilishi kerak",
        )

        # Endi jamoa to'ldi (1 a'zo = limit 1) — ikkinchisi kirmaydi.
        self.assertTrue(await RF.register_referral(6002, f"ref_{ADMIN_A}"))
        user2 = await db.get_user(6002)
        self.assertIsNone(
            user2.get("team_id"), "to'lgan jamoaga biriktirilmasligi kerak"
        )


class TeamChoiceTests(unittest.IsolatedAsyncioTestCase):
    """Jamoalar yopiq — jamoaga faqat jamoa admini qo'shadi.

    Oddiy foydalanuvchi jamoani tanlay olmaydi: jamoaga qo'shilish
    telefon taklifi (``➕ Do'st qo'shish``) yoki jamoa havolasi
    (``/start team_<id>``) orqali amalga oshadi.
    """

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_picker_is_closed_for_ordinary_user(self) -> None:
        """Oddiy foydalanuvchi jamoalarni ko'ra olmaydi."""
        await db.create_team("Jamoa One", ADMIN_A, max_users=5)
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_1),
            message=message,
        )
        await Tm.show_team_picker(update, USER_1)

        reply = message.reply_text.await_args.args[0]
        self.assertIn("yopiq", reply.lower())
        # Jamoalarning nomi ko'rinmasligi kerak.
        self.assertNotIn("Jamoa One", reply)

    async def test_picker_is_closed_for_callback(self) -> None:
        """Oddiy foydalanuvchi ``team:pick`` bilan jamoaga qo'shila olmaydi."""
        team = await db.create_team("Jamoa One", ADMIN_A, max_users=5)
        q = SimpleNamespace(
            data=f"team:pick:{int(team['id'])}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=USER_1, full_name="Vali", username="vali"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_pick_callback(
                update, USER_1, f"team:pick:{int(team['id'])}"
            )

        user = await db.get_user(USER_1)
        self.assertIsNone(
            user.get("team_id") if user else None,
            "jamoalar yopiq — oddiy user jamoaga qo'shila olmaydi",
        )
        q.answer.assert_awaited()

    async def test_picker_opens_for_super_admin(self) -> None:
        """Super admin jamoalarni ko'radi va boshqaradi."""
        from config.config import SUPER_ADMIN

        await db.create_team("Jamoa One", ADMIN_A, max_users=5)
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=message,
        )
        await Tm.show_team_picker(update, SUPER_ADMIN)

        reply = message.reply_text.await_args.args[0]
        self.assertIn("Jamoa One", reply)

    async def test_pick_title_explains_both_choices(self) -> None:
        """Matnda ikkala variant ham tushuntiriladi."""
        self.assertIn("guruh bilan ishlash", T.TEAM_PICK_TITLE.lower())
        self.assertIn("jamoasiz", T.TEAM_PICK_TITLE.lower())


class NumberingConsistencyTests(unittest.IsolatedAsyncioTestCase):
    """Ro'yxatdagi raqamlar va pastdagi tugmalar mos kelishi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_user_group_delete_buttons_are_numbered(self) -> None:
        """Foydalanuvchi panelida o'chirish tugmalari raqamli."""
        groups = [
            {"id": 1, "value": "@birinchi"},
            {"id": 2, "value": "@ikkinchi"},
        ]
        kb = KB.kb_groups_delete(groups)
        labels = [b.text for row in kb.inline_keyboard for b in row]
        self.assertIn("🗑 1. @birinchi", labels)
        self.assertIn("🗑 2. @ikkinchi", labels)

    async def test_admin_group_delete_buttons_are_numbered(self) -> None:
        """Admin panelida o'chirish tugmalari raqamli (matn bilan mos)."""
        groups = [
            {"id": 1, "value": "@birinchi", "interval_min": None},
            {"id": 2, "value": "@ikkinchi", "interval_min": 15},
        ]
        kb = KB.kb_admin_groups(1001, groups)
        labels = [b.text for row in kb.inline_keyboard for b in row]
        self.assertIn("🗑 1. @birinchi", labels)
        self.assertIn("🗑 2. @ikkinchi", labels)
        # Interval tugmasi o'zgarmagan.
        self.assertIn("⏱ Umumiy", labels)
        self.assertIn("⏱ 15 daq", labels)

    async def test_admin_post_delete_buttons_are_numbered(self) -> None:
        """Admin panelida post o'chirish tugmalari raqamli."""
        posts = [{"id": 1, "text": "Birinchi post"}, {"id": 2, "text": "Ikkinchi post"}]
        kb = KB.kb_admin_posts(1001, posts)
        labels = [b.text for row in kb.inline_keyboard for b in row]
        self.assertIn("🗑 1. Birinchi post", labels)
        self.assertIn("🗑 2. Ikkinchi post", labels)

    async def test_numbering_matches_text_list(self) -> None:
        """Matndagi raqamlar va tugmadagi raqamlar bir xil."""
        groups = [
            {"id": 1, "value": "@birinchi"},
            {"id": 2, "value": "@ikkinchi"},
            {"id": 3, "value": "@uchinchi"},
        ]
        text = T.groups_delete_text(groups)
        kb = KB.kb_groups_delete(groups)
        labels = [b.text for row in kb.inline_keyboard for b in row]
        for index, group in enumerate(groups, 1):
            self.assertIn(f"{index}. {group['value']}", text)
            self.assertIn(f"🗑 {index}. {group['value']}", labels)

    async def test_callback_data_unchanged(self) -> None:
        """callback_data o'zgarmadi (raqam faqat ko'rinishda)."""
        groups = [{"id": 77, "value": "@test"}]
        kb = KB.kb_groups_delete(groups)
        callbacks = [b.callback_data for row in kb.inline_keyboard for b in row]
        self.assertIn("delg:id:77:0", callbacks)


class TeamApprovalSeparationTests(unittest.IsolatedAsyncioTestCase):
    """Jamoali foydalanuvchilarni faqat jamoa admini tasdiqlaydi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_approve_team_member_rejects_when_team_full(self) -> None:
        """Jamoa sig'i to'lgan bo'lsa, yangi a'zo tasdiqlanmaydi.

        Chegara `>=` bilan tekshiriladi: jamoada a'zolar soni limitga
        teng bo'lsa, yana bir kishi qo'shilmasligi kerak.
        """
        team = await db.create_team("To'la jamoa", ADMIN_A, max_users=2)
        team_id = int(team["id"])
        await db.set_team_admin(
            ADMIN_A, team_id, max_users=2, admin_expires_at=calc_expires(30)
        )
        # Admin + 1 a'zo = limit 2 → jamoa to'ldi.
        await db.upsert_user(USER_1, name="Birinchi", team_id=team_id)
        await db.upsert_user(
            USER_2,
            name="Ikkinchi",
            team_id=team_id,
            owner_admin_uid=ADMIN_A,
            awaiting_approval=1,
        )

        q = SimpleNamespace(
            answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        update = SimpleNamespace(callback_query=q)
        await Tm.approve_team_member(update, ADMIN_A, USER_2, days=30)

        q.answer.assert_awaited()
        self.assertIn(
            "sig'imi to'lgan",
            q.answer.await_args.args[0],
            "to'lgan jamoaga a'zo tasdiqlanmashi kerak",
        )
        u = await db.get_user(USER_2)
        self.assertTrue(
            u.get("awaiting_approval"),
            "rad etilgan a'zo tasdiqlanmagan bo'lishi kerak",
        )

    async def test_approve_team_member_sets_duration(self) -> None:
        """Tasdiqlangan a'zoga muddat beriladi va tasdiqlanadi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        team_id = int(team["id"])
        await db.set_team_admin(
            ADMIN_A, team_id, max_users=5, admin_expires_at=calc_expires(30)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=team_id,
            owner_admin_uid=ADMIN_A,
            awaiting_approval=1,
        )

        q = SimpleNamespace(
            answer=AsyncMock(), edit_message_text=AsyncMock()
        )
        update = SimpleNamespace(callback_query=q)
        await Tm.approve_team_member(update, ADMIN_A, USER_1, days=30)

        u = await db.get_user(USER_1)
        self.assertEqual(int(u.get("awaiting_approval") or 0), 0)
        self.assertEqual(int(u.get("is_admin") or 0), 1)
        self.assertIsNotNone(
            u.get("tariff_expires_at"),
            "a'zoga muddat berilishi kerak",
        )

    async def test_pending_list_excludes_team_users(self) -> None:
        """Super admin 'Tasdiq kutilayotganlar' ro'yxatida jamoali userlar yo'q."""
        await db.upsert_user(USER_1, name="Jamoali", awaiting_approval=1, owner_admin_uid=ADMIN_A)
        await db.upsert_user(USER_2, name="Jamoasiz", awaiting_approval=1)

        pending = await db.get_pending_users()
        uids = [int(p["uid"]) for p in pending]
        self.assertNotIn(USER_1, uids, "jamoali user super admin ro'yxatida bo'lmasligi kerak")
        self.assertIn(USER_2, uids, "jamoasiz user super admin ro'yxatida bo'lishi kerak")

    async def test_auto_approve_excludes_team_users(self) -> None:
        """Avto-tasdiq jamoali userlarni tasdiqlamaydi."""
        await db.upsert_user(
            USER_1,
            name="Jamoali",
            awaiting_approval=1,
            owner_admin_uid=ADMIN_A,
            pending_session="enc",
        )
        await db.upsert_user(
            USER_2, name="Jamoasiz", awaiting_approval=1, pending_session="enc"
        )

        candidates = await db.get_auto_approvable_candidates()
        uids = [int(c["uid"]) for c in candidates]
        self.assertNotIn(USER_1, uids)
        self.assertIn(USER_2, uids)

    async def test_team_member_has_approve_button(self) -> None:
        """Jamoa admini a'zolar ro'yxatida tasdiqlash tugmasini ko'radi."""
        members = [
            {"uid": USER_1, "name": "Kutilmoqda", "awaiting_approval": 1},
            {"uid": USER_2, "name": "Tasdiqlangan", "awaiting_approval": 0},
        ]
        kb = KB.kb_team_members(members)
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn(f"tadm:approve:{USER_1}", callbacks)
        self.assertNotIn(f"tadm:approve:{USER_2}", callbacks)

    async def test_team_admin_approves_own_member(self) -> None:
        """Jamoa admini o'z a'zosini tasdiqlaydi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.upsert_user(
            ADMIN_A, name="Admin", is_team_admin=1, team_id=int(team["id"])
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            awaiting_approval=1,
        )

        q = SimpleNamespace(
            data=f"tadm:approve:{USER_1}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(update, ADMIN_A, f"tadm:approve:{USER_1}")

        # Birinchi bosqich — muddat tanlash oynasi ochiladi.
        markup = q.edit_message_text.await_args.kwargs.get("reply_markup")
        callbacks = {
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        }
        self.assertIn(f"tadm:approveterm:{USER_1}:7", callbacks)

        # Ikkinchi bosqich — muddat tanlanadi va tasdiqlanadi.
        await Tm.handle_team_admin_callback(
            update, ADMIN_A, f"tadm:approveterm:{USER_1}:7"
        )
        member = await db.get_user(USER_1)
        self.assertTrue(member["is_admin"], "jamoa admini a'zosini tasdiqlashi kerak")
        self.assertIsNotNone(member["tariff_expires_at"])

        # Muddat tanlangan (7 kun) — standart 30 kun emas.
        assert_expires_in_days(self, member["tariff_expires_at"], 7)

    async def test_notify_goes_to_team_admin(self) -> None:
        """Ariza xabari jamoa adminiga boradi, super admin ga emas."""
        from bot import login as Login

        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            awaiting_approval=1,
        )

        sent = []

        async def _send(chat_id, text, **kwargs):
            sent.append((int(chat_id), text))

        app = SimpleNamespace(bot=SimpleNamespace(send_message=_send))
        with patch.object(Login, "application", app):
            await Login.notify_super_for_approval(USER_1)

        targets = [chat_id for chat_id, _ in sent]
        self.assertIn(ADMIN_A, targets, "xabar jamoa adminiga borishi kerak")
        self.assertNotIn(
            SUPER_ADMIN, targets, "super admin jamoali arizani olmasligi kerak"
        )
        self.assertIn("JAMOA", sent[0][1])

    async def test_notify_goes_to_super_admin_for_teamless(self) -> None:
        """Jamoasiz ariza super admin ga boradi."""
        from bot import login as Login

        await db.upsert_user(USER_2, name="Jamoasiz", awaiting_approval=1)

        sent = []

        async def _send(chat_id, text, **kwargs):
            sent.append((int(chat_id), text))

        app = SimpleNamespace(bot=SimpleNamespace(send_message=_send))
        with patch.object(Login, "application", app):
            await Login.notify_super_for_approval(USER_2)

        targets = [chat_id for chat_id, _ in sent]
        self.assertIn(SUPER_ADMIN, targets)
        self.assertNotIn(ADMIN_A, targets)


class ApprovalDurationTests(unittest.IsolatedAsyncioTestCase):
    """Tasdiqlashda muddatni tanlash — super admin va jamoa admini uchun."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_super_admin_approve_offers_durations(self) -> None:
        """Super admin tasdiqlashda muddat tanlash oynasi ochiladi."""
        kb = KB.kb_approve_term_options(USER_1, [1, 7, 30, 90])
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn(f"app:term:{USER_1}:1", callbacks)
        self.assertIn(f"app:term:{USER_1}:7", callbacks)
        self.assertIn(f"app:term:{USER_1}:30", callbacks)
        self.assertIn(f"app:term:{USER_1}:90", callbacks)

    async def test_team_approve_offers_durations(self) -> None:
        """Jamoa admini tasdiqlashda muddat tanlash oynasi ochiladi."""
        kb = KB.kb_team_approve_term_options(USER_1, [1, 7, 30, 90])
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn(f"tadm:approveterm:{USER_1}:7", callbacks)
        self.assertIn(f"tadm:approveterm:{USER_1}:30", callbacks)

    async def test_approve_with_chosen_duration(self) -> None:
        """Tanlangan muddat beriladi (standart 30 kun emas)."""
        from admin import admin_actions

        await db.upsert_user(USER_1, name="Vali", awaiting_approval=1)

        q = SimpleNamespace(
            data=f"app:term:{USER_1}:7",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(admin_actions, "application", None):
            await admin_actions.action_approve(update, SUPER_ADMIN, USER_1, days=7)

        user = await db.get_user(USER_1)
        self.assertTrue(user["is_admin"])
        assert_expires_in_days(self, user["tariff_expires_at"], 7)

    async def test_approve_defaults_to_configured_duration(self) -> None:
        """Muddat berilmasa standart qiymat ishlatiladi."""
        from admin import admin_actions
        from config.config import DEFAULT_DURATION_DAYS

        await db.upsert_user(USER_1, name="Vali", awaiting_approval=1)

        q = SimpleNamespace(
            data=f"app:term:{USER_1}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(admin_actions, "application", None):
            await admin_actions.action_approve(update, SUPER_ADMIN, USER_1)

        user = await db.get_user(USER_1)
        assert_expires_in_days(
            self, user["tariff_expires_at"], DEFAULT_DURATION_DAYS
        )

    async def test_super_admin_cannot_approve_team_user(self) -> None:
        """Super admin jamoali foydalanuvchini tasdiqlamaydi."""
        from admin import admin_actions

        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            awaiting_approval=1,
        )

        q = SimpleNamespace(
            data=f"app:term:{USER_1}:7",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(admin_actions, "application", None):
            await admin_actions.action_approve(update, SUPER_ADMIN, USER_1, days=7)

        user = await db.get_user(USER_1)
        self.assertFalse(user["is_admin"], "super admin jamoali userni tasdiqlamasligi kerak")
        text = q.edit_message_text.await_args.args[0]
        self.assertIn("jamoa adminining vazifasi", text)


class DurationCapTests(unittest.IsolatedAsyncioTestCase):
    """Muddat chegarasi (anti-fraud): jamoa admini 60 kundan ko'p bera olmaydi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    def test_default_cap_is_60_days(self) -> None:
        from config.config import TEAM_MEMBER_MAX_DAYS

        self.assertEqual(TEAM_MEMBER_MAX_DAYS, 60)

    def test_clamp_days_for_team_admin(self) -> None:
        from core.duration_policy import clamp_days

        self.assertEqual(clamp_days(7, is_super_admin=False), 7)
        self.assertEqual(clamp_days(30, is_super_admin=False), 30)
        # Chegaradan oshgan — qisqartiriladi.
        self.assertEqual(clamp_days(90, is_super_admin=False), 60)
        self.assertEqual(clamp_days(365, is_super_admin=False), 60)
        self.assertEqual(clamp_days(1000, is_super_admin=False), 60)

    def test_clamp_days_for_super_admin_unlimited(self) -> None:
        from core.duration_policy import clamp_days

        self.assertEqual(clamp_days(365, is_super_admin=True), 365)
        self.assertEqual(clamp_days(9999, is_super_admin=True), 9999)

    def test_is_over_cap(self) -> None:
        from core.duration_policy import is_over_cap

        self.assertFalse(is_over_cap(60, is_super_admin=False))
        self.assertTrue(is_over_cap(61, is_super_admin=False))
        self.assertFalse(is_over_cap(365, is_super_admin=True))

    def test_cap_note(self) -> None:
        from core.duration_policy import cap_note

        self.assertIn("60", cap_note(is_super_admin=False))
        self.assertEqual(cap_note(is_super_admin=True), "")

    async def test_team_admin_approval_respects_cap(self) -> None:
        """Jamoa admini 365 kun so'rasa — 60 kunga qisqaradi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            awaiting_approval=1,
        )

        q = SimpleNamespace(
            data=f"tadm:approveterm:{USER_1}:365",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(
                update, ADMIN_A, f"tadm:approveterm:{USER_1}:365"
            )

        member = await db.get_user(USER_1)
        self.assertTrue(member["is_admin"])
        # Muddat 60 kundan ko'p bo'lmasligi kerak. Aniq sanani emas,
        # **muddat intervalini** tekshiramiz — bu vaqt chegarasiga bog'liq
        # emas (server vaqti TZ'si farq qilishi mumkin, `calc_expires` esa
        # UTC'dan foydalanadi).
        from datetime import datetime, timezone

        expires = datetime.strptime(
            member["tariff_expires_at"], "%Y-%m-%d %H:%M:%S"
        ).replace(tzinfo=timezone.utc)
        delta = expires - datetime.now(timezone.utc)
        self.assertLessEqual(
            delta.total_seconds(),
            60 * 86400 + 5,
            "jamoa admini 60 kundan ko'p muddat bermasligi kerak",
        )
        self.assertGreater(
            delta.total_seconds(),
            59 * 86400,
            "muddat taxminan 60 kun bo'lishi kerak",
        )

    async def test_team_admin_setterm_rejects_over_cap(self) -> None:
        """Allaqachon tasdiqlangan a'zoga muddat berishda chegara buzilmaydi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )

        q = SimpleNamespace(
            data=f"tadm:setterm:{USER_1}:365",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(
                update, ADMIN_A, f"tadm:setterm:{USER_1}:365"
            )

        # Rad etilgan — muddat o'zgarmagan.
        q.answer.assert_awaited()
        alert = q.answer.await_args.kwargs.get("show_alert")
        self.assertTrue(alert, "foydalanuvchiga ogohlantirish ko'rsatilishi kerak")
        self.assertIn("60", q.answer.await_args.args[0])

    async def test_team_admin_setterm_allows_within_cap(self) -> None:
        """Chegara ichidagi muddat beriladi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )

        q = SimpleNamespace(
            data=f"tadm:setterm:{USER_1}:30",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(
                update, ADMIN_A, f"tadm:setterm:{USER_1}:30"
            )

        member = await db.get_user(USER_1)
        assert_expires_in_days(self, member["tariff_expires_at"], 30)

    async def test_team_approve_menu_hides_over_cap_options(self) -> None:
        """Muddat oynasida chegara oshgan variantlar ko'rsatilmaydi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        q = SimpleNamespace(
            data=f"tadm:approve:{USER_1}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(update, ADMIN_A, f"tadm:approve:{USER_1}")

        markup = q.edit_message_text.await_args.kwargs.get("reply_markup")
        callbacks = {
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        }
        self.assertIn(f"tadm:approveterm:{USER_1}:30", callbacks)
        self.assertIn(f"tadm:approveterm:{USER_1}:60", callbacks)
        self.assertNotIn(
            f"tadm:approveterm:{USER_1}:90", callbacks
        )
        self.assertNotIn(
            f"tadm:approveterm:{USER_1}:365", callbacks
        )

    async def test_super_admin_approve_menu_keeps_long_options(self) -> None:
        """Super admin uchun uzun muddat variantlari saqlanadi."""
        await db.upsert_user(USER_1, name="Vali", awaiting_approval=1)
        q = SimpleNamespace(
            data=f"app:yes:{USER_1}",
            from_user=SimpleNamespace(id=SUPER_ADMIN),
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            effective_chat=SimpleNamespace(type="private"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Cb, "application", None):
            await Cb.handle_admin_approve(update, SUPER_ADMIN, f"app:yes:{USER_1}")

        markup = q.edit_message_text.await_args.kwargs.get("reply_markup")
        callbacks = {
            b.callback_data
            for row in markup.inline_keyboard
            for b in row
            if b.callback_data
        }
        self.assertIn(f"app:term:{USER_1}:365", callbacks)

    async def test_super_admin_approve_not_capped(self) -> None:
        """Super admin 365 kun bersa — chekalanmaydi."""
        from admin import admin_actions
        await db.upsert_user(USER_1, name="Vali", awaiting_approval=1)

        q = SimpleNamespace(
            data=f"app:term:{USER_1}:365",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(admin_actions, "application", None):
            await admin_actions.action_approve(update, SUPER_ADMIN, USER_1, days=365)

        user = await db.get_user(USER_1)
        assert_expires_in_days(self, user["tariff_expires_at"], 365)


class TeamAdminExpiryWorkerTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa admini muddati tugasa — jamoasi ham to'xtaydi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_team_owner_expired_for_member(self) -> None:
        """Jamoa admini muddati tugagan — a'zo uchun True."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(-1)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )
        self.assertTrue(await db.team_owner_expired(USER_1))

    async def test_team_owner_not_expired_while_admin_active(self) -> None:
        """Jamoa admini faol — a'zo uchun False."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )
        self.assertFalse(await db.team_owner_expired(USER_1))

    async def test_team_owner_expired_false_for_plain_user(self) -> None:
        """Oddiy user uchun False."""
        await db.upsert_user(USER_1, name="Oddiy")
        self.assertFalse(await db.team_owner_expired(USER_1))

    async def test_team_owner_expired_false_for_admin_itself(self) -> None:
        """Jamoa admini uchun False (uning muddati alohida tekshiriladi)."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(-1)
        )
        self.assertFalse(await db.team_owner_expired(ADMIN_A))

    async def test_start_blocked_when_team_admin_expired(self) -> None:
        """Jamoa admini muddati tugagan — Start ishlamaydi."""
        from bot import menu as Menu

        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(-1)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            is_admin=1,
            session="sess",
            tariff_expires_at=calc_expires(365),
        )
        await db.add_chat(USER_1, "-100123")
        await db.add_post(USER_1, "Post", "matn", [])

        with patch.object(Menu, "worker_manager", SimpleNamespace(is_running=lambda u: False)):
            ok, message = await Menu.confirm_start(USER_1)

        self.assertFalse(ok, "muddati tugagan jamoada Start ishlamasligi kerak")
        self.assertIn("muddat", message.lower())


class TeamLeaveTests(unittest.IsolatedAsyncioTestCase):
    """Jamoadan chiqish — muddat ham tugaydi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def _make_member(self) -> tuple[int, int]:
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
            is_admin=1,
            tariff_expires_at=calc_expires(30),
        )
        return int(team["id"]), ADMIN_A

    async def test_leave_team_clears_membership(self) -> None:
        """Chiqishdan keyin team_id va owner_admin_uid tozalanadi."""
        await self._make_member()
        result = await db.leave_team(USER_1)
        self.assertIsNotNone(result)
        user = await db.get_user(USER_1)
        self.assertIsNone(user["team_id"])
        self.assertIsNone(user["owner_admin_uid"])

    async def test_leave_team_clears_expiry(self) -> None:
        """Jamoa admini bergan muddat chiqish bilan tugaydi."""
        await self._make_member()
        await db.leave_team(USER_1)
        user = await db.get_user(USER_1)
        self.assertIsNone(user["tariff_expires_at"])

    async def test_leave_team_keeps_super_admin_expiry(self) -> None:
        """Super admin bergan muddat saqlanadi (jamoa admini emas)."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="Vali",
            team_id=int(team["id"]),
            owner_admin_uid=SUPER_ADMIN,
            tariff_expires_at=calc_expires(30),
        )
        await db.leave_team(USER_1)
        user = await db.get_user(USER_1)
        self.assertIsNotNone(
            user["tariff_expires_at"],
            "super admin bergan muddat jamoadan chiqishda saqlanishi kerak",
        )
        self.assertIsNone(user["team_id"])

    async def test_leave_team_admin_cannot_leave(self) -> None:
        """Jamoa admini o'z jamoasidan chiqmaydi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        result = await db.leave_team(ADMIN_A)
        self.assertIsNone(result, "jamoa egasi jamoasidan chiqmasligi kerak")
        user = await db.get_user(ADMIN_A)
        self.assertEqual(int(user["team_id"]), int(team["id"]))

    async def test_leave_team_plain_user_returns_none(self) -> None:
        """Jamoada bo'lmagan user uchun None."""
        await db.upsert_user(USER_1, name="Oddiy")
        self.assertIsNone(await db.leave_team(USER_1))

    async def test_leave_confirm_flow_stops_worker(self) -> None:
        """Chiqish tasdiqlanganda posting to'xtaydi."""
        await self._make_member()
        await db.set_running(USER_1, True)

        q = SimpleNamespace(
            data="team:leaveconfirm",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=USER_1),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_member_callback(
                update, USER_1, "team:leaveconfirm"
            )

        user = await db.get_user(USER_1)
        self.assertIsNone(user["team_id"])
        self.assertIsNone(user["tariff_expires_at"])
        self.assertFalse(user["running"], "posting to'xtatilishi kerak")

    async def test_leave_ask_shows_confirmation(self) -> None:
        """Chiqishdan oldin tasdiqlash oynasi ko'rsatiladi."""
        await self._make_member()
        q = SimpleNamespace(
            data="team:leaveask",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=USER_1),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_member_callback(update, USER_1, "team:leaveask")

        markup = q.edit_message_text.await_args.kwargs.get("reply_markup")
        callbacks = {
            b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn("team:leaveconfirm", callbacks)
        self.assertIn("team:leavecancel", callbacks)
        # Hali chiqmagan — muddat saqlanadi.
        user = await db.get_user(USER_1)
        self.assertIsNotNone(user["tariff_expires_at"])

    async def test_leave_cancel_keeps_membership(self) -> None:
        """Bekor qilinsa — jamoada qoladi, muddat saqlanadi."""
        await self._make_member()
        q = SimpleNamespace(
            data="team:leavecancel",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=USER_1),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_member_callback(update, USER_1, "team:leavecancel")

        user = await db.get_user(USER_1)
        self.assertIsNotNone(user["team_id"])
        self.assertIsNotNone(user["tariff_expires_at"])

    async def test_team_admin_cannot_leave_via_callback(self) -> None:
        """Jamoa admini callback orqali ham chiqmaydi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        q = SimpleNamespace(
            data="team:leaveconfirm",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_member_callback(
                update, ADMIN_A, "team:leaveconfirm"
            )

        user = await db.get_user(ADMIN_A)
        self.assertEqual(int(user["team_id"]), int(team["id"]))


class TeamAdminRegistrationTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa admini bo'lish oqimi — darhol tasdiqlangan bo'lishi kerak."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_new_team_admin_is_not_awaiting_approval(self) -> None:
        """Jamoani yaratgan admin ustiga tasdiq kutilmasligi kerak."""
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=ADMIN_A),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_size(update, ADMIN_A, "5")
            await Tm.handle_team_admin_name(update, ADMIN_A, "Mening jamoam")

        user = await db.get_user(ADMIN_A)
        self.assertTrue(user["is_team_admin"], "admin bo'lishi kerak")
        self.assertFalse(
            user["awaiting_approval"],
            "jamoa admini tasdiq kutilmasligi kerak",
        )
        self.assertIsNotNone(user["team_id"])
        self.assertTrue(
            user["is_admin"],
            "jamoa admini ham oddiy user kabi posting qila olishi kerak",
        )
        self.assertIsNotNone(user["tariff_expires_at"])

    async def test_team_admin_can_access_panel_immediately(self) -> None:
        """Jamoa admini darhol o'z paneliga kirishi kerak."""
        update = SimpleNamespace(
            message=SimpleNamespace(reply_text=AsyncMock()),
            effective_user=SimpleNamespace(id=ADMIN_A),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_size(update, ADMIN_A, "5")
            await Tm.handle_team_admin_name(update, ADMIN_A, "Mening jamoam")

        panel = SimpleNamespace(
            data="tadm:back",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        cb_update = SimpleNamespace(
            callback_query=panel,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(cb_update, ADMIN_A, "tadm:back")

        # Panel ochildi (rad etilmadi).
        called = (
            panel.edit_message_text.await_args is not None
            or cb_update.message.reply_text.await_args is not None
        )
        self.assertTrue(called, "jamoa admini paneli ochilishi kerak")


class TeamBlockTests(unittest.IsolatedAsyncioTestCase):
    """Jamoa admini bloklansa — jamoasi ham to'xtaydi."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def test_team_owner_disabled_when_admin_blocked(self) -> None:
        """Jamoa admini bloklanganda a'zo uchun True."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )
        self.assertFalse(await db.team_owner_disabled(USER_1))

        await db.set_blocked(ADMIN_A, True)
        self.assertTrue(
            await db.team_owner_disabled(USER_1),
            "bloklangan jamoa admini a'zosi uchun True bo'lishi kerak",
        )

    async def test_team_owner_disabled_false_for_plain_user(self) -> None:
        """Oddiy user uchun False."""
        await db.upsert_user(USER_1, name="Oddiy")
        self.assertFalse(await db.team_owner_disabled(USER_1))

    async def test_blocked_admin_team_members_stopped(self) -> None:
        """Bloklashda jamoa a'zolarining postingi to'xtatiladi."""
        from admin import admin_actions

        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )
        await db.set_running(USER_1, True)

        with patch.object(admin_actions, "application", None):
            stopped = await admin_actions._stop_blocked_admin_team(ADMIN_A)

        self.assertEqual(stopped, 1, "a'zo to'xtatilishi kerak")
        member = await db.get_user(USER_1)
        self.assertFalse(member["running"], "a'zoning postingi to'xtatilishi kerak")


class TeamKickAndExpiryTests(unittest.IsolatedAsyncioTestCase):
    """Jamoadan chiqarish, muddati tugagan indikator va muddat yangilash."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def _make_team(self) -> dict:
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A,
            int(team["id"]),
            max_users=5,
            admin_expires_at=calc_expires(365),
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )
        return team

    async def test_kick_removes_member_from_team(self) -> None:
        """Admin a'zoni jamoadan chiqarishi — a'zo jamoasiz qoladi."""
        await self._make_team()
        await db.set_running(USER_1, True)

        q = SimpleNamespace(
            data=f"tadm:kick:{USER_1}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None), patch.object(
            Tm, "_send", AsyncMock(return_value=True)
        ):
            await Tm.handle_team_admin_callback(update, ADMIN_A, f"tadm:kick:{USER_1}")

        member = await db.get_user(USER_1)
        self.assertIsNone(member["team_id"], "jamoadan chiqarilishi kerak")
        self.assertFalse(member["running"], "posting to'xtatilishi kerak")

    async def test_kick_cannot_target_other_team_member(self) -> None:
        """Boshqa jamoaning a'zosini chiqarib bo'lmaydi (izolyatsiya)."""
        await self._make_team()
        # USER_2 boshqa jamoada
        other = await db.create_team("Boshqa jamoa", ADMIN_B, max_users=5)
        await db.upsert_user(
            USER_2,
            name="Begona",
            team_id=int(other["id"]),
            owner_admin_uid=ADMIN_B,
        )

        q = SimpleNamespace(
            data=f"tadm:kick:{USER_2}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(update, ADMIN_A, f"tadm:kick:{USER_2}")

        member = await db.get_user(USER_2)
        self.assertIsNotNone(member["team_id"], "begona jamoaga tegilishi mumkin emas")

    async def test_kick_cannot_remove_team_owner(self) -> None:
        """Jamoa egasi jamoasidan chiqarilmaydi."""
        await self._make_team()
        q = SimpleNamespace(
            data=f"tadm:kick:{ADMIN_A}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=ADMIN_A),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(Tm, "application", None):
            await Tm.handle_team_admin_callback(update, ADMIN_A, f"tadm:kick:{ADMIN_A}")

        owner = await db.get_user(ADMIN_A)
        self.assertIsNotNone(owner["team_id"], "jamoa egasi chiqarilmaydi")

    async def test_expired_member_has_indicator(self) -> None:
        """Muddati tugagan a'zo ro'yxatda ⌛ bilan ko'rinadi."""
        team = await self._make_team()
        await db.set_user_limits(USER_1, tariff_expires_at="2020-01-01 00:00:00")

        members = await db.get_team_members(int(team["id"]))
        text = T.team_members_text(members)
        self.assertIn("⌛", text, "muddati tugagan indikator kerak")
        self.assertIn("muddat", text.lower())

    async def test_active_member_has_no_expiry_indicator(self) -> None:
        """Faol a'zo ⌛ olmaydi."""
        team = await self._make_team()
        await db.set_user_limits(USER_1, tariff_expires_at=calc_expires(30))
        members = await db.get_team_members(int(team["id"]))
        text = T.team_members_text(members)
        self.assertNotIn("⌛ A'zo", text)

    async def test_member_expired_helper(self) -> None:
        """member_expired to'g'ri ishlaydi."""
        self.assertFalse(T.member_expired({}))
        self.assertFalse(T.member_expired({"tariff_expires_at": calc_expires(10)}))
        self.assertTrue(
            T.member_expired({"tariff_expires_at": "2020-01-01 00:00:00"})
        )


class MainKeyboardRoleTests(unittest.IsolatedAsyncioTestCase):
    """Asosiy menyuda jamoa tugmalari har bir ekranda saqlanishi kerak."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    @staticmethod
    def _buttons(markup) -> list[str]:
        return [b.text for row in markup.keyboard for b in row]

    async def test_team_admin_sees_team_menu_button(self) -> None:
        """Jamoa admini asosiy menyuda «👥 Jamoam» tugmasini ko'radi."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        markup = await KB.kb_main_for(ADMIN_A)
        self.assertIn(T.BTN_TEAM_MENU, self._buttons(markup))

    async def test_team_member_sees_team_menu_button(self) -> None:
        """Jamoa a'zosi ham «👥 Jamoam» tugmasini ko'radi (chiqish uchun)."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.upsert_user(
            USER_1, name="A'zo", team_id=int(team["id"]), owner_admin_uid=ADMIN_A
        )
        markup = await KB.kb_main_for(USER_1)
        self.assertIn(T.BTN_TEAM_MENU, self._buttons(markup))

    async def test_plain_user_sees_no_team_pick_button(self) -> None:
        """Jamoasiz foydalanuvchi jamoani tanlash tugmasini KO'RMASDI.

        Jamoalar yopiq — jamoaga faqat jamoa admini qo'shadi.
        """
        await db.upsert_user(USER_1, name="Oddiy")
        markup = await KB.kb_main_for(USER_1)
        self.assertNotIn(T.BTN_TEAM_PICK, self._buttons(markup))
        self.assertNotIn(T.BTN_TEAM_MENU, self._buttons(markup))

    async def test_plain_user_does_not_see_admin_button(self) -> None:
        """Jamoasiz foydalanuvchi «👑 Admin bo'lish» tugmasini KO'RMASDI.

        Jamoa adminini faqat super admin panelidan qo'shish mumkin.
        """
        await db.upsert_user(USER_1, name="Oddiy")
        markup = await KB.kb_main_for(USER_1)
        self.assertNotIn(
            T.BTN_TEAM_ADMIN,
            self._buttons(markup),
            "jamoa adminini faqat super admin yaratadi",
        )

    async def test_team_member_does_not_see_admin_button(self) -> None:
        """Oddiy jamoa a'zosiga jamoa yaratish tugmasi kerak emas."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.upsert_user(
            USER_1, name="A'zo", team_id=int(team["id"]), owner_admin_uid=ADMIN_A
        )
        markup = await KB.kb_main_for(USER_1)
        self.assertNotIn(T.BTN_TEAM_ADMIN, self._buttons(markup))
        self.assertNotIn(T.BTN_TEAM_PICK, self._buttons(markup))

    async def test_team_admin_does_not_see_team_pick(self) -> None:
        """Jamoa adminiga jamoani tanlash tugmasi kerak emas."""
        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
        await db.set_team_admin(
            ADMIN_A, int(team["id"]), max_users=5, admin_expires_at=calc_expires(365)
        )
        markup = await KB.kb_main_for(ADMIN_A)
        self.assertNotIn(T.BTN_TEAM_PICK, self._buttons(markup))
        self.assertNotIn(T.BTN_TEAM_ADMIN, self._buttons(markup))

    async def test_login_keyboard_has_no_admin_button(self) -> None:
        """Kirish ekranida jamoa admini bo'lish tugmasi yo'q."""
        buttons = [b.text for row in KB.kb_login().keyboard for b in row]
        self.assertNotIn(T.BTN_TEAM_ADMIN, buttons)
        self.assertIn(T.BTN_LOGIN, buttons)

    async def test_legacy_team_pick_text_still_works(self) -> None:
        """Eski klaviaturadagi «🎯 Jamoa tanlash» matni ham ishlaydi.

        Avval `BTN_TEAM_PICK` ikki marta belgilangan edi va ikkinchi
        qiymati ("🎯 Jamoa tanlash") yashirib qolgan edi. Eski klaviatura
        foydalanuvchilari uchun bu matn qabul qilinishi kerak.
        """
        from bot.menu import route_menu_button

        await db.upsert_user(USER_1, name="Oddiy")
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_1),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        handled = await route_menu_button(update, "🎯 Jamoa tanlash")
        self.assertTrue(handled, "eski tugma matni ham ishlashi kerak")

    async def test_admin_button_starts_team_creation(self) -> None:
        """«👑 Admin bo'lish» jamoa admini uchun jamoa yaratish oqimini boshlaydi.

        Tugma menyudan olib tashlangan (jamoa adminini faqat super admin
        yaratadi), lekin eski klaviaturadagi matn ham ishlashda davom etadi.
        """
        from bot.menu import route_menu_button

        await db.upsert_user(USER_1, name="Jamoa admini", is_team_admin=1)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=USER_1),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        handled = await route_menu_button(update, T.BTN_TEAM_ADMIN)
        self.assertTrue(handled, "tugma qayta ishlovchi bo'lishi kerak")

        from bot.login import user_states

        self.assertEqual(
            user_states.get(USER_1, {}).get("step"),
            "team_admin_size",
            "jamoa sig'imi so'ralishi kerak",
        )


class TeamHandoverTests(unittest.IsolatedAsyncioTestCase):
    """Jamoani boshqa adminga topshirish (super admin)."""

    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
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

    async def _setup(self) -> tuple[dict, int]:
        from admin import admin_panel

        team = await db.create_team("Jamoa", ADMIN_A, max_users=7)
        await db.set_team_admin(
            ADMIN_A,
            int(team["id"]),
            max_users=7,
            admin_expires_at=calc_expires(60),
        )
        await db.set_team_admin(
            ADMIN_B,
            0,
            max_users=5,
            admin_expires_at=calc_expires(30),
        )
        await db.upsert_user(
            USER_1,
            name="A'zo",
            team_id=int(team["id"]),
            owner_admin_uid=ADMIN_A,
        )
        await db.set_user_limits(ADMIN_A, tariff_expires_at=calc_expires(60))
        return team, admin_panel

    async def test_handover_moves_team_and_members(self) -> None:
        """Topshirishdan keyin jamoa va a'zolar yangi admin ostida."""
        team, admin_panel = await self._setup()
        q = SimpleNamespace(
            data=f"adm:teamhandoverset:{ADMIN_A}:{ADMIN_B}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(admin_panel, "application", None):
            await admin_panel.set_team_handover(update, ADMIN_A, ADMIN_B)

        # Jamoaning egasi yangi admin.
        teams = await db.get_teams(ADMIN_B)
        self.assertTrue(teams, "yangi admin jamoani olishi kerak")
        self.assertEqual(int(teams[0]["id"]), int(team["id"]))

        # A'zolar yangi admin ostida.
        member = await db.get_user(USER_1)
        self.assertEqual(int(member["owner_admin_uid"]), ADMIN_B)

        # Eski admin endi jamoa admini emas.
        old = await db.get_user(ADMIN_A)
        self.assertFalse(old["is_team_admin"])

        # Yangi admin jamoa admini bo'ldi.
        new = await db.get_user(ADMIN_B)
        self.assertTrue(new["is_team_admin"])
        self.assertEqual(int(new["team_id"]), int(team["id"]))

    async def test_handover_keeps_team_limit_and_expiry(self) -> None:
        """Sig'im va muddat yangi adminga o'tadi."""
        _, admin_panel = await self._setup()
        q = SimpleNamespace(
            data=f"adm:teamhandoverset:{ADMIN_A}:{ADMIN_B}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        with patch.object(admin_panel, "application", None):
            await admin_panel.set_team_handover(update, ADMIN_A, ADMIN_B)

        new = await db.get_user(ADMIN_B)
        self.assertEqual(int(new["admin_max_users"]), 7, "sig'im o'tishi kerak")
        self.assertIsNotNone(new["admin_expires_at"], "muddat o'tishi kerak")
        self.assertFalse(new["awaiting_approval"], "tasdiq kutilmasligi kerak")

    async def test_handover_rejects_non_team_admin(self) -> None:
        """Jamoa admini bo'lmagan user topshirilmaydi."""
        await self._setup()
        await db.upsert_user(USER_2, name="Oddiy")
        q = SimpleNamespace(
            data=f"adm:teamhandoverset:{ADMIN_A}:{USER_2}",
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            callback_query=q,
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )
        from admin import admin_panel

        with patch.object(admin_panel, "application", None):
            await admin_panel.set_team_handover(update, ADMIN_A, USER_2)

        new = await db.get_user(USER_2)
        self.assertFalse(new["is_team_admin"], "topshirilmasligi kerak")
        old = await db.get_user(ADMIN_A)
        self.assertTrue(old["is_team_admin"], "eski admin o'z o'rnida qolishi kerak")
