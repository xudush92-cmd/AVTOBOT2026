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

from bot import keyboards as KB
from bot import texts as T
from bot.login import (
    LoginCtx,
    cleanup_login,
    describe_code_delivery,
    finalize_login,
    login_ctx,
    mask_phone,
    user_states as login_states,
)
from config.config import API_HASH, API_ID, SUPER_ADMIN
from core import database as db
from core.logger import log
from core.utils import format_expires, truncate


# ─────────────────────────────────────────────────────────────────────────
# APPLICATION (main.py da o'rnatiladi)
# ─────────────────────────────────────────────────────────────────────────
application = None


def set_application(app) -> None:
    global application
    application = app


# ─────────────────────────────────────────────────────────────────────────
# YANGI FOYDALANUVCHI QO'SHISH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_user(update: Update, admin_uid: int) -> None:
    """Super admin panelidan yangi Telegram akkauntini qo'shishni boshlaydi."""
    if admin_uid != SUPER_ADMIN:
        return

    await cleanup_login(admin_uid)
    login_states[admin_uid] = {
        "step": "admin_new_user_name",
        "ts": time.time(),
    }
    await update.callback_query.edit_message_text(
        T.ADMIN_ADD_USER_NAME,
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

    existing = next(
        (
            user
            for user in await db.get_all_users()
            if user.get("phone") == phone
        ),
        None,
    )
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
            ),
        )
        return

    # Eski tugallanmagan yaratish jarayoni/client qolib ketmasin.
    await cleanup_login(admin_uid)

    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await asyncio.wait_for(
            client.send_code_request(phone), timeout=30
        )
        destination, type_name, next_name, delivery_timeout = (
            describe_code_delivery(result)
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
            log(
                f"✅ Admin user qo'shish kodsiz tasdiqlandi: "
                f"phone={mask_phone(phone)}"
            )
            await finalize_login(admin_uid)
            return

        if not phone_code_hash:
            raise RuntimeError(
                f"Telegram {type_name} qaytardi, phone_code_hash yo'q"
            )

        login_states[admin_uid] = {
            "step": "admin_code_input",
            "ts": time.time(),
            "admin_add_user": True,
        }
        await application.bot.send_message(
            admin_uid,
            "➕ FOYDALANUVCHI QO'SHISH\n\n"
            f"👤 {full_name}\n"
            f"📱 {phone}\n\n"
            "✅ Telegram kod so'rovini qabul qildi.\n"
            f"📍 Yetkazish: {destination}\n\n"
            "Kelgan kodni kiriting. Jarayonni istalgan payt pastdagi "
            "tugma bilan to'xtatishingiz mumkin.",
            reply_markup=KB.kb_admin_add_user_cancel(),
        )
        log(
            f"📩 Admin yangi user kodi: admin={admin_uid} "
            f"phone={mask_phone(phone)} delivery={type_name} "
            f"next={next_name} timeout={delivery_timeout}"
        )

    except Exception as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        login_ctx.pop(admin_uid, None)
        login_states.pop(admin_uid, None)
        log(
            f"❌ request_new_user_session: {type(e).__name__}: {e}",
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
    if action == "logout":
        await action_logout(update, admin_uid, target)
        return
    if action == "addg":
        await action_add_group(update, admin_uid, target)
        return
    if action == "addp":
        await action_add_post(update, admin_uid, target)
        return
    if action == "expire":
        await action_show_expire(update, admin_uid, target)
        return
    if action == "block":
        await action_block(update, admin_uid, target)
        return
    if action == "unblock":
        await action_unblock(update, admin_uid, target)
        return
    if action == "delete":
        await action_delete(update, admin_uid, target)
        return
    if action == "detail":
        await action_detail(update, admin_uid, target)
        return
    if action == "back":
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
    blocked = user.get("is_blocked")
    running = user.get("running")
    expires = user.get("tariff_expires_at")
    chats = await db.count_chats(target)
    posts = await db.count_posts(target)
    interval = user.get("interval_min", 60)

    if blocked:
        state = "🚫 Bloklangan"
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
        f"⏰ Vaqt: {interval} daqiqa"
    )

    kb = KB.kb_user_card(
        target,
        running=running,
        blocked=blocked,
        has_session=bool(user.get("session")),
    )
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=kb)
      

