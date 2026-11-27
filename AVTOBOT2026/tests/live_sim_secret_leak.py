"""
Dalil: 2FA parol logga tushishi mumkin edi.

Simulyatsiya qilinadi:
1. Foydalanuvchi ``step="password"`` holatida 2FA parol kiritadi;
2. ``main.py::on_message()`` da xato yuz beradi;
3. Xato logga yoziladi.

Eski kodda logga **parolning o'zi** yozilardi
(``action=(update.message.text or "")[:40]``).

Bu skript eski kodda ham, yangi kodda ham ishlaydi —
farq faqat yozilgan matnda.
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

UID = 991460501
SECRET = "MySecretPassword123"


async def main() -> int:
    import main
    from bot.login import user_states

    # 1) Foydalanuvchi 2FA parol bosqichida.
    user_states.clear()
    user_states[UID] = {"step": "password", "ts": 0}

    # 2) Xato bilan keladigan xabar.
    message = SimpleNamespace(
        text=SECRET,
        reply_text=AsyncMock(),
        delete=AsyncMock(),
    )
    update = SimpleNamespace(
        message=message,
        effective_user=SimpleNamespace(id=UID),
        effective_message=message,
    )
    context = SimpleNamespace(error=None)

    written: list[str] = []

    def fake_log(msg, level="info", *args, **kwargs):
        written.append(str(msg))

    # 3) Xato yuz beradi (parol kiritilganda).
    # ``core.errlog.log`` ni patch qilamiz — butun log yozuvi shu
    # orqali o'tadi (log_error ham shuni ishlatadi).
    with (
        patch("core.errlog.log", side_effect=fake_log),
        patch.object(
            main,
            "_on_message_locked",
            AsyncMock(side_effect=RuntimeError("sign_in failed")),
        ),
    ):
        await main.on_message(update, context)

    user_states.clear()

    text = "\n".join(written)
    leaked = SECRET in text
    print("--- Logga yozilgan matn ---")
    print(text[:900] or "(bo'sh)")
    print()
    if leaked:
        print("❌ XAVF: 2FA parol logga tushdi!")
        return 1
    print("✅ Parol logga tushmadi — faqat bosqich nomi yozildi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
