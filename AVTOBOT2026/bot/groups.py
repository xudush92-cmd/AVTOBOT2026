"""
Guruhlar bilan ishlash.

Funksiyalar:
- Bulk qo'shish (bir nechta guruhni bir marta)
- O'chirish
- Ro'yxatni ko'rsatish
- Qo'shishda faqat formatni tekshirish; postingda Telegram entity'ni topish
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time

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
from core.utils import (
    group_reference_key,
    normalize_group_reference,
    parse_group_lines_with_errors,
)


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

        # is_user_authorized() FloodWait'ni ham False ga aylantiradi.
        me = await asyncio.wait_for(client.get_me(), timeout=15)
        if me is None:
            return False, "unauthorized"

        entity = await asyncio.wait_for(resolve_group_entity(client, group), timeout=30)
        if bool(getattr(entity, "left", False)):
            return False, "not_member"

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
# GURUHLARNI TEKSHIRISH (a'zolik + yozish huquqi)
# ─────────────────────────────────────────────────────────────────────────
async def check_one_group(uid: int, group_id: int) -> tuple[str, bool, str]:
    """Bitta guruhni Telegram orqali tekshiradi (post yuborilmaydi).

    Returns:
        (guruh_qiymati, mumkinmi, sabab_kodi)
    """
    record = await db.get_chat_record(uid, group_id)
    if not record:
        return "", False, "not_found"
    value = str(record["value"])
    session = await db.get_session(uid)
    if not session:
        return value, False, "unauthorized"
    ok, reason = await check_group_access(session, value)
    return value, ok, reason


async def begin_check_groups(update: Update) -> None:
    """💬 Guruhlar → 🔎 Guruhni tekshirish oynasi."""
    uid = update.effective_user.id
    groups = await db.get_chat_records(uid)
    if not groups:
        await update.message.reply_text(
            T.GROUPS_EMPTY_HINT, reply_markup=KB.kb_groups_menu()
        )
        return
    await update.message.reply_text(
        T.GROUP_PICKER_CHECK,
        reply_markup=KB.kb_group_check_picker(groups, 0),
    )


async def handle_group_check_callback(
    update: Update, uid: int, data: str
) -> None:
    """``gchk:id:<group_id>:<page>`` — tanlangan guruhni tekshiradi."""
    q = update.callback_query
    parts = data.split(":")
    if len(parts) >= 2 and parts[1] == "back":
        await q.edit_message_text(
            "💬 Guruhlar menyusi", reply_markup=KB.kb_groups_menu()
        )
        return
    if len(parts) >= 3 and parts[1] == "page":
        try:
            page = max(0, int(parts[2]))
        except ValueError:
            page = 0
        groups = await db.get_chat_records(uid)
        await q.edit_message_text(
            T.GROUP_PICKER_CHECK, reply_markup=KB.kb_group_check_picker(groups, page)
        )
        return
    if len(parts) != 4 or parts[1] != "id":
        return
    try:
        group_id = int(parts[2])
        page = max(0, int(parts[3]))
    except ValueError:
        return

    await q.edit_message_text("⏳ Telegram orqali tekshirilmoqda...")
    value, ok, reason = await check_one_group(uid, group_id)
    if not value:
        await q.edit_message_text("❌ Guruh topilmadi (ro'yxatdan o'chirilgan).")
        return

    groups = await db.get_chat_records(uid)
    await q.edit_message_text(
        T.group_check_result(value, ok, reason),
        reply_markup=KB.kb_group_check_picker(groups, page),
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHLAR RO'YXATI
# ─────────────────────────────────────────────────────────────────────────
async def show_groups(update: Update) -> None:
    """Guruhlar ro'yxatini ko'rsatish."""
    uid = update.effective_user.id
    chats = await db.get_chat_records(uid)

    if not chats:
        await update.message.reply_text(
            T.GROUPS_EMPTY_HINT,
            reply_markup=KB.kb_groups_menu(),
        )
        return

    global_interval = await db.get_interval(uid)
    lines = [f"💬 GURUHLAR ({len(chats)} ta):"]
    for index, group in enumerate(chats, 1):
        interval = group.get("interval_min")
        mode = (
            f"alohida {int(interval)} daq"
            if interval is not None
            else f"umumiy {global_interval} daq"
        )
        lines.append(f"{index}. {group['value']} — {mode}")
    lines.append("\n⏱ «Guruh intervali» orqali har birini alohida sozlang.")
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

    user_states[uid] = {"step": "add_group", "ts": time.time()}
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
    Faqat formatni tekshirib saqlaymiz; Telegram'ga ulanmaymiz.
    """
    from bot.login import user_states

    uid = update.effective_user.id

    # Mavjud hisob sessiyasini o'zgartirmaymiz; faqat borligini tekshiramiz.
    if not await db.get_session(uid):
        user_states.pop(uid, None)
        await update.message.reply_text(
            "❌ Sessiya topilmadi. Qaytadan 🔑 Login qiling.",
            reply_markup=KB.kb_login(),
        )
        return

    groups, invalid = parse_group_lines_with_errors(text)
    if not groups:
        await update.message.reply_text(
            "❌ Guruh topilmadi yoki formati noto'g'ri. Qaytadan yuboring:",
            reply_markup=KB.kb_input_cancel(),
        )
        return

    user_states.pop(uid, None)

    msg = await update.message.reply_text(f"⏳ {len(groups)} ta guruh saqlanmoqda...")

    added: list[str] = []
    duplicates: list[str] = []
    errors = [f"{value} (noto'g'ri format)" for value in invalid]
    existing = {group_reference_key(value) for value in await db.get_chats(uid)}

    for i, group in enumerate(groups, 1):
        # Bir guruh URL va @username bilan qayta qo'shilmasin.
        group_key = group_reference_key(group)
        if group_key in existing:
            duplicates.append(group)
            continue

        # Telegram'da hech qanday tekshiruv yo'q — faqat format va DB.
        saved, save_reason = await db.add_chat(uid, group)
        if saved:
            added.append(group)
            existing.add(group_key)
        elif save_reason == "duplicate":
            duplicates.append(group)
        elif save_reason == "limit":
            # Paket chegarasi — qolganlarini sinab ko'rishning hojati yo'q.
            limits = await db.get_limits(uid)
            errors.append(
                f"{group} (❌ {T.group_limit_message(int(limits.get('max_groups') or 0), int(limits.get('used_groups') or 0))})"
            )
            errors.extend(f"{rest} (paket chegarasi)" for rest in groups[i:])
            break
        else:
            errors.append(f"{group} (saqlashda xato)")

        # Har 5 guruhda progress yangilash
        if i % 5 == 0:
            with contextlib.suppress(Exception):
                await msg.edit_text(
                    f"⏳ {i}/{len(groups)} saqlandi...\n"
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
    """➖ Guruh o'chirish tugmasi bosilganda — ro'yxat inline tugma bo'lib chiqadi."""
    uid = update.effective_user.id
    groups = await db.get_chat_records(uid)

    if not groups:
        await update.message.reply_text(T.GROUPS_EMPTY)
        return

    await update.message.reply_text(
        T.ASK_DEL_GROUP,
        reply_markup=KB.kb_groups_delete(groups),
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHLARNI AVTOMATIK TOPISH (akkaunt dialoglaridan)
# ─────────────────────────────────────────────────────────────────────────
# Bitta skanerlashda ko'rib chiqiladigan dialoglarning xavfsiz chegarasi.
DISCOVER_MAX_DIALOGS = 500
# Har bir guruhning yozish huquqini tekshirish uchun ketadigan maksimal vaqt.
DISCOVER_PERMISSION_TIMEOUT_S = 20
# Har bitta guruh tekshiruvi orasidagi tasodifiy pauza (odam tezligiga taqlid).
DISCOVER_PAUSE_MIN_S = 1.0
DISCOVER_PAUSE_MAX_S = 3.0
# Bitta foydalanuvchi skanerni necha soniyada bir marta bosishi mumkin.
DISCOVER_COOLDOWN_S = 10 * 60

# In-memory himoya holati (restartda tozalanadi — bu qabul qilinadi, chunki
# Telegram FloodWait'i serverning o'zida ham yuritiladi).
_last_discover_ts: dict[int, float] = {}
_flood_wait_until: dict[int, float] = {}
_discover_running: set[int] = set()


def reset_discover_guards() -> None:
    """Testlar va favqulodda holatlar uchun himoya holatini tozalaydi."""
    _last_discover_ts.clear()
    _flood_wait_until.clear()
    _discover_running.clear()


def _dialog_reference(entity) -> str:
    """Topilgan entity uchun bazada saqlanadigan canonical reference."""
    username = getattr(entity, "username", None)
    if username:
        return f"@{username}"
    # Username yo'q (yopiq guruh) — marked peer ID: -100... yoki -...
    return str(utils.get_peer_id(entity))


def _is_broadcast_channel(entity) -> bool:
    """Broadcast kanal (megaguruh emas) — skanerga umuman kiritilmaydi."""
    return isinstance(entity, types.Channel) and bool(
        getattr(entity, "broadcast", False)
    )


async def discover_groups(update: Update) -> None:
    """🔍 Guruhlarni topish: akkaunt a'zo bo'lgan, yozish mumkin GURUHLARNI qo'shadi.

    Qo'lda havola yuborish o'rniga bot ulangan Telegram sessiyasi orqali barcha
    dialoglarni ko'rib chiqadi va yozish huquqi bor guruh/megaguruplarni
    avtomatik saqlaydi. Broadcast kanallar (obuna kanallari) siyosat bo'yicha
    umuman qo'shilmaydi. Takrorlar va huquqsizlar o'tkazib yuboriladi; paket
    chegarasi hurmat qilinadi.

    Anti-spam himoyasi:
    - har guruh tekshiruvi orasida 1–3 soniyali tasodifiy pauza;
    - har foydalanuvchi uchun 10 daqiqalik cooldown;
    - Telegram FloodWait bersa, ko'rsatilgan vaqtgacha skaner bloklanadi;
    - bir vaqtda bitta foydalanuvchi uchun faqat bitta skaner ishlaydi.
    """
    uid = update.effective_user.id
    session = await db.get_session(uid)
    if not session:
        await update.message.reply_text(
            T.DISCOVER_NO_SESSION,
            reply_markup=KB.kb_login(),
        )
        return

    now = time.time()

    # 1) Telegramning FloodWait kutish vaqti tugamagan bo'lsa — to'xtatamiz.
    flood_until = _flood_wait_until.get(uid, 0)
    if flood_until > now:
        wait_s = int(flood_until - now)
        await update.message.reply_text(
            T.discover_flood_wait_text(wait_s),
        )
        return

    # 2) Cooldown: oldingi skanerga hali vaqt bo'lmagan bo'lsa — ruxsat yo'q.
    last_ts = _last_discover_ts.get(uid, 0)
    if last_ts and now - last_ts < DISCOVER_COOLDOWN_S:
        wait_min = max(1, int((DISCOVER_COOLDOWN_S - (now - last_ts)) / 60) + 1)
        await update.message.reply_text(
            T.discover_cooldown_text(wait_min),
        )
        return

    # 3) Bir vaqtda bitta skaner — ikkinchisi bosilmaydi.
    if uid in _discover_running:
        await update.message.reply_text(T.DISCOVER_ALREADY_RUNNING)
        return

    from worker import worker as W
    from worker.client_pool import PoolBusyError, SessionInvalidError

    pool = W.client_pool
    if pool is None:
        await update.message.reply_text(T.GENERIC_ERROR)
        return

    status_msg = await update.message.reply_text(T.DISCOVER_START)

    try:
        client = await pool.acquire(uid, session)
    except SessionInvalidError:
        with contextlib.suppress(Exception):
            await status_msg.edit_text(T.DISCOVER_INVALID)
        return
    except PoolBusyError:
        with contextlib.suppress(Exception):
            await status_msg.edit_text(T.DISCOVER_BUSY)
        return
    except Exception as exc:  # noqa: BLE001
        log(f"discover_groups acquire {uid}: {type(exc).__name__}", "warning")
        with contextlib.suppress(Exception):
            await status_msg.edit_text(T.GENERIC_ERROR)
        return

    # Skaner boshlandi — cooldown shu yerdan hisoblanadi (kirishda rad etilgan
    # urinishlar foydalanuvchini bloklab qo'ymasligi uchun).
    _last_discover_ts[uid] = time.time()
    _discover_running.add(uid)

    added: list[str] = []
    duplicate_count = 0
    skipped = 0
    channels_skipped = 0
    errors: list[str] = []
    limit_hit = False
    scanned = 0

    existing_keys = {
        group_reference_key(value) for value in await db.get_chats(uid)
    }

    def _remember_flood(seconds: int) -> None:
        wait_s = max(1, int(seconds))
        _flood_wait_until[uid] = time.time() + wait_s
        errors.append(f"FloodWait ({wait_s}s)")

    try:
        me = await asyncio.wait_for(client.get_me(), timeout=15)
        async for dialog in client.iter_dialogs():
            if scanned >= DISCOVER_MAX_DIALOGS:
                break
            entity = dialog.entity
            if not _is_group_entity(entity):
                continue
            # Chiqib ketilgan / kirish taqiqlangan dialoglarni o'tkazamiz.
            if isinstance(
                entity, (types.ChatForbidden, types.ChannelForbidden)
            ) or bool(getattr(entity, "left", False)):
                continue
            # Siyosat: broadcast kanallar (obuna kanallari) qo'shilmaydi —
            # faqat oddiy guruhlar va megaguruplar qoladi.
            if _is_broadcast_channel(entity):
                channels_skipped += 1
                continue

            scanned += 1
            reference = _dialog_reference(entity)
            key = group_reference_key(reference)
            if key in existing_keys:
                duplicate_count += 1
                continue

            try:
                permissions = await asyncio.wait_for(
                    client.get_permissions(entity, me),
                    timeout=DISCOVER_PERMISSION_TIMEOUT_S,
                )
                rejection = _posting_rejection(entity, permissions)
            except (
                UserNotParticipantError,
                ChannelPrivateError,
                PeerIdInvalidError,
            ):
                skipped += 1
            except (asyncio.TimeoutError, TimeoutError):
                skipped += 1
            except FloodWaitError as exc:
                log(f"discover_groups FloodWait {uid}: {exc.seconds}s", "warning")
                _remember_flood(exc.seconds)
                break
            except Exception as exc:  # noqa: BLE001
                log(
                    f"discover_groups permission {reference}: {type(exc).__name__}",
                    "warning",
                )
                skipped += 1
            else:
                if rejection:
                    skipped += 1
                else:
                    saved, reason = await db.add_chat(uid, reference)
                    if saved:
                        added.append(reference)
                        existing_keys.add(key)
                    elif reason == "duplicate":
                        duplicate_count += 1
                    elif reason == "limit":
                        limit_hit = True
                        break
                    else:
                        errors.append(reference)

            if scanned % 20 == 0:
                with contextlib.suppress(Exception):
                    await status_msg.edit_text(
                        T.discover_progress(scanned, len(added))
                    )

            # Anti-spam: har bir tekshirilgan guruh orasida odamga o'xshash
            # tasodifiy pauza. FloodWait bo'lsa darhol chiqib ketamiz.
            pause = random.uniform(DISCOVER_PAUSE_MIN_S, DISCOVER_PAUSE_MAX_S)
            await asyncio.sleep(pause)
    except FloodWaitError as exc:
        log(f"discover_groups dialog FloodWait {uid}: {exc.seconds}s", "warning")
        _remember_flood(exc.seconds)
    except Exception as exc:  # noqa: BLE001
        log(f"discover_groups scan {uid}: {type(exc).__name__}", "error")
        errors.append(type(exc).__name__)
    finally:
        _discover_running.discard(uid)
        await pool.release(uid)

    limits = await db.get_limits(uid)
    max_groups = int(limits.get("max_groups") or 0)
    report = T.discover_report(
        added,
        duplicate_count,
        skipped,
        errors,
        channels_skipped=channels_skipped,
        limit_hit=limit_hit,
        limit=max_groups,
    )
    with contextlib.suppress(Exception):
        await status_msg.edit_text(report)

    from bot.menu import worker_manager

    running = bool(worker_manager and worker_manager.is_running(uid))
    await update.message.reply_text(
        "🏠 Asosiy menyu",
        reply_markup=KB.kb_main(running=running),
    )
    log(
        f"🔍 Guruh topish: {uid} → +{len(added)} "
        f"(takror {duplicate_count}, o'tkazildi {skipped}, "
        f"kanal {channels_skipped}, xato {len(errors)})"
    )
