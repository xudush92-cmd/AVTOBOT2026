"""Start paytidagi sessiya tekshiruvi va vaqtinchalik xatolardan tiklanish."""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from telethon.errors import AuthKeyUnregisteredError, FloodWaitError  # noqa: E402

from admin import admin_actions  # noqa: E402
from bot import menu, texts as T  # noqa: E402
from core import database as db  # noqa: E402
from core import session_manager  # noqa: E402
from worker import worker as posting_worker  # noqa: E402
from worker.client_pool import (  # noqa: E402
    ClientPool,
    PoolBusyError,
    SessionInvalidError,
)


class FakeTelegramClient:
    instances: ClassVar[list[FakeTelegramClient]] = []
    me_id: int | None = 42
    error: Exception | None = None

    def __init__(self, _session, *_args, **_kwargs):
        self.connected = False
        self.disconnected = False
        self.me_checks = 0
        self.__class__.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False
        self.disconnected = True

    def is_connected(self) -> bool:
        return self.connected

    async def get_me(self):
        self.me_checks += 1
        if self.__class__.error:
            raise self.__class__.error
        if self.__class__.me_id is None:
            return None
        return SimpleNamespace(id=self.__class__.me_id)


class StartSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        FakeTelegramClient.instances.clear()
        FakeTelegramClient.me_id = 42
        FakeTelegramClient.error = None
        self.pool = ClientPool(1, "hash", max_clients=2)
        await self.pool.start()
        self.manager = SimpleNamespace(
            is_running=MagicMock(return_value=False),
            start_worker=AsyncMock(return_value=True),
        )

    async def asyncTearDown(self) -> None:
        await self.pool.stop()

    @contextmanager
    def pool_client(self):
        with (
            patch("worker.client_pool.TelegramClient", FakeTelegramClient),
            patch("worker.client_pool.StringSession", side_effect=lambda value: value),
        ):
            yield

    @contextmanager
    def start_dependencies(self):
        with (
            self.pool_client(),
            patch.object(posting_worker, "client_pool", self.pool),
            patch.object(menu, "worker_manager", self.manager),
            patch.object(
                db,
                "get_user",
                new=AsyncMock(
                    return_value={
                        "uid": 42,
                        "is_admin": 1,
                        "session": "existing-session",
                        "is_blocked": 0,
                        "running": 0,
                    }
                ),
            ),
            patch.object(db, "is_tariff_expired", new=AsyncMock(return_value=False)),
            patch.object(db, "is_blocked", new=AsyncMock(return_value=False)),
            patch.object(db, "get_chats", new=AsyncMock(return_value=["@group"])),
            patch.object(db, "get_posts", new=AsyncMock(return_value=[{"text": "hi"}])),
            patch.object(db, "get_interval", new=AsyncMock(return_value=30)),
            patch.object(db, "set_running", new=AsyncMock()) as set_running,
            patch.object(db, "del_session", new=AsyncMock()) as del_session,
            patch.object(
                admin_actions, "user_card_markup", new=AsyncMock(return_value="card")
            ),
        ):
            yield set_running, del_session

    async def test_user_start_verifies_once_then_worker_reuses_client(self) -> None:
        with self.start_dependencies() as (set_running, del_session):
            ok, text = await menu.confirm_start(42)
            self.assertTrue(ok, text)
            self.assertEqual(FakeTelegramClient.instances[0].me_checks, 1)
            self.assertEqual(self.pool.stats()["references"], 0)
            await self.pool.acquire(42, "existing-session")
            await self.pool.release(42)
            self.assertEqual(FakeTelegramClient.instances[0].me_checks, 1)
            set_running.assert_awaited_once_with(42, True)
            self.manager.start_worker.assert_awaited_once_with(42)
            del_session.assert_not_awaited()

    async def test_admin_start_verifies_target_once_not_admin(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        with self.start_dependencies() as (set_running, del_session):
            await admin_actions.action_start(update, 999, 42)
            self.assertEqual(FakeTelegramClient.instances[0].me_checks, 1)
            self.assertIn(
                "boshlandi", update.callback_query.edit_message_text.await_args.args[0]
            )
            set_running.assert_awaited_once_with(42, True)
            self.manager.start_worker.assert_awaited_once_with(42)
            del_session.assert_not_awaited()

    async def test_missing_or_wrong_identity_stops_both_starts_without_deletion(
        self,
    ) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        for me_id in (None, 999):
            with self.subTest(me_id=me_id):
                FakeTelegramClient.me_id = me_id
                with self.start_dependencies() as (set_running, del_session):
                    ok, text = await menu.confirm_start(42)
                    self.assertFalse(ok)
                    self.assertEqual(text, T.START_SESSION_INVALID)
                    await admin_actions.action_start(update, 999, 42)
                    self.assertEqual(
                        update.callback_query.edit_message_text.await_args.args[0],
                        T.START_SESSION_INVALID,
                    )
                    set_running.assert_not_awaited()
                    del_session.assert_not_awaited()
                    self.manager.start_worker.assert_not_awaited()
                self.assertEqual(self.pool.stats()["total_clients"], 0)
                self.assertEqual(self.pool._reservations, set())
                self.assertTrue(FakeTelegramClient.instances[-1].disconnected)

    async def test_flood_timeout_or_network_failure_is_retryable(self) -> None:
        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock())
        )
        for error in (
            FloodWaitError(None, 90),
            asyncio.TimeoutError(),
            OSError("down"),
        ):
            with self.subTest(error=type(error).__name__):
                FakeTelegramClient.error = error
                with self.start_dependencies() as (set_running, del_session):
                    ok, text = await menu.confirm_start(42)
                    self.assertFalse(ok)
                    self.assertEqual(text, T.START_SESSION_RETRY)
                    await admin_actions.action_start(update, 999, 42)
                    self.assertEqual(
                        update.callback_query.edit_message_text.await_args.args[0],
                        T.START_SESSION_RETRY,
                    )
                    set_running.assert_not_awaited()
                    del_session.assert_not_awaited()
                    self.manager.start_worker.assert_not_awaited()
                self.assertEqual(self.pool.stats()["total_clients"], 0)
                self.assertEqual(self.pool._reservations, set())
                self.assertTrue(FakeTelegramClient.instances[-1].disconnected)
        FakeTelegramClient.error = None
        with self.start_dependencies():
            ok, _ = await menu.confirm_start(42)
        self.assertTrue(ok)

    async def test_cached_start_rechecks_once_and_releases_on_flood(self) -> None:
        with self.pool_client():
            await self.pool.verify_session(42, "existing-session")
            client = FakeTelegramClient.instances[-1]
            self.assertEqual(client.me_checks, 1)
            FakeTelegramClient.error = FloodWaitError(None, 90)
            with self.assertRaises(PoolBusyError):
                await self.pool.verify_session(42, "existing-session")
            self.assertEqual(client.me_checks, 2)
            self.assertTrue(client.disconnected)
            self.assertEqual(self.pool.stats()["total_clients"], 0)
            FakeTelegramClient.error = None
            await self.pool.verify_session(42, "existing-session")
            self.assertEqual(FakeTelegramClient.instances[-1].me_checks, 1)

    async def test_pool_distinguishes_authorization_from_temporary_errors(self) -> None:
        with self.pool_client():
            FakeTelegramClient.me_id = None
            with self.assertRaises(SessionInvalidError):
                await self.pool.acquire(42, "existing-session")
            FakeTelegramClient.me_id = 42
            FakeTelegramClient.error = AuthKeyUnregisteredError(None)
            with self.assertRaises(SessionInvalidError):
                await self.pool.acquire(42, "existing-session")
            FakeTelegramClient.error = OSError("temporary network failure")
            with self.assertRaises(PoolBusyError):
                await self.pool.acquire(42, "existing-session")
            self.assertEqual(self.pool.stats()["total_clients"], 0)
            self.assertEqual(self.pool._reservations, set())

    async def test_logout_flood_does_not_report_success_to_delete_session(self) -> None:
        client = SimpleNamespace(
            connect=AsyncMock(),
            get_me=AsyncMock(side_effect=FloodWaitError(None, 30)),
            log_out=AsyncMock(),
            disconnect=AsyncMock(),
        )
        with (
            patch.object(session_manager, "TelegramClient", return_value=client),
            patch.object(
                session_manager, "StringSession", side_effect=lambda value: value
            ),
        ):
            self.assertFalse(
                await session_manager.revoke_telegram_session("existing-session", 42)
            )
        client.log_out.assert_not_awaited()
        client.disconnect.assert_awaited_once()


