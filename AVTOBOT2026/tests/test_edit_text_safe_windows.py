"""
``edit_text_safe`` — barcha callback oynalarida "Message is not modified"
xatosiga chidamlilik.

PR #50 da ``edit_text_safe`` faqat ``gint:``/``mg:``/``gchk:``
callback'larida ishlatilgan edi. Audit natijasida **250 ta** raw
``q.edit_message_text`` joyi qoldi — ularning orasida **statik**
oynalar bor (statistika, jamoa adminlari ro'yxati, tasdiq kutilayotganlar),
ya'ni foydalanuvchi bir xil tugmani ikki marta bossa Telegram
``BadRequest: Message is not modified`` beradi.

Bu fayl:
- ``edit_text_safe`` qaytarish qiymatini tekshiradi (``True``/``False``);
- statik oynalarda "not modified" xatosini tekshiradi;
- eski kodda xato chiqagan joylarni (dalil) qayd etadi.
"""

from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from telegram.error import BadRequest

from core.utils import edit_text_safe

UID = 991460501


def inline_update(data: str = "adm:stats") -> SimpleNamespace:
    q = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock(), edit_text=AsyncMock()),
    )
    return SimpleNamespace(
        callback_query=q,
        message=None,
        effective_user=SimpleNamespace(id=UID),
    )


class EditTextSafeReturnValueTests(unittest.IsolatedAsyncioTestCase):
    """``edit_text_safe`` natijani to'g'ri qaytarishi kerak.

    ⚠️ Bu muhim: ``edit_text_safe`` xatoni yutib oladi, shuning uchun
    ``with contextlib.suppress(...)`` ichida chaqirilsa, natija
    (``shown = True``) **har doim** o'rnatiladi va «xabar ko'rsatildi»
    deb hisoblanadi — bu esa xato.
    """

    async def test_returns_true_on_success(self) -> None:
        query = SimpleNamespace(edit_message_text=AsyncMock())
        self.assertTrue(await edit_text_safe(query, "Matn"))

    async def test_returns_true_on_not_modified(self) -> None:
        query = SimpleNamespace(
            edit_message_text=AsyncMock(
                side_effect=BadRequest("Message is not modified")
            )
        )
        self.assertTrue(await edit_text_safe(query, "Matn"))

    async def test_returns_false_on_other_error(self) -> None:
        query = SimpleNamespace(
            edit_message_text=AsyncMock(
                side_effect=BadRequest("chat not found")
            )
        )
        with patch("core.utils.log"):
            self.assertFalse(await edit_text_safe(query, "Matn"))

    async def test_returns_false_on_none_query(self) -> None:
        self.assertFalse(await edit_text_safe(None, "Matn"))


class StaticAdminWindowTests(unittest.IsolatedAsyncioTestCase):
    """Super adminning **statik** oynalari — "not modified" ga chidamli.

    Bu oynalarda matn o'zgarmaydi: statistika, jamoa adminlari ro'yxati,
    tasdiq kutilayotganlar. Foydalanuvchi bir xil tugmani ikki marta
    bosishi — normal holat.
    """

    async def _run(self, func_name: str, data: str) -> None:
        from admin import admin_panel as AP

        update = inline_update(data)
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )

        async def fake_records(*_a, **_k):
            return []

        async def fake_stats(*_a, **_k):
            return {
                "today_referrals": 0,
                "today_sends_ok": 0,
                "today_sends_failed": 0,
                "total_users": 0,
                "admins": 0,
                "waiting": 0,
                "blocked": 0,
                "running": 0,
                "total_groups": 0,
                "total_posts": 0,
                "total_active": 0,
                "teams": 0,
                "team_admins": 0,
            }

        # Worker va client pool statistikasi — DB bilan bog'liq emas,
        # lekin real chaqirilsa bazaga ulanish kerak.
        import worker.worker as W

        fake_pool_stats = {
            "in_use": 0,
            "total_clients": 0,
            "max": 0,
            "active_workers": 0,
        }
        fake_pool = SimpleNamespace(stats=lambda: fake_pool_stats)

        with (
            patch.object(AP.db, "get_all_users", fake_records),
            patch.object(AP.db, "get_pending_users", fake_records),
            patch.object(AP.db, "get_team_admins", fake_records),
            patch.object(AP.db, "get_user_info", fake_stats),
            patch.object(AP.db, "get_stats", fake_stats),
            patch.object(W, "client_pool", fake_pool),
        ):
            await getattr(AP, func_name)(update)

    async def test_show_stats(self) -> None:
        await self._run("show_stats", "adm:stats")

    async def test_show_team_admins(self) -> None:
        await self._run("show_team_admins", "adm:teamadmins")

    async def test_show_pending(self) -> None:
        await self._run("show_pending", "adm:pending")

    async def test_show_expired(self) -> None:
        await self._run("show_expired", "adm:expired")

    async def test_show_blocked(self) -> None:
        await self._run("show_blocked", "adm:blocked")

    async def test_show_users(self) -> None:
        await self._run("show_users", "adm:users")


class ApplySelectedGroupsFallbackTests(unittest.IsolatedAsyncioTestCase):
    """Skaner natijasi — xabar tahrirlamasa, yangi xabar yuborilishi kerak.

    ⚠️ Bu joyda ``edit_text_safe`` natijasi tekshirilishi shart:
    ``suppress`` ichida chaqirilsa, «xabar ko'rsatildi» deb
    hisoblanib, yangi xabar yuborilmaydi va foydalanuvchi natijani
    ko'rmaydi.
    """

    async def test_falls_back_to_new_message(self) -> None:
        from bot import groups as G

        update = inline_update("disc:apply")
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=RuntimeError("can't edit")
        )

        async def fake_window(_uid, note="", page=0):
            return "💬 GURUHLAR", None

        with (
            patch.object(G.db, "get_chat_records", AsyncMock(return_value=[])),
            patch.object(G.db, "get_limits", AsyncMock(return_value={})),
            patch.object(G.db, "add_chat", AsyncMock(return_value=(True, ""))),
            patch(
                "bot.my_groups.build_groups_window",
                fake_window,
            ),
        ):
            await G.apply_selected_groups(update, UID, [])

        update.callback_query.message.reply_text.assert_awaited()


if __name__ == "__main__":
    unittest.main()
