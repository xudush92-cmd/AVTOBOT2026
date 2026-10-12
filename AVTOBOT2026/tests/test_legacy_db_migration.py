"""Eski (albom/limit/send_logs bo'lmagan) bazada migratsiya va ma'lumot saqlanishi.

Bu test production dagi `.db` fayli bilan bo'lishi mumkin bo'lgan eng
og'riqli holatni qayta yaratadi: ustunlar soni kam, `send_logs` jadvali yo'q, postlarda
faqat `photo` bor. Tekshiriladi:

- ``init_db()`` xatosiz yangi ustun va jadvallarni qo'shadi;
- mavjud foydalanuvchi, guruh, post va referal yozuvlari o'zgarmaydi;
- yangi limitlar ``0`` = cheksiz bo'ladi — eski userlar hech qanday
  cheklovga uchramaydi;
- media ro'yxati eski ``photo`` ustunidan avtomatik tiklanadi;
- hisobot/status ekranlari va ``send_logs`` asosidagi so'rovlar bunday
  bazada ham xatosiz ishlaydi.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from cryptography.fernet import Fernet  # noqa: E402

from core import database as db  # noqa: E402
from core import session_crypto  # noqa: E402

# cf8eda0 dagi sxema (aynan shu ko'rinishda production bazasi mavjud).
LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    uid INTEGER PRIMARY KEY, name TEXT DEFAULT '', username TEXT DEFAULT '',
    phone TEXT DEFAULT '', session TEXT DEFAULT '', pending_session TEXT DEFAULT '',
    is_admin INTEGER DEFAULT 0, is_blocked INTEGER DEFAULT 0,
    awaiting_approval INTEGER DEFAULT 0, tariff_expires_at TEXT, warned_at TEXT,
    interval_min INTEGER DEFAULT 60, running INTEGER DEFAULT 0,
    referrer_uid INTEGER, referral_counted INTEGER DEFAULT 0,
    created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
    value TEXT NOT NULL, created_at TEXT, UNIQUE(uid, value));
CREATE INDEX IF NOT EXISTS idx_groups_uid ON groups(uid);
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL,
    text TEXT DEFAULT '', entities TEXT DEFAULT '[]', photo TEXT DEFAULT '',
    created_at TEXT);
CREATE INDEX IF NOT EXISTS idx_posts_uid ON posts(uid);
CREATE TABLE IF NOT EXISTS referrals (
    id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_uid INTEGER NOT NULL,
    referred_uid INTEGER NOT NULL, counted INTEGER DEFAULT 0, created_at TEXT,
    UNIQUE(referred_uid));
"""


