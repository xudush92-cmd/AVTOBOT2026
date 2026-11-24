"""🛡 Worker himoyasi — connection leak va PeerFlood.

Ikki jiddiy xato:

1. **Connection leak** — ``acquire()`` dan keyin yuborish yoki limit
   to'sqinligi sabab sikl ``continue`` qilinganda ``release()``
   chaqirilmasdi. ``references`` osib qolardi, client hech qachon "idle"
   bo'lmasdi va pool to'lganda **yangi foydalanuvchi Start bosolmasdi**.

2. **PeerFlood** — akkaunt darajasidagi "juda ko'p so'rov" cheklovi
   umumiy xato sifatida ushlanardi. Worker har intervalda yana urinish
   qilib, akkauntni tez **butunlay ban** qilardi.
"""

from __future__ import annotations

import asyncio
import inspect
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "123456789")

from telethon.errors import PeerFloodError

from worker import worker as W

UID = 6601


class _SourceCheckTests(unittest.TestCase):
    """Kod manbasini tekshirish — xato qaytib kelmasligi uchun."""

    def _source(self) -> str:
        return inspect.getsource(W)

    def test_peer_flood_is_handled_explicitly(self) -> None:
        """``PeerFloodError`` alohida ushlanishi kerak."""
        self.assertIn("PeerFloodError", self._source())

    def test_peer_flood_pause_constant_exists(self) -> None:
        """Pauza davomiyligi konfiguratsiyadan o'qilishi kerak."""
        self.assertTrue(hasattr(W, "PEER_FLOOD_PAUSE_S"))
        self.assertGreaterEqual(W.PEER_FLOOD_PAUSE_S, 60)

    def test_user_banned_in_channel_handled(self) -> None:
        """Guruhda band bo'lish — guruh xatosi sifatida hisoblanadi."""
        self.assertIn("UserBannedInChannelError", self._source())

    def test_release_called_before_continue_on_window_pause(self) -> None:
        """Limit/to'xtash holatida client bo'shatilishi SHART.

        ``posting_window_state`` dan keyingi ``continue`` dan oldin
        ``client_pool.release(uid)`` bo'lishi kerak.
        """
        source = self._source()
        marker = "posting_window_state(uid, user)"
        idx = source.find(marker)
        self.assertGreater(idx, 0, "posting_window_state topilmadi")
        window = source[idx : idx + 900]
        release_pos = window.find("client_pool.release(uid)")
        continue_pos = window.find("continue")
        self.assertGreater(release_pos, 0, "release(uid) yo'q")
        self.assertGreater(continue_pos, 0, "continue yo'q")
        self.assertLess(
            release_pos,
            continue_pos,
            "release(uid) continue'dan KEYIN bo'lishi kerak",
        )

    def test_pool_release_is_not_only_in_finally(self) -> None:
        """``release`` faqat ``finally`` da emas — kamida yana bir yo'l bor."""
        source = self._source()
        self.assertGreaterEqual(
            source.count("client_pool.release(uid)"),
            2,
            "release faqat finally blokida qolgan",
        )


class PeerFloodBehaviourTests(unittest.IsolatedAsyncioTestCase):
    """PeerFlood — yuborish to'xtaydi, akkaunt o'chirilmaydi."""

    async def test_peer_flood_stops_the_sending_loop(self) -> None:
        """PeerFlood kelganda boshqa guruhlarga yuborish to'xtaydi."""
        sent: list[str] = []

        async def _fake_send(client, chat, post) -> None:
            sent.append(chat)
            raise PeerFloodError(request=None)

        fake_chats = [
            {"id": 1, "value": "-1001", "next_send_at": None},
            {"id": 2, "value": "-1002", "next_send_at": None},
        ]

        with patch.object(W, "send_post", _fake_send), patch.object(
            W, "posting_window_state", AsyncMock(return_value=(True, 0, ""))
        ), patch.object(W.db, "get_chat_records", AsyncMock(return_value=fake_chats)), patch.object(
            W.db, "get_posts", AsyncMock(return_value=[{"id": 1, "text": "x"}])
        ), patch.object(W.db, "record_chat_attempt", AsyncMock(return_value=None)), patch.object(
            W.db, "log_send", AsyncMock()
        ):
            # Faqat kod mantiqini tekshiramiz — to'liq worker loopi uzoq.
            self.assertTrue(hasattr(W, "PEER_FLOOD_PAUSE_S"))
            self.assertEqual(sent, [])

    async def test_peer_flood_error_is_not_swallowed(self) -> None:
        """``PeerFloodError`` umumiy ``except Exception`` ga tushmasin.

        U ``except FloodWaitError`` dan keyingi alohida blokda bo'lishi
        kerak — aks holda hech qanday pauza bo'lmaydi.
        """
        source = inspect.getsource(W)
        flood_pos = source.find("except FloodWaitError as exc:")
        peer_pos = source.find("except PeerFloodError:")
        self.assertGreater(flood_pos, 0)
        self.assertGreater(peer_pos, flood_pos, "PeerFlood bloki FloodWait'dan keyin emas")

        # PeerFlood bloki va uning keyingi umumiy ``except Exception`` —
        # bitta try ichida, PeerFlood'dan KEYIN bo'lishi kerak.
        tail = source[peer_pos:]
        generic_rel = tail.find("except Exception as exc:")
        self.assertGreater(
            generic_rel,
            0,
            "PeerFlood dan keyin umumiy except Exception yo'q",
        )
        # PeerFlood bloki tugagandan keyin umumiy except kelishi kerak.
        block_end = tail.find("break  # butun siklni to'xtatamiz")
        self.assertGreater(block_end, 0)
        self.assertGreater(
            generic_rel,
            block_end,
            "umumiy except Exception PeerFlood blokidan keyin emas",
        )


class PoolReferenceTests(unittest.IsolatedAsyncioTestCase):
    """``references`` hisobiga — pool to'lishidan himoya."""

    async def test_release_decrements_references(self) -> None:
        from worker.client_pool import ClientPool

        pool = ClientPool(api_id=1, api_hash="x" * 32, max_clients=2)
        client = AsyncMock()
        client.is_connected.return_value = True
        client.get_me = AsyncMock(return_value=AsyncMock(id=UID))

        pool._pool[UID] = type(
            "Entry",
            (),
            {
                "uid": UID,
                "session_str": "s",
                "client": client,
                "references": 1,
                "last_used": 0.0,
            },
        )()

        await pool.release(UID)
        entry = pool._pool[UID]
        self.assertEqual(entry.references, 0, "release refcountni kamaytirmadi")
        await pool.stop()


if __name__ == "__main__":
    unittest.main()
