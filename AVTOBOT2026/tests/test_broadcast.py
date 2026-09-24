from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "12345")
os.environ.setdefault("API_HASH", "test-api-hash")
os.environ.setdefault("BOT_TOKEN", "123:test-token")
os.environ.setdefault("ADMIN_ID", "999")
os.environ.setdefault(
    "SESSION_ENCRYPTION_KEY",
    "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
)

from admin import broadcast  # noqa: E402
from bot import login  # noqa: E402
from config.config import SUPER_ADMIN  # noqa: E402


class BroadcastRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        broadcast.broadcast_pending.clear()
        broadcast.broadcast_jobs.clear()
        login.user_states.clear()
        self.bot = SimpleNamespace(
            send_photo=AsyncMock(),
            send_message=AsyncMock(),
            edit_message_text=AsyncMock(),
        )
        broadcast.set_application(SimpleNamespace(bot=self.bot))

    async def asyncTearDown(self) -> None:
        await broadcast.shutdown()
        broadcast.broadcast_pending.clear()
        broadcast.broadcast_jobs.clear()
        login.user_states.clear()
        broadcast.application = None

    async def test_photo_preview_progress_and_cancellation(self) -> None:
        photo = SimpleNamespace(file_id="telegram-photo-id")
        message = SimpleNamespace(
            text=None,
            caption="x" * 1500,
            photo=[photo],
            reply_photo=AsyncMock(),
        )
        receive_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=SUPER_ADMIN),
            message=message,
        )
        await broadcast.receive_broadcast(receive_update)

        preview = message.reply_photo.await_args.kwargs["caption"]
        self.assertLessEqual(len(preview), 1024)
        self.assertIn("BROADCAST PREVIEW", preview)

        send_query = SimpleNamespace(
            message=SimpleNamespace(chat_id=SUPER_ADMIN, message_id=77),
            edit_message_text=AsyncMock(),
        )
        send_update = SimpleNamespace(callback_query=send_query)
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_photo(*args, **kwargs) -> None:
            started.set()
            await release.wait()

        self.bot.send_photo.side_effect = slow_photo
        users = [{"uid": 101}, {"uid": 102}, {"uid": 103}]
        with patch.object(
            broadcast.db,
            "get_broadcast_users",
            new=AsyncMock(return_value=users),
        ):
            await broadcast.handle_broadcast_callback(
                send_update,
                SUPER_ADMIN,
                "bc:send",
            )

        job = broadcast.broadcast_jobs[SUPER_ADMIN]
        await asyncio.wait_for(started.wait(), timeout=1)

        stop_query = SimpleNamespace(edit_message_text=AsyncMock())
        await broadcast.handle_broadcast_callback(
            SimpleNamespace(callback_query=stop_query),
            SUPER_ADMIN,
            "bc:stop",
        )
        release.set()
        await asyncio.wait_for(job.task, timeout=2)

        self.assertTrue(job.cancel.is_set())
        self.assertEqual(job.sent, 1)
        self.assertEqual(self.bot.send_photo.await_count, 1)
        self.assertEqual(
            self.bot.send_photo.await_args.kwargs["photo"],
            "telegram-photo-id",
        )
        final_text = self.bot.edit_message_text.await_args.kwargs["text"]
        self.assertIn("TO'XTATILDI", final_text)


if __name__ == "__main__":
    unittest.main()
