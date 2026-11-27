"""
Live-simulyatsiya — UID 6169018469 uchun ikkala xato.

1. ``NoneType' object has no attribute 'reply_text'``
2. ``BadRequest: Message is not modified``

Bu fayl haqiqiy ``telegram.error.BadRequest`` klassidan foydalanadi —
soxta xato emas, Telegram'ning o'z istisnosi.
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

UID = 6169018469


def inline_update(data: str) -> SimpleNamespace:
    """Inline callback — ``update.message`` = None (haqiqiy Telegram oqimi)."""
    q = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
        message=SimpleNamespace(reply_text=AsyncMock(), edit_text=AsyncMock()),
    )
    return SimpleNamespace(
        callback_query=q,
        message=None,
        effective_user=SimpleNamespace(id=UID),
    )


async def main() -> int:
    from bot import groups as G
    from bot import my_groups as MG
    from bot import timer

    failures: list[str] = []

    # ── 1. gint:manual — eski xato: NoneType.reply_text ──────────────
    update = inline_update("gint:manual:1")

    async def fake_record(_uid, _gid):
        return {"id": 1, "value": "-100888", "title": "Test Guruh"}

    with patch.object(timer.db, "get_chat_record", fake_record):
        await timer.handle_group_interval_callback(update, UID, "gint:manual:1")

    if not update.callback_query.message.reply_text.await_count:
        failures.append("gint:manual — xabar yuborilmadi")
    print("1) gint:manual → xabar yuborildi:", bool(
        update.callback_query.message.reply_text.await_count
    ))

    # ── 2. gint:reset — eski xato: Message is not modified ────────────
    update = inline_update("gint:reset:1")
    update.callback_query.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )

    async def fake_interval(_uid):
        return 10

    async def fake_set(_uid, _gid, _value):
        return True

    with (
        patch.object(timer.db, "get_chat_record", fake_record),
        patch.object(timer.db, "get_interval", fake_interval),
        patch.object(timer.db, "set_chat_interval", fake_set),
    ):
        try:
            await timer.handle_group_interval_callback(
                update, UID, "gint:reset:1"
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"gint:reset — xato yuz berdi: {exc!r}")
    print("2) gint:reset → istisno yo'q:", not failures)

    # ── 3. mg:manual — eski xato: NoneType.reply_text ────────────────
    update = inline_update("mg:manual:1")
    with patch.object(MG.db, "get_chat_record", fake_record):
        await MG.handle_my_groups_callback(update, UID, "mg:manual:1")
    ok3 = bool(update.callback_query.message.reply_text.await_count)
    if not ok3:
        failures.append("mg:manual — xabar yuborilmadi")
    print("3) mg:manual → xabar yuborildi:", ok3)

    # ── 4. mg:interval — 'not modified' xatosi laytni sindirmaydi ─────
    update = inline_update("mg:interval:1")
    update.callback_query.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )
    with (
        patch.object(MG.db, "get_chat_record", fake_record),
        patch.object(MG.db, "get_interval", fake_interval),
    ):
        try:
            await MG.show_group_interval(update, UID, 1)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"mg:interval — xato yuz berdi: {exc!r}")
    print("4) mg:interval → istisno yo'q:", True)

    # ── 5. gint:back — xabar tahrlanadi (inline kontekstda) ─────────
    update = inline_update("gint:back")

    async def fake_window(_uid, note="", page=0):
        return "Matn", None

    with patch("bot.my_groups.build_groups_window", fake_window):
        await timer.handle_group_interval_callback(update, UID, "gint:back")
    ok5 = update.callback_query.edit_message_text.await_count > 0
    if not ok5:
        failures.append("gint:back — xabar tahrirlanmadi")
    print("5) gint:back → xabar tahrlanadi:", ok5)

    # ── 6. gchk:page — 'not modified' xatosi laytni sindirmaydi ──────
    update = inline_update("gchk:page:0")
    update.callback_query.edit_message_text = AsyncMock(
        side_effect=BadRequest("Message is not modified")
    )

    async def fake_records(_uid):
        return [{"id": 1, "value": "-100888", "title": "Test Guruh"}]

    with patch.object(G.db, "get_chat_records", fake_records):
        try:
            await G.handle_group_check_callback(update, UID, "gchk:page:0")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"gchk:page — xato yuz berdi: {exc!r}")
    print("6) gchk:page → istisno yo'q:", True)

    print()
    if failures:
        print("❌ MUAMMOLAR:")
        for item in failures:
            print("  -", item)
        return 1
    print("✅ Barcha inline callback oqimlari xatosiz ishladi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
