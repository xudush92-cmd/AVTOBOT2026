"""Super admin/user ajratilishi va sessiya himoyasi testlari."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiosqlite

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from admin import admin_actions  # noqa: E402
from bot.keyboards import kb_user_card  # noqa: E402
from config.config import SUPER_ADMIN  # noqa: E402
from core import database as db  # noqa: E402


class AdminDatabaseSeparationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.previous_db = db._db
        self.conn = await aiosqlite.connect(":memory:")
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(
            """
            CREATE TABLE users (
                uid INTEGER PRIMARY KEY,
                is_admin INTEGER DEFAULT 0,
                is_blocked INTEGER DEFAULT 0,
                awaiting_approval INTEGER DEFAULT 0,
                running INTEGER DEFAULT 0,
                created_at TEXT
            );
            CREATE TABLE groups (uid INTEGER NOT NULL);
            CREATE TABLE posts (uid INTEGER NOT NULL);
            """
        )
        await self.conn.executemany(
            "INSERT INTO users "
            "(uid, is_admin, is_blocked, awaiting_approval, running, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (SUPER_ADMIN, 1, 1, 1, 1, "2026-01-01"),
                (2001, 1, 1, 1, 1, "2026-01-02"),
            ],
        )
        await self.conn.executemany(
            "INSERT INTO groups (uid) VALUES (?)",
            [(SUPER_ADMIN,), (2001,)],
        )
        await self.conn.executemany(
            "INSERT INTO posts (uid) VALUES (?)",
            [(SUPER_ADMIN,), (2001,)],
        )
        await self.conn.commit()
        db._db = self.conn

    async def asyncTearDown(self) -> None:
        await self.conn.close()
        db._db = self.previous_db

    async def test_super_admin_is_not_returned_as_regular_user(self) -> None:
        users = await db.get_all_users()
        self.assertEqual([user["uid"] for user in users], [2001])

    async def test_stats_do_not_count_super_admin(self) -> None:
        stats = await db.get_stats()
        self.assertEqual(stats["total_users"], 1)
        self.assertEqual(stats["admins"], 1)
        self.assertEqual(stats["blocked"], 1)
        self.assertEqual(stats["waiting"], 1)
        self.assertEqual(stats["running"], 1)
        self.assertEqual(stats["total_groups"], 1)
        self.assertEqual(stats["total_posts"], 1)


class AdminSessionProtectionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _update():
        return SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )

    async def test_stale_super_admin_user_card_is_rejected(self) -> None:
        update = self._update()
        with patch.object(admin_actions.db, "get_user", new=AsyncMock()) as get_user:
            await admin_actions.handle_user_card(
                update,
                SUPER_ADMIN,
                f"uc:sess:{SUPER_ADMIN}",
            )

        get_user.assert_not_awaited()
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("Super admin", text)

    async def test_existing_session_does_not_request_another_code(self) -> None:
        update = self._update()
        user = {
            "uid": 2001,
            "name": "Test User",
            "phone": "+998901234567",
            "session": "existing-session",
        }
        with (
            patch.object(
                admin_actions.db,
                "get_user",
                new=AsyncMock(return_value=user),
            ),
            patch.object(
                admin_actions,
                "cleanup_login",
                new=AsyncMock(),
            ) as cleanup,
        ):
            await admin_actions.action_open_session(
                update,
                SUPER_ADMIN,
                2001,
            )

        cleanup.assert_not_awaited()
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("allaqachon mavjud", text)

    def test_session_keyboard_only_shows_valid_action(self) -> None:
        active = kb_user_card(2001, has_session=True)
        active_callbacks = {
            button.callback_data for row in active.inline_keyboard for button in row
        }
        self.assertNotIn("uc:sess:2001", active_callbacks)
        self.assertIn("uc:logoutask:2001", active_callbacks)
        self.assertNotIn("uc:logoutconfirm:2001", active_callbacks)

        inactive = kb_user_card(2001, has_session=False)
        inactive_callbacks = {
            button.callback_data for row in inactive.inline_keyboard for button in row
        }
        self.assertIn("uc:sess:2001", inactive_callbacks)
        self.assertNotIn("uc:logout:2001", inactive_callbacks)


if __name__ == "__main__":
    unittest.main()
