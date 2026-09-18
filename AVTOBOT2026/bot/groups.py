"""
Guruhlar bilan ishlash.

Funksiyalar:
- Bulk qo'shish (bir nechta guruhni bir marta)
- O'chirish
- Ro'yxatni ko'rsatish
- Telegram'da guruhni tekshirish
"""

from __future__ import annotations

import asyncio
import contextlib

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    PeerIdInvalidError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession
from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as KB
from bot import texts as T
from config.config import API_HASH, API_ID
from core import database as db
from core.logger import log
from core.utils import parse_group_lines

from telethon import TelegramClient
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    PeerIdInvalidError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession
from telethon.tl.types import (
    Channel,
    ChannelParticipantAdmin,
    ChannelParticipantCreator,
)


# ─────────────────────────────────────────────────────────────────────────
# GURUHNI TEKSHIRISH (Telegram orqali)
# ─────────────────────────────────────────────────────────────────────────
async def verify_group(client: TelegramClient, group: str) -> tuple[bool, str]:
    """
    Bitta guruhga kirish va YOZISH imkonini tekshiradi.

    Muhim: mavjud client bilan ishlaydi — har bir guruh uchun yangi
    client ochilmaydi (bulk qo'shishda FloodWait va sekinlik oldini oladi).

    Returns:
        (True, 'ok')            — muvaffaqiyat
        (False, 'topilmadi')    — topilmadi
        (False, 'yopiq')        — private
        (False, "yozish huquqi yo'q") — kanal, admin emas
        (False, 'yozish taqiqlangan') — mute/ban
        (False, "noto'g'ri format")
        (False, 'flood')        — FloodWait
        (False, 'xato')         — boshqa xatolik
    """
    try:
        s = group.strip()
        if s.lstrip("-").isdigit():
            entity = await client.get_entity(int(s))
        else:
            entity = await client.get_entity(s)

        # ── Yozish huquqini tekshirish ──
        if isinstance(entity, Channel) and entity.broadcast:
            # Kanal: faqat admin/creator post qila oladi
            perms = await client.get_permissions(entity, "me")
            role = getattr(perms, "participant", perms)
            if not isinstance(
                role, (ChannelParticipantAdmin, ChannelParticipantCreator)
            ):
                return False, "yozish huquqi yo'q (kanal, admin emas)"
        else:
            # Guruh: ban/mute tekshirish (bo'lsa)
            try:
                perms = await client.get_permissions(entity, "me")
                role = getattr(perms, "participant", perms)
                banned = getattr(role, "banned_rights", None)
                if banned is not None and getattr(
                    banned, "send_messages", False
                ):
                    return False, "yozish taqiqlangan"
            except Exception:
                pass  # huquqni aniqlab bo'lmadi — worker baribir kuzatadi

        return True, "ok"

    except (UsernameNotOccupiedError, UsernameInvalidError, PeerIdInvalidError):
        return False, "topilmadi"
    except ChannelPrivateError:
        return False, "yopiq"
    except FloodWaitError:
        return False, "flood"
    except ValueError:
        return False, "noto'g'ri format"
    except Exception as e:
        log(f"verify_group {group}: {type(e).__name__}: {e}", "warning")
        return False, "xato"


