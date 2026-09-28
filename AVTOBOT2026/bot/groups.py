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

from telegram import Update
from telethon import TelegramClient, utils
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    PeerIdInvalidError,
    UserNotParticipantError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession
from telethon.tl import types
from telethon.tl.functions.messages import CheckChatInviteRequest

from bot import keyboards as KB
from bot import texts as T
from config.config import API_HASH, API_ID
from core import database as db
from core.logger import log
from core.utils import group_reference_key, normalize_group_reference, parse_group_lines


# ─────────────────────────────────────────────────────────────────────────
# GURUHNI TOPISH VA TEKSHIRISH (Telegram orqali)
# ─────────────────────────────────────────────────────────────────────────
class GroupResolveError(ValueError):
    """Guruh reference'i nima sababdan ishlamaganini saqlaydi."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


_REASON_TEXT = {
    "not_found": "topilmadi",
    "not_member": "akkaunt avval guruhga kirishi kerak",
    "private": "yopiq yoki kirish taqiqlangan",
    "invalid": "noto'g'ri havola",
    "not_group": "bu guruh yoki kanal emas",
    "no_write": "yozish huquqi yo'q",
    "unauthorized": "Telegram sessiyasi yaroqsiz",
    "flood": "Telegram vaqtincha chekladi (FloodWait)",
    "timeout": "Telegram javobi kechikdi",
    "error": "Telegram tekshiruvida xato",
}


def group_reason_text(reason: str) -> str:
    return _REASON_TEXT.get(reason, _REASON_TEXT["error"])


def _is_group_entity(entity) -> bool:
    return isinstance(
        entity,
        (types.Chat, types.Channel, types.ChatForbidden, types.ChannelForbidden),
    )


def _message_sending_is_banned(rights) -> bool:
    """Telegram ChatBannedRights matn yuborishni taqiqlaganini tekshiradi."""
    return bool(
        rights
        and (
            getattr(rights, "send_messages", False)
            or getattr(rights, "send_plain", False)
        )
    )


def _posting_rejection(entity, permissions) -> str | None:
    """Participant va chat huquqlaridan membership/posting xulosasini oladi."""
    if not permissions or bool(getattr(permissions, "has_left", False)):
        return "not_member"

    participant = getattr(permissions, "participant", None)
    participant_rights = getattr(participant, "banned_rights", None)
    if bool(getattr(participant, "left", False)) or bool(
        getattr(participant_rights, "view_messages", False)
    ):
        return "not_member"

    is_creator = bool(getattr(permissions, "is_creator", False))
    is_admin = bool(getattr(permissions, "is_admin", False) or is_creator)
    if bool(getattr(entity, "broadcast", False)):
        can_post = bool(getattr(permissions, "post_messages", False))
        return None if is_creator or can_post else "no_write"

    if is_admin:
        return None

    # ParticipantPermissions'da send_messages property yo'q; haqiqiy taqiq raw
    # participant/entity ChatBannedRights ichida bo'ladi. Birinchi tekshiruv eski
    # yoki mock permission obyektlari bilan ham moslikni saqlaydi.
    if getattr(permissions, "send_messages", None) is False:
        return "no_write"
    if bool(getattr(permissions, "is_banned", False)) and not participant_rights:
        return "no_write"
    if any(
        _message_sending_is_banned(rights)
        for rights in (
            participant_rights,
            getattr(entity, "banned_rights", None),
            getattr(entity, "default_banned_rights", None),
        )
    ):
        return "no_write"
    return None


async def _find_joined_dialog(client: TelegramClient, target: int):
    """StringSession'da entity keshi bo'lmasa, a'zo dialoglardan ID'ni topadi."""
    try:
        entity = await client.get_entity(target)
        if _is_group_entity(entity):
            return entity
    except (ValueError, PeerIdInvalidError, ChannelPrivateError):
        pass

    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not _is_group_entity(entity):
            continue
        marked_id = utils.get_peer_id(entity)
        if dialog.id == target or marked_id == target:
            return entity
        if target > 0 and int(getattr(entity, "id", 0) or 0) == target:
            return entity
    raise GroupResolveError("not_found")


async def resolve_group_entity(client: TelegramClient, group: str):
    """Public URL, invite, post URL yoki ID'ni Telegram group entity'ga aylantiradi."""
    reference = normalize_group_reference(group)
    if not reference:
        raise GroupResolveError("invalid")

    if reference.startswith("https://t.me/+"):
        invite_hash = reference.rsplit("+", 1)[-1]
        if not invite_hash:
            raise GroupResolveError("invalid")
        try:
            invite = await client(CheckChatInviteRequest(invite_hash))
        except (InviteHashExpiredError, InviteHashInvalidError) as exc:
            raise GroupResolveError("invalid") from exc
        if not isinstance(invite, types.ChatInviteAlready):
            raise GroupResolveError("not_member")
        entity = invite.chat
    elif reference.lstrip("-").isdigit():
        entity = await _find_joined_dialog(client, int(reference))
    elif reference.startswith("@"):
        try:
            entity = await client.get_entity(reference)
        except ValueError as exc:
            raise GroupResolveError("not_found") from exc
    else:
        raise GroupResolveError("invalid")

    if not _is_group_entity(entity):
        raise GroupResolveError("not_group")
    if isinstance(entity, (types.ChatForbidden, types.ChannelForbidden)) or bool(
        getattr(entity, "deactivated", False)
    ):
        raise GroupResolveError("private")
    return entity


async def check_group_access(session_str: str, group: str) -> tuple[bool, str]:
    """Ulangan akkaunt guruhga a'zo va yozish huquqiga ega ekanini tekshiradi."""
    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)

        authorized = await asyncio.wait_for(client.is_user_authorized(), timeout=15)
        if not authorized:
            return False, "unauthorized"

        entity = await asyncio.wait_for(resolve_group_entity(client, group), timeout=30)
        if bool(getattr(entity, "left", False)):
            return False, "not_member"

        me = await asyncio.wait_for(client.get_me(), timeout=15)
        try:
            permissions = await asyncio.wait_for(
                client.get_permissions(entity, me), timeout=20
            )
        except UserNotParticipantError:
            return False, "not_member"

        rejection = _posting_rejection(entity, permissions)
        return (False, rejection) if rejection else (True, "ok")

    except GroupResolveError as exc:
        return False, exc.reason
    except (UsernameNotOccupiedError, UsernameInvalidError, PeerIdInvalidError):
        return False, "not_found"
    except UserNotParticipantError:
        return False, "not_member"
    except ChannelPrivateError:
        return False, "private"
    except (InviteHashExpiredError, InviteHashInvalidError):
        return False, "invalid"
    except FloodWaitError:
        return False, "flood"
    except (asyncio.TimeoutError, TimeoutError):
        return False, "timeout"
    except ValueError:
        return False, "invalid"
    except Exception as exc:
        log(f"check_group_access {group}: {type(exc).__name__}", "warning")
        return False, "error"
    finally:
        if client:
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
            reply_markup=KB.kb_groups_menu(),
        )
        return

    lines = [f"💬 GURUHLAR ({len(chats)} ta):"] + [
        f"{index}. {chat}" for index, chat in enumerate(chats, 1)
    ]
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 3800:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    for index, chunk in enumerate(chunks):
        await update.message.reply_text(
            chunk,
            reply_markup=(KB.kb_groups_menu() if index == len(chunks) - 1 else None),
        )


