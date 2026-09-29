"""Saqlangan Telethon sessiyasini tekshirish va Telegramda bekor qilish.

Sessiya egaligini tekshirish natijasi faqat 4 xil bo'ladi:

- ``valid``     — authorization Telegramda tirik va aynan kutilgan UID'ga tegishli;
- ``mismatch``  — authorization tirik, lekin boshqa Telegram akkauntiga tegishli;
- ``invalid``   — authorization definitiv yaroqsiz (revoked, o'chirilgan, buzilgan);
- ``temporary`` — Telegram/tarmoq vaqtincha javob bermadi (FloodWait, timeout, OSError).

Vaqtinchalik xatolar hech qachon ``invalid`` deb talqin qilinmaydi: aks holda
ishlayotgan sessiya tasodifan o'chirilib ketardi.
"""

from __future__ import annotations

import asyncio
import contextlib

from telethon import TelegramClient
from telethon.errors import (
    AuthKeyDuplicatedError,
    AuthKeyUnregisteredError,
    FloodWaitError,
    SessionRevokedError,
    UserDeactivatedBanError,
    UserDeactivatedError,
)
from telethon.sessions import StringSession

from config.config import API_HASH, API_ID
from core.logger import log

# Telegram authorization'i definitiv yaroqsiz ekanini bildiruvchi xatolar.
DEFINITIVE_INVALID_ERRORS: tuple[type[BaseException], ...] = (
    AuthKeyDuplicatedError,
    AuthKeyUnregisteredError,
    SessionRevokedError,
    UserDeactivatedError,
    UserDeactivatedBanError,
)

# Vaqtinchalik (qayta urinish mumkin bo'lgan) xatolar.
TEMPORARY_ERRORS: tuple[type[BaseException], ...] = (
    FloodWaitError,
    asyncio.TimeoutError,
    TimeoutError,
    OSError,
    ConnectionError,
)

VALID = "valid"
MISMATCH = "mismatch"
INVALID = "invalid"
TEMPORARY = "temporary"


async def validate_telegram_session_owner(session: str, expected_uid: int) -> str:
    """Sessiya aynan ``expected_uid`` akkauntiga tegishli ekanini tekshiradi.

    ``get_me()`` natijasidagi UID solishtiriladi. FloodWait, timeout va
    tarmoq xatolari ``temporary`` deb qaytariladi — ular sessiya yaroqsizligini
    bildirmaydi va chaqiruvchi bu holatda pending sessiyani saqlab qolishi
    kerak.
    """
    if not session:
        return INVALID

    client: TelegramClient | None = None
    try:
        # Buzilgan StringSession konstruktorning o'zida ValueError beradi.
        client = TelegramClient(StringSession(session), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        me = await asyncio.wait_for(client.get_me(), timeout=15)
        if me is None:
            # connect() bo'ldi, lekin authorization yo'q — Telegramda tirik emas.
            return INVALID
        actual_uid = int(getattr(me, "id", 0) or 0)
        if actual_uid != int(expected_uid):
            log(
                f"🚫 Sessiya boshqa akkauntga tegishli: "
                f"expected={expected_uid} actual={actual_uid}",
                "warning",
            )
            return MISMATCH
        return VALID

    except DEFINITIVE_INVALID_ERRORS as exc:
        log(
            f"ℹ️ Sessiya definitiv yaroqsiz: uid={expected_uid} {type(exc).__name__}",
            "warning",
        )
        return INVALID

    except (ValueError, TypeError) as exc:
        log(
            f"ℹ️ Sessiya formati buzilgan: uid={expected_uid} {type(exc).__name__}",
            "warning",
        )
        return INVALID

    except TEMPORARY_ERRORS as exc:
        log(
            f"⚠️ Sessiyani tekshirib bo'lmadi (vaqtinchalik): "
            f"uid={expected_uid} {type(exc).__name__}",
            "warning",
        )
        return TEMPORARY

    except Exception as exc:
        # Kutilmagan API/tarmoq xatosi ham sessiyani o'chirish uchun asos emas.
        log(
            f"⚠️ Sessiya tekshiruvida kutilmagan xato: "
            f"uid={expected_uid} {type(exc).__name__}",
            "warning",
        )
        return TEMPORARY

    finally:
        if client:
            with contextlib.suppress(Exception):
                await client.disconnect()


async def revoke_telegram_session(session: str, uid: int) -> bool:
    """Authorization'ni Telegram Devices ro'yxatidan haqiqiy log_out qiladi.

    ``True`` — Telegramda bekor qilinadigan authorization qolmadi (yoki u allaqachon
    yaroqsiz edi, ya'ni lokal tozalash xavfsiz). ``False`` — FloodWait/tarmoq
    sababli aniq bo'lmadi, chaqiruvchi lokal ma'lumotni saqlab turishi kerak.
    """
    if not session:
        return True

    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(session), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        # is_user_authorized() FloodWait'ni ham False deb yashirishi mumkin:
        # vaqtinchalik xatoda lokal sessiyani o'chirib yubormaslik kerak.
        me = await asyncio.wait_for(client.get_me(), timeout=15)
        if me is not None:
            await asyncio.wait_for(client.log_out(), timeout=20)
        return True
    except DEFINITIVE_INVALID_ERRORS as exc:
        # Telegramda tirik authorization yo'q — bekor qilinadigan narsa ham yo'q.
        log(
            f"ℹ️ Sessiya allaqachon yaroqsiz, revoke shart emas: "
            f"uid={uid} {type(exc).__name__}",
            "warning",
        )
        return True
    except (ValueError, TypeError) as exc:
        log(
            f"ℹ️ Sessiya formati buzilgan, revoke shart emas: "
            f"uid={uid} {type(exc).__name__}",
            "warning",
        )
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
