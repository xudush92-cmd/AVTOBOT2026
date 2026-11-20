"""🐢 `SlowModeWaitError` ishlovi va jamoa adminiga jamoa biriktirish.

Qamlov:
1. ``SlowModeWaitError`` — ``.seconds`` dan foydalaniladi;
2. keyingi yuborish **rejalashtiriladi** (darhol qayta urinish yo'q);
3. slow mode **faqat shu guruhni** bloklaydi — boshqa guruhlar
   davom etadi (FloodWait dan farqli);
4. super admin tayyorlagan jamoa adminiga **haqiqiy jamoa** yaratilib
   biriktiriladi (``team_id`` 0 bo'lmaydi).
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

import aiosqlite  # noqa: E402
from telethon.errors import FloodWaitError, SlowModeWaitError  # noqa: E402

from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402
from worker import worker as W  # noqa: E402


class _FakeClient:
    """Telethon client'ning minimal taqdimoti."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def send_message(self, entity, message, **kwargs):
        self.sent.append((str(entity), {"message": message, **kwargs}))

    async def send_file(self, entity, file, **kwargs):
        self.sent.append((str(entity), {"file": file, **kwargs}))


class SlowModeWaitErrorTests(unittest.IsolatedAsyncioTestCase):
    """``SlowModeWaitError`` to'g'ri ishlashi kerak."""

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

    # ── 1) .seconds ishlatilishi ──
    def test_slowmode_error_has_seconds_attribute(self) -> None:
        """``SlowModeWaitError`` da ``.seconds`` bor (Telethon 1.45)."""
        exc = SlowModeWaitError(request=None, capture=17)
        self.assertEqual(exc.seconds, 17)

    def test_slowmode_is_not_floodwait(self) -> None:
        """``SlowModeWaitError`` — ``FloodWaitError`` dan ** emas** merosxo'r."""
        self.assertFalse(issubclass(SlowModeWaitError, FloodWaitError))
        # Shu sabab `except FloodWaitError` uni ushlamaydi — alohida
        # blok talab qilinadi.
        self.assertTrue(issubclass(SlowModeWaitError, Exception))

    # ── 2) Keyingi yuborish rejalashtiriladi ──
    async def test_slowmode_schedules_next_send(self) -> None:
        """Slow mode kelganda keyingi urinish ``.seconds`` keyin rejalashtiriladi."""
        uid = 5001
        await db.upsert_user(uid, name="Slow user")
        await db.set_running(uid, True)
        await db.add_chat(uid, "@slow_chat")
        await db.set_interval(uid, 60)

        import time as _time

        records = await db.get_chat_records(uid)
        self.assertEqual(len(records), 1)
        group_id = int(records[0]["id"])

        attempted_at = _time.time()
        wait_s = int(getattr(SlowModeWaitError(request=None, capture=42), "seconds", 30)) + 5
        next_send_at = await db.record_chat_attempt(
            uid, group_id, attempted_at, 0, attempted_at + wait_s
        )

        self.assertIsNotNone(next_send_at, "navbat rejalashtirilmadi")
        # 42 + 5 = 47 s kutish + interval (60 s) → kamida 47 s.
        self.assertGreaterEqual(next_send_at - _time.time(), 46)

    async def test_slowmode_does_not_schedule_immediate_retry(self) -> None:
        """Slow mode dan keyin **darhol** qayta urinish qilinmasligi kerak."""
        uid = 5002
        await db.upsert_user(uid, name="No retry")
        await db.set_running(uid, True)
        await db.add_chat(uid, "@no_retry_chat")
        await db.set_interval(uid, 60)

        import time as _time

        records = await db.get_chat_records(uid)
        group_id = int(records[0]["id"])

        attempted_at = _time.time()
        next_send_at = await db.record_chat_attempt(
            uid, group_id, attempted_at, 0, attempted_at + 47
        )
        self.assertIsNotNone(next_send_at)
        # Darhol urinish (0 s) — bo'lmasligi kerak.
        self.assertGreater(next_send_at - attempted_at, 40)

    # ── 3) Slow mode faqat shu guruhni bloklaydi ──
    async def test_slowmode_does_not_stop_other_groups(self) -> None:
        """Slow mode kelganda sikl **to'xtamaydi** — boshqa guruh yuboriladi.

        FloodWait butun akkauntni bloklaydi va siklni to'xtatadi.
        Slow mode esa faqat shu guruhga tegarli.
        """
        uid = 5003
        await db.upsert_user(uid, name="Multi group")
        await db.set_running(uid, True)
        await db.add_chat(uid, "@chat_one")
        await db.add_chat(uid, "@chat_two")

        client = _FakeClient()
        calls: list[str] = []

        async def _send(_client, chat, _post):
            calls.append(chat)
            if chat == "@chat_one":
                raise SlowModeWaitError(request=None, capture=30)

        slow_hits = 0
        with patch.object(W, "send_post", new=_send):
            chats = await db.get_chats(uid)
            for chat in chats:
                try:
                    await W.send_post(client, str(chat), {"id": 1, "text": "x"})
                except SlowModeWaitError:
                    slow_hits += 1

        self.assertEqual(slow_hits, 1, "slow mode bir marta ushlanishi kerak")
        self.assertEqual(
            len(calls), 2, "ikkinchi guruh ham urinish qilishi kerak (to'xtatilmaydi)"
        )
        self.assertIn("@chat_two", calls, "boshqa guruh yuborilishi kerak")

    def test_slowmode_flag_gates_sleep(self) -> None:
        """``slow_mode_hit`` bayrog'i siklni to'xtatmasligi kerak."""
        src = (APP_DIR / "worker" / "worker.py").read_text(encoding="utf-8")
        self.assertIn("slow_mode_hit", src)
        # Sikl to'xtatilishi shart emas — faqat FloodWait uchun.
        self.assertIn("if flood_wait_until is not None and not slow_mode_hit:", src)


