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
from core.utils import parse_group_lines, truncate


# ─────────────────────────────────────────────────────────────────────────
# GURUHNI TEKSHIRISH (Telegram orqali)
# ─────────────────────────────────────────────────────────────────────────
async def check_group_access(session_str: str, group: str) -> tuple[bool, str]:
    """
    Guruhga kirish imkonini tekshiradi.

    Returns:
        (True, 'ok')           — muvaffaqiyat
        (False, 'not_found')   — topilmadi
        (False, 'private')     — yopiq
        (False, 'invalid')     — noto'g'ri format
        (False, 'flood')       — FloodWait
        (False, 'error')       — boshqa xatolik
    """
    client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)

        if not await client.is_user_authorized():
            return False, "invalid"

        # Entity'ni olish
        if group.startswith("@"):
            entity = await client.get_entity(group)
        elif group.lstrip("-").isdigit():
            entity = await client.get_entity(int(group))
        elif group.startswith("https://t.me/") or group.startswith("t.me/"):
            entity = await client.get_entity(group)
        else:
            entity = await client.get_entity(group)

        # Yozish huquqini tekshirish
        try:
            await client.get_permissions(entity, "me")
        except Exception:
            pass

        return True, "ok"

    except (UsernameNotOccupiedError, UsernameInvalidError, PeerIdInvalidError):
        return False, "not_found"
    except ChannelPrivateError:
        return False, "private"
    except FloodWaitError:
        return False, "flood"
    except ValueError:
        return False, "invalid"
    except Exception as e:
        log(f"check_group_access {group}: {type(e).__name__}: {e}", "warning")
        return False, "error"
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

    if not chats:
        await update.message.reply_text(
            T.GROUPS_EMPTY,
            reply_markup=KB.kb_main(
                running=await db.get_user(uid) and (await db.get_user(uid)).get("running"),
            ),
        )
        return

    await update.message.reply_text(T.groups_list(chats))


# ─────────────────────────────────────────────────────────────────────────
# GURUH QO'SHISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_groups(update: Update) -> None:
    """➕ Guruh qo'shish tugmasi bosilganda."""
    uid = update.effective_user.id
    from bot.login import user_states

    user_states[uid] = {"step": "add_group", "ts": __import__("time").time()}
    await update.message.reply_text(T.ASK_ADD_GROUP)
  

# ─────────────────────────────────────────────────────────────────────────
# GURUH QO'SHISH — BULK
# ─────────────────────────────────────────────────────────────────────────
async def handle_add_groups(update: Update, text: str) -> None:
    """
    Foydalanuvchi bir yoki bir nechta guruh yuboradi.
    Har birini tekshirib, natijani ko'rsatamiz.
    """
    from bot.login import user_states

    uid = update.effective_user.id
    user_states.pop(uid, None)

    # Sessiyani olish
    session = await db.get_session(uid)
    if not session:
        await update.message.reply_text(
            "❌ Sessiya topilmadi. Qaytadan 🔑 Login qiling.",
            reply_markup=KB.kb_login(),
        )
        return

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

    added: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = []
    existing = set(await db.get_chats(uid))

    # Har bir guruhni tekshirish
    for i, group in enumerate(groups, 1):
        # Takroriy?
        if group in existing:
            duplicates.append(group)
            continue

        # Telegram'da tekshirish
        ok, reason = await check_group_access(session, group)

        if not ok:
            if reason == "flood":
                errors.append(f"{group} (FloodWait)")
                # Flood — biroz kutamiz
                await asyncio.sleep(3)
            elif reason == "not_found":
                errors.append(f"{group} (topilmadi)")
            elif reason == "private":
                errors.append(f"{group} (yopiq)")
            else:
                errors.append(f"{group} (xato)")
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

        # Har 5 guruhda progress yangilash
        if i % 5 == 0:
            with contextlib.suppress(Exception):
                await msg.edit_text(
                    f"⏳ {i}/{len(groups)} tekshirildi...\n"
                    f"✅ {len(added)} | ⚠️ {len(duplicates)} | ❌ {len(errors)}"
                )

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