# ─────────────────────────────────────────────────────────────────────────
# START / STOP
# ─────────────────────────────────────────────────────────────────────────
async def action_start(update: Update, admin_uid: int, target: int) -> None:
    """Admin nomidan postingni boshlash."""
    q = update.callback_query
    from bot.menu import worker_manager

    if not worker_manager:
        await q.edit_message_text("❌ Worker manager topilmadi.")
        return

    if worker_manager.is_running(target):
        await q.edit_message_text("⚠️ Allaqachon ishlamoqda.")
        return

    if await db.is_tariff_expired(target):
        await q.edit_message_text(
            "⏸ Foydalanuvchi muddati tugagan.",
            reply_markup=KB.kb_user_card(target),
        )
        return

    chats = await db.get_chats(target)
    posts = await db.get_posts(target)
    if not chats or not posts:
        await q.edit_message_text(
            "❌ Guruh yoki post yo'q.",
            reply_markup=KB.kb_user_card(target),
        )
        return

    started = await worker_manager.start_worker(target)
    if not started:
        await q.edit_message_text(
            "⚠️ Tizim band. Qaytadan urinib ko'ring.",
            reply_markup=KB.kb_user_card(target),
        )
        return

    await db.set_running(target, True)
    log(f"▶️ Admin {admin_uid} → Start {target}")
    await q.edit_message_text(
        f"✅ {target} uchun posting boshlandi.",
        reply_markup=KB.kb_user_card(target, running=True),
    )


async def action_stop(update: Update, admin_uid: int, target: int) -> None:
    """Admin nomidan postingni to‘xtatish."""
    q = update.callback_query
    from bot.menu import worker_manager

    if worker_manager:
        await worker_manager.stop_worker(target)
    await db.set_running(target, False)

    log(f"⛔ Admin {admin_uid} → Stop {target}")
    await q.edit_message_text(
        f"⛔ {target} uchun posting to'xtatildi.",
        reply_markup=KB.kb_user_card(target, running=False),
    )