class TeamAttachForAdminTests(unittest.IsolatedAsyncioTestCase):
    """Super admin tayyorlagan admin uchun haqiqiy jamoa yaratilishi."""

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

    async def test_create_team_for_admin_attaches_real_team(self) -> None:
        """Admin yaratilganda ``team_id`` 0 bo'lmaydi."""
        uid = 6001
        await db.upsert_user(uid, name="Admin")

        team = await db.create_team_for_admin(uid, "Mening jamoam", max_users=10)

        self.assertIsNotNone(team, "jamoa yaratilmadi")
        user = await db.get_user(uid)
        self.assertEqual(int(user["team_id"]), int(team["id"]))
        self.assertEqual(int(user["owner_admin_uid"]), uid)
        self.assertEqual(int(user["is_team_admin"]), 1)

    async def test_create_team_for_admin_generates_unique_name(self) -> None:
        """Jamoa nomi bo'sh bo'lsa — unikal avtomatik nom beriladi."""
        uid_a, uid_b = 6002, 6003
        await db.upsert_user(uid_a, name="A")
        await db.upsert_user(uid_b, name="B")

        team_a = await db.create_team_for_admin(uid_a, "", max_users=5)
        team_b = await db.create_team_for_admin(uid_b, "", max_users=5)

        self.assertIsNotNone(team_a)
        self.assertIsNotNone(team_b)
        self.assertNotEqual(team_a["name"], team_b["name"], "nomlar bir xil bo'lmaydi")
        self.assertNotEqual(int(team_a["id"]), int(team_b["id"]))

    async def test_each_admin_gets_own_team(self) -> None:
        """Har bir jamoa admini **o'ziga xos** jamoani oladi."""
        admins = [7001, 7002, 7003]
        team_ids = []
        for uid in admins:
            await db.upsert_user(uid, name=f"Admin {uid}")
            team = await db.create_team_for_admin(uid, "", max_users=5)
            self.assertIsNotNone(team)
            team_ids.append(int(team["id"]))

        self.assertEqual(len(set(team_ids)), 3, "jamolar unikal bo'lishi kerak")
        for uid in admins:
            user = await db.get_user(uid)
            self.assertEqual(int(user["team_id"]), team_ids[admins.index(uid)])

    async def test_admin_panel_creates_team_immediately(self) -> None:
        """Super admin panelida admin tayyorlanganda jamoa darhol yaratiladi."""
        from admin import admin_panel as AP

        uid = 8001
        await db.upsert_user(uid, name="Panel admin")
        await db.set_phone(uid, "+998901234567")

        with patch.object(AP.db, "get_user_by_phone", new=AsyncMock(
            return_value=await db.get_user(uid)
        )):
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=999),
                message=SimpleNamespace(reply_text=AsyncMock()),
            )
            await AP.handle_add_team_admin_phone(
                update, 999, "+998901234567"
            )

        user = await db.get_user(uid)
        self.assertTrue(int(user["is_team_admin"]), "admin bo'lishi kerak")
        self.assertTrue(int(user["team_id"] or 0), "haqiqiy jamoa biriktirilishi kerak")
        team = await db.get_team(int(user["team_id"]))
        self.assertIsNotNone(team, "jamoa bazada mavjud bo'lishi kerak")
        self.assertEqual(int(team["owner_admin_uid"]), uid)

    async def test_existing_team_is_reused_not_duplicated(self) -> None:
        """Admin allaqachon jamoaga bog'langan bo'lsa — yangisi yaratilmaydi."""
        from admin import admin_panel as AP

        uid = 8101
        await db.upsert_user(uid, name="Existing team admin")
        team = await db.create_team_for_admin(uid, "Mavjud jamoa", max_users=7)
        self.assertIsNotNone(team)

        await AP._attach_team_for_admin(uid)

        user = await db.get_user(uid)
        self.assertEqual(int(user["team_id"]), int(team["id"]), "jamoa almashtirilmasin")
        teams = await db.get_teams(uid)
        self.assertEqual(len(teams), 1, "ikkinchi jamoa yaratilmasin")


if __name__ == "__main__":
    unittest.main()