async def add_groups_for(
    uid: int,
    groups: list[str],
    progress_fn=None,
) -> tuple[list[str], list[str], list[str], str | None]:
    """
    Guruhlarni tekshirib, foydalanuvchiga qo'shadi.

    BUTUN BATCH uchun bitta Telethon client ishlatiladi — 50 ta guruh
    qo'shish 50 marta connect bo'lmaydi (tezkor, FloodWait xavfi past).

    Args:
        uid: foydalanuvchi id
        groups: guruhlar ro'yxati
        progress_fn: har 5 guruhda chaqiriladi (i, added, duplicates, errors)

    Returns:
        (added, duplicates, errors, fatal)
        fatal != None — jarayon umuman boshlanmagan (sessiya yo'q va h.k.)
    """
    session = await db.get_session(uid)
    if not session:
        return [], [], [], "Sessiya topilmadi. Qaytadan 🔑 Login qiling."

    added: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = []
    existing = set(await db.get_chats(uid))

    client = TelegramClient(StringSession(session), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        if not await client.is_user_authorized():
            return [], [], [], "Sessiya yaroqsiz. Qaytadan 🔑 Login qiling."

        for i, group in enumerate(groups, 1):
            # Takroriy?
            if group in existing:
                duplicates.append(group)
                continue

            # Telegram'da tekshirish
            ok, reason = await verify_group(client, group)

            if not ok:
                errors.append(f"{group} ({reason})")
                if reason == "flood":
                    # Flood — biroz kutamiz
                    await asyncio.sleep(3)
                continue

            # Bazaga qo'shish
            saved, save_reason = await db.add_chat(uid, group)
            if saved:
                added.append(group)
                existing.add(group)
            elif save_reason == "duplicate":
                duplicates.append(group)
            else:
                errors.append(f"{group} (saqlashda xato)")

            # Har 5 guruhda progress
            if progress_fn and i % 5 == 0:
                with contextlib.suppress(Exception):
                    await progress_fn(i, added, duplicates, errors)
    finally:
        with contextlib.suppress(Exception):
            await client.disconnect()

    return added, duplicates, errors, None


async def check_group_access(session_str: str, group: str) -> tuple[bool, str]:
    """
    Bitta guruhni yangi client bilan tekshiradi.

    ⚠️ Ko'p guruh tekshirish uchun add_groups_for() ni ishlating —
    u bitta client bilan batch qilib tekshiradi (tezkor va xavfsizroq).
    """
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        if not await client.is_user_authorized():
            return False, "yaroqsiz sessiya"
        return await verify_group(client, group)
    except FloodWaitError:
        return False, "flood"
    except Exception as e:
        log(f"check_group_access {group}: {type(e).__name__}: {e}", "warning")
        return False, "xato"
    finally:
        with contextlib.suppress(Exception):
            await client.disconnect()


# ─────────────────────────────────────────────────────────────────────────
# GURUHLAR RO'YXATI
# ─────────────────────────────────────────────────────────────────────────
async def show_groups(update: Update) -> None:
    """Guruhlar ro'yxatini ko'rsatish."""
    uid = update.effective_user.id
    chats = await db.get_chats(uid)

    user = await db.get_user(uid)
    running = bool(user and user.get("running")) if user else False

    if not chats:
        await update.message.reply_text(
            T.GROUPS_EMPTY,
            reply_markup=KB.kb_main(running=running),
        )
        return

    await update.message.reply_text(T.groups_list(chats))


# ─────────────────────────────────────────────────────────────────────────
# GURUH QO'SHISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_groups(update: Update) -> None:
    """➕ Guruh qo'shish tugmasi bosilganda."""
    import time

    uid = update.effective_user.id
    from bot.login import user_states

    user_states[uid] = {"step": "add_group", "ts": time.time()}
    await update.message.reply_text(T.ASK_ADD_GROUP)


# ─────────────────────────────────────────────────────────────────────────
# GURUH QO'SHISH — BULK
# ─────────────────────────────────────────────────────────────────────────
async def handle_add_groups(update: Update, text: str) -> None:
    """
    Foydalanuvchi bir yoki bir nechta guruh yuboradi.
    Butun batch bitta client bilan tekshiriladi.
    """
    from bot.login import user_states

    uid = update.effective_user.id
    user_states.pop(uid, None)

    # Qatorlarni ajratish
    groups = parse_group_lines(text)
    if not groups:
        await update.message.reply_text(
            "❌ Guruh topilmadi. Qaytadan yuboring:",
        )
        return

    # Natija xabari
    msg = await update.message.reply_text(
        f"⏳ {len(groups)} ta guruh tekshirilmoqda...\n"
        "Bu bir necha daqiqa olishi mumkin."
    )

    async def _progress(
        i: int, added: list[str], duplicates: list[str], errors: list[str]
    ) -> None:
        await msg.edit_text(
            f"⏳ {i}/{len(groups)} tekshirildi...\n"
            f"✅ {len(added)} | ⚠️ {len(duplicates)} | ❌ {len(errors)}"
        )

    added, duplicates, errors, fatal = await add_groups_for(
        uid, groups, progress_fn=_progress
    )

    # Fatal — sessiya muammosi
    if fatal:
        with contextlib.suppress(Exception):
            await msg.edit_text(
                f"❌ {fatal}",
                reply_markup=KB.kb_login(),
            )
        return

    # Yakuniy natija
    report = T.groups_added_report(added, duplicates, errors)
    with contextlib.suppress(Exception):
        await msg.edit_text(report)

    log(f"📊 Guruhlar: {uid} → +{len(added)} (⚠️{len(duplicates)} ❌{len(errors)})")


# ─────────────────────────────────────────────────────────────────────────
# GURUH O'CHIRISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_delete_groups(update: Update) -> None:
    """➖ Guruh o'chirish tugmasi bosilganda."""
    uid = update.effective_user.id
    chats = await db.get_chats(uid)

    if not chats:
        await update.message.reply_text(T.GROUPS_EMPTY)
        return

    await update.message.reply_text(
        T.ASK_DEL_GROUP,
        reply_markup=KB.kb_groups_delete(chats),
      )
