"""🔒 Foydalanuvchi lock'larining izolyatsiyasi.

Qamlov:
- turli foydalanuvchilar bir-birini **bloklamasligi** kerak
  (striped lock collision — `uid % 256` — bu muammo bo'lsa,
  foydalanuvchilar o'zaro kutib qoladi);
- bitta foydalanuvchining o'z amallari ketma-ket bo'lishi kerak.
"""

from __future__ import annotations

import asyncio
import os
import sys
import unittest
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from core import update_locks


class UpdateLockIsolationTests(unittest.IsolatedAsyncioTestCase):
    """Lock'lar turli foydalanuvchilarni o'zaro bloklamasligi kerak."""

    async def test_different_users_do_not_share_lock(self) -> None:
        """Turli uid'lar turli lock olishi kerak."""
        locks = {update_locks.user_update_lock(uid) for uid in range(1, 200)}
        self.assertEqual(
            len(locks), 199, "turli foydalanuvchilar lock bo'lishi kerak"
        )

    async def test_same_user_gets_same_lock(self) -> None:
        """Bir xil uid — bir xil lock (o'z amallari ketma-ket)."""
        self.assertIs(
            update_locks.user_update_lock(42),
            update_locks.user_update_lock(42),
        )

    async def test_operation_locks_are_isolated(self) -> None:
        """Operation lock'lar ham izolyatsiyalangan bo'lishi kerak."""
        locks = {update_locks.user_operation_lock(uid) for uid in range(1, 200)}
        self.assertEqual(len(locks), 199)

    async def test_one_user_does_not_block_another(self) -> None:
        """Bir foydalanuvchi lock ushlab turganda, boshqasi kutmasligi kerak."""
        slow_started = asyncio.Event()
        release_slow = asyncio.Event()
        fast_done = asyncio.Event()

        async def _slow():
            async with update_locks.user_update_lock(1):
                slow_started.set()
                await release_slow.wait()

        async def _fast():
            await slow_started.wait()
            async with update_locks.user_update_lock(2):
                fast_done.set()

        slow_task = asyncio.create_task(_slow())
        fast_task = asyncio.create_task(_fast())

        # Tez foydalanuvchi 0.5 s ichida tamom bo'lishi kerak.
        try:
            await asyncio.wait_for(fast_done.wait(), timeout=0.5)
        except TimeoutError:
            self.fail("boshqa foydalanuvchi bloklandi (lock collision)")
        finally:
            release_slow.set()
            await asyncio.gather(slow_task, fast_task, return_exceptions=True)

    async def test_collision_uids_do_not_block_each_other(self) -> None:
        """``uid`` va ``uid + 256`` (eski stripe chegarasi) bir-birini
        bloklamasligi kerak."""
        slow_started = asyncio.Event()
        release_slow = asyncio.Event()
        fast_done = asyncio.Event()

        async def _slow():
            async with update_locks.user_update_lock(1):
                slow_started.set()
                await release_slow.wait()

        async def _fast():
            await slow_started.wait()
            async with update_locks.user_update_lock(257):
                fast_done.set()

        slow_task = asyncio.create_task(_slow())
        fast_task = asyncio.create_task(_fast())

        try:
            await asyncio.wait_for(fast_done.wait(), timeout=0.5)
        except TimeoutError:
            self.fail("collision uid'lar bir-birini blokladi")
        finally:
            release_slow.set()
            await asyncio.gather(slow_task, fast_task, return_exceptions=True)

    async def test_same_user_actions_are_serial(self) -> None:
        """Bir foydalanuvchining amallari ketma-ket bo'lishi kerak."""
        order = []

        async def _action(idx: int):
            async with update_locks.user_update_lock(7):
                order.append(f"start{idx}")
                await asyncio.sleep(0.01)
                order.append(f"end{idx}")

        await asyncio.gather(_action(1), _action(2))
        # Har bir amal to'liq tugaganidan keyin ikkinchisi boshlanishi kerak.
        self.assertIn(("start1", "end1"), [(order[0], order[1])])
        self.assertIn(("start2", "end2"), [(order[2], order[3])])


if __name__ == "__main__":
    unittest.main()
