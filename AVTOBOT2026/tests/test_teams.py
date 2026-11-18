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
from bot import teams as Tm  # noqa: E402
from bot import texts as T  # noqa: E402
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
        """Admin bo'lish oqimi: raqam → nom → jamoa yaratiladi."""
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=ADMIN_A, username="admina"),
            message=SimpleNamespace(reply_text=AsyncMock()),
        )

        await Tm.begin_team_admin_register(update, ADMIN_A)
        state = Tm.user_states.get(ADMIN_A) if hasattr(Tm, "user_states") else None
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

    async def test_admin_registration_rejects_small_size(self) -> None:
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
        """Jamoa to'ldiq bo'lsa — referal biriktirilmaydi."""
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

        self.assertTrue(await RF.register_referral(USER_1, f"ref_{ADMIN_A}"))
        user = await db.get_user(USER_1)
        self.assertIsNone(user.get("team_id"), "to'lgan jamoaga biriktirilmasligi kerak")


class TeamChoiceTests(unittest.IsolatedAsyncioTestCase):
    """Foydalanuvchi jamoa bilan yoki jamoasiz ishlashni tanlaydi."""

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

    async def test_skip_button_exists_in_picker(self) -> None:
        """Jamoa tanlash oynasida jamoasiz davom etish tugmasi bor."""
        await db.create_team("Jamoa One", ADMIN_A, max_users=5)
        teams = await db.get_all_teams()
        kb = KB.kb_team_pick(teams)
        callbacks = {
            b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
        }
        self.assertIn("team:skip", callbacks)

    async def test_pick_title_explains_both_choices(self) -> None:
        """Matnda ikkala variant ham tushuntiriladi."""
        self.assertIn("guruh bilan ishlash", T.TEAM_PICK_TITLE.lower())
        self.assertIn("jamoasiz", T.TEAM_PICK_TITLE.lower())

    async def test_skip_does_not_assign_team(self) -> None:
        """Jamoasiz davom etilganda user jamoasiz qoladi."""
        await db.create_team("Jamoa One", ADMIN_A, max_users=5)
        teams = await db.get_all_teams()
        q = SimpleNamespace(
            data="team:skip",
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
            await Tm.handle_team_pick_callback(update, USER_1, "team:skip")

        user = await db.get_user(USER_1)
        self.assertIsNone(
            user.get("team_id") if user else None,
            "jamoasiz davom etilganda jamoa biriktirilmasligi kerak",
        )

    async def test_pick_assigns_team(self) -> None:
        """Jamoa tanlanganda user jamoaga biriktiriladi."""
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
        self.assertEqual(int(user["team_id"]), int(team["id"]))
        self.assertEqual(int(user["owner_admin_uid"]), ADMIN_A)


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
        from core.utils import calc_expires

        self.assertEqual(member["tariff_expires_at"], calc_expires(7))

    async def test_notify_goes_to_team_admin(self) -> None:
        """Ariza xabari jamoa adminiga boradi, super admin ga emas."""
        from bot import login as Login

        team = await db.create_team("Jamoa", ADMIN_A, max_users=5)
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
        from core.utils import calc_expires

        self.assertTrue(user["is_admin"])
        self.assertEqual(user["tariff_expires_at"], calc_expires(7))

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
        from core.utils import calc_expires

        self.assertEqual(
            user["tariff_expires_at"], calc_expires(DEFAULT_DURATION_DAYS)
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
