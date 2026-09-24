"""Saqlangan Telethon sessiyasini Telegram serverida bekor qilish."""

from __future__ import annotations

import asyncio
import contextlib

from telethon import TelegramClient
from telethon.sessions import StringSession

from config.config import API_HASH, API_ID
from core.logger import log


async def revoke_telegram_session(session: str, uid: int) -> bool:
    """Authorization'ni Telegram Devices ro'yxatidan haqiqiy log_out qiladi."""
    if not session:
        return True

    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(session), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=15)
        if authorized:
            await asyncio.wait_for(client.log_out(), timeout=20)
        return True
    except Exception as exc:
        log(
            f"⚠️ Sessiyani Telegramda revoke qilib bo'lmadi: "
            f"uid={uid} {type(exc).__name__}",
            "warning",
        )
        return False
    finally:
        if client:
            with contextlib.suppress(Exception):
                await client.disconnect()
