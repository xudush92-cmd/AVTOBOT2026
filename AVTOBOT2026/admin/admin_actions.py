"""
Admin foydalanuvchi nomidan amallar.

Funksiyalar:
- User kartasini ko'rsatish
- Sessiya ochish (admin nomidan)
- Guruh qo'shish (admin nomidan)
- Post qo'shish (admin nomidan)
- Muddat uzaytirish
- Bloklash / o'chirish
- Start / Stop
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import Update

from bot import action_tokens
from bot import keyboards as KB
from bot import texts as T
from bot.login import (
    LoginCtx,
    cleanup_login,
    describe_code_delivery,
    finalize_login,
    login_ctx,
    mask_phone,
    send_numpad,
)
from bot.login import (
    user_states as login_states,
)
from config.config import (
    API_HASH,
    API_ID,
    DEFAULT_DURATION_DAYS,
    MAX_INTERVAL_MIN,
    MEDIA_DIR,
    SUPER_ADMIN,
)
from core import database as db
from core.logger import log
from core.session_manager import revoke_telegram_session
from core.update_locks import user_operation_lock, user_update_lock
from core.utils import (
    calc_expires,
    format_expires,
    safe_unlink,
    truncate,
    wipe_directory,
)

# ─────────────────────────────────────────────────────────────────────────
# APPLICATION (main.py da o'rnatiladi)
# ─────────────────────────────────────────────────────────────────────────
application = None


def set_application(app) -> None:
    global application
    application = app


async def user_card_markup(
    target: int,
    *,
    running: bool | None = None,
    blocked: bool | None = None,
    has_session: bool | None = None,
):
    """Kartadagi holatga bog'liq tugmalarni bazadagi joriy qiymatlar bilan quradi."""
    user = await db.get_user(target) or {}
    return KB.kb_user_card(
        target,
        running=bool(user.get("running")) if running is None else running,
        blocked=bool(user.get("is_blocked")) if blocked is None else blocked,
        has_session=(bool(user.get("session")) if has_session is None else has_session),
        approved=bool(user.get("is_admin")),
        awaiting=bool(user.get("awaiting_approval")),
    )


# ─────────────────────────────────────────────────────────────────────────
# YANGI FOYDALANUVCHI QO'SHISH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_user(update: Update, admin_uid: int) -> None:
    """Super admin panelidan yangi Telegram akkauntini qo'shishni boshlaydi."""
    if admin_uid != SUPER_ADMIN:
        return

    await cleanup_login(admin_uid)
    login_states[admin_uid] = {
        "step": "admin_new_user_full_name",
        "ts": time.time(),
    }
    await update.callback_query.edit_message_text(
        T.ADMIN_ADD_USER_FULL_NAME,
        reply_markup=KB.kb_admin_add_user_cancel(),
    )


async def cancel_add_user(update: Update, admin_uid: int) -> None:
    """Yaratilayotgan Telethon client va admin FSM holatini to'liq yopadi."""
    if admin_uid != SUPER_ADMIN:
        return

    state = login_states.get(admin_uid, {})
    ctx = login_ctx.get(admin_uid)
    active = (
        str(state.get("step", "")).startswith("admin_new_user_")
        or bool(state.get("admin_add_user"))
        or bool(ctx and ctx.mode == "admin_add_user")
    )
    if active:
        await cleanup_login(admin_uid)
        text = T.ADMIN_ADD_USER_CANCELLED
    else:
        text = "ℹ️ Faol foydalanuvchi qo'shish jarayoni yo'q."

    await update.callback_query.edit_message_text(
        text,
        reply_markup=KB.kb_admin_panel(),
    )


async def request_new_user_session(
    admin_uid: int,
    full_name: str,
    phone: str,
) -> None:
    """Yangi user telefoni uchun kod so'raydi; UID login tugagach aniqlanadi."""
    if admin_uid != SUPER_ADMIN:
        return

    # Adminning o'z raqamiga tasodifan yana kod yuborilishining oldini olamiz.
    admin_phone = await db.get_phone(SUPER_ADMIN)
    if admin_phone and admin_phone == phone:
        login_states.pop(admin_uid, None)
        await application.bot.send_message(
            admin_uid,
            "⚠️ Bu super adminning o'z telefon raqami.\n\n"
            "Oddiy foydalanuvchi uchun boshqa raqam kiriting.",
            reply_markup=KB.kb_admin_panel(),
        )
        return

    existing = await db.get_user_by_phone(phone)
    if existing:
        target_uid = int(existing["uid"])
        login_states.pop(admin_uid, None)
        await application.bot.send_message(
            admin_uid,
            "ℹ️ Bu telefon raqami foydalanuvchilar ro'yxatida mavjud.\n\n"
            f"👤 {existing.get('name') or 'Noma`lum'}\n"
            f"🆔 {target_uid}",
            reply_markup=KB.kb_user_card(
                target_uid,
                running=bool(existing.get("running")),
                blocked=bool(existing.get("is_blocked")),
                has_session=bool(existing.get("session")),
                approved=bool(existing.get("is_admin")),
                awaiting=bool(existing.get("awaiting_approval")),
            ),
        )
        return

    # Eski tugallanmagan yaratish jarayoni/client qolib ketmasin.
    await cleanup_login(admin_uid)

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await asyncio.wait_for(client.send_code_request(phone), timeout=30)
        destination, type_name, next_name, delivery_timeout = describe_code_delivery(
            result
        )
        phone_code_hash = getattr(result, "phone_code_hash", "") or ""

        login_ctx[admin_uid] = LoginCtx(
            client=client,
            phone=phone,
            phone_code_hash=phone_code_hash,
            started_at=time.time(),
            target_name=full_name,
            mode="admin_add_user",
        )

        if type(result).__name__ == "SentCodeSuccess" or (
            not phone_code_hash and await client.is_user_authorized()
        ):
            log(f"✅ Admin user qo'shish kodsiz tasdiqlandi: phone={mask_phone(phone)}")
            await finalize_login(admin_uid)
            return

        if not phone_code_hash:
            raise RuntimeError(f"Telegram {type_name} qaytardi, phone_code_hash yo'q")

        code_length = getattr(getattr(result, "type", None), "length", None) or 5
        code_hint = f"👤 {full_name}\n📱 {phone}\n📍 Yetkazish: {destination}"
        login_states[admin_uid] = {
            "step": "code",
            "ts": time.time(),
            "code_buffer": "",
            "code_length": code_length,
            "code_hint": code_hint,
            "admin_add_user": True,
        }
        await send_numpad(admin_uid, "", hint=code_hint)
        log(
            f"📩 Admin yangi user kodi: admin={admin_uid} "
            f"phone={mask_phone(phone)} delivery={type_name} "
            f"next={next_name} timeout={delivery_timeout}"
        )

    except Exception as e:
        if login_ctx.get(admin_uid):
            await cleanup_login(admin_uid)
        else:
            if client:
                with contextlib.suppress(Exception):
                    await client.disconnect()
            login_states.pop(admin_uid, None)
        log(
            f"❌ request_new_user_session: {type(e).__name__}",
            "error",
        )
        await application.bot.send_message(
            admin_uid,
            f"❌ Foydalanuvchi qo'shilmadi: {type(e).__name__}\n\n"
            "Telefon raqamini tekshirib, qaytadan urinib ko'ring.",
            reply_markup=KB.kb_admin_panel(),
        )


