from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")
os.environ.setdefault(
    "SESSION_ENCRYPTION_KEY",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)

from core import database as db  # noqa: E402


class GroupIntervalDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "groups.db"
        await db.init_db()
        await db.upsert_user(42, is_admin=1, interval_min=60)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_per_group_override_and_general_interval_are_independent(self) -> None:
        self.assertTrue((await db.add_chat(42, "@general"))[0])
        self.assertTrue((await db.add_chat(42, "@custom"))[0])
        records = await db.get_chat_records(42)
        general_id, custom_id = (int(item["id"]) for item in records)

        self.assertTrue(await db.set_chat_interval(42, custom_id, 30))
        self.assertEqual(await db.get_interval(42), 60)
        records = {item["id"]: item for item in await db.get_chat_records(42)}
        self.assertIsNone(records[general_id]["interval_min"])
        self.assertEqual(records[custom_id]["interval_min"], 30)

        self.assertTrue(await db.set_interval(42, 45))
        self.assertEqual(await db.get_interval(42), 45)
        records = {item["id"]: item for item in await db.get_chat_records(42)}
        self.assertIsNone(records[general_id]["interval_min"])
        self.assertEqual(records[custom_id]["interval_min"], 30)

        self.assertTrue(await db.set_chat_interval(42, custom_id, None))
        records = {item["id"]: item for item in await db.get_chat_records(42)}
        self.assertIsNone(records[custom_id]["interval_min"])
        self.assertEqual(await db.get_interval(42), 45)

    async def test_schedule_is_persisted_and_recomputed_without_ignoring_flood_wait(self) -> None:
        self.assertTrue((await db.add_chat(42, "@scheduled"))[0])
        group_id = int((await db.get_chat_records(42))[0]["id"])
        self.assertTrue(
            await db.record_chat_attempt(
                42,
                group_id,
                attempted_at=1_000,
                jitter_s=0,
                flood_wait_until=1_500,
            )
        )

        self.assertTrue(await db.set_chat_interval(42, group_id, 60))
        group = await db.get_chat_record(42, group_id)
        self.assertEqual(group["interval_min"], 60)
        self.assertEqual(group["last_attempt_at"], 1_000)
        self.assertEqual(group["flood_wait_until"], 1_500)
        self.assertEqual(group["next_send_at"], 4_600)

        self.assertTrue(await db.set_interval(42, 30))
        group = await db.get_chat_record(42, group_id)
        self.assertEqual(group["next_send_at"], 4_600)

    async def test_general_interval_reschedules_only_groups_that_inherit_it(self) -> None:
        await db.add_chat(42, "@inherit")
        await db.add_chat(42, "@override")
        records = await db.get_chat_records(42)
        inherit_id, override_id = (int(item["id"]) for item in records)

        await db.set_chat_interval(42, override_id, 20)
        await db.record_chat_attempt(42, inherit_id, 1_000, jitter_s=0)
        await db.record_chat_attempt(42, override_id, 1_000, jitter_s=0)

        await db.set_interval(42, 30)
        inherit = await db.get_chat_record(42, inherit_id)
        override = await db.get_chat_record(42, override_id)
        self.assertEqual(inherit["next_send_at"], 2_800)
        self.assertEqual(override["interval_min"], 20)
        self.assertEqual(override["next_send_at"], 2_200)


class GroupIntervalMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        self.legacy_path = Path(self.temp.name) / "legacy.db"
        db.DB_PATH = self.legacy_path

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_path
        self.temp.cleanup()

    async def test_existing_groups_get_inherited_schedule_columns(self) -> None:
        conn = sqlite3.connect(self.legacy_path)
        conn.executescript(
            """
            CREATE TABLE users (
                uid INTEGER PRIMARY KEY,
                name TEXT DEFAULT '',
                username TEXT DEFAULT '',
                phone TEXT DEFAULT '',
                session TEXT DEFAULT '',
                pending_session TEXT DEFAULT '',
                is_admin INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                awaiting_approval INTEGER DEFAULT 0,
                tariff_expires_at TEXT,
                warned_at TEXT,
                interval_min INTEGER DEFAULT 60,
                running INTEGER DEFAULT 0,
                referrer_uid INTEGER,
                referral_counted INTEGER DEFAULT 0,
                created_at TEXT,
                updated_at TEXT
            );
            CREATE TABLE groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid INTEGER NOT NULL,
                value TEXT NOT NULL,
                created_at TEXT,
                UNIQUE(uid, value),
                FOREIGN KEY (uid) REFERENCES users(uid) ON DELETE CASCADE
            );
            INSERT INTO users (uid, name, is_admin, interval_min)
            VALUES (77, 'Legacy user', 1, 37);
            INSERT INTO groups (uid, value, created_at)
            VALUES (77, '@legacy_group', '2026-01-01 00:00:00');
            """
        )
        conn.commit()
        conn.close()

        await db.init_db()
        group = (await db.get_chat_records(77))[0]
        self.assertEqual(group["value"], "@legacy_group")
        self.assertIsNone(group["interval_min"])
        self.assertIsNone(group["next_send_at"])
        self.assertEqual(await db.get_interval(77), 37)


if __name__ == "__main__":
    unittest.main()
