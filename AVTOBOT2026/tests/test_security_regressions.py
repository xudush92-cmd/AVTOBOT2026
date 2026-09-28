from __future__ import annotations

import asyncio
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from cryptography.fernet import Fernet

from bot import action_tokens
from bot import callbacks
from bot import texts as T
from core import database as db
from core import session_crypto
from core.utils import is_valid_full_name, is_valid_interval
from worker.client_pool import ClientPool, SessionInvalidError
from worker.worker import WorkerManager


class SessionCryptoTests(unittest.TestCase):
    def tearDown(self) -> None:
        session_crypto._fernet = None

    def test_generated_key_file_is_private_and_reusable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory)
            key_file = data_dir / ".session.key"
            with (
                patch.object(session_crypto, "SESSION_ENCRYPTION_KEY", ""),
                patch.object(session_crypto, "DATA_DIR", data_dir),
                patch.object(session_crypto, "_KEY_FILE", key_file),
            ):
                session_crypto._fernet = None
                session_crypto.ensure_session_cipher()
                encrypted = session_crypto.encrypt_session("secret-session")
                self.assertEqual(
                    session_crypto.decrypt_session(encrypted),
                    "secret-session",
                )
                self.assertEqual(stat.S_IMODE(key_file.stat().st_mode), 0o600)

    def test_invalid_configured_key_fails_at_startup(self) -> None:
        with patch.object(session_crypto, "SESSION_ENCRYPTION_KEY", "invalid-key"):
            session_crypto._fernet = None
            with self.assertRaises(ValueError):
                session_crypto.ensure_session_cipher()


class DatabaseSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        await db.close_db()
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "test.db"
        self.old_path = db.DB_PATH
        db.DB_PATH = self.db_path
        session_crypto._fernet = Fernet(Fernet.generate_key())
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_path
        session_crypto._fernet = None
        self.temp.cleanup()

    async def test_sessions_are_encrypted_and_export_is_sanitized(self) -> None:
        uid = 101
        secret = "1A-test-string-session-secret"
        pending = "1A-pending-secret"
        await db.upsert_user(uid, name="Ali Valiyev")
        await db.set_session(uid, secret)
        await db.set_pending(uid, pending)

        async with db._conn().execute(
            "SELECT session, pending_session FROM users WHERE uid = ?", (uid,)
        ) as cursor:
            raw = await cursor.fetchone()
        self.assertTrue(raw["session"].startswith("enc:v1:"))
        self.assertTrue(raw["pending_session"].startswith("enc:v1:"))
        self.assertNotIn(secret, raw["session"])
        self.assertEqual(await db.get_session(uid), secret)
        self.assertEqual(await db.get_pending(uid), pending)

        restore = Path(self.temp.name) / "restored.db"
        await db.backup_to(restore)
        with sqlite3.connect(restore) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            restored = conn.execute(
                "SELECT name, session, pending_session FROM users WHERE uid = ?",
                (uid,),
            ).fetchone()
        self.assertEqual(restored[0], "Ali Valiyev")
        self.assertEqual(restored[1], raw["session"])
        self.assertEqual(restored[2], raw["pending_session"])

        export = Path(self.temp.name) / "sanitized.db"
        await db.backup_to(export, sanitize_sessions=True)
        with sqlite3.connect(export) as conn:
            exported = conn.execute(
                "SELECT session, pending_session FROM users WHERE uid = ?", (uid,)
            ).fetchone()
        self.assertEqual(exported, ("", ""))
        export_bytes = export.read_bytes()
        self.assertNotIn(secret.encode(), export_bytes)
        self.assertNotIn(pending.encode(), export_bytes)
        self.assertNotIn(raw["session"].encode(), export_bytes)
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse(Path(f"{export}{suffix}").exists())

    async def test_plaintext_and_duplicate_phone_migration(self) -> None:
        await db.upsert_user(11, name="Primary User")
        await db.upsert_user(12, name="Duplicate User")
        await db.close_db()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DROP INDEX idx_users_phone_unique")
            conn.execute(
                "UPDATE users SET phone = ?, session = ? WHERE uid = 11",
                ("+998901111111", "legacy-session"),
            )
            conn.execute(
                "UPDATE users SET phone = ?, pending_session = ? WHERE uid = 12",
                ("+998901111111", "legacy-pending"),
            )
            conn.commit()

        await db.init_db()
        self.assertEqual(await db.get_session(11), "legacy-session")
        self.assertEqual(await db.get_pending(12), "legacy-pending")
        users = [await db.get_user(11), await db.get_user(12)]
        self.assertEqual(sum(user["phone"] == "+998901111111" for user in users), 1)
        with sqlite3.connect(self.db_path) as conn:
            raw = conn.execute(
                "SELECT session, pending_session FROM users ORDER BY uid"
            ).fetchall()
        self.assertTrue(raw[0][0].startswith("enc:v1:"))
        self.assertTrue(raw[1][1].startswith("enc:v1:"))
        storage = self.db_path.read_bytes()
        wal = Path(f"{self.db_path}-wal")
        if wal.exists():
            storage += wal.read_bytes()
        self.assertNotIn(b"legacy-session", storage)
        self.assertNotIn(b"legacy-pending", storage)

    async def test_phone_is_unique_and_stable_ids_are_uid_scoped(self) -> None:
        await db.upsert_user(1, name="Ali Valiyev")
        await db.upsert_user(2, name="Vali Aliyev")
        self.assertTrue(await db.set_phone(1, "+998901234567"))
        self.assertFalse(await db.set_phone(2, "+998901234567"))

        self.assertEqual(await db.add_chat(1, "@first"), (True, "ok"))
        self.assertEqual(await db.add_chat(2, "@second"), (True, "ok"))
        first_id = (await db.get_chat_records(1))[0]["id"]
        self.assertIsNone(await db.remove_chat_by_id(2, first_id))
        self.assertEqual(await db.get_chats(1), ["@first"])
        self.assertEqual(await db.remove_chat_by_id(1, first_id), "@first")

        ok, _, post_id = await db.add_post(1, "post", [], None)
        self.assertTrue(ok)
        self.assertIsNone(await db.remove_post_by_id(2, int(post_id)))
        self.assertIsNotNone(await db.remove_post_by_id(1, int(post_id)))

    async def test_referral_is_validated_and_counted_once_atomically(self) -> None:
        await db.upsert_user(20, name="Referrer One", is_admin=1)
        await db.upsert_user(21, name="Referrer Two", is_admin=1)
        self.assertFalse(await db.set_referrer(30, 9999))
        self.assertIsNone(await db.get_user(30))
        await db.upsert_user(31, is_admin=1)
        self.assertFalse(await db.set_referrer(31, 20))

        results = await asyncio.gather(
            db.set_referrer(30, 20),
            db.set_referrer(30, 21),
        )
        self.assertEqual(sum(results), 1)
        referred = await db.get_user(30)
        winner = int(referred["referrer_uid"])
        await db.approve_user(30, "2030-01-01 00:00:00")
        self.assertEqual(await db.try_count_referral(30), winner)
        self.assertIsNone(await db.try_count_referral(30))
        self.assertEqual(await db.count_referrals(winner), 1)

        await db.upsert_user(40, is_admin=1, referrer_uid=winner)
        self.assertIsNone(await db.try_count_referral(40))
        self.assertFalse((await db.get_user(40))["referral_counted"])

    async def test_approval_sets_default_only_when_tariff_is_missing(self) -> None:
        await db.upsert_user(5, awaiting_approval=1)
        self.assertTrue(await db.approve_user(5, "2030-01-01 00:00:00"))
        user = await db.get_user(5)
        self.assertTrue(user["is_admin"])
        self.assertFalse(user["awaiting_approval"])
        self.assertEqual(user["tariff_expires_at"], "2030-01-01 00:00:00")

        await db.mark_warned(5)
        warned_at = (await db.get_user(5))["warned_at"]
        await db.upsert_user(5, awaiting_approval=1)
        await db.approve_user(5, "2040-01-01 00:00:00")
        existing = await db.get_user(5)
        self.assertEqual(existing["tariff_expires_at"], "2030-01-01 00:00:00")
        self.assertEqual(existing["warned_at"], warned_at)


class UiSafetyTests(unittest.TestCase):
    def test_full_name_interval_and_masked_code(self) -> None:
        self.assertTrue(is_valid_full_name("O'ktam Aliyev"))
        self.assertFalse(is_valid_full_name("O'ktam"))
        self.assertFalse(is_valid_full_name("Aliyev 123"))
        self.assertTrue(is_valid_interval(5))
        self.assertTrue(is_valid_interval(10080))
        self.assertFalse(is_valid_interval(10081))

        rendered = T.numpad_text("12345", code_length=5)
        self.assertIn("● ● ● ● ●", rendered)
        self.assertNotIn("1 2 3 4 5", rendered)
        self.assertNotIn("12345", rendered)

    def test_confirmation_token_is_one_time_and_replaced(self) -> None:
        first = action_tokens.issue(44, "delete")
        second = action_tokens.issue(44, "delete")
        self.assertFalse(action_tokens.consume(44, "delete", first))
        self.assertTrue(action_tokens.consume(44, "delete", second))
        self.assertFalse(action_tokens.consume(44, "delete", second))


class CallbackAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.bot = SimpleNamespace(send_message=AsyncMock())
        callbacks.application = SimpleNamespace(bot=self.bot)

    async def asyncTearDown(self) -> None:
        callbacks.application = None

    @staticmethod
    def update(uid: int, data: str, chat_type: str = "private"):
        query = SimpleNamespace(
            from_user=SimpleNamespace(id=uid),
            data=data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=SimpleNamespace(message_id=10, chat_id=uid),
        )
        return SimpleNamespace(
            callback_query=query,
            effective_chat=SimpleNamespace(type=chat_type),
        )

    async def test_sensitive_callback_is_ignored_outside_private_chat(self) -> None:
        update = self.update(50, "go:yes:token", chat_type="group")
        with patch.object(callbacks.db, "is_blocked", new=AsyncMock()) as blocked:
            await callbacks.handle_callback(update, SimpleNamespace())
        update.callback_query.answer.assert_awaited_once()
        blocked.assert_not_awaited()
        update.callback_query.edit_message_text.assert_not_awaited()

    async def test_deleted_or_sessionless_user_cannot_replay_callback(self) -> None:
        update = self.update(51, "delp:id:7:0")
        with (
            patch.object(callbacks.db, "is_blocked", new=AsyncMock(return_value=False)),
            patch.object(callbacks.db, "get_user", new=AsyncMock(return_value=None)),
        ):
            await callbacks.handle_callback(update, SimpleNamespace())
        text = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("faol emas", text)
        self.bot.send_message.assert_awaited_once()

    async def test_blocked_user_cannot_replay_callback(self) -> None:
        update = self.update(52, "self:close")
        with patch.object(
            callbacks.db,
            "is_blocked",
            new=AsyncMock(return_value=True),
        ):
            await callbacks.handle_callback(update, SimpleNamespace())
        self.assertEqual(
            update.callback_query.edit_message_text.await_args.args[0], T.BLOCKED
        )
        self.bot.send_message.assert_awaited_once()


class FakeTelegramClient:
    instances: list["FakeTelegramClient"] = []

    def __init__(self, *_args, **_kwargs):
        self.connected = False
        self.disconnected = False
        self.__class__.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        self.disconnected = True

    async def is_user_authorized(self) -> bool:
        return True

    def is_connected(self) -> bool:
        return self.connected


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_pool_reference_count_and_idle_eviction(self) -> None:
        FakeTelegramClient.instances.clear()
        with (
            patch("worker.client_pool.TelegramClient", FakeTelegramClient),
            patch("worker.client_pool.StringSession", side_effect=lambda value: value),
        ):
            pool = ClientPool(1, "hash", max_clients=1)
            await pool.start()
            first = await pool.acquire(1, "session-one")
            same = await pool.acquire(1, "session-one")
            self.assertIs(first, same)
            self.assertEqual(pool.stats()["references"], 2)
            await pool.release(1)
            await pool.release(1)
            second = await pool.acquire(2, "session-two")
            self.assertIsNot(first, second)
            self.assertTrue(FakeTelegramClient.instances[0].disconnected)
            await pool.release(2)
            await pool.stop()

    async def test_malformed_session_does_not_leak_pool_capacity(self) -> None:
        with patch(
            "worker.client_pool.StringSession",
            side_effect=ValueError("invalid session"),
        ):
            pool = ClientPool(1, "hash", max_clients=1)
            await pool.start()
            with self.assertRaises(SessionInvalidError):
                await pool.acquire(1, "malformed")
            self.assertEqual(pool._reservations, set())
            self.assertEqual(pool.stats()["total_clients"], 0)
            await pool.stop()

    async def test_worker_start_is_atomic_for_same_uid(self) -> None:
        manager = WorkerManager(max_workers=2)
        entered = asyncio.Event()

        async def factory(_uid: int, stop: asyncio.Event) -> None:
            entered.set()
            await stop.wait()

        manager.set_worker_factory(factory)
        results = await asyncio.gather(
            manager.start_worker(77),
            manager.start_worker(77),
        )
        self.assertEqual(sum(results), 1)
        await asyncio.wait_for(entered.wait(), timeout=1)
        self.assertTrue(manager.is_running(77))
        self.assertTrue(await manager.stop_worker(77))
        self.assertFalse(manager.is_running(77))