# ─────────────────────────────────────────────────────────────────────────
# ASOSIY ROUTER
# ─────────────────────────────────────────────────────────────────────────
def _callback_page(parts: list[str], index: int) -> int:
    """Callbackdagi sahifani xavfsiz o'qiydi."""
    try:
        return max(0, int(parts[index]))
    except (IndexError, ValueError):
        return 0


async def handle_user_card(update: Update, admin_uid: int, data: str) -> None:
    """Foydalanuvchi kartasi callback'lari."""
    if admin_uid != SUPER_ADMIN:
        return

    q = update.callback_query
    parts = data.split(":")
    if len(parts) < 3:
        return

    action = parts[1]
    try:
        target = int(parts[2])
    except ValueError:
        return

    # Super admin oddiy user kartasi orqali boshqarilmaydi. Eski xabar yoki
    # qo'lda tuzilgan callback ham adminning sessiyasini qayta ochmasin.
    if target == SUPER_ADMIN:
        await q.edit_message_text(
            "🛡 Super admin oddiy foydalanuvchilardan alohida boshqariladi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    if not await db.get_user(target):
        await q.edit_message_text(
            "❌ Foydalanuvchi topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    # Router allaqachon admin actor lockini ushlab turadi. Target shu striped
    # lockka tushsa u ham serial; aks holda target actor lockini alohida olamiz.
    target_lock = user_update_lock(target)
    if target_lock is user_update_lock(admin_uid):
        await _handle_user_card_target_locked(update, admin_uid, action, target, parts)
    else:
        async with target_lock:
            await _handle_user_card_target_locked(
                update, admin_uid, action, target, parts
            )


async def _handle_user_card_target_locked(
    update: Update,
    admin_uid: int,
    action: str,
    target: int,
    parts: list[str],
) -> None:
    """Admin va target update locklari ichidagi selected-user dispatcher."""
    q = update.callback_query
    if not await db.get_user(target):
        await q.edit_message_text(
            "❌ Foydalanuvchi endi mavjud emas.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    # Eski karta tugmasi faol admin/login FSM bilan aralashmasin.
    if action != "authcancel" and login_states.get(admin_uid):
        await cleanup_login(admin_uid)

    if action == "view":
        await show_user_card(update, target)
        return
    if action == "start":
        await action_start(update, admin_uid, target)
        return
    if action == "stop":
        await action_stop(update, admin_uid, target)
        return
    if action == "sess":
        await action_open_session(update, admin_uid, target)
        return
    if action == "authcancel":
        await cleanup_login(admin_uid)
        await show_user_card(update, target)
        return
    if action == "logoutask":
        token = action_tokens.issue(admin_uid, f"uc:logout:{target}")
        await q.edit_message_text(
            "⚠️ Telegram sessiyasi uzilsinmi?\n\n"
            "Bu authorization Telegram Devices ro'yxatidan ham bekor qilinadi.",
            reply_markup=KB.kb_user_confirm(
                target,
                "logoutconfirm",
                "✅ Sessiyani uzish",
                token,
            ),
        )
        return
    if action == "logoutconfirm":
        token = parts[3] if len(parts) > 3 else ""
        if not action_tokens.consume(admin_uid, f"uc:logout:{target}", token):
            await q.edit_message_text("⚠️ Bu tasdiqlash oynasi eskirgan.")
            return
        await action_logout(update, admin_uid, target)
        return
    if action == "groups":
        page = _callback_page(parts, 3)
        await action_show_groups(update, target, page)
        return
    if action == "posts":
        page = _callback_page(parts, 3)
        await action_show_posts(update, target, page)
        return
    if action == "delg":
        await action_delete_group(update, admin_uid, target, parts)
        return
    if action == "delp":
        await action_delete_post(update, admin_uid, target, parts)
        return
    if action == "addg":
        await action_add_group(update, admin_uid, target)
        return
    if action == "addp":
        await action_add_post(update, admin_uid, target)
        return
    if action == "interval":
        await action_show_interval(update, target)
        return
    if action == "expire":
        await action_show_expire(update, admin_uid, target)
        return
    if action == "msg":
        await action_send_message(update, admin_uid, target)
        return
    if action == "approve":
        await action_approve(update, admin_uid, target)
        return
    if action == "rejectask":
        token = action_tokens.issue(admin_uid, f"uc:reject:{target}")
        await q.edit_message_text(
            "⚠️ Ariza rad etilsinmi? Kiritilgan ism va telefon ham o'chiriladi.",
            reply_markup=KB.kb_user_confirm(
                target, "rejectconfirm", "❌ Rad etish", token
            ),
        )
        return
    if action == "rejectconfirm":
        token = parts[3] if len(parts) > 3 else ""
        if not action_tokens.consume(admin_uid, f"uc:reject:{target}", token):
            await q.edit_message_text("⚠️ Bu tasdiqlash oynasi eskirgan.")
            return
        await action_reject(update, admin_uid, target)
        return
    if action == "blockask":
        token = action_tokens.issue(admin_uid, f"uc:block:{target}")
        await q.edit_message_text(
            "⚠️ Foydalanuvchi bloklansinmi? Faol posting darhol to'xtaydi.",
            reply_markup=KB.kb_user_confirm(
                target, "blockconfirm", "🚫 Bloklash", token
            ),
        )
        return
    if action == "blockconfirm":
        token = parts[3] if len(parts) > 3 else ""
        if not action_tokens.consume(admin_uid, f"uc:block:{target}", token):
            await q.edit_message_text("⚠️ Bu tasdiqlash oynasi eskirgan.")
            return
        await action_block(update, admin_uid, target)
        return
    if action == "unblock":
        await action_unblock(update, admin_uid, target)
        return
    if action == "deleteask":
        token = action_tokens.issue(admin_uid, f"uc:delete:{target}")
        await q.edit_message_text(
            "⚠️ FOYDALANUVCHINI BUTUNLAY O'CHIRISH\n\n"
            "Sessiya Telegramda bekor qilinadi; guruh, post, rasm va referral "
            "ma'lumotlari qaytarib bo'lmaydigan tarzda o'chadi.",
            reply_markup=KB.kb_user_confirm(
                target, "deleteconfirm", "🗑 O'chirish", token
            ),
        )
        return
    if action == "deleteconfirm":
        token = parts[3] if len(parts) > 3 else ""
        if not action_tokens.consume(admin_uid, f"uc:delete:{target}", token):
            await q.edit_message_text("⚠️ Bu tasdiqlash oynasi eskirgan.")
            return
        await action_delete(update, admin_uid, target)
        return
    if action == "detail":
        await action_detail(update, admin_uid, target)
        return
    if action == "back":
        action_tokens.clear(admin_uid)
        await show_user_card(update, target)
        return


# ─────────────────────────────────────────────────────────────────────────
# FOYDALANUVCHI KARTASI
# ─────────────────────────────────────────────────────────────────────────
async def show_user_card(update: Update, target: int) -> None:
    """Foydalanuvchi kartasini ko‘rsatadi."""
    q = update.callback_query
    user = await db.get_user(target)

    if not user:
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                "❌ Foydalanuvchi topilmadi.",
                reply_markup=KB.kb_admin_back(),
            )
        return

    name = user.get("name") or "Noma'lum"
    username = f"@{user.get('username')}" if user.get("username") else "username yo'q"
    phone = user.get("phone") or "—"
    session = "✅ Faol" if user.get("session") else "❌ Yo'q"
    blocked = bool(user.get("is_blocked"))
    from bot.menu import worker_manager

    running = bool(worker_manager and worker_manager.is_running(target))
    if bool(user.get("running")) != running:
        await db.set_running(target, running)
    approved = bool(user.get("is_admin"))
    awaiting = bool(user.get("awaiting_approval"))
    expires = user.get("tariff_expires_at")
    chats = await db.count_chats(target)
    posts = await db.count_posts(target)
    interval = user.get("interval_min", 60)

    if blocked:
        state = "🚫 Bloklangan"
    elif awaiting:
        state = "⏳ Admin tasdig'ini kutmoqda"
    elif not approved:
        state = "❌ Tasdiqlanmagan"
    elif running:
        state = "🟢 Ishlamoqda"
    elif user.get("session"):
        state = "⚪ To'xtatilgan"
    else:
        state = "🔑 Login kerak"

    created = (user.get("created_at") or "")[:10]

    text = (
        f"👤 {name}\n"
        f"📱 {phone} | {username}\n"
        f"🆔 {target}\n"
        f"📅 Ro'yxatdan: {created}\n"
        f"📅 Muddat: {format_expires(expires)}\n"
        f"🔐 Sessiya: {session}\n"
        f"📊 Holat: {state}\n\n"
        f"💬 Guruhlar: {chats} ta\n"
        f"📝 Postlar: {posts} ta\n"
        f"⏱ Taxminiy posting oralig'i: {interval} daqiqa"
    )

    kb = KB.kb_user_card(
        target,
        running=running,
        blocked=blocked,
        has_session=bool(user.get("session")),
        approved=approved,
        awaiting=awaiting,
    )
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────
# START / STOP
# ─────────────────────────────────────────────────────────────────────────
async def action_start(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_start_locked(update, admin_uid, target)


async def _action_start_locked(update: Update, admin_uid: int, target: int) -> None:
    """Admin nomidan postingni boshlash."""
    q = update.callback_query
    from bot.menu import worker_manager

    if not worker_manager:
        await q.edit_message_text(
            "❌ Worker manager topilmadi.",
            reply_markup=await user_card_markup(target),
        )
        return

    if worker_manager.is_running(target):
        await q.edit_message_text(
            "⚠️ Allaqachon ishlamoqda.",
            reply_markup=await user_card_markup(target, running=True),
        )
        return

    user = await db.get_user(target)
    if not user or not user.get("is_admin"):
        await q.edit_message_text(
            "❌ Avval foydalanuvchini tasdiqlang.",
            reply_markup=await user_card_markup(target),
        )
        return
    if not user.get("session"):
        await q.edit_message_text(
            "❌ Avval Telegram sessiyasini ulang.",
            reply_markup=await user_card_markup(target, has_session=False),
        )
        return

    if await db.is_blocked(target):
        await q.edit_message_text(
            "🚫 Avval foydalanuvchini blokdan chiqaring.",
            reply_markup=await user_card_markup(target, blocked=True),
        )
        return

    if await db.is_tariff_expired(target):
        await q.edit_message_text(
            "⏸ Foydalanuvchi muddati tugagan.",
            reply_markup=await user_card_markup(target),
        )
        return

    chats = await db.get_chats(target)
    posts = await db.get_posts(target)
    if not chats or not posts:
        await q.edit_message_text(
            "❌ Guruh yoki post yo'q.",
            reply_markup=await user_card_markup(target),
        )
        return

    await db.set_running(target, True)
    started = await worker_manager.start_worker(target)
    if not started:
        await db.set_running(target, False)
        await q.edit_message_text(
            "⚠️ Tizim band. Qaytadan urinib ko'ring.",
            reply_markup=await user_card_markup(target),
        )
        return
    log(f"▶️ Admin {admin_uid} → Start {target}")
    await q.edit_message_text(
        f"✅ {target} uchun posting boshlandi.",
        reply_markup=await user_card_markup(target, running=True),
    )


async def action_stop(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_stop_locked(update, admin_uid, target)


async def _action_stop_locked(update: Update, admin_uid: int, target: int) -> None:
    """Admin nomidan postingni to‘xtatish."""
    q = update.callback_query
    from bot.menu import worker_manager

    if worker_manager:
        await worker_manager.stop_worker(target)
    from worker.worker import client_pool

    if client_pool:
        await client_pool.remove(target)
    await db.set_running(target, False)

    log(f"⛔ Admin {admin_uid} → Stop {target}")
    await q.edit_message_text(
        f"⛔ {target} uchun posting to'xtatildi.",
        reply_markup=await user_card_markup(target, running=False),
    )


# ─────────────────────────────────────────────────────────────────────────
# SESSIYA OCHISH
# ─────────────────────────────────────────────────────────────────────────
async def action_open_session(update: Update, admin_uid: int, target: int) -> None:
    """
    Admin foydalanuvchi nomidan sessiya ochadi.

    1. Kod so'raladi.
    2. Admin kodni raqamli tugmalarda kiritadi.
    3. UID mosligi tekshirilgach sessiya saqlanadi.
    """
    q = update.callback_query

    if admin_uid != SUPER_ADMIN:
        return
    if target == SUPER_ADMIN:
        await q.edit_message_text(
            "🛡 Super admin uchun bu yerdan sessiya ochib bo'lmaydi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    user = await db.get_user(target)

    if not user:
        await q.edit_message_text("❌ Foydalanuvchi topilmadi.")
        return

    if user.get("session"):
        await q.edit_message_text(
            "ℹ️ Bu foydalanuvchida sessiya allaqachon mavjud.\n\n"
            "Yangi sessiya kerak bo'lsa, avval eskisini o'chiring.",
            reply_markup=await user_card_markup(target, has_session=True),
        )
        return

    phone = user.get("phone")
    if not phone:
        await q.edit_message_text(
            "❌ Foydalanuvchining telefon raqami yo'q.",
            reply_markup=await user_card_markup(target, has_session=False),
        )
        return

    # Oldingi tugallanmagan admin loginini client bilan birga yopamiz.
    await cleanup_login(admin_uid)

    # To'g'ridan-to'g'ri kod so'raymiz (request_code ni chaqirmaymiz!)
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await asyncio.wait_for(client.send_code_request(phone), timeout=30)
        destination, type_name, next_name, delivery_timeout = describe_code_delivery(
            result
        )
        phone_code_hash = getattr(result, "phone_code_hash", "") or ""
        login_ctx[admin_uid] = LoginCtx(
            client=client,
            phone=phone,
            phone_code_hash=phone_code_hash,
            started_at=time.time(),
            for_uid=target,
            target_name=user.get("name", ""),
        )

        if type(result).__name__ == "SentCodeSuccess" or (
            not phone_code_hash and await client.is_user_authorized()
        ):
            log(f"✅ Admin sessiya kodsiz tasdiqlandi: target={target}")
            await finalize_login(admin_uid, target_update_locked=True)
            return
        if not phone_code_hash:
            raise RuntimeError(f"{type_name}: phone_code_hash yo'q")

        code_length = getattr(getattr(result, "type", None), "length", None) or 5
        code_hint = (
            f"👤 {user.get('name')}\n"
            f"🆔 {target}\n"
            f"📱 {phone}\n"
            f"📍 Yetkazish: {destination}"
        )
        login_states[admin_uid] = {
            "step": "code",
            "ts": time.time(),
            "target_uid": target,
            "code_buffer": "",
            "code_length": code_length,
            "code_hint": code_hint,
            "admin_add_user": True,
            "admin_session_target": target,
        }

        await q.edit_message_text(
            "🔑 Sessiyani ulash\n\n"
            "Kod alohida xavfsiz kanal orqali olingan bo'lsa, uni keyingi "
            "oynadagi raqamli tugmalar bilan kiriting. Kod xabarda ochiq "
            "ko'rsatilmaydi."
        )
        await send_numpad(admin_uid, "", hint=code_hint)

        log(
            f"📩 Admin kod so'rovi: admin={admin_uid} target={target} "
            f"phone={mask_phone(phone)} delivery={type_name} "
            f"next={next_name} timeout={delivery_timeout}"
        )

    except Exception as e:
        if login_ctx.get(admin_uid):
            await cleanup_login(admin_uid)
        else:
            if client:
                with contextlib.suppress(Exception):
                    await client.disconnect()
            login_states.pop(admin_uid, None)
        log(f"❌ action_open_session xato: {type(e).__name__}", "error")
        await q.edit_message_text(
            f"❌ Kod so'ralmadi: {type(e).__name__}\n\nQaytadan urinib ko'ring.",
            reply_markup=await user_card_markup(target, has_session=False),
        )


async def action_logout(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_logout_locked(update, admin_uid, target)


async def _action_logout_locked(update: Update, admin_uid: int, target: int) -> None:
    """Authorizationni Telegram tomonda bekor qilib, lokal sessiyani o'chiradi."""
    q = update.callback_query
    session = await db.get_session(target)
    if not session:
        await q.edit_message_text(
            "ℹ️ Sessiya allaqachon yo'q.",
            reply_markup=await user_card_markup(target, has_session=False),
        )
        return
    from bot.menu import worker_manager
    from worker.worker import client_pool

    if worker_manager:
        await worker_manager.stop_worker(target)
    if client_pool:
        await client_pool.remove(target)
    await db.set_running(target, False)

    if not await revoke_telegram_session(session, target):
        await q.edit_message_text(
            "❌ Telegram bilan ulanish bo'lmadi. Posting to'xtatildi, lekin "
            "authorizationni keyin bekor qilish imkonini saqlash uchun sessiya "
            "o'chirilmadi.",
            reply_markup=await user_card_markup(target, has_session=True),
        )
        return

    await db.del_session(target)

    log(f"🚪 Admin {admin_uid} → Logout {target}")
    await q.edit_message_text(
        f"🚪 {target} sessiyasi o'chirildi.",
        reply_markup=await user_card_markup(target, has_session=False),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            "🚪 Admin sizning sessiyangizni o'chirdi.\n\nQaytadan 🔑 Login qiling.",
            reply_markup=KB.kb_login(),
        )


# ─────────────────────────────────────────────────────────────────────────
# GURUH / POST BOSHQARUVI
# ─────────────────────────────────────────────────────────────────────────
async def action_show_groups(update: Update, target: int, page: int = 0) -> None:
    """Tanlangan user guruhlarini sahifalab boshqaradi."""
    q = update.callback_query
    groups = await db.get_chat_records(target)
    page_size = 10
    max_page = max(0, (len(groups) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    visible = groups[start : start + page_size]
    lines = [f"💬 GURUHLAR — {target} ({len(groups)} ta)\n"]
    if visible:
        for index, group in enumerate(visible, start + 1):
            lines.append(f"{index}. {group['value']}")
        lines.append("\nGuruhni o'chirish uchun uning 🗑 tugmasini bosing.")
    else:
        lines.append(T.GROUPS_EMPTY)
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=KB.kb_admin_groups(target, groups, page, page_size),
    )


async def action_show_posts(update: Update, target: int, page: int = 0) -> None:
    """Tanlangan user postlarini sahifalab boshqaradi."""
    q = update.callback_query
    posts = await db.get_posts(target)
    page_size = 10
    max_page = max(0, (len(posts) - 1) // page_size)
    page = min(max(page, 0), max_page)
    start = page * page_size
    visible = posts[start : start + page_size]
    lines = [f"📝 POSTLAR — {target} ({len(posts)} ta)\n"]
    if visible:
        for index, post in enumerate(visible, start + 1):
            preview = truncate(
                (post.get("text") or "(rasm)").strip().replace("\n", " "),
                80,
            )
            lines.append(f"{index}. {preview}")
        lines.append("\nPostni o'chirish uchun uning 🗑 tugmasini bosing.")
    else:
        lines.append(T.POSTS_EMPTY)
    await q.edit_message_text(
        "\n".join(lines),
        reply_markup=KB.kb_admin_posts(target, posts, page, page_size),
    )


async def action_delete_group(
    update: Update,
    admin_uid: int,
    target: int,
    parts: list[str],
) -> None:
    """Admin tanlagan user guruhini barqaror ID bo'yicha o'chiradi."""
    if len(parts) < 4:
        return
    try:
        group_id = int(parts[3])
    except ValueError:
        return
    page = _callback_page(parts, 4)
    async with user_operation_lock(target):
        exists = bool(await db.get_user(target))
        removed = await db.remove_chat_by_id(target, group_id) if exists else None
    if not exists:
        await update.callback_query.edit_message_text(
            "❌ Foydalanuvchi endi mavjud emas.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    if removed:
        log(f"🗑 Admin {admin_uid} → {target} guruh: {removed}")
    await action_show_groups(update, target, page)


async def action_delete_post(
    update: Update,
    admin_uid: int,
    target: int,
    parts: list[str],
) -> None:
    """Admin tanlagan user postini barqaror ID bo'yicha o'chiradi."""
    if len(parts) < 4:
        return
    try:
        post_id = int(parts[3])
    except ValueError:
        return
    from bot.posts import delete_post_by_id

    page = _callback_page(parts, 4)
    async with user_operation_lock(target):
        exists = bool(await db.get_user(target))
        deleted, preview = (
            await delete_post_by_id(target, post_id) if exists else (False, "")
        )
    if not exists:
        await update.callback_query.edit_message_text(
            "❌ Foydalanuvchi endi mavjud emas.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    if deleted:
        log(f"🗑 Admin {admin_uid} → {target} post: {preview}")
    await action_show_posts(update, target, page)


async def action_add_group(update: Update, admin_uid: int, target: int) -> None:
    """Admin foydalanuvchi nomidan guruh qo'shadi."""
    q = update.callback_query
    login_states[admin_uid] = {
        "step": "admin_add_group",
        "ts": time.time(),
        "target_uid": target,
    }
    await q.edit_message_text(
        f"➕ Guruh qo'shish\n\n"
        f"Foydalanuvchi: {target}\n\n"
        f"Guruhlarni yuboring (har biri yangi qatorda):\n\n"
        f"@guruh1\n@guruh2\n...",
        reply_markup=KB.kb_admin_section_back(target, "groups"),
    )


async def action_add_post(update: Update, admin_uid: int, target: int) -> None:
    """Admin foydalanuvchi nomidan post qo'shadi."""
    q = update.callback_query
    login_states[admin_uid] = {
        "step": "admin_add_post",
        "ts": time.time(),
        "target_uid": target,
    }
    await q.edit_message_text(
        f"📝 Post qo'shish\n\n"
        f"Foydalanuvchi: {target}\n\n"
        f"Post matni yoki rasm yuboring.",
        reply_markup=KB.kb_admin_section_back(target, "posts"),
    )


# ─────────────────────────────────────────────────────────────────────────
# POSTING ORALIG'I
# ─────────────────────────────────────────────────────────────────────────
async def action_show_interval(update: Update, target: int) -> None:
    """Tanlangan userning posting oralig'i sozlamalarini ko'rsatadi."""
    q = update.callback_query
    current = await db.get_interval(target)
    await q.edit_message_text(
        "⏱ TAXMINIY POSTING ORALIG'I\n\n"
        f"Foydalanuvchi: {target}\n"
        f"Hozirgi oraliq: taxminan {current} daqiqa\n\n"
        "Anti-spam uchun real vaqt 5 daqiqagacha farq qilishi mumkin. "
        "Bu sozlama tarif muddatidan alohida. Yangi oraliqni tanlang:",
        reply_markup=KB.kb_admin_interval(target),
    )


async def handle_interval(update: Update, admin_uid: int, data: str) -> None:
    """Admin posting oralig'i callback'ini qayta ishlaydi."""
    if admin_uid != SUPER_ADMIN:
        return
    q = update.callback_query
    parts = data.split(":")
    if len(parts) != 3:
        return
    try:
        target = int(parts[1])
    except ValueError:
        return
    if target == SUPER_ADMIN or not await db.get_user(target):
        await q.edit_message_text(
            "❌ Foydalanuvchi topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    if parts[2] == "manual":
        login_states[admin_uid] = {
            "step": "admin_set_interval",
            "ts": time.time(),
            "target_uid": target,
        }
        await q.edit_message_text(
            "✏️ POSTING ORALIG'INI KIRITISH\n\n"
            f"Foydalanuvchi: {target}\n\n"
            f"Oraliqni daqiqada kiriting (5–{MAX_INTERVAL_MIN}).\n"
            "Masalan: 45",
            reply_markup=KB.kb_admin_section_back(target),
        )
        return

    try:
        minutes = int(parts[2])
    except ValueError:
        return
    if minutes < 5 or minutes > MAX_INTERVAL_MIN:
        await q.edit_message_text(
            f"❌ Posting oralig'i 5–{MAX_INTERVAL_MIN} daqiqa bo'lishi kerak.",
            reply_markup=KB.kb_admin_interval(target),
        )
        return

    async with user_operation_lock(target):
        exists = bool(await db.get_user(target))
        if exists:
            await db.set_interval(target, minutes)
    if not exists:
        await q.edit_message_text(
            "❌ Foydalanuvchi endi mavjud emas.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    log(f"⏱ Admin {admin_uid} → {target} interval={minutes}")
    await q.edit_message_text(
        f"✅ Taxminiy posting oralig'i {minutes} daqiqaga o'rnatildi.\n"
        "Anti-spam uchun real vaqt 5 daqiqagacha farq qiladi.",
        reply_markup=await user_card_markup(target),
    )


# ─────────────────────────────────────────────────────────────────────────
# MUDDAT UZAYTIRISH
# ─────────────────────────────────────────────────────────────────────────
async def action_show_expire(update: Update, admin_uid: int, target: int) -> None:
    """Muddat uzaytirish tugmalarini ko‘rsatadi."""
    q = update.callback_query
    expires = await db.get_tariff_expires(target)

    await q.edit_message_text(
        f"⏰ Muddat uzaytirish\n\n"
        f"Foydalanuvchi: {target}\n"
        f"Hozirgi muddat: {format_expires(expires)}\n\n"
        "Yangi muddat variantini tanlang:",
        reply_markup=KB.kb_expire_options(target),
    )


async def handle_expire(update: Update, admin_uid: int, data: str) -> None:
    """Muddat uzaytirish callback'i."""
    q = update.callback_query

    if admin_uid != SUPER_ADMIN:
        return

    parts = data.split(":")
    if len(parts) < 3:
        return

    try:
        target = int(parts[1])
        days_str = parts[2]
    except (ValueError, IndexError):
        return
    if target == SUPER_ADMIN or not await db.get_user(target):
        await q.edit_message_text(
            "❌ Foydalanuvchi topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    if days_str == "forever":
        async with user_operation_lock(target):
            exists = bool(await db.get_user(target))
            if exists:
                await db.set_tariff_expires(target, None)
        if not exists:
            await q.edit_message_text(
                "❌ Foydalanuvchi endi mavjud emas.",
                reply_markup=KB.kb_admin_back(),
            )
            return
        await q.edit_message_text(
            "✅ Tarif cheklanmagan muddatga o'rnatildi.",
            reply_markup=await user_card_markup(target),
        )
        return

    # Qo'lda kiritish
    if days_str == "manual":
        login_states[admin_uid] = {
            "step": "admin_set_expire",
            "ts": time.time(),
            "target_uid": target,
        }
        await q.edit_message_text(
            f"✏️ Muddatni qo'lda kiritish\n\n"
            f"Foydalanuvchi: {target}\n\n"
            f"Necha kun qo'shmoqchisiz? (raqamda)\n\n"
            f"Masalan: 30",
            reply_markup=KB.kb_admin_section_back(target),
        )
        return

    try:
        days = int(days_str)
    except ValueError:
        return
    if not 1 <= days <= 3650:
        await q.edit_message_text(
            "❌ Muddat 1–3650 kun oralig'ida bo'lishi kerak.",
            reply_markup=KB.kb_expire_options(target),
        )
        return

    from datetime import datetime, timedelta, timezone

    new_iso = ""
    async with user_operation_lock(target):
        exists = bool(await db.get_user(target))
        if exists:
            current = await db.get_tariff_expires(target)
            if current:
                try:
                    dt = datetime.strptime(current, "%Y-%m-%d %H:%M:%S").replace(
                        tzinfo=timezone.utc
                    )
                    dt = max(dt, datetime.now(timezone.utc))
                except Exception:
                    dt = datetime.now(timezone.utc)
            else:
                dt = datetime.now(timezone.utc)

            new_dt = dt + timedelta(days=days)
            new_iso = new_dt.strftime("%Y-%m-%d %H:%M:%S")
            await db.set_tariff_expires(target, new_iso)
    if not exists:
        await q.edit_message_text(
            "❌ Foydalanuvchi endi mavjud emas.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    log(f"⏰ Admin {admin_uid} → {target} +{days} kun")
    await q.edit_message_text(
        f"✅ Muddat uzaytirildi: +{days} kun\nYangi muddat: {new_iso[:10]}",
        reply_markup=await user_card_markup(target),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            f"✅ Tarifingiz uzaytirildi!\n\n📅 Yangi muddat: {new_iso[:10]}",
        )


# ─────────────────────────────────────────────────────────────────────────
# TASDIQLASH / BLOK / O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def action_approve(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_approve_locked(update, admin_uid, target)


async def _action_approve_locked(update: Update, admin_uid: int, target: int) -> None:
    q = update.callback_query
    user = await db.get_user(target)
    if not user or not user.get("awaiting_approval"):
        await q.edit_message_text(
            "⚠️ Ariza eskirgan yoki allaqachon ko'rib chiqilgan.",
            reply_markup=await user_card_markup(target) if user else KB.kb_admin_back(),
        )
        return
    pending = await db.get_pending(target)
    if pending:
        # Eski versiyadan qolgan pending sessiyaning UID bindingiga ishonmaymiz.
        # Telegramda revoke qilib, approvaldan keyin yangi login talab qilamiz.
        if not await revoke_telegram_session(pending, target):
            await q.edit_message_text(
                "❌ Eski pending authorization bekor qilinmadi. Xavfsizlik "
                "uchun ariza hozircha tasdiqlanmadi.",
                reply_markup=await user_card_markup(target),
            )
            return
        await db.del_pending(target)
    await db.approve_user(target, calc_expires(DEFAULT_DURATION_DAYS))
    log(f"✅ Admin {admin_uid} → Approve {target}")
    await q.edit_message_text(
        f"✅ {target} tasdiqlandi. Tarif: {DEFAULT_DURATION_DAYS} kun.",
        reply_markup=await user_card_markup(target),
    )
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            T.USER_APPROVED,
            reply_markup=KB.kb_login(),
        )
    with contextlib.suppress(Exception):
        from bot.referral import on_referral_counted

        await on_referral_counted(target)


async def action_reject(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_reject_locked(update, admin_uid, target)


async def _action_reject_locked(update: Update, admin_uid: int, target: int) -> None:
    q = update.callback_query
    user = await db.get_user(target)
    if not user or not user.get("awaiting_approval"):
        await q.edit_message_text(
            "⚠️ Ariza eskirgan yoki allaqachon ko'rib chiqilgan.",
            reply_markup=await user_card_markup(target) if user else KB.kb_admin_back(),
        )
        return
    pending = await db.get_pending(target)
    if pending and not await revoke_telegram_session(pending, target):
        await q.edit_message_text(
            "❌ Pending Telegram authorization bekor qilinmadi. "
            "Xavfsizlik uchun ariza hozircha o'chirilmadi.",
            reply_markup=await user_card_markup(target),
        )
        return
    await cleanup_login(target)
    await db.delete_user(target)
    wipe_directory(MEDIA_DIR / str(target))
    log(f"❌ Admin {admin_uid} → Reject {target}")
    await q.edit_message_text(
        f"❌ {target} arizasi rad etildi va ma'lumotlari o'chirildi.",
        reply_markup=KB.kb_admin_back(),
    )
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target, T.USER_REJECTED, reply_markup=KB.kb_login()
        )


async def action_block(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_block_locked(update, admin_uid, target)


async def _action_block_locked(update: Update, admin_uid: int, target: int) -> None:
    """Foydalanuvchini bloklash."""
    q = update.callback_query
    from bot.menu import worker_manager

    if worker_manager:
        await worker_manager.stop_worker(target)
    from worker.worker import client_pool

    if client_pool:
        await client_pool.remove(target)
    await cleanup_login(target)
    await db.set_blocked(target, True)
    await db.set_running(target, False)

    log(f"🚫 Admin {admin_uid} → Block {target}")
    await q.edit_message_text(
        f"🚫 {target} bloklandi.",
        reply_markup=await user_card_markup(target, blocked=True),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target, T.BLOCKED, reply_markup=KB.kb_blocked()
        )


async def action_unblock(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_unblock_locked(update, admin_uid, target)


async def _action_unblock_locked(update: Update, admin_uid: int, target: int) -> None:
    """Blokdan chiqarish."""
    q = update.callback_query
    await db.set_blocked(target, False)
    log(f"🔓 Admin {admin_uid} → Unblock {target}")

    await q.edit_message_text(
        f"🔓 {target} blokdan chiqarildi.",
        reply_markup=await user_card_markup(target, blocked=False),
    )

    user = await db.get_user(target)
    if user and user.get("awaiting_approval"):
        markup = KB.kb_pending()
        notice = "✅ Hisobingiz blokdan chiqarildi. Tasdiqni kuting."
    elif user and user.get("is_admin") and user.get("session"):
        markup = KB.kb_main(running=False)
        notice = "✅ Hisobingiz blokdan chiqarildi."
    else:
        markup = KB.kb_login()
        notice = "✅ Hisobingiz blokdan chiqarildi. Qayta Login qiling."
    with contextlib.suppress(Exception):
        await application.bot.send_message(target, notice, reply_markup=markup)


async def action_delete(update: Update, admin_uid: int, target: int) -> None:
    async with user_operation_lock(target):
        await _action_delete_locked(update, admin_uid, target)


async def _action_delete_locked(update: Update, admin_uid: int, target: int) -> None:
    """Authorization, media va bog'langan DB yozuvlari bilan birga o'chiradi."""
    q = update.callback_query
    user = await db.get_user(target)
    if not user:
        await q.edit_message_text(
            "⚠️ Foydalanuvchi allaqachon o'chirilgan.", reply_markup=KB.kb_admin_back()
        )
        return

    from bot.menu import worker_manager
    from worker.worker import client_pool

    if worker_manager:
        await worker_manager.stop_worker(target)
    if client_pool:
        await client_pool.remove(target)
    await db.set_running(target, False)
    await cleanup_login(target)

    sessions = [
        value
        for value in (await db.get_session(target), await db.get_pending(target))
        if value
    ]
    for session in dict.fromkeys(sessions):
        if not await revoke_telegram_session(session, target):
            await q.edit_message_text(
                "❌ Telegram authorization bekor qilinmadi. Posting to'xtatildi, "
                "lekin xavfsizlik uchun foydalanuvchi hozircha o'chirilmadi.",
                reply_markup=await user_card_markup(target),
            )
            return

    posts = await db.get_posts(target)
    if not await db.delete_user(target):
        await q.edit_message_text(
            "⚠️ Foydalanuvchi allaqachon o'chirilgan.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    for post in posts:
        if post.get("photo"):
            safe_unlink(post["photo"])
    wipe_directory(MEDIA_DIR / str(target))
    log(f"🗑 Admin {admin_uid} → Delete {target}")

    await q.edit_message_text(
        f"🗑 {target} butunlay o'chirildi.",
        reply_markup=KB.kb_admin_back(),
    )
    with contextlib.suppress(Exception):
        await application.bot.send_message(target, "❌ Hisobingiz o'chirildi.")


# ─────────────────────────────────────────────────────────────────────────
# FOYDALANUVCHIGA XABAR YUBORISH
# ─────────────────────────────────────────────────────────────────────────
async def action_send_message(
    update: Update, admin_uid: int, target: int
) -> None:
    """
    Admin tanlangan foydalanuvchiga bitta matnli xabar yozib yuboradi.

    Botni tushunmayotgan userga admin tushuntirish yozishi uchun.
    """
    q = update.callback_query
    login_states[admin_uid] = {
        "step": "admin_user_message",
        "ts": time.time(),
        "target_uid": target,
    }
    await q.edit_message_text(
        f"✉️ XABAR YUBORISH\n\n"
        f"Foydalanuvchi: {target}\n\n"
        f"Yubormoqchi bo'lgan matnni shu yerning o'ziga yozing.\n"
        f"Xabar to'g'ridan-to'g'ri foydalanuvchiga boradi.",
        reply_markup=KB.kb_admin_section_back(target, "back"),
    )


# ─────────────────────────────────────────────────────────────────────────
# BATAFSIL
# ─────────────────────────────────────────────────────────────────────────
async def action_detail(update: Update, admin_uid: int, target: int) -> None:
    """Batafsil statistika."""
    q = update.callback_query
    user = await db.get_user(target)
    if not user:
        await q.edit_message_text("❌ Topilmadi.")
        return

    chats = await db.get_chats(target)
    posts = await db.get_posts(target)
    referrals = await db.count_referrals(target)

    lines = [
        f"📊 BATAFSIL — {user.get('name', 'Noma`lum')}",
        "",
        f"🆔 {target}",
        f"📱 {user.get('phone', '—')}",
        f"👥 Referallar: {referrals} ta",
        "",
        f"💬 GURUHLAR ({len(chats)}):",
    ]
    for i, g in enumerate(chats[:10], 1):
        lines.append(f"  {i}. {truncate(g, 40)}")
    if len(chats) > 10:
        lines.append(f"  ... yana {len(chats) - 10} ta")

    lines.append("")
    lines.append(f"📝 POSTLAR ({len(posts)}):")
    for i, p in enumerate(posts[:5], 1):
        text = (p.get("text") or "(rasm)").replace("\n", " ")
        icon = "🖼" if p.get("photo") else "📄"
        lines.append(f"  {i}. {icon} {truncate(text, 40)}")
    if len(posts) > 5:
        lines.append(f"  ... yana {len(posts) - 5} ta")

    with contextlib.suppress(Exception):
        await q.edit_message_text(
            "\n".join(lines),
            reply_markup=await user_card_markup(target),
        )