class LegacyMigrationTestCase(unittest.IsolatedAsyncioTestCase):
    UID = 2001

    async def asyncSetUp(self) -> None:
        import aiosqlite

        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "prod.db"

        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.executescript(LEGACY_SCHEMA)
            await conn.execute(
                "INSERT INTO users (uid, name, phone, session, is_admin, interval_min, "
                "tariff_expires_at, referrer_uid, referral_counted, created_at, updated_at) "
                "VALUES (?, 'Ali Valiyev', '+998901112233', '', 1, 45, "
                "'2099-01-01 00:00:00', 1001, 1, '2026-01-01 00:00:00', "
                "'2026-01-01 00:00:00')",
                (self.UID,),
            )
            await conn.execute(
                "INSERT INTO users (uid, name, is_admin, created_at, updated_at) "
                "VALUES (1001, 'Referrer', 1, '2026-01-01 00:00:00', "
                "'2026-01-01 00:00:00')"
            )
            await conn.execute(
                "INSERT INTO groups (uid, value, created_at) "
                "VALUES (?, '@elonlar', '2026-01-01 00:00:00')", (self.UID,)
            )
            await conn.execute(
                "INSERT INTO groups (uid, value, created_at) "
                "VALUES (?, '-1001234567890', '2026-01-01 00:00:00')", (self.UID,)
            )
            await conn.execute(
                "INSERT INTO posts (uid, text, entities, photo, created_at) "
                "VALUES (?, 'Eski post', "
                "'[{\"type\":\"bold\",\"offset\":0,\"length\":4}]', "
                "'/data/media/old.jpg', '2026-01-01 00:00:00')",
                (self.UID,),
            )
            await conn.execute(
                "INSERT INTO referrals (referrer_uid, referred_uid, counted, created_at) "
                "VALUES (1001, ?, 1, '2026-01-01 00:00:00')", (self.UID,)
            )
            await conn.commit()

        session_crypto._fernet = Fernet(Fernet.generate_key())

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_init_db_migrates_without_losing_data(self) -> None:
        await db.init_db()

        user = await db.get_user(self.UID)
        self.assertEqual(user["name"], "Ali Valiyev")
        self.assertEqual(int(user["interval_min"]), 45)
        # Yangi ustunlar bor, lekin bo'sh = cheksiz (eski xatti-harakat).
        self.assertEqual(user["plan"], "")
        self.assertEqual(int(user["max_groups"] or 0), 0)
        self.assertEqual(int(user["daily_limit"] or 0), 0)

        self.assertEqual(
            await db.get_chats(self.UID), ["@elonlar", "-1001234567890"]
        )
        posts = await db.get_posts(self.UID)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["text"], "Eski post")
        self.assertEqual(posts[0]["photo"], "/data/media/old.jpg")
        # media ro'yxati eski photo ustunidan tiklanadi (worker shu bilan ishlaydi).
        self.assertEqual(
            posts[0]["media"], [{"path": "/data/media/old.jpg", "kind": "photo"}]
        )
        self.assertTrue(posts[0]["link_preview"])
        self.assertEqual(
            posts[0]["entities"], [{"type": "bold", "offset": 0, "length": 4}]
        )

        limits = await db.get_limits(self.UID)
        self.assertEqual(limits["label"], "📦 Limitlarsiz")
        self.assertEqual(limits["used_groups"], 2)
        self.assertEqual(limits["used_posts"], 1)
        self.assertFalse(await db.is_tariff_expired(self.UID))

        refs = await db.get_referrals(1001)
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0]["counted"])
        self.assertFalse(refs[0]["revoked"])

    async def test_old_users_are_not_limited(self) -> None:
        await db.init_db()
        for index in range(8):
            ok, reason = await db.add_chat(self.UID, f"@guru{index}")
            self.assertTrue(ok, reason)
        self.assertEqual(await db.max_groups_for(self.UID), 0)
        ok, _reason, post_id = await db.add_post(self.UID, "yangi", [], None)
        self.assertTrue(ok)
        self.assertIsNotNone(post_id)

    async def test_send_logs_created_and_usable(self) -> None:
        await db.init_db()
        records = await db.get_chat_records(self.UID)
        gid = int(records[0]["id"])
        await db.log_send(self.UID, True, group_id=gid, post_id=1)
        await db.log_send(self.UID, False, group_id=gid, error="Forbidden")

        stats = await db.send_stats(self.UID)
        self.assertEqual(stats["sent_ok"], 1)
        self.assertEqual(stats["sent_failed"], 1)
        self.assertIn("Forbidden", str(stats["last_error"]))

        health = await db.group_health(self.UID)
        self.assertEqual(len(health), len(records))
        self.assertEqual(int(health[0]["last_ok"]), 0)

        # Yangi yozuvlar saqlanadi, juda eskisi tozalanadi.
        await db.log_send(self.UID, True, group_id=gid, sent_at=time.time() - 400 * 86400)
        self.assertEqual(await db.prune_send_logs(retention_days=30), 1)
        self.assertEqual((await db.send_stats(self.UID))["sent_ok"], 1)
        # Urinishdan keyingi navbat ham eski bazada ishlaydi.
        self.assertGreater(
            await db.record_chat_attempt(self.UID, gid, time.time(), 0), 0
        )

    async def test_worker_and_screens_work_on_migrated_db(self) -> None:
        from bot import menu
        from worker import worker as W

        await db.init_db()
        allowed, wait_s, reason = await W.posting_window_state(
            self.UID, await db.get_user(self.UID)
        )
        self.assertTrue(allowed)
        self.assertEqual((wait_s, reason), (0, ""))

        async def render(fn):
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=self.UID),
                message=SimpleNamespace(reply_text=AsyncMock()),
            )
            await fn(update)
            return update.message.reply_text.await_args.args[0]

        self.assertIn("STATUS", (await render(menu.show_status)).upper())
        self.assertIn("HISOBOT", (await render(menu.show_report)).upper())
        self.assertIn("PAKET", (await render(menu.show_plan)).upper())

    async def test_stats_panel_survives_missing_history(self) -> None:
        await db.init_db()
        stats = await db.get_stats()
        self.assertEqual(stats["total_users"], 2)
        self.assertEqual(stats["today_sends_ok"], 0)
        self.assertEqual(stats["today_referrals"], 0)


if __name__ == "__main__":
    unittest.main()
