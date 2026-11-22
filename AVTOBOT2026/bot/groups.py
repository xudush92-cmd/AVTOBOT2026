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
import random  # noqa: F401 — eski testlar `G.random` ni patch qiladi
import time

from telegram import Update
from telethon import TelegramClient, utils
from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    PeerIdInvalidError,
    SlowModeWaitError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
    UserNotParticipantError,
)
from telethon.sessions import StringSession
from telethon.tl import types
from telethon.tl.functions.messages import CheckChatInviteRequest

from bot import discover_sessions
from bot import keyboards as KB
from bot import my_groups as MY_GROUPS
from bot import texts as T
from bot.discover_sessions import (
    GROUPS_PAGE_SIZE,
    DiscoveredGroup,
)
from config.config import API_HASH, API_ID
from config.config import (
    DISCOVER_BATCH_PAUSE_S as CONFIG_DISCOVER_BATCH_PAUSE_S,
)
from config.config import DISCOVER_BATCH_SIZE as CONFIG_DISCOVER_BATCH_SIZE
from config.config import (
    DISCOVER_PERMISSION_TIMEOUT_S as CONFIG_DISCOVER_PERMISSION_TIMEOUT_S,
)
from config.config import (
    DISCOVER_PROGRESS_EVERY as CONFIG_DISCOVER_PROGRESS_EVERY,
)
from core import database as db
from core.errlog import log_gap
from core.logger import log
from core.utils import (
    group_reference_key,
    normalize_group_reference,
    parse_group_lines_with_errors,
    reply_text_safe,
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


def _dialog_title(entity, dialog=None) -> str:
    """Dialog nomini oladi (guruh nomi)."""
    for source in (entity, dialog):
        if source is None:
            continue
        title = getattr(source, "title", None)
        if title:
            return str(title)
        name = getattr(source, "name", None)
        if name:
            return str(name)
    return ""


def _dialog_members(entity) -> int:
    """Guruh a'zolarining taxminiy soni."""
    for attr in ("participants_count", "count"):
        value = getattr(entity, attr, None)
        if isinstance(value, int) and value > 0:
            return value
    return 0


def _is_megagroup(entity) -> bool:
    """Megaguruh (supergroup) yoki oddiy guruh emas."""
    return bool(getattr(entity, "megagroup", False))


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
    except SlowModeWaitError:
        # Guruh sekin rejimda — bu yuborish xatosi, o'qish xatosi emas.
        # Sabab "flood" emas, chunki Flood butun akkauntni bloklaydi.
        return False, "slow_mode"
    except TimeoutError:
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
        from bot import my_groups as MG

        await MG.render_groups_inline(update, uid)
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
        # Orqaga — yangi inline "💬 Guruhlar" oynasi (eski menyu emas).
        from bot import my_groups as MG

        await MG.render_groups_inline(update, uid, edit=True)
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
        from bot import my_groups as MG

        await MG.render_groups_inline(update, uid)
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
            reply_markup=(
                await KB.kb_main_for(uid) if index == len(chunks) - 1 else None
            ),
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
    # Natija allaqachon `msg` da ko'rsatildi — asosiy menyuni qaytaramiz.
    # ``kb_main()`` rolsiz variant ishlatiladi: bu oqimda baza bilan
    # qo'shimcha so'rov kerak emas.
    await update.message.reply_text(
        "💬 Guruhlar",
        reply_markup=KB.kb_main(),
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
        T.groups_delete_text(groups),
        reply_markup=KB.kb_groups_delete(groups),
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHLARNI AVTOMATIK TOPISH (akkaunt dialoglaridan)
# ─────────────────────────────────────────────────────────────────────────
# Bitta skanerlashda ko'rib chiqiladigan dialoglarning xavfsiz chegarasi.
DISCOVER_MAX_DIALOGS = 500
# Har bir guruhning yozish huquqini tekshirish uchun ketadigan maksimal vaqt.
DISCOVER_PERMISSION_TIMEOUT_S = CONFIG_DISCOVER_PERMISSION_TIMEOUT_S
# Har bitta guruh tekshiruvi orasidagi tasodifiy pauza (odam tezligiga taqlid).
DISCOVER_PAUSE_MIN_S = 0.05
DISCOVER_PAUSE_MAX_S = 0.25
# Bir vaqtda (parallel) tekshiriladigan guruhlar soni — skanerni tezlashtiradi.
DISCOVER_BATCH_SIZE = CONFIG_DISCOVER_BATCH_SIZE
# Batch'lar orasidagi pauza — Telegram'ga "odam tezligi" signalini beradi.
DISCOVER_BATCH_PAUSE_S = CONFIG_DISCOVER_BATCH_PAUSE_S
# Progress xabari qancha guruhdan keyin yangilanadi.
DISCOVER_PROGRESS_EVERY = CONFIG_DISCOVER_PROGRESS_EVERY
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


class _StaticClientContext:
    """Tayyor client'ni context manager sifatida beradi.

    ``pool.acquire`` yo'li (testlar/eski pool) uchun ishlatiladi —
    ``isolated_client`` mavjud bo'lsa u afzal ko'riladi.
    """

    __slots__ = ("client",)

    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *_exc_info) -> bool:
        return False


async def discover_groups(update: Update) -> None:
    """🔍 Guruhlarni topish — ro'yxat ko'rsatadi, hech narsa avtomatik qo'shilmaydi.

    Qo'lda havola yuborish o'rniga bot ulangan Telegram sessiyasi orqali barcha
    dialoglarni ko'rib chiqadi va yozish huquqi bor guruh/megaguruplarni
    **topadi**. Lekin ular **hech qachon avtomatik qo'shilmaydi** — topilgan
    guruhlar ro'yxat qilib ko'rsatiladi va foydalanuvchi keraklilarini
    qo'lda ✅ belgilaydi.

    Broadcast kanallar (obuna kanallari) siyosat bo'yicha umuman ko'rsatilmaydi.
    Takrorlar va huquqsizlar o'tkazib yuboriladi.

    Anti-spam himoyasi:
    - har guruh tekshiruvi orasida 1–3 soniyali tasodifiy pauza;
    - har foydalanuvchi uchun 10 daqiqalik cooldown;
    - Telegram FloodWait bersa, ko'rsatilgan vaqtgacha skaner bloklanadi;
    - bir vaqtda bitta foydalanuvchi uchun faqat bitta skaner ishlaydi.
    """
    uid = update.effective_user.id
    session = await db.get_session(uid)
    if not session:
        # Bu oyna inline tugma («🔍 Guruhlarni topish») orqali ochiladi —
        # `update.message` mavjud bo'lmasligi mumkin, shuning uchun
        # `reply_text_safe` ishlatiladi.
        log_gap(uid, "Telegram sessiyasi yo'q — skanerlash mumkin emas")
        await reply_text_safe(
            update,
            T.DISCOVER_NO_SESSION,
            reply_markup=KB.kb_login(),
        )
        return

    now = time.time()

    # 1) Telegramning FloodWait kutish vaqti tugamagan bo'lsa — to'xtatamiz.
    flood_until = _flood_wait_until.get(uid, 0)
    if flood_until > now:
        wait_s = int(flood_until - now)
        log_gap(uid, f"FloodWait — skanerlash {wait_s}s bloklandi")
        await reply_text_safe(
            update,
            T.discover_flood_wait_text(wait_s),
        )
        return

    # 2) Cooldown: oldingi skanerga hali vaqt bo'lmagan bo'lsa — ruxsat yo'q.
    last_ts = _last_discover_ts.get(uid, 0)
    if last_ts and now - last_ts < DISCOVER_COOLDOWN_S:
        wait_min = max(1, int((DISCOVER_COOLDOWN_S - (now - last_ts)) / 60) + 1)
        log_gap(uid, f"Cooldown — skanerlash {wait_min} daqiqa kutmoqda")
        await reply_text_safe(
            update,
            T.discover_cooldown_text(wait_min),
        )
        return

    # 3) Bir vaqtda bitta skaner — ikkinchisi bosilmaydi.
    if uid in _discover_running:
        log_gap(uid, "Skanerlash allaqachon ishlab turibdi")
        await reply_text_safe(update, T.DISCOVER_ALREADY_RUNNING)
        return

    from worker import worker as W
    from worker.client_pool import PoolBusyError, SessionInvalidError

    pool = W.client_pool
    if pool is None:
        await reply_text_safe(update, T.GENERIC_ERROR)
        return

    # Status xabari — inline kontekstda ham kerak (guruhlar tugmasi).
    status_msg = await reply_text_safe(update, T.DISCOVER_START, want_message=True)

    async def _status_edit(
        text: str, markup=None, *, parse_mode: str | None = None
    ) -> None:
        """Status xabarini tahrirlaydi (yuborilmagan bo'lsa — jim)."""
        if status_msg is None:
            return
        with contextlib.suppress(Exception):
            await status_msg.edit_text(
                text, parse_mode=parse_mode, reply_markup=markup
            )

    # Skaner uchun **alohida** client olamiz (pool'dagi umumiy client emas).
    # Sabab: Telethon'da bitta client ketma-ket RPC yuboradi — skaner
    # davomida shu foydalanuvchining **posting'i** sekinlashardi yoki
    # kutib qolardi. Alohida client bilan ikkalasi parallel ishlaydi.
    client_ctx = getattr(pool, "isolated_client", None)
    if client_ctx is None:
        # Test yoki eski pool — oddiy acquire'ga qaytamiz.
        try:
            client = await pool.acquire(uid, session)
        except SessionInvalidError:
            await _status_edit(T.DISCOVER_INVALID)
            return
        except PoolBusyError:
            await _status_edit(T.DISCOVER_BUSY)
            return
        except Exception as exc:  # noqa: BLE001
            log(f"discover_groups acquire {uid}: {type(exc).__name__}", "warning")
            await _status_edit(T.GENERIC_ERROR)
            return
        release_needed = True
        # ``acquire`` natijasi — uni ham context manager sifatida ishlatamiz.
        client_ctx = _StaticClientContext(client)
    else:
        release_needed = False
        client_ctx = client_ctx(uid, session)

    # Skaner boshlandi — cooldown shu yerdan hisoblanadi (kirishda rad etilgan
    # urinishlar foydalanuvchini bloklab qo'ymasligi uchun).
    _last_discover_ts[uid] = time.time()
    _discover_running.add(uid)

    found: list[DiscoveredGroup] = []
    duplicate_count = 0
    skipped = 0
    channels_skipped = 0
    errors: list[str] = []
    scanned = 0
    flood_hit = False

    existing_keys = {
        discover_sessions.build_key(value)
        for value in await db.get_chats(uid)
    }
    existing_keys.discard("")
    seen_keys: set[str] = set()

    def _remember_flood(seconds: int) -> None:
        wait_s = max(1, int(seconds))
        _flood_wait_until[uid] = time.time() + wait_s
        errors.append(f"FloodWait ({wait_s}s)")

    async def _check_one(tg_client, me, entity) -> tuple[str | None, str]:
        """Bitta guruhning yozish huquqini tekshiradi.

        Qaytaradi: ``(rejection, reference)``. ``rejection`` — None bo'lsa
        guruh yozishga mos keladi. Xatolar ``"skip"`` yoki ``"flood"``
        shaklida qaytariladi.
        """
        reference = _dialog_reference(entity)
        try:
            permissions = await asyncio.wait_for(
                tg_client.get_permissions(entity, me),
                timeout=DISCOVER_PERMISSION_TIMEOUT_S,
            )
            rejection = _posting_rejection(entity, permissions)
        except (
            UserNotParticipantError,
            ChannelPrivateError,
            PeerIdInvalidError,
        ):
            return "skip", reference
        except TimeoutError:
            return "skip", reference
        except FloodWaitError as exc:
            log(f"discover_groups FloodWait {uid}: {exc.seconds}s", "warning")
            _remember_flood(exc.seconds)
            return "flood", reference
        except Exception as exc:  # noqa: BLE001
            log(
                f"discover_groups permission {reference}: {type(exc).__name__}",
                "warning",
            )
            return "skip", reference
        return rejection, reference

    # 1) Dialoglarni yig'ish — bu bosqich faqat lokal ma'lumot o'qiydi
    #    (tarmoq so'rovi yo'q), shuning uchun tez ishlaydi.
    candidates: list[tuple[object, object]] = []
    try:
        async with client_ctx as client:
            # Akkauntni aniqlaymiz — huquq tekshiruvi shu ma'lumotga bog'liq.
            try:
                me = await asyncio.wait_for(client.get_me(), timeout=15)
            except Exception as exc:  # noqa: BLE001
                log(f"discover_groups get_me {uid}: {type(exc).__name__}", "error")
                errors.append(type(exc).__name__)
                me = None

            try:
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
                    # Siyosat: broadcast kanallar (obuna kanallari) ko'rsatilmaydi —
                    # faqat oddiy guruhlar va megaguruplar.
                    if _is_broadcast_channel(entity):
                        channels_skipped += 1
                        continue

                    scanned += 1
                    reference = _dialog_reference(entity)
                    key = discover_sessions.build_key(reference)
                    if not key:
                        skipped += 1
                        continue
                    if key in existing_keys:
                        duplicate_count += 1
                        continue
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    candidates.append((entity, dialog))
            except FloodWaitError as exc:
                log(
                    f"discover_groups dialog FloodWait {uid}: {exc.seconds}s",
                    "warning",
                )
                _remember_flood(exc.seconds)
            except Exception as exc:  # noqa: BLE001
                log(f"discover_groups scan {uid}: {type(exc).__name__}", "error")
                errors.append(type(exc).__name__)

            # 2) Yozish huquqini tekshirish — PARALLEL batch'lar bilan.
            #    Har bir guruh uchun alohida RPC ketar edi (ketma-ket), bu esa
            #    skanerni juda uzozlashtirardi. Endi ``DISCOVER_BATCH_SIZE`` ta
            #    guruh bir vaqtda tekshiriladi.
            if me is not None and candidates:
                batch_size = max(1, DISCOVER_BATCH_SIZE)
                for start in range(0, len(candidates), batch_size):
                    batch = candidates[start : start + batch_size]
                    results = await asyncio.gather(
                        *(
                            _check_one(client, me, entity)
                            for entity, _dialog in batch
                        ),
                        return_exceptions=True,
                    )
                    for (entity, dialog), result in zip(batch, results):
                        if isinstance(result, BaseException):
                            log(
                                f"discover_groups batch {uid}: "
                                f"{type(result).__name__}",
                                "warning",
                            )
                            skipped += 1
                            continue
                        rejection, reference = result
                        if rejection == "flood":
                            flood_hit = True
                            break
                        if rejection == "skip" or rejection:
                            skipped += 1
                            continue
                        # ✅ Guruh yozishga mos keldi.
                        found.append(
                            DiscoveredGroup(
                                reference=reference,
                                title=_dialog_title(entity, dialog),
                                members=_dialog_members(entity),
                                kind=(
                                    "megaguruh"
                                    if _is_megagroup(entity)
                                    else "guruh"
                                ),
                                key=discover_sessions.build_key(reference),
                            )
                        )
                    if flood_hit:
                        break
                    # Progress — foydalanuvchi kutayotganini bilishi uchun.
                    done = start + len(batch)
                    if (
                        done % DISCOVER_PROGRESS_EVERY < batch_size
                        or done >= len(candidates)
                    ):
                        await _status_edit(
                            T.discover_progress(scanned, len(found))
                        )
                    # Anti-spam: batch'lar orasida qisqa pauza.
                    if DISCOVER_BATCH_PAUSE_S > 0:
                        await asyncio.sleep(DISCOVER_BATCH_PAUSE_S)
    except SessionInvalidError:
        await _status_edit(T.DISCOVER_INVALID)
        return
    except PoolBusyError:
        await _status_edit(T.DISCOVER_BUSY)
        return
    except Exception as exc:  # noqa: BLE001
        log(f"discover_groups scan {uid}: {type(exc).__name__}", "warning")
        errors.append(type(exc).__name__)
    finally:
        _discover_running.discard(uid)
        if release_needed:
            await pool.release(uid)

    # Hech narsa qo'shilmedi — endi tanlov sessiyasini boshlaymiz.
    selection = discover_sessions.start_session(uid, found)

    if not found:
        await _status_edit(T.DISCOVER_PICK_EMPTY)
        from bot.menu import show_home

        await show_home(update, uid)
        log(
            f"🔍 Guruh topish: {uid} — topilmadi "
            f"(o'tkazildi {skipped}, kanal {channels_skipped}, xato {len(errors)})"
        )
        return

    # Ro'yxatni bir xabarda ko'rsatamiz — «qidirilmoqda» xabari almashtiriladi.
    # Ro'yxatni **status xabarining o'zida** ko'rsatamiz — yangi xabar
    # yubormaymiz (eski «qidirilmoqda» xabari qolib ketmasin).
    await _render_discover_list(update, status_msg, uid, selection, page=0, edit=True)
    log(
        f"🔍 Guruh topish: {uid} — {len(found)} ta topildi, "
        f"tanlov kutilmoqda (takror {duplicate_count}, o'tkazildi {skipped}, "
        f"kanal {channels_skipped}, xato {len(errors)})"
    )


def _discover_header(selection, page: int, pages: int) -> str:
    """Ro'yxat xabari matni — sarlavha + shu sahifaning havolalari.

    Havolalar xabar matnida ko'rsatiladi (tugma matni 64 belgi bilan
    cheklangan, shuning uchun u yerda sig'maydi). Foydalanuvchi shu
    yerda to'g'ridan-to'g'ri guruhga o'ta oladi.
    """
    header = T.DISCOVER_PICK_HEADER.format(
        total=len(selection.groups),
        page=page + 1,
        pages=pages,
        selected=len(selection.selected),
    )
    links = [
        group.display_detail()
        for group in selection.page_groups(page, GROUPS_PAGE_SIZE)
        if group.link()
    ]
    if links:
        header += T.DISCOVER_PICK_LINKS.format(links="\n".join(links))
    return header


async def _render_discover_list(
    update: Update,
    message,
    uid: int,
    selection,
    page: int = 0,
    edit: bool = False,
) -> None:
    """Topilgan guruhlar ro'yxatini ko'rsatadi (sahifalash bilan).

    ``edit=True`` — mavjud xabar tahrirlanadi (inline callback dan).
    Aks holda yangi xabar yuboriladi.
    """
    pages = selection.page_count(GROUPS_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    groups = selection.page_groups(page, GROUPS_PAGE_SIZE)
    header = _discover_header(selection, page, pages)
    markup = KB.kb_discover_groups(
        groups,
        selection.selected,
        page=page,
        page_size=GROUPS_PAGE_SIZE,
        total=len(selection.groups),
        pages=pages,
    )
    if edit and message is not None:
        with contextlib.suppress(Exception):
            await message.edit_text(header, parse_mode="HTML", reply_markup=markup)
            return
    # Inline kontekstda `update.message` mavjud bo'lmasligi mumkin.
    await reply_text_safe(
        update,
        header,
        reply_markup=markup,
        parse_mode="HTML",
    )


async def handle_discover_callback(update: Update, uid: int, data: str) -> None:
    """Guruh tanlash inline callback'lari."""
    q = update.callback_query
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "noop":
        await q.answer()
        return

    selection = discover_sessions.get_session(uid)
    if selection is None:
        await q.answer(T.DISCOVER_PICK_EXPIRED, show_alert=True)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                T.DISCOVER_PICK_EXPIRED,
                reply_markup=await KB.kb_main_for(uid),
            )
        return

    if action == "toggle":
        try:
            index = int(parts[2])
        except (ValueError, IndexError):
            return
        if index < 0 or index >= len(selection.groups):
            await q.answer("Bu guruh topilmadi", show_alert=True)
            log_gap(uid, "Guruh topilmadi yoki o'chirilgan", action=data)
            return
        group = selection.groups[index]
        now_selected = selection.toggle(group.key)
        await q.answer(
            f"{'✅ Tanlandi' if now_selected else '⬜ Bekor qilindi'}: "
            f"{group.title or group.reference}",
            show_alert=True,
        )
        await _render_discover_list(
            update, q.message, uid, selection, page=index // GROUPS_PAGE_SIZE, edit=True
        )
        return

    if action == "page":
        try:
            page = int(parts[2])
        except (ValueError, IndexError):
            return
        await q.answer()
        await _render_discover_list(
            update, q.message, uid, selection, page=page, edit=True
        )
        return

    if action == "cancel":
        discover_sessions.clear_session(uid)
        await q.answer("Bekor qilindi")
        # ✅ Xabar to'liq o'chiriladi — eskirgan oyna qolmasligi kerak.
        # Agar o'chirish imkoni bo'lmasa (masalan, eskirgan xabar),
        # hech qanday "Bekor qilindi" qoldirmay o'zgartirish ham yo'q —
        # foydalanuvchi uchun toza yopilish.
        deleted = False
        with contextlib.suppress(Exception):
            await q.delete_message()
            deleted = True
        if not deleted:
            with contextlib.suppress(Exception):
                await q.edit_message_reply_markup(reply_markup=None)
        return

    if action == "apply":
        selected = selection.selected_groups()
        if not selected:
            await q.answer(T.DISCOVER_APPLY_NONE, show_alert=True)
            return

        added: list[str] = []
        duplicates = 0
        skipped = 0
        limit_hit = False
        limits = await db.get_limits(uid)
        max_groups = int(limits.get("max_groups") or 0)

        for group in selected:
            saved, reason = await db.add_chat(uid, group.reference)
            if saved:
                added.append(group.reference)
            elif reason == "duplicate":
                duplicates += 1
            elif reason == "limit":
                limit_hit = True
                break
            else:
                skipped += 1

        discover_sessions.clear_session(uid)

        limits = await db.get_limits(uid)
        max_groups = int(limits.get("max_groups") or 0)
        report = T.DISCOVER_APPLY_HEADER.format(
            added=len(added),
            duplicates=duplicates,
            skipped=skipped,
        )
        if limit_hit:
            report += T.DISCOVER_LIMIT_HIT.format(limit=max_groups)
        await q.answer(
            f"✅ {len(added)} ta guruh qo'shildi",
            show_alert=True,
        )

        # ✅ Qo'shilgan guruhlar foydalanuvchiga darhol ko'rinishi kerak —
        # shuning uchun hisobot va yangilangan «💬 Guruhlar» oynasi
        # bir xil xabarda chiqadi.
        try:
            groups_text, groups_markup = await MY_GROUPS.build_groups_window(
                uid, note=report
            )
        except Exception as exc:  # noqa: BLE001 — himoya
            log(
                f"discover_groups apply window xatosi: {uid} "
                f"({type(exc).__name__})",
                "warning",
            )
            groups_text, groups_markup = None, None

        shown = False
        if groups_text:
            # Birinchi urinish — skaner xabarini shu oyna bilan almashtirish.
            with contextlib.suppress(Exception):
                await q.edit_message_text(
                    groups_text,
                    parse_mode="HTML",
                    reply_markup=groups_markup,
                )
                shown = True
            if not shown:
                # Xabar tahrirlab bo'lmasa (eskirgan/klaviyurasiz) —
                # yangi xabar yuboramiz, shunda foydalanuvchi guruhlarini
                # ko'ra oladi.
                with contextlib.suppress(Exception):
                    await q.message.reply_text(
                        groups_text,
                        parse_mode="HTML",
                        reply_markup=groups_markup,
                    )
                    shown = True

        if not shown:
            # Hisobotni ko'rsatishning oxirgi urinishlari.
            with contextlib.suppress(Exception):
                await q.edit_message_text(
                    report,
                    parse_mode="HTML",
                    reply_markup=await KB.kb_main_for(uid),
                )
            with contextlib.suppress(Exception):
                await q.message.reply_text(
                    report,
                    parse_mode="HTML",
                    reply_markup=await KB.kb_main_for(uid),
                )
        log(
            f"✅ Tanlangan guruhlar qo'shildi: {uid} → +{len(added)} "
            f"(takror {duplicates}, o'tkazildi {skipped})"
        )
        return