# ─────────────────────────────────────────────────────────────────────────
# SESSIYA OCHISH
# ─────────────────────────────────────────────────────────────────────────
async def action_open_session(update: Update, admin_uid: int, target: int) -> None:
    """
    Admin foydalanuvchi nomidan sessiya ochadi.

    1. Kod so'raladi (request_code ISHLATILMAYDI)
    2. Admin kodni matn sifatida kiritadi
    3. attempt_signin chaqiriladi
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
            reply_markup=KB.kb_user_card(target, has_session=True),
        )
        return

    phone = user.get("phone")
    if not phone:
        await q.edit_message_text(
            "❌ Foydalanuvchining telefon raqami yo'q.",
            reply_markup=KB.kb_user_card(target, has_session=False),
        )
        return

    # Oldingi tugallanmagan admin loginini client bilan birga yopamiz.
    await cleanup_login(admin_uid)

    # To'g'ridan-to'g'ri kod so'raymiz (request_code ni chaqirmaymiz!)
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await asyncio.wait_for(
            client.send_code_request(phone), timeout=30
        )
        destination, type_name, next_name, delivery_timeout = (
            describe_code_delivery(result)
        )
        phone_code_hash = getattr(result, "phone_code_hash", "") or ""
        if not phone_code_hash:
            raise RuntimeError(f"{type_name}: phone_code_hash yo'q")

        login_ctx[admin_uid] = LoginCtx(
            client=client,
            phone=phone,
            phone_code_hash=phone_code_hash,
            started_at=time.time(),
            for_uid=target,
            target_name=user.get("name", ""),
        )

        login_states[admin_uid] = {
            "step": "admin_code_input",
            "ts": time.time(),
            "target_uid": target,
        }

        await q.edit_message_text(
            f"🔑 Sessiyani ulash\n\n"
            f"👤 {user.get('name')}\n"
            f"📱 {phone}\n\n"
            f"✅ Telegram kod so'rovini qabul qildi.\n"
            f"📍 Yetkazish: {destination}\n\n"
            f"Foydalanuvchidan kodni Telegramdan tashqari xavfsiz kanal orqali "
            f"olib, shu yerga kiriting.\n\n"
            f"⚠️ Kodni Telegram xabari qilib yuborish uni bekor qilishi mumkin."
        )

        log(
            f"📩 Admin kod so'rovi: admin={admin_uid} target={target} "
            f"phone={mask_phone(phone)} delivery={type_name} "
            f"next={next_name} timeout={delivery_timeout}"
        )

    except Exception as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        login_ctx.pop(admin_uid, None)
        login_states.pop(admin_uid, None)
        log(f"❌ action_open_session xato: {type(e).__name__}: {e}", "error")
        await q.edit_message_text(
            f"❌ Kod so'ralmadi: {type(e).__name__}\n\n"
            f"Qaytadan urinib ko'ring.",
            reply_markup=KB.kb_user_card(target, has_session=False),
        )


async def action_logout(update: Update, admin_uid: int, target: int) -> None:
    """Foydalanuvchi sessiyasini o‘chirish."""
    q = update.callback_query
    from bot.menu import worker_manager

    if worker_manager:
        await worker_manager.stop_worker(target)
    from worker.worker import client_pool
    if client_pool:
        await client_pool.remove(target)
    await db.del_session(target)
    await db.set_running(target, False)

    log(f"🚪 Admin {admin_uid} → Logout {target}")
    await q.edit_message_text(
        f"🚪 {target} sessiyasi o'chirildi.",
        reply_markup=KB.kb_user_card(target, has_session=False),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            "🚪 Admin sizning sessiyangizni o'chirdi.\n\n"
            "Qaytadan 🔑 Login qiling.",
            reply_markup=KB.kb_login(),
        )


# ─────────────────────────────────────────────────────────────────────────
# GURUH / POST QO'SHISH
# ─────────────────────────────────────────────────────────────────────────
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
        f"@guruh1\n@guruh2\n..."
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
        f"Post matni yoki rasm yuboring."
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
        f"Necha kun qo'shamiz?",
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
            f"Masalan: 30"
        )
        return

    try:
        days = int(days_str)
    except ValueError:
        return

    from datetime import datetime, timedelta, timezone

    current = await db.get_tariff_expires(target)
    if current:
        try:
            dt = datetime.strptime(current, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            if dt < datetime.now(timezone.utc):
                dt = datetime.now(timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    new_dt = dt + timedelta(days=days)
    new_iso = new_dt.strftime("%Y-%m-%d %H:%M:%S")

    await db.set_tariff_expires(target, new_iso)

    log(f"⏰ Admin {admin_uid} → {target} +{days} kun")
    await q.edit_message_text(
        f"✅ Muddat uzaytirildi: +{days} kun\n"
        f"Yangi muddat: {new_iso[:10]}",
        reply_markup=KB.kb_user_card(target),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            f"✅ Tarifingiz uzaytirildi!\n\n"
            f"📅 Yangi muddat: {new_iso[:10]}",
        )


# ─────────────────────────────────────────────────────────────────────────
# BLOK / O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def action_block(update: Update, admin_uid: int, target: int) -> None:
    """Foydalanuvchini bloklash."""
    q = update.callback_query
    from bot.menu import worker_manager

    if worker_manager:
        await worker_manager.stop_worker(target)
    await db.set_blocked(target, True)
    await db.set_running(target, False)

    log(f"🚫 Admin {admin_uid} → Block {target}")
    await q.edit_message_text(
        f"🚫 {target} bloklandi.",
        reply_markup=KB.kb_user_card(target, blocked=True),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target, T.BLOCKED, reply_markup=KB.kb_blocked()
        )


async def action_unblock(update: Update, admin_uid: int, target: int) -> None:
    """Blokdan chiqarish."""
    q = update.callback_query
    await db.set_blocked(target, False)
    log(f"🔓 Admin {admin_uid} → Unblock {target}")

    await q.edit_message_text(
        f"🔓 {target} blokdan chiqarildi.",
        reply_markup=KB.kb_user_card(target, blocked=False),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            "✅ Hisobingiz blokdan chiqarildi.\n\n🔑 Login bosing.",
            reply_markup=KB.kb_login(),
        )


async def action_delete(update: Update, admin_uid: int, target: int) -> None:
    """Foydalanuvchini butunlay o‘chirish."""
    q = update.callback_query
    from bot.menu import worker_manager

    if worker_manager:
        await worker_manager.stop_worker(target)
    from worker.worker import client_pool
    if client_pool:
        await client_pool.remove(target)

    await db.delete_user(target)
    log(f"🗑 Admin {admin_uid} → Delete {target}")

    await q.edit_message_text(
        f"🗑 {target} butunlay o'chirildi.",
        reply_markup=KB.kb_admin_back(),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target, "❌ Hisobingiz o'chirildi."
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
            reply_markup=KB.kb_user_card(target),
        )