class WorkerSessionRetentionTests(unittest.IsolatedAsyncioTestCase):
    @contextmanager
    def worker_dependencies(self, pool):
        app = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        with (
            patch.object(posting_worker, "client_pool", pool),
            patch.object(posting_worker, "application", app),
            patch.object(posting_worker.random, "randint", return_value=0),
            patch.object(db, "get_user", new=AsyncMock(return_value={"is_admin": 1})),
            patch.object(db, "is_tariff_expired", new=AsyncMock(return_value=False)),
            patch.object(db, "get_session", new=AsyncMock(return_value="original")),
            patch.object(db, "get_chats", new=AsyncMock(return_value=["@group"])),
            patch.object(db, "get_posts", new=AsyncMock(return_value=[{"text": "hi"}])),
            patch.object(db, "get_interval", new=AsyncMock(return_value=60)),
            patch.object(db, "set_running", new=AsyncMock()) as set_running,
            patch.object(db, "del_session", new=AsyncMock()) as del_session,
        ):
            yield set_running, del_session

    async def test_invalid_worker_session_stops_but_is_not_erased(self) -> None:
        pool = SimpleNamespace(
            acquire=AsyncMock(side_effect=SessionInvalidError("revoked")),
            remove=AsyncMock(),
            release=AsyncMock(),
        )
        with self.worker_dependencies(pool) as (set_running, del_session):
            await posting_worker.posting_loop(42, asyncio.Event())
        del_session.assert_not_awaited()
        pool.remove.assert_awaited_once_with(42)
        set_running.assert_awaited_with(42, False)

    async def test_send_auth_error_does_not_erase_session(self) -> None:
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=SimpleNamespace()),
            remove=AsyncMock(),
            release=AsyncMock(),
        )
        with (
            self.worker_dependencies(pool) as (set_running, del_session),
            patch.object(
                posting_worker,
                "send_post",
                new=AsyncMock(side_effect=AuthKeyUnregisteredError(None)),
            ),
        ):
            await posting_worker.posting_loop(42, asyncio.Event())
        del_session.assert_not_awaited()
        pool.remove.assert_awaited_once_with(42)
        pool.release.assert_awaited_once_with(42)
        set_running.assert_awaited_with(42, False)

    async def test_flood_during_acquire_waits_and_keeps_session(self) -> None:
        busy = PoolBusyError("flood")
        busy.__cause__ = FloodWaitError(None, 90)
        pool = SimpleNamespace(
            acquire=AsyncMock(side_effect=busy),
            remove=AsyncMock(),
            release=AsyncMock(),
        )
        stop = asyncio.Event()
        with (
            self.worker_dependencies(pool) as (_set_running, del_session),
            patch.object(
                posting_worker, "sleep_or_stop", new=AsyncMock(return_value=True)
            ) as sleeper,
        ):
            await posting_worker.posting_loop(42, stop)
        sleeper.assert_awaited_once_with(stop, 95)
        pool.remove.assert_not_awaited()
        del_session.assert_not_awaited()

    async def test_repeated_network_timeouts_do_not_delete_group(self) -> None:
        pool = SimpleNamespace(
            acquire=AsyncMock(return_value=SimpleNamespace()),
            remove=AsyncMock(),
            release=AsyncMock(),
        )
        rounds = 0

        async def fast_sleep(_stop, seconds):
            nonlocal rounds
            if seconds >= 300:  # interval: sikl yakunlandi
                rounds += 1
                return rounds == 4  # MAX_GROUP_FAILS (3) dan ham ko'proq
            return False

        with (
            self.worker_dependencies(pool) as (_set_running, del_session),
            patch.object(
                posting_worker,
                "send_post",
                new=AsyncMock(side_effect=asyncio.TimeoutError()),
            ) as send_post,
            patch.object(posting_worker, "sleep_or_stop", new=fast_sleep),
            patch.object(db, "remove_chat_by_value", new=AsyncMock()) as remove_chat,
        ):
            await posting_worker.posting_loop(42, asyncio.Event())
        self.assertEqual(send_post.await_count, 4)
        remove_chat.assert_not_awaited()
        del_session.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
