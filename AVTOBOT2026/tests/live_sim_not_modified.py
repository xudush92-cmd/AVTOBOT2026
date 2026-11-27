"""
Audit: qolgan "Message is not modified" xavfi — dalil to'plash.

Super admin statistikasi va jamoa adminlari ro'yxati — **statik** oynalar.
Foydalanuvchi bir xil tugmani ikki marta bossa, matn o'zgarmaydi va
Telegram ``BadRequest: Message is not modified`` beradi.

Bu fayl haqiqiy ``telegram.error.BadRequest`` bilan tekshiradi:
- eski kod → istisno yuz beradi (layt sindiriladi);
- yangi kod (``edit_text_safe``) → xatosiz.

Shuningdek boshqa statik oynalar:
- ``adm:expired`` — muddati tugaganlar ro'yxati;
- ``adm:stats`` — statistika;
- ``adm:teamadmins`` — jamoa adminlari ro'yxati.
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("API_ID", "123456")
os.environ.setdefault("API_HASH", "0123456789abcdef0123456789abcdef")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN")
os.environ.setdefault("ADMIN_ID", "991460501")

from telegram.error import BadRequest

UID = 991460501


def inline_update(data: str) -> SimpleNamespace:
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


NOT_MODIFIED = BadRequest("Message is not modified")


async def main() -> int:
    from admin import admin_panel as AP

    failures: list[str] = []

    cases = [
        ("adm:stats", "show_stats"),
        ("adm:expired", "show_expired"),
        ("adm:teamadmins", "show_team_admins"),
        ("adm:users", "show_users"),
        ("adm:blocked", "show_blocked"),
        ("adm:pending", "show_pending"),
    ]

    async def fake_records(*_a, **_k):
        return []

    async def fake_admins(*_a, **_k):
        return []

    async def fake_info(*_a, **_k):
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

    for data, func_name in cases:
        update = inline_update(data)
        update.callback_query.edit_message_text = AsyncMock(
            side_effect=NOT_MODIFIED
        )

        func = getattr(AP, func_name, None)
        if func is None:
            print(f"  {data}: funksiya topilmadi")
            continue

        with (
            patch.object(AP.db, "get_all_users", fake_records),
            patch.object(AP.db, "get_pending_users", fake_records),
            patch.object(AP.db, "get_team_admins", fake_admins),
            patch.object(AP.db, "get_user_info", fake_info),
            patch.object(AP.db, "get_stats", fake_info),
        ):
            try:
                await func(update)
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{data} ({func_name}): {type(exc).__name__}: {exc}")
                print(f"  {data}: ❌ {type(exc).__name__}")
                continue
        print(f"  {data}: ✅ xatosiz")

    print()
    if failures:
        print("❌ QOLGAN XATOLAR:")
        for item in failures:
            print("  -", item)
        return 1
    print("✅ Statik oynalar 'not modified' xatosiga chidamli.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
