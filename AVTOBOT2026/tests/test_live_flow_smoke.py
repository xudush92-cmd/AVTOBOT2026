"""🔥 Live-flow smoke test — «guruhlar yo'q» tuzatishidan keyin.

Foydalanuvchi nuqtasidan to'liq oqim tekshiriladi:
1. skaner guruhlarni topadi;
2. «Tanlanganlarni qo'shish» bosiladi;
3. guruhlar bazaga yoziladi;
4. «💬 Guruhlar» oynasi ularni **ko'rsatadi** (bo'sh xabar chiqmaydi);
5. guruh o'chirilganda log izi qoladi.

Bu test haqiqiy Telegram API'siga ulanmaydi — ma'lumotlar bazasi va
callback'lar real kod bilan, Telegram esa stub bilan almashtiriladi.
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

from bot import discover_sessions as DS
from bot import groups as G
from bot import my_groups as MG
from core import database as db

UID = 6169018469


class LiveFlowSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.old_db_path = db.DB_PATH
        db.DB_PATH = Path(self.temp.name) / "test.db"
        await db.init_db()
        await db.upsert_user(UID, name="Eshmat Toshmatov", is_admin=1)

    async def asyncTearDown(self) -> None:
        await db.close_db()
        db.DB_PATH = self.old_db_path
        self.temp.cleanup()

    async def test_full_add_and_view_flow(self) -> None:
        """Skaner → qo'shish → ko'rish → o'chirish (log bilan)."""
        # 1) Skaner topdi.
        session = DS.start_session(
            UID,
            [
                DS.DiscoveredGroup(reference="@taxi_1", title="Toshkent Taksi"),
                DS.DiscoveredGroup(reference="@taxi_2", title="Xorazm Taksi"),
            ],
        )
        session.selected.update({session.groups[0].key, session.groups[1].key})

        # 2) «Tanlanganlarni qo'shish» bosildi.
        answer = AsyncMock()
        callback = SimpleNamespace(
            data="disc:apply",
            message=SimpleNamespace(
                reply_text=AsyncMock(), delete_message=AsyncMock()
            ),
            answer=answer,
            edit_message_text=AsyncMock(),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=callback,
        )

        await G.handle_discover_callback(update, UID, "disc:apply")

        alerts = [call.args[0] for call in answer.call_args_list if call.args]
        self.assertTrue(any("qo'shildi" in a for a in alerts), alerts)

        # 3) Bazada 2 ta guruh bor.
        rows = await db.get_chat_records(UID)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["title"], "Toshkent Taksi")

        # 4) «💬 Guruhlar» oynasi ularni ko'rsatadi — bo'sh xabar chiqmaydi.
        text, _markup = await MG.build_groups_window(UID)
        self.assertNotIn("Sizda hali guruh yo'q", text)
        self.assertIn("Toshkent Taksi", text)
        # Havola HTML-escape qilingan holda chiqadi (``_`` → ``\_``).
        self.assertIn("https://t.me/taxi\\_1", text)

        # 5) Guruh o'chiriladi — logda iz qoladi.
        group_id = rows[0]["id"]
        del_callback = SimpleNamespace(
            data=f"mg:del:{group_id}",
            message=None,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
        del_update = SimpleNamespace(
            effective_user=SimpleNamespace(id=UID),
            callback_query=del_callback,
        )

        with patch("bot.my_groups.log") as mock_log:
            await MG.handle_my_groups_callback(
                del_update, UID, f"mg:del:{group_id}"
            )

        self.assertTrue(mock_log.called)
        self.assertEqual(len(await db.get_chat_records(UID)), 1)


if __name__ == "__main__":
    unittest.main()
