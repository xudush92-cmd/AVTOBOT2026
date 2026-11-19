"""Backup bloklovchi xatolikning regressiya testlari.

Muammo: ``db.backup_to()`` butun bazani nusxa ko'chirish paytida global
``_write_lock`` ni ushlab turardi. Katta bazada bu barcha foydalanuvchilarning
yozuvlarini (login, interval o'zgarishi, guruh qo'shish) bloklab qoldirardi —
ya'ni bitta super admin eksporti boshqa odamlarni kutishga majbur qilardi.

Ikkinchi, yanada jiddiy muammo: ``aiosqlite`` har bir ulanish uchun bitta
worker thread ishlatadi va ``backup()`` aynan shu thread'da bajarilishi kerak.
Asosiy ulanish ustida ``backup()`` ishlatilsa, parallel yozuv bilan birga
**deadlock** yuzaga keladi (yozuv commit'i nusxadan keyingi navbatda turadi,
nusxa esa yozuvni kutadi).

Yechim: nusxa uchun alohida manba ulanishi ishlatiladi va ``_write_lock``
butunlay ushlanmaydi.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")


from core import database as db


class BackupNonBlockingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "backup_lock.db"
        self._old_path = db.DB_PATH
        db.DB_PATH = self.db_path
        await db.init_db()

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self._old_path
        self.temp.cleanup()

    async def _make_bulk_rows(self, count: int = 20000) -> None:
        await db._conn().execute("CREATE TABLE IF NOT EXISTS bulk (v INTEGER)")
        await db._conn().executemany(
            "INSERT INTO bulk (v) VALUES (?)", [(i,) for i in range(count)]
        )
        await db._conn().commit()

    async def test_backup_does_not_deadlock_with_concurrent_writes(self) -> None:
        """Parallel yozuv bilan birga backup deadlock qilmasligi kerak."""
        await db.upsert_user(9001, name="Writer")
        await self._make_bulk_rows()

        target = Path(self.temp.name) / "out.db"
        writes_completed = 0

        async def concurrent_writer() -> None:
            nonlocal writes_completed
            for i in range(40):
                await db.upsert_user(9100 + i, name=f"Concurrent {i}")
                writes_completed += 1

        writer_task = asyncio.create_task(concurrent_writer())
        # Timeout qo'yamiz — deadlock bo'lsa test osilib qolmasin.
        await asyncio.wait_for(
            db.backup_to(target), timeout=30
        )
        await asyncio.wait_for(writer_task, timeout=30)

        self.assertEqual(writes_completed, 40)
        self.assertTrue(target.exists())

        with sqlite3.connect(target) as conn:
            self.assertEqual(
                conn.execute("PRAGMA integrity_check").fetchone()[0], "ok"
            )
            self.assertGreaterEqual(
                conn.execute("SELECT COUNT(*) FROM bulk").fetchone()[0], 20000
            )

    async def test_backup_uses_separate_source_connection(self) -> None:
        """Manba ulanish boshqa bo'lishi kerak (deadlockning oldini oladi)."""
        await db.upsert_user(9150, name="Separate Source")
        target = Path(self.temp.name) / "sep.db"

        seen: list[int] = []
        original_connect = db.aiosqlite.connect

        def tracking_connect(target_path, *args, **kwargs):
            seen.append(str(target_path))
            return original_connect(target_path, *args, **kwargs)

        db.aiosqlite.connect = tracking_connect  # type: ignore[assignment]
        try:
            await db.backup_to(target)
        finally:
            db.aiosqlite.connect = original_connect  # type: ignore[assignment]

        # Manba (DB_PATH) va maqsad (destination) — ikki xil ulanish.
        self.assertIn(str(self.db_path), seen)
        self.assertIn(str(target), seen)
        self.assertNotEqual(str(self.db_path), str(target))

    async def test_backup_lock_is_not_held_during_copy(self) -> None:
        """`_write_lock` nusxa ko'chirish paytida band bo'lmasligi kerak."""
        await db.upsert_user(9400, name="Lock Probe")
        target = Path(self.temp.name) / "probe.db"

        observed: list[bool] = []
        original_connect = db.aiosqlite.connect

        def tracking_connect(target_path, *args, **kwargs):
            conn = original_connect(target_path, *args, **kwargs)
            if str(target_path) == str(self.db_path):
                original_backup = conn.backup

                async def tracking_backup(dest, *a, **kw):
                    observed.append(db._write_lock.locked())
                    return await original_backup(dest, *a, **kw)

                conn.backup = tracking_backup  # type: ignore[method-assign]
            return conn

        db.aiosqlite.connect = tracking_connect  # type: ignore[assignment]
        try:
            await db.backup_to(target)
        finally:
            db.aiosqlite.connect = original_connect  # type: ignore[assignment]

        self.assertEqual(len(observed), 1)
        self.assertFalse(
            observed[0],
            "backup_to nusxa ko'chirish paytida global _write_lock ni ushlab turadi",
        )

    async def test_backup_content_is_consistent_snapshot(self) -> None:
        """Nusxa bo'sh yoki buzilgan bo'lmasligi kerak."""
        await db.upsert_user(9200, name="Snapshot User")
        target = Path(self.temp.name) / "snap.db"
        await db.backup_to(target)

        with sqlite3.connect(target) as conn:
            rows = conn.execute(
                "SELECT name FROM users WHERE uid = ?", (9200,)
            ).fetchall()
        self.assertEqual(rows, [("Snapshot User",)])

    async def test_backup_sanitized_export_still_works(self) -> None:
        """Sessiyani chiqarib tashlash funksiyasi buzilmasligi kerak."""
        await db.upsert_user(9300, name="Export User")
        await db.set_session(9300, "secret-session-value")
        target = Path(self.temp.name) / "sanitized.db"
        await db.backup_to(target, sanitize_sessions=True)

        with sqlite3.connect(target) as conn:
            value = conn.execute(
                "SELECT session FROM users WHERE uid = ?", (9300,)
            ).fetchone()[0]
        self.assertEqual(value, "")

        raw = target.read_bytes()
        self.assertNotIn(b"secret-session-value", raw)
        for suffix in ("-wal", "-shm", "-journal"):
            self.assertFalse(Path(f"{target}{suffix}").exists())


if __name__ == "__main__":
    unittest.main()