# ─────────────────────────────────────────────────────────────────────────
# GURUH QO'SHISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_groups(update: Update) -> None:
    """➕ Guruh qo'shish tugmasi bosilganda."""
    uid = update.effective_user.id
    from bot.login import user_states

    user_states[uid] = {"step": "add_group", "ts": __import__("time").time()}
    await update.message.reply_text(
        T.ASK_ADD_GROUP,
        reply_markup=KB.kb_input_cancel(),
    )


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

    # Sessiyani olish
    session = await db.get_session(uid)
    if not session:
        user_states.pop(uid, None)
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
            reply_markup=KB.kb_input_cancel(),
        )
        return

    user_states.pop(uid, None)

    # Natija xabari
    msg = await update.message.reply_text(
        f"⏳ {len(groups)} ta guruh tekshirilmoqda...\n"
        "Bu bir necha daqiqa olishi mumkin."
    )

    added: list[str] = []
    duplicates: list[str] = []
    errors: list[str] = []
    existing = {group_reference_key(value) for value in await db.get_chats(uid)}

    # Har bir guruhni tekshirish
    for i, group in enumerate(groups, 1):
        # Bir guruh URL va @username bilan qayta qo'shilmasin.
        group_key = group_reference_key(group)
        if group_key in existing:
            duplicates.append(group)
            continue

        # Telegram'da tekshirish
        ok, reason = await check_group_access(session, group)

        if not ok:
            errors.append(f"{group} ({group_reason_text(reason)})")
            if reason == "flood":
                await asyncio.sleep(3)
            continue

        # Bazaga canonical ko'rinishda qo'shish
        saved, save_reason = await db.add_chat(uid, group)
        if saved:
            added.append(group)
            existing.add(group_key)
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
    await update.message.reply_text(
        "💬 Guruhlar menyusi",
        reply_markup=KB.kb_groups_menu(),
    )

    log(f"📊 Guruhlar: {uid} → +{len(added)} (⚠️{len(duplicates)} ❌{len(errors)})")


# ─────────────────────────────────────────────────────────────────────────
# GURUH O'CHIRISH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_delete_groups(update: Update) -> None:
    """➖ Guruh o'chirish tugmasi bosilganda."""
    uid = update.effective_user.id
    groups = await db.get_chat_records(uid)

    if not groups:
        await update.message.reply_text(T.GROUPS_EMPTY)
        return

    await update.message.reply_text(
        T.ASK_DEL_GROUP,
        reply_markup=KB.kb_groups_delete(groups),
    )
