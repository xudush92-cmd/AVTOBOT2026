"""
AVTOBOT v2 — asosiy ishga tushiruvchi fayl.

Ishga tushirish:
    python main.py
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Admin modullari
from admin import admin_actions as AA
from admin import admin_panel as AP
from admin import auto_approve as AutoApprove
from admin import broadcast as BC

# Bot modullari
from bot import callbacks as CB
from bot import keyboards as KB
from bot import login as Login
from bot import menu as Menu
from bot import teams as Teams
from bot import texts as T

# Config
from config.config import (
    API_HASH,
    API_ID,
    AUTO_APPROVE_CHECK_INTERVAL_S,
    BACKUP_RETENTION,
    BOT_TOKEN,
    CLEANUP_INTERVAL_S,
    EXPIRY_CHECK_INTERVAL_S,
    LOGIN_TIMEOUT_S,
    MAX_CLIENT_POOL,
    MAX_CONCURRENT_WORKERS,
    MAX_INTERVAL_MIN,
    MAX_ISOLATED_CLIENTS,
    SUPER_ADMIN,
    TELEGRAM_CONNECT_TIMEOUT,
    TELEGRAM_CONNECTION_POOL_SIZE,
    TELEGRAM_GET_UPDATES_POOL_TIMEOUT,
    TELEGRAM_GET_UPDATES_READ_TIMEOUT,
    TELEGRAM_POOL_TIMEOUT,
    TELEGRAM_READ_TIMEOUT,
    TELEGRAM_WRITE_TIMEOUT,
)

# Core
from core import database as db
from core.errlog import log_error, log_gap
from core.logger import log
from core.rate_limit import RateLimiter
from core.update_locks import user_operation_lock, user_update_lock
from core.utils import (
    format_expires,
    is_valid_full_name,
    is_valid_interval,
    is_valid_phone,
    prune_old_backups,
    prune_orphan_media,
)

# Worker
from worker import health as Health
from worker import worker as Worker
from worker.client_pool import ClientPool

# ─────────────────────────────────────────────────────────────────────────
# GLOBAL
# ─────────────────────────────────────────────────────────────────────────
# Kirish oynasida ham bosilishi mumkin bo'lgan menyu tugmalari.
# Ulardan biri bosilsa, kiritish oynasi bekor qilinadi va tugma
# oddiy menyudagidek bajariladi.
MENU_BUTTONS = frozenset(
    {
        T.BTN_FIND_GROUPS,
        T.BTN_DEL_GROUP,
        T.BTN_GROUPS,
        T.BTN_GROUP_INTERVAL,
        T.BTN_ADD_POST,
        T.BTN_DEL_POST,
        T.BTN_TIMER,
        T.BTN_INTERVAL,
        T.BTN_REFERRAL,
        T.BTN_TEAM_ADMIN,
        T.BTN_TEAM_MENU,
        T.BTN_TEAM_PICK,
    }
)

rate_limiter = RateLimiter()
application: Application | None = None
client_pool: ClientPool | None = None
worker_manager: Worker.WorkerManager | None = None
health_server: Health.HealthServer | None = None


# ─────────────────────────────────────────────────────────────────────────
# SUPER ADMIN MENYUSI
# ─────────────────────────────────────────────────────────────────────────
async def send_super_admin_panel(message) -> None:
    """Super admin uchun reklama menyusisiz boshqaruv panelini yuboradi."""
    stats = await db.get_stats()
    await message.reply_text(
        "🖥 SUPER ADMIN PANEL\n\n"
        f"👥 Foydalanuvchilar: {stats['total_users']} ta\n"
        f"✅ Tasdiqlangan: {stats['admins']} ta\n"
        f"⏳ Kutayotgan: {stats['waiting']} ta\n"
        f"🟢 Faol: {stats['running']} ta\n"
        f"🚫 Bloklangan: {stats['blocked']} ta\n\n"
        "Kerakli bo'limni tanlang:",
        reply_markup=KB.kb_admin_panel(),
    )


# ─────────────────────────────────────────────────────────────────────────
# LOGIN KIRISH NUQTASI (RATE LIMIT BILAN)
# ─────────────────────────────────────────────────────────────────────────
async def start_login_with_limit(update: Update, uid: int) -> None:
    """UID login limitini tekshirib, login/ro'yxatdan o'tishni boshlaydi.

    Yangi va tasdiqlanmagan foydalanuvchilar ham xuddi shu limitga (3 ta/soat)
    tushadi, shuning uchun uni /start orqali aylanib o'tib bo'lmaydi.
    """
    if not rate_limiter.is_allowed(uid, "login"):
        wait_min = rate_limiter.get_wait_time(uid, "login")
        await update.message.reply_text(T.rate_limit_text(wait_min))
        return
    await Login.begin_login(update)


# ─────────────────────────────────────────────────────────────────────────
# /help va /status
# ─────────────────────────────────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Bot ichidagi qisqa yo'riqnoma (matn yozib bo'lmas foydalanuvchilar uchun)."""
    uid = update.effective_user.id
    async with user_update_lock(uid):
        user = await db.get_user(uid)
        approved = bool(user and user.get("is_admin") and not user.get("awaiting_approval"))
        if uid == SUPER_ADMIN or not approved:
            await update.message.reply_text(T.WELCOME_SHORT)
            return
        await update.message.reply_text(
            T.HELP_TEXT,
            reply_markup=await get_menu(uid),
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/status — olib tashlangan; foydalanuvchiga qisqa yo'riqnoma."""
    uid = update.effective_user.id
    async with user_update_lock(uid):
        user = await db.get_user(uid)
        if uid == SUPER_ADMIN or not (user and user.get("is_admin")):
            await update.message.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
            return
        await update.message.reply_text(
            "ℹ️ «Status» va «Hisobot» olib tashlangan.\n\n"
            "Holatni «▶️ Start» / «⛔ Stop» tugmalari orqali boshqarasiz.",
            reply_markup=await get_menu(uid),
        )


# ─────────────────────────────────────────────────────────────────────────
# /start COMMAND
# ─────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    async with user_update_lock(uid):
        await _cmd_start_locked(update, context)


async def _auto_assign_team_from_link(
    update: Update, uid: int, arg: str
) -> bool:
    """``/start team_<id>`` havolasidan kelgan user.

    Jamoa avtomatik tanlanadi (tasdiq admin tomonidan beriladi). Muvaffaqiyat
    bo'lsa ``True`` qaytaradi.

    Eslatma: ``adm_<uid>`` (shaxsiy jamoa havolasi) olib tashlangan —
    jamoalar faqat **umumiy** referal havolasi orqali to'ldiriladi.
    """
    if not isinstance(arg, str):
        return False

    team_id: int | None = None
    owner_uid = 0

    if arg.startswith("team_") and arg[5:].isdigit():
        team_id = int(arg[5:])
    else:
        return False

    if team_id is None:
        return False

    team = await db.get_team(team_id)
    if not team:
        return False

    if not await db.team_has_free_slot(team_id):
        await update.message.reply_text(T.TEAM_PICK_FULL, reply_markup=KB.kb_login())
        return True

    owner_uid = int(team.get("owner_admin_uid") or owner_uid or 0)
    if owner_uid and owner_uid != SUPER_ADMIN:
        if await db.team_admin_expired(owner_uid):
            await update.message.reply_text(
                T.TEAM_ADMIN_EXPIRED.format(expires="—"),
                reply_markup=KB.kb_login(),
            )
            return True

    saved = await db.set_team_pending(
        uid,
        team_id,
        owner_uid,
        name=update.effective_user.full_name or "",
        username=update.effective_user.username or "",
    )
    if not saved:
        return False

    name = team.get("name") or "Noma'lum"
    await update.message.reply_text(
        T.TEAM_SELECTED.format(name=name),
        reply_markup=KB.kb_login(),
    )
    return True


async def _cmd_start_locked(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start buyrug'i; private chatdan tashqarida PII oqimini boshlamaydi."""
    uid = update.effective_user.id
    effective_chat = getattr(update, "effective_chat", None)
    if effective_chat and effective_chat.type != "private":
        await update.message.reply_text(
            "🔒 AVTOBOT ro'yxatdan o'tish va boshqaruv uchun faqat private chatda ishlaydi.\n\n"
            "Bot profilini ochib, shaxsiy chatda /start bosing."
        )
        return

    # Rate limit
    if not rate_limiter.is_allowed(uid, "command"):
        wait_min = rate_limiter.get_wait_time(uid, "command")
        await update.message.reply_text(T.rate_limit_text(wait_min))
        return

    # Super admin oddiy user sessiyasi/reklama menyusiga bog'liq emas.
    if uid == SUPER_ADMIN:
        await Login.cleanup_login(uid)
        await db.upsert_user(SUPER_ADMIN, is_admin=1)
        await update.message.reply_text(
            "🛡 Super admin boshqaruv rejimi.",
            reply_markup=KB.kb_super_admin(),
        )
        await send_super_admin_panel(update.message)
        return

    # Bloklangan user referral yoki boshqa holatni o'zgartirmaydi.
    if await db.is_blocked(uid):
        await update.message.reply_text(
            T.BLOCKED,
            reply_markup=KB.kb_blocked(),
        )
        return

    # Referral faqat yangi/tasdiqlanmagan foydalanuvchiga bir marta bog'lanadi.
    if context.args:
        arg = context.args[0]
        if arg == "refshare":
            # Do'stlarga yuborish uchun tayyor matn — foydalanuvchi uni
            # forward qilib yuboradi (havolani qo'lda nusxalamasligi uchun).
            from bot.referral import share_referral_message

            await update.message.reply_text(await share_referral_message(uid))
            return
        with contextlib.suppress(Exception):
            from bot.referral import register_referral

            await register_referral(uid, arg)

    user = await db.get_user(uid)

    # Yangi user — ro'yxatdan o'tish darhol ism-familiyadan boshlanadi.
    if not user:
        # Jamoa adminiga havoladan kelgan user — jamoasi avtomatik tanlanadi.
        if context.args:
            await _auto_assign_team_from_link(update, uid, context.args[0])
        await start_login_with_limit(update, uid)
        return

    current_username = update.effective_user.username or ""
    if user.get("username", "") != current_username:
        await db.upsert_user(uid, username=current_username)
        user["username"] = current_username

    # Tasdiq kutilmoqda
    if user.get("awaiting_approval"):
        await update.message.reply_text(
            T.LOGIN_ALREADY_PENDING,
            reply_markup=KB.kb_pending(),
        )
        return

    if not user.get("is_admin"):
        await start_login_with_limit(update, uid)
        return

    # Sessiya yo'q — login oqimi xuddi shu limit ostida boshlanadi.
    if not user.get("session"):
        await start_login_with_limit(update, uid)
        return

    # Sessiya bor — menyu
    running = worker_manager.is_running(uid) if worker_manager else False

    name = user.get("name") or "Foydalanuvchi"
    await update.message.reply_text(
        f"🤖 AVTOBOT\n\n"
        f"👤 {name}\n"
        f"📊 Holat: {'🟢 Ishlamoqda' if running else '🔴 Toʻxtatilgan'}\n\n"
        f"Menyudan kerakli amalni tanlang:",
        reply_markup=KB.kb_main(
            running=running,
            team_admin=bool(user.get("is_team_admin")),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────
# MESSAGE HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Private chatdagi xabarlar.

    Xato yuz bersa — foydalanuvchi javob olmay qolmasin: logga to'liq
    traceback yoziladi va foydalanuvchiga «Xatolik yuz berdi» yuboriladi.
    """
    uid = update.effective_user.id
    try:
        async with user_update_lock(uid):
            await _on_message_locked(update, context)
    except Exception as exc:  # noqa: BLE001
        log_error(
            uid,
            "Matnli xabarni qayta ishlash",
            exc,
            action=(update.message.text or "")[:40] if update.message else None,
        )
        with contextlib.suppress(Exception):
            await update.effective_message.reply_text(T.GENERIC_ERROR)


async def _on_message_locked(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Private chatdagi oddiy xabarlar."""
    uid = update.effective_user.id
    msg = update.message
    text = (msg.text or "").strip()
    state = Login.user_states.get(uid, {})
    step = state.get("step")

    # ── LOGIN FSM ──
    if step in ("full_name", "phone", "code", "qr", "password"):
        # Kirish oynasida menyu tugmasi bosilsa, kiritish oynasi bekor
        # qilinadi va tugma oddiy menyudagidek bajariladi (masalan
        # «👑 Admin bo'lish» — jamoa yaratish oqimini boshladi).
        if text in MENU_BUTTONS:
            Login.user_states.pop(uid, None)
            log_gap(uid, "Kiritish oynasi bekor qilindi", action="login_fsm")
            await msg.reply_text("ℹ️ Oldingi kiritish oynasi bekor qilindi.")
            handled = await Menu.route_menu_button(update, text)
            if not handled:
                await msg.reply_text(
                    T.USE_MENU_BUTTONS, reply_markup=await get_menu(uid)
                )
            return
        if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
            admin_flow = bool(state.get("admin_add_user")) or uid == SUPER_ADMIN
            log_gap(uid, "Kiritish oynasi vaqti tugadi", action="login_fsm")
            await Login.cleanup_login(uid)
            await msg.reply_text(
                T.CODE_TIMEOUT,
                reply_markup=(KB.kb_super_admin() if admin_flow else KB.kb_login()),
            )
            return
        if text == T.BTN_BACK:
            await Login.cleanup_login(uid)
            await msg.reply_text(
                T.ACTION_CANCELLED,
                reply_markup=(
                    KB.kb_super_admin() if uid == SUPER_ADMIN else KB.kb_login()
                ),
            )
            return
        if not rate_limiter.is_allowed(uid, "message"):
            await msg.reply_text(
                T.rate_limit_text(rate_limiter.get_wait_time(uid, "message"))
            )
            return
        if step == "full_name":
            await Login.handle_full_name(update, text)
            return
        if step == "phone":
            await Login.handle_phone(update, text)
            return
        if step == "code":
            await Login.handle_code(update, text)
            return
        if step == "qr":
            await Login.handle_qr_waiting(update)
            return
        if step == "password":
            await Login.handle_password(update, text)
            return

    # ── JAMOA FSM ──
    if step in (
        "team_admin_size",
        "team_admin_name",
        "team_admin_message",
        "team_admin_rename",
        "team_add_friend",
    ):
        if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
            Login.user_states.pop(uid, None)
            await msg.reply_text(
                "⏰ Kiritish oynasi eskirdi. Amalni qaytadan boshlang.",
                reply_markup=await get_menu(uid),
            )
            return
        if text == T.BTN_BACK:
            Login.user_states.pop(uid, None)
            log_gap(uid, "Amal bekor qilindi", action="menu_fsm")
            await msg.reply_text(
                T.ACTION_CANCELLED, reply_markup=await get_menu(uid)
            )
            return
        if not rate_limiter.is_allowed(uid, "message"):
            await msg.reply_text(
                T.rate_limit_text(rate_limiter.get_wait_time(uid, "message"))
            )
            return
        if step == "team_admin_size":
            await Teams.handle_team_admin_size(update, uid, text)
            return
        if step == "team_admin_name":
            await Teams.handle_team_admin_name(update, uid, text)
            return
        if step == "team_add_friend":
            await Teams.handle_add_friend_phone(update, uid, text)
            return
        if step == "team_admin_message":
            await Teams.send_team_message(update, uid, text)
            return
        if step == "team_admin_rename":
            await Teams.handle_team_admin_rename(update, uid, text)
            return

    # ── SUPER ADMIN: yangi jamoa admini qo'shish ──
    if step == "super_add_team_admin":
        if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
            Login.user_states.pop(uid, None)
            await msg.reply_text(
                "⏰ Kiritish oynasi eskirdi. Amalni qaytadan boshlang.",
                reply_markup=KB.kb_admin_back(),
            )
            return
        if text == T.BTN_BACK:
            Login.user_states.pop(uid, None)
            log_gap(uid, "Amal bekor qilindi", action="admin_fsm")
            await msg.reply_text(T.ACTION_CANCELLED, reply_markup=KB.kb_admin_back())
            return
        if not rate_limiter.is_allowed(uid, "message"):
            await msg.reply_text(
                T.rate_limit_text(rate_limiter.get_wait_time(uid, "message"))
            )
            return
        await AP.handle_add_team_admin_phone(update, uid, text)
        return

    # ── ADMIN FSM ──
    if step in (
        "admin_new_user_full_name",
        "admin_new_user_phone",
        "admin_add_group",
        "admin_add_post",
        "admin_set_interval",
        "admin_set_group_interval",
        "admin_set_expire",
        "admin_broadcast",
        "admin_user_message",
    ):
        if uid != SUPER_ADMIN:
            return
        if text == T.BTN_ADMIN:
            await Login.cleanup_login(uid)
            BC.broadcast_pending.pop(uid, None)
            await send_super_admin_panel(msg)
            return
        if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
            Login.user_states.pop(uid, None)
            if step == "admin_broadcast":
                BC.broadcast_pending.pop(uid, None)
            await msg.reply_text(
                "⏰ Admin kiritish oynasi eskirdi. Amalni qaytadan boshlang.",
                reply_markup=KB.kb_super_admin(),
            )
            return
        target_uid = state.get("target_uid")
        if target_uid is None:
            await handle_admin_fsm(update, uid, step, text)
        else:
            async with user_operation_lock(int(target_uid)):
                await handle_admin_fsm(update, uid, step, text)
        return

    # ── SUPER ADMIN: faqat boshqaruv paneli ──
    if uid == SUPER_ADMIN:
        if text == T.BTN_ADMIN:
            await send_super_admin_panel(msg)
        else:
            await msg.reply_text(
                "🛡 Super admin uchun faqat boshqaruv paneli mavjud.",
                reply_markup=KB.kb_super_admin(),
            )
        return

    # ── RATE LIMIT ──
    if not rate_limiter.is_allowed(uid, "message"):
        wait_min = rate_limiter.get_wait_time(uid, "message")
        await msg.reply_text(T.rate_limit_text(wait_min))
        return

    # ── BLOKLANGAN ──
    if await db.is_blocked(uid):
        await msg.reply_text(T.BLOCKED, reply_markup=KB.kb_blocked())
        return

    # ── USER TEKSHIRISH ──
    user = await db.get_user(uid)
    if not user:
        if text == T.BTN_LOGIN:
            await start_login_with_limit(update, uid)
            return
        if text == T.BTN_TEAM_ADMIN:
            # Jamoa admini bo'lish — login'dan oldin ham mumkin.
            from bot import teams as Tm

            await Tm.begin_team_admin_register(update, uid)
            return
        await msg.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
        return

    if user.get("awaiting_approval"):
        await msg.reply_text(T.LOGIN_ALREADY_PENDING, reply_markup=KB.kb_pending())
        return

    if not user.get("is_admin"):
        if text == T.BTN_LOGIN:
            await start_login_with_limit(update, uid)
            return
        if text == T.BTN_TEAM_ADMIN:
            # Jamoa admini bo'lish — tasdiqlanish talab qilinmaydi.
            from bot import teams as Tm

            await Tm.begin_team_admin_register(update, uid)
            return
        await msg.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
        return

    # ── SESSIYA YO'Q ──
    if not user.get("session"):
        if text == T.BTN_LOGIN:
            await start_login_with_limit(update, uid)
            return
        if text == T.BTN_TEAM_ADMIN:
            # Jamoa admini bo'lish — sessiya talab qilinmaydi.
            from bot import teams as Tm

            await Tm.begin_team_admin_register(update, uid)
            return
        await msg.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
        return

    # ── FSM: add_post / set_interval (add_group va set_group_interval
    # faqat admin/legacy oqimlari uchun saqlangan) ──
    if step in (
        "add_group",
        "add_post",
        "set_interval",
        "set_interval_confirm",
        "set_group_interval",
        "my_group_interval_manual",
    ):
        menu_buttons = MENU_BUTTONS
        # Start/Stop/Status/Paket yorliqlari holatni o'zida olib yuradi
        # ("▶️ Start (🔴 OFF)") yoki eski klaviaturalarda qolgan bo'lishi mumkin.
        dynamic_prefixes = (
            T.BTN_START,
            T.BTN_STOP,
            T.BTN_STATUS,
            T.BTN_PLAN,
        )
        if text in menu_buttons or text.startswith(dynamic_prefixes):
            # Foydalanuvchi kiritish oynasini chetlab menyu tugmasini bosdi:
            # oyna yopiladi va tugma oddiy menyudagidek bajariladi.
            Login.user_states.pop(uid, None)
            await msg.reply_text("ℹ️ Oldingi kiritish oynasi bekor qilindi.")
            handled = await Menu.route_menu_button(update, text)
            if not handled:
                await msg.reply_text(
                    T.USE_MENU_BUTTONS, reply_markup=await get_menu(uid)
                )
            return
        if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
            Login.user_states.pop(uid, None)
            await msg.reply_text(
                "⏰ Kiritish oynasi eskirdi. Amalni qaytadan boshlang.",
                reply_markup=await get_menu(uid),
            )
            return
        if text == T.BTN_BACK:
            Login.user_states.pop(uid, None)
            log_gap(uid, "Amal bekor qilindi", action="menu_fsm")
            await msg.reply_text(
                T.ACTION_CANCELLED, reply_markup=await get_menu(uid)
            )
            return
        if step == "set_interval_confirm":
            await msg.reply_text("Pastdagi Ha/Yo'q tugmalaridan birini tanlang.")
            return
        if step == "add_group":
            from bot.groups import handle_add_groups

            async with user_operation_lock(uid):
                if not await _can_mutate_user_resources(uid):
                    Login.user_states.pop(uid, None)
                    await msg.reply_text(
                        "❌ Hisob yoki sessiya endi faol emas.",
                        reply_markup=KB.kb_login(),
                    )
                    return
                await handle_add_groups(update, text)
            return
        if step == "add_post":
            from bot.posts import handle_add_post

            async with user_operation_lock(uid):
                if not await _can_mutate_user_resources(uid):
                    Login.user_states.pop(uid, None)
                    await msg.reply_text(
                        "❌ Hisob yoki sessiya endi faol emas.",
                        reply_markup=KB.kb_login(),
                    )
                    return
                await handle_add_post(update)
            return
        if step == "set_interval":
            from bot.timer import handle_set_interval

            async with user_operation_lock(uid):
                if not await _can_mutate_user_resources(uid):
                    Login.user_states.pop(uid, None)
                    await msg.reply_text(
                        "❌ Hisob yoki sessiya endi faol emas.",
                        reply_markup=KB.kb_login(),
                    )
                    return
                await handle_set_interval(update, text)
            return
        if step == "set_group_interval":
            from bot.timer import handle_set_group_interval

            async with user_operation_lock(uid):
                if not await _can_mutate_user_resources(uid):
                    Login.user_states.pop(uid, None)
                    await msg.reply_text(
                        "❌ Hisob yoki sessiya endi faol emas.",
                        reply_markup=KB.kb_login(),
                    )
                    return
                await handle_set_group_interval(update, text)
            return

        if step == "my_group_interval_manual":
            from bot.my_groups import handle_manual_interval

            async with user_operation_lock(uid):
                if not await _can_mutate_user_resources(uid):
                    Login.user_states.pop(uid, None)
                    await msg.reply_text(
                        "❌ Hisob yoki sessiya endi faol emas.",
                        reply_markup=KB.kb_login(),
                    )
                    return
                await handle_manual_interval(update, uid, text)
            return

    # ── LOGIN TUGMASI ──
    if text == T.BTN_LOGIN:
        await msg.reply_text(
            "✅ Siz allaqachon kirgansiz.",
            reply_markup=await get_menu(uid),
        )
        return

    # ── MENYU TUGMALARI ──
    ok = await Menu.route_menu_button(update, text)
    if ok:
        return

    # ── NOMA'LUM ──
    await msg.reply_text(
        T.USE_MENU_BUTTONS,
        reply_markup=await get_menu(uid),
    )


# ─────────────────────────────────────────────────────────────────────────
# YORDAMCHILAR
# ─────────────────────────────────────────────────────────────────────────
async def _can_mutate_user_resources(uid: int) -> bool:
    """Operation lock olingach target hali ham faol ekanini qayta tekshiradi."""
    user = await db.get_user(uid)
    return bool(
        user
        and user.get("is_admin")
        and not user.get("is_blocked")
        and not user.get("awaiting_approval")
        and user.get("session")
    )


async def get_menu(uid: int):
    """Rolga va posting holatiga mos menyu."""
    if uid == SUPER_ADMIN:
        return KB.kb_super_admin()
    running = worker_manager.is_running(uid) if worker_manager else False
    user = await db.get_user(uid) or {}
    team_admin = bool(user.get("is_team_admin"))
    # Oddiy jamoa a'zosi ham "Jamoam" tugmasini ko'radi — undan chiqishi uchun.
    team_member = bool(user.get("team_id")) and not team_admin
    return KB.kb_main(
        running=running, team_admin=team_admin, team_member=team_member
    )


# ─────────────────────────────────────────────────────────────────────────
# ADMIN FSM
# ─────────────────────────────────────────────────────────────────────────
async def handle_admin_fsm(update: Update, uid: int, step: str, text: str) -> None:
    """Admin FSM handlerlari."""
    msg = update.message
    state = Login.user_states.get(uid, {})
    target = state.get("target_uid")

    # Caller target-operation lockni ushlab turadi; kutish davomida o'chirilgan
    # target uchun eski FSM xabari yangi resurs yaratmasligi kerak.
    if target is not None and not await db.get_user(int(target)):
        Login.user_states.pop(uid, None)
        await msg.reply_text(
            "❌ Foydalanuvchi endi mavjud emas. Amal bekor qilindi.",
            reply_markup=KB.kb_admin_panel(),
        )
        return

    # ── YANGI FOYDALANUVCHI: ISM VA FAMILIYA ──
    if step == "admin_new_user_full_name":
        full_name = " ".join(text.strip().split())
        if not is_valid_full_name(full_name):
            await msg.reply_text(
                T.ADMIN_ADD_USER_FULL_NAME_INVALID,
                reply_markup=KB.kb_admin_add_user_cancel(),
            )
            return

        state.update(
            step="admin_new_user_phone",
            full_name=full_name[:64],
            ts=time.time(),
        )
        Login.user_states[uid] = state
        await msg.reply_text(
            T.ADMIN_ADD_USER_PHONE,
            reply_markup=KB.kb_admin_add_user_cancel(),
        )
        return

    # ── YANGI FOYDALANUVCHI: TELEFON ──
    if step == "admin_new_user_phone":
        phone = text.strip().replace(" ", "").replace("-", "")
        if not is_valid_phone(phone):
            await msg.reply_text(
                T.PHONE_INVALID,
                reply_markup=KB.kb_admin_add_user_cancel(),
            )
            return

        full_name = state.get("full_name", "").strip()
        if not full_name:
            await Login.cleanup_login(uid)
            await msg.reply_text(
                "❌ Ism-familiya topilmadi. Jarayonni qaytadan boshlang.",
                reply_markup=KB.kb_admin_panel(),
            )
            return

        await msg.reply_text(
            f"⏳ {full_name} uchun Telegram kodi so'ralmoqda...",
            reply_markup=KB.kb_admin_add_user_cancel(),
        )
        await AA.request_new_user_session(uid, full_name, phone)
        return

    # ── GURUH QO'SHISH ──
    if step == "admin_add_group":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        from core.utils import group_reference_key, parse_group_lines_with_errors

        if not await db.get_session(target):
            Login.user_states.pop(uid, None)
            await msg.reply_text(
                f"❌ {target} sessiyasi yo'q.",
                reply_markup=await AA.user_card_markup(target),
            )
            return

        groups, invalid = parse_group_lines_with_errors(text)
        if not groups:
            await msg.reply_text(
                "❌ Guruh topilmadi yoki formati noto'g'ri. Qaytadan yuboring:"
            )
            return

        Login.user_states.pop(uid, None)
        status = await msg.reply_text(f"⏳ {len(groups)} ta guruh saqlanmoqda...")

        added, duplicates = [], []
        errors = [f"{value} (noto'g'ri format)" for value in invalid]
        existing = {group_reference_key(value) for value in await db.get_chats(target)}

        for group in groups:
            group_key = group_reference_key(group)
            if group_key in existing:
                duplicates.append(group)
                continue
            # Formatdan tashqari Telegram tarmog'i bu bosqichda tekshirilmaydi.
            # Guruh nomi (title) bu yerda bo'sh qoladi — foydalanuvchining
            # «💬 Guruhlar» oynasi ochilganda nomi fon task'da to'ldiriladi.
            saved, save_reason = await db.add_chat(target, group)
            if saved:
                added.append(group)
                existing.add(group_key)
            elif save_reason == "duplicate":
                duplicates.append(group)
            elif save_reason == "limit":
                limits = await db.get_limits(target)
                errors.append(
                    f"{group} (paket chegarasi: "
                    f"{limits.get('max_groups')} ta guruh)"
                )
                break
            else:
                errors.append(f"{group} (saqlashda xato)")

        await status.edit_text(
            T.groups_added_report(added, duplicates, errors),
            reply_markup=KB.kb_admin_groups(target, await db.get_chat_records(target)),
        )
        log(f"📊 Admin {uid} → {target} guruhlar +{len(added)}")
        return

    # ── POST QO'SHISH ──
    if step == "admin_add_post":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return
        if not await db.get_session(target):
            Login.user_states.pop(uid, None)
            await msg.reply_text(
                f"❌ {target} sessiyasi yo'q.",
                reply_markup=await AA.user_card_markup(target),
            )
            return

        # Media yuklash va post saqlash user oqimi bilan bir xil mantikada
        # (bot/media_ingest) — admin ham rasm, video va albom yubora oladi.
        from bot.media_ingest import (
            download_message_media,
            message_text_and_entities,
        )

        post_text, entities = message_text_and_entities(msg)
        items, errors = await download_message_media(msg, target)
        if errors and not items:
            await msg.reply_text("\n".join(errors))
            return
        if not post_text.strip() and not items:
            await msg.reply_text("❌ Bo'sh post.")
            return

        Login.user_states.pop(uid, None)
        ok, reason, post_id = await db.add_post(
            target, post_text, entities, None, items, True
        )
        if not ok:
            from bot.media_ingest import remove_media

            with contextlib.suppress(Exception):
                remove_media([item["path"] for item in items])
            await msg.reply_text(
                "❌ Saqlanmadi."
                if reason != "limit"
                else f"❌ Post limiti to'lgan ({await db.max_posts_for(target)} ta)."
            )
            return

        await msg.reply_text(
            f"✅ Post qo'shildi: {target} (#{post_id}, media={len(items)} ta)",
            reply_markup=KB.kb_admin_posts(target, await db.get_posts(target)),
        )
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                target,
                f"📝 Admin sizga yangi post qo'shdi.\n\n"
                f"Jami postlar: {await db.count_posts(target)} ta",
            )
        return

    # ── POSTING ORALIG'INI QO'LDA KIRITISH ──
    if step == "admin_set_interval":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        try:
            minutes = int(text)
            if minutes < 5 or minutes > MAX_INTERVAL_MIN:
                raise ValueError
        except ValueError:
            await msg.reply_text(f"❌ 5 dan {MAX_INTERVAL_MIN} gacha daqiqa kiriting.")
            return

        Login.user_states.pop(uid, None)
        await db.set_interval(target, minutes)
        log(f"⏱ Admin {uid} → {target} interval={minutes}")
        await msg.reply_text(
            f"✅ Umumiy posting oralig'i {minutes} daqiqaga o'rnatildi.\n"
            "Alohida sozlangan guruhlar o'z intervalini saqlaydi.\n"
            "Anti-spam uchun real vaqt 5 daqiqagacha farq qiladi.",
            reply_markup=await AA.user_card_markup(target),
        )
        return

    # ── GURUH INTERVALINI QO'LDA KIRITISH ──
    if step == "admin_set_group_interval":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        try:
            group_id = int(state.get("group_id"))
            minutes = int(text.strip())
            if not is_valid_interval(minutes):
                raise ValueError
        except (TypeError, ValueError):
            await msg.reply_text(
                f"❌ {T.MIN_INTERVAL_MIN}–{MAX_INTERVAL_MIN} orasida butun daqiqa kiriting."
            )
            return

        saved = await db.set_chat_interval(int(target), group_id, minutes)
        Login.user_states.pop(uid, None)
        if not saved:
            await msg.reply_text(
                "❌ Guruh topilmadi yoki sozlama saqlanmadi.",
                reply_markup=await AA.user_card_markup(int(target)),
            )
            return
        log(f"⏱ Admin {uid} → {target} guruh {group_id}: {minutes} daqiqa")
        await msg.reply_text(
            f"✅ {target} foydalanuvchisining guruh intervali "
            f"{minutes} daqiqaga o'rnatildi.",
            reply_markup=KB.kb_admin_groups(
                int(target), await db.get_chat_records(int(target))
            ),
        )
        return

    # ── MUDDATNI QO'LDA KIRITISH ──
    # Yangi muddat hozirdan boshlab hisoblanadi va oldingi muddatni bekor
    # qiladi (mavjud muddat ustiga qo'shilmaydi).
    if step == "admin_set_expire":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        try:
            days = int(text)
            if days < 1 or days > 3650:
                raise ValueError
        except ValueError:
            await msg.reply_text("❌ 1 dan 3650 gacha son kiriting.")
            return

        Login.user_states.pop(uid, None)

        result = await AA.give_new_term(uid, int(target), days)
        if result is None:
            await msg.reply_text(
                "❌ Foydalanuvchi endi mavjud emas. Amal bekor qilindi.",
                reply_markup=KB.kb_admin_panel(),
            )
            return

        previous, new_expires = result
        await msg.reply_text(
            T.new_term_admin_text(days, new_expires, previous),
            reply_markup=await AA.user_card_markup(target),
        )

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                target,
                T.new_term_user_text(new_expires),
            )
        return

    # ── FOYDALANUVCHIGA XABAR YUBORISH ──
    if step == "admin_user_message":
        Login.user_states.pop(uid, None)
        if target is None:
            await msg.reply_text(
                "❌ Xatolik. Qaytadan urinib ko'ring.",
                reply_markup=KB.kb_admin_panel(),
            )
            return
        try:
            await application.bot.send_message(int(target), text)
            sent = True
        except Exception:
            sent = False
        if sent:
            log(f"✉️ Admin {uid} → {target} xabar yuborildi")
        await msg.reply_text(
            (
                f"✅ Xabar yuborildi: {target}"
                if sent
                else "❌ Yuborilmadi (foydalanuvchi botni bloklagan bo'lishi mumkin)."
            ),
            reply_markup=await AA.user_card_markup(int(target)),
        )
        return

    # ── BROADCAST ──
    if step == "admin_broadcast":
        await BC.receive_broadcast(update)
        return


# ─────────────────────────────────────────────────────────────────────────
# STALE LOGIN JANITOR
# ─────────────────────────────────────────────────────────────────────────
async def expire_stale_logins() -> int:
    """Timestamp'li barcha tugallanmagan FSM holatlarini xavfsiz tozalaydi."""
    now = time.time()
    expired: set[int] = set()
    kinds: dict[int, str] = {}

    for uid, ctx in list(Login.login_ctx.items()):
        if now - ctx.started_at > LOGIN_TIMEOUT_S:
            expired.add(uid)
            kinds[uid] = (
                "admin"
                if ctx.mode == "admin_add_user" or ctx.for_uid is not None
                else "login"
            )

    login_steps = {"full_name", "phone", "code", "qr", "password"}
    for uid, state in list(Login.user_states.items()):
        timestamp = state.get("ts")
        if timestamp is None or now - timestamp <= LOGIN_TIMEOUT_S:
            continue
        expired.add(uid)
        step = str(state.get("step") or "")
        if (
            uid == SUPER_ADMIN
            or step.startswith("admin_")
            or state.get("admin_add_user")
        ):
            kinds[uid] = "admin"
        elif step in login_steps:
            kinds.setdefault(uid, "login")
        else:
            kinds.setdefault(uid, "input")

    cleaned = 0
    for uid in expired:
        async with user_update_lock(uid):
            # Snapshot olinganidan keyin kelgan yangi update holatni yangilagan
            # bo'lishi mumkin; yangi FSM'ni janitor adashib o'chirmaydi.
            ctx = Login.login_ctx.get(uid)
            state = Login.user_states.get(uid, {})
            ctx_stale = bool(ctx and now - ctx.started_at > LOGIN_TIMEOUT_S)
            timestamp = state.get("ts")
            state_stale = bool(
                timestamp is not None and now - timestamp > LOGIN_TIMEOUT_S
            )
            if not ctx_stale and not state_stale:
                continue

            with contextlib.suppress(Exception):
                await Login.cleanup_login(uid)
            if uid == SUPER_ADMIN:
                BC.broadcast_pending.pop(uid, None)
            cleaned += 1

            with contextlib.suppress(Exception):
                kind = kinds.get(uid, "login")
                if kind == "admin":
                    await application.bot.send_message(
                        uid,
                        "⏰ Admin kiritish oynasi eskirdi. Amalni qaytadan boshlang.",
                        reply_markup=KB.kb_super_admin(),
                    )
                elif kind == "input":
                    user = await db.get_user(uid)
                    running = bool(worker_manager and worker_manager.is_running(uid))
                    await application.bot.send_message(
                        uid,
                        "⏰ Kiritish oynasi eskirdi. Amalni qaytadan boshlang.",
                        reply_markup=(
                            await KB.kb_main_for(uid, running=running)
                            if user and user.get("is_admin") and user.get("session")
                            else KB.kb_login()
                        ),
                    )
                else:
                    await application.bot.send_message(
                        uid,
                        T.CODE_TIMEOUT,
                        reply_markup=KB.kb_login(),
                    )

    if cleaned:
        log(f"🧹 Stale FSM: {cleaned} ta tozalandi")
    return cleaned


async def janitor_tick() -> int:
    """Bir marta: stale loginlar, UID va telefon limit yozuvlarini tozalaydi.

    Qo'shimcha: yig'ilib, lekin yakunlanmay qolgan albom postlari ham
    saqlab qo'yiladi — foydalanuvchi «✅ Tayyor» tugmasini bosmasa ham
    media yo'qolib ketmaydi.
    """
    cleaned = 0
    with contextlib.suppress(Exception):
        cleaned = await expire_stale_logins()
    with contextlib.suppress(Exception):
        from bot.posts import sweep_stale_albums

        swept = await sweep_stale_albums()
        if swept:
            log(f"🖼 {swept} ta yakunlanmay qolgan albom saqlandi")
    rate_limiter.cleanup_all()
    Login.cleanup_phone_requests()
    Login.cleanup_sms_attempts()
    return cleaned


async def login_janitor_loop(stop: asyncio.Event) -> None:
    """Har daqiqada stale loginlarni tekshiradi."""
    log("🧹 Login janitor boshlandi")
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=60)
                break
            except asyncio.TimeoutError:
                pass
            await janitor_tick()
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────
# TARIFF JANITOR
# ─────────────────────────────────────────────────────────────────────────
async def check_tariff_expiry() -> int:
    """Muddati tugagan foydalanuvchilarni to'xtatadi."""
    expired = await db.get_expired_users()
    if not expired:
        await check_team_admin_expiry()
        return 0

    stopped = 0
    for uid in expired:
        async with user_operation_lock(uid):
            user = await db.get_user(uid)
            if (
                not user
                or not user.get("running")
                or not await db.is_tariff_expired(uid)
            ):
                continue
            if worker_manager and worker_manager.is_running(uid):
                await worker_manager.stop_worker(uid)
            if client_pool:
                await client_pool.remove(uid)
            await db.set_running(uid, False)
            stopped += 1
            with contextlib.suppress(Exception):
                await application.bot.send_message(
                    uid,
                    T.EXPIRED_TEXT,
                    reply_markup=await KB.kb_main_for(uid),
                )

        with contextlib.suppress(Exception):
            info = await db.get_user_info(uid)
            name = info.get("name") or str(uid)
            await application.bot.send_message(
                SUPER_ADMIN,
                f"⏰ Muddat tugadi\n\n👤 {name} ({uid})\nPosting to'xtatildi.",
            )

    if stopped:
        log(f"⏰ Tariff expiry: {stopped} ta to'xtatildi")
    await check_team_admin_expiry()
    return stopped


async def check_team_admin_expiry() -> int:
    """Muddati tugagan jamoa adminlarini va ularning jamoalarini to'xtatadi."""
    expired_admins = await db.get_expired_team_admins()
    if not expired_admins:
        return 0

    stopped = 0
    for admin_uid in expired_admins:
        admin = await db.get_user(admin_uid)
        if not admin:
            continue

        # Jamoa adminining o'zi ham to'xtaydi.
        targets: list[int] = [admin_uid]
        # Uning jamoasidagi foydalanuvchilar ham to'xtaydi.
        try:
            for member in await db.get_users_by_owner(admin_uid):
                targets.append(int(member["uid"]))
        except Exception as exc:  # pragma: no cover - himoya
            log(f"👥 Jamoa a'zolari o'qilmadi: {type(exc).__name__}", "error")

        for uid in targets:
            async with user_operation_lock(uid):
                user = await db.get_user(uid)
                if not user or not user.get("running"):
                    continue
                if worker_manager and worker_manager.is_running(uid):
                    await worker_manager.stop_worker(uid)
                if client_pool:
                    await client_pool.remove(uid)
                await db.set_running(uid, False)
                stopped += 1

            with contextlib.suppress(Exception):
                await application.bot.send_message(
                    uid,
                    T.EXPIRED_TEXT,
                    reply_markup=await KB.kb_main_for(uid),
                )

        # Adminga va super admin ga xabar.
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                admin_uid,
                T.TEAM_ADMIN_EXPIRED.format(
                    expires=format_expires(admin.get("admin_expires_at"))
                ),
                reply_markup=await KB.kb_main_for(admin_uid),
            )
        with contextlib.suppress(Exception):
            info = await db.get_user_info(admin_uid)
            await application.bot.send_message(
                SUPER_ADMIN,
                f"⌛ Jamoa admini muddati tugadi\n\n"
                f"👑 {info.get('name') or admin_uid} ({admin_uid})\n"
                f"Jamoasi to'xtatildi.\n"
                "Muddatni uzaytirish uchun: 🖥 Super Admin → 👑 Jamoa adminlari",
            )

    if stopped:
        log(f"⌛ Jamoa admini expiry: {stopped} ta to'xtatildi")
    return stopped


async def warn_last_day() -> None:
    """Oxirgi kun ogohlantirishini yuboradi (faqat bir marta)."""
    from core.utils import is_last_day

    users = await db.get_all_users()
    for snapshot in users:
        uid = snapshot.get("uid")
        if not uid:
            continue
        async with user_operation_lock(int(uid)):
            user = await db.get_user(int(uid))
            if (
                not user
                or not user.get("is_admin")
                or user.get("warned_at")
                or not is_last_day(user.get("tariff_expires_at"))
            ):
                continue
            try:
                await application.bot.send_message(uid, T.LAST_DAY_WARNING)
            except Exception:
                continue
            await db.mark_warned(int(uid))
            log(f"⚠️ Oxirgi kun ogohlantirishi: {uid}")


async def tariff_janitor_loop(stop: asyncio.Event) -> None:
    """Har soatda muddatni tekshiradi."""
    log("⏰ Tariff janitor boshlandi")
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=EXPIRY_CHECK_INTERVAL_S)
                break
            except asyncio.TimeoutError:
                pass
            with contextlib.suppress(Exception):
                await check_tariff_expiry()
            with contextlib.suppress(Exception):
                await warn_last_day()
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────
# TEZ TASDIQLASH JANITORI
# ─────────────────────────────────────────────────────────────────────────
async def auto_approve_tick() -> int:
    """Bir marta: past riskli arizalarni tasdiqlashga urinadi."""
    with contextlib.suppress(Exception):
        return await AutoApprove.auto_approve_once()
    return 0


async def auto_approve_loop(stop: asyncio.Event) -> None:
    """``AUTO_APPROVE_ENABLED=0`` bo'lsa faqat uyquda turadi (hech narsa qilmaydi)."""
    from config.config import AUTO_APPROVE_ENABLED

    if not AUTO_APPROVE_ENABLED:
        log("⚡ Avto-tasdiq o'chirilgan (admin navbati ishlaydi)")
        await stop.wait()
        return
    log("⚡ Avto-tasdiq janitori boshlandi")
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=AUTO_APPROVE_CHECK_INTERVAL_S
                )
                break
            except asyncio.TimeoutError:
                pass
            with contextlib.suppress(Exception):
                await auto_approve_tick()
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────
# CLEANUP JANITOR
# ─────────────────────────────────────────────────────────────────────────
async def cleanup_janitor_once() -> None:
    """Ortiqcha ma'lumotlarni bir marta tozalaydi."""
    # Bazada yo'q foydalanuvchilarning media (rasm) papkalari
    with contextlib.suppress(Exception):
        valid_uids = await db.get_all_uids()
        removed = prune_orphan_media(valid_uids)
        if removed:
            log(f"🧹 Media: {removed} ta yetim papka o'chirildi")

    # Eski backup/eksport nusxalari (disk to'lib ketmasligi uchun)
    with contextlib.suppress(Exception):
        removed = prune_old_backups(BACKUP_RETENTION)
        if removed:
            log(f"🧹 Zaxira: {removed} ta eski nusxa o'chirildi")

    # Eski yuborish yozuvlari (hisobot juda o'sib ketmasligi uchun)
    with contextlib.suppress(Exception):
        removed = await db.prune_send_logs()
        if removed:
            log(f"🧹 Hisobot: {removed} ta eski yuborish yozuvi o'chirildi")

    # Baza statistikasi va WAL hajmi
    with contextlib.suppress(Exception):
        await db.optimize_db()


async def cleanup_janitor_loop(stop: asyncio.Event) -> None:
    """Har CLEANUP_INTERVAL_S soniyada davriy tozalashni bajaradi."""
    log("🧽 Cleanup janitor boshlandi")
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=CLEANUP_INTERVAL_S)
                break
            except asyncio.TimeoutError:
                pass
            with contextlib.suppress(Exception):
                await cleanup_janitor_once()
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────
# RESTORE
# ─────────────────────────────────────────────────────────────────────────
async def restore_running_workers() -> None:
    """Restartdan keyin avval ishlagan workerlarni tiklaydi."""
    running = await db.get_all_running()
    restored = 0
    for uid in running:
        async with user_operation_lock(uid):
            user = await db.get_user(uid)
            chats = await db.get_chats(uid)
            posts = await db.get_posts(uid)
            if (
                not user
                or not user.get("running")
                or not user.get("is_admin")
                or user.get("is_blocked")
                or not user.get("session")
                or not chats
                or not posts
                or await db.is_tariff_expired(uid)
            ):
                await db.set_running(uid, False)
                continue
            if await worker_manager.start_worker(uid):
                restored += 1
            else:
                # Worker boshlanmadi (limit band yoki xato) — holatni
                # tuzatamiz, aks holda admin "ishlayapti" deb ko'radi.
                await db.set_running(uid, False)
    log(f"🔁 {restored} ta worker tiklandi")


# ─────────────────────────────────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB handler xatosi — to'liq traceback bilan yoziladi.

    Bu — oxirgi himoya chizig'i: handler'ning ichida xato ushlanmagan
    bo'lsa, shu yerda qayd etiladi va foydalanuvchiga javob beriladi.
    """
    error = context.error
    uid = None
    with contextlib.suppress(Exception):
        if update is not None and getattr(update, "effective_user", None):
            uid = update.effective_user.id
    log_error(uid, "PTB handler xatosi", error, action="handler")
    with contextlib.suppress(Exception):
        if update is not None and getattr(update, "effective_message", None):
            await update.effective_message.reply_text(T.GENERIC_ERROR)


# ─────────────────────────────────────────────────────────────────────────
# TELEGRAM STARTUP SO'ROVLARI
# ─────────────────────────────────────────────────────────────────────────
async def _with_retry(func, *, attempts: int = 3, delay: float = 5.0):
    """Telegram so'rovini bir necha marta urinib ko'radi.

    Telegram API vaqtincha javob bermay qolsa (``TimedOut``,
    ``NetworkError``), so'rovni darhol tashlab ketish botni butunlay
    o'ldiradi. Shu sabab bir necha urinish va oraliqda kutish.

    Barcha urinishlar muvaffaqiyatsiz bo'lsa, oxirgi xato raised bo'ladi.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return await func()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt >= attempts:
                break
            log(
                f"⚠️ Telegram so'rovi muvaffaqiyatsiz ({type(exc).__name__}: {exc})"
                f" — {attempt}/{attempts}, {delay:.0f}s dan keyin qayta uriniladi",
                "error",
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
    raise last_error if last_error else RuntimeError("Telegram so'rovi muvaffaqiyatsiz")


async def set_bot_commands(app: Application) -> bool:
    """Menyu buyruqlarini ro'ylaydi. Xato bo'lsa ham botni to'xtatmaydi.

    Faqat menyu buyruqlari uchun — muvaffaqiyatsiz bo'lishi botning
    ishlashiga halaqit bermaydi. Shu sabab xato yutiladi va logga yoziladi.
    """
    commands = [
        BotCommand("start", "Botni ochish / menyu"),
        BotCommand("help", "Qanday ishlaydi — qisqa yo'riqnoma"),
    ]
    try:
        await _with_retry(lambda: app.bot.set_my_commands(commands))
        return True
    except Exception as exc:  # noqa: BLE001
        log(
            f"⚠️ Menyu buyruqlari ro'ylanmadi ({type(exc).__name__}: {exc})"
            f" — bot ishlashda davom etadi",
            "error",
        )
        return False


# ─────────────────────────────────────────────────────────────────────────
# POLLING SUPERVISOR
# ─────────────────────────────────────────────────────────────────────────
def _get_polling_task(updater) -> asyncio.Task | None:
    """PTB ichidagi polling task'ini topadi.

    PTB atribut nomi versiyalar orasida o'zgargan bo'lishi mumkin, shu
    sabab bir necha nom tekshiriladi. Topilmasa ``None`` qaytariladi.
    """
    for attr in (
        "_Updater__polling_task",
        "_polling_task",
        "polling_task",
    ):
        task = getattr(updater, attr, None)
        if isinstance(task, asyncio.Task):
            return task
    return None


async def _restart_polling(app: Application) -> None:
    """Polling'ni to'xtatib, to'g'ri qayta ishga tushiradi.

    PTB 21.6 da ``Updater.start_polling()`` quyidagi shartlarda
    ``RuntimeError`` beradi:

    * ``This Updater is already running!`` — ``_running`` hali ``True``;
    * ``This Updater was not initialized via `Updater.initialize`!``.

    Shuning uchun to'rtta qadam ketma-ket bajariladi va har biri
    alohida tekshiriladi:

    1. ``stop()`` — polling task'ni to'xtatadi, ``_running = False``.
    2. ``initialize()`` — bot qayta tayyorlanadi.
    3. ``start_polling()`` — yangi polling task.

    Oldingi kodda har bir qadam ``contextlib.suppress(Exception)`` bilan
    yashirilardi. Bu **xato** edi: ``stop()`` xatosi yashiringanda
    ``_running`` ``True`` bo'lib qolardi va ``start_polling()`` ham
    xato berardi — supervisor esa har siklda "Polling qayta boshlandi"
    deb yozib, botni **javob bermaydigan** holatda qoldirardi.

    Xato bo'lsa, holat to'g'rilanadi va xato qaytariladi — supervisor
    uni yashirmasligi kerak.
    """
    updater = app.updater

    # 1. To'xtatish. `stop()` "This Updater is not running!" xatosini
    #    berishi mumkin (polling allaqachon to'xtagan bo'lsa) — bu
    #    normal holat, davom etamiz. Lekin `stop()` **har doim**
    #    chaqiriladi — PTB ichida eski polling task'ni tozalash uchun
    #    kerak.
    try:
        await updater.stop()
    except Exception as exc:  # noqa: BLE001
        log(f"⚠️ Polling to'xtatishda xato: {type(exc).__name__}: {exc}", "error")

    # 2. `_running` qoldiqi True bo'lsa, `start_polling` "already running"
    #    xatosini beradi. PTB ichki atributni to'g'ridan-to'g'ri
    #    tozalaymiz (PTB API'sida boshqa yo'l yo'q).
    if getattr(updater, "running", False):
        with contextlib.suppress(Exception):
            updater._running = False  # noqa: SLF001

    # 3. Tayyorlash.
    try:
        await updater.initialize()
    except Exception as exc:  # noqa: BLE001
        log(f"⚠️ Polling initialize xato: {type(exc).__name__}: {exc}", "error")

    # 4. Qayta ishga tushirish — xatoni YASHIRMAYMAN, lekin logga yozamiz.
    try:
        await updater.start_polling(
            drop_pending_updates=False,
            error_callback=lambda exc: log(
                f"⚠️ Polling xato: {type(exc).__name__}: {exc}",
                "error",
            ),
        )
    except Exception as exc:  # noqa: BLE001
        log(
            f"💥 Polling qayta ishga tushmadi: {type(exc).__name__}: {exc}",
            "error",
        )
        raise


async def polling_supervisor(app: Application, stop_event: asyncio.Event) -> None:
    """Polling'ni kuzatib turadi — task to'xtasa, qayta boshlaydi.

    Telegram API vaqtincha javob bermay qolsa (``NetworkError``,
    ``TimedOut``, ``Bad Gateway``), PTB ichidagi retry tugab qolishi
    mumkin. Bundayda bot "javob bermaydi" bo'lib qoladi. Bu supervisor
    polling task'i tugaganini aniqlab, uni qayta ishga tushiradi.

    ``stop_event`` qo'yilganda loop to'xtaydi.
    """
    retry_delay = 5
    while not stop_event.is_set():
        try:
            # `polling_task` — ichki task; tugagach polling to'xtaydi.
            task = _get_polling_task(app.updater)
            if task is None:
                # Polling hali boshlanmagan — biroz kutamiz.
                await asyncio.wait_for(stop_event.wait(), timeout=2)
                continue

            done, _ = await asyncio.wait(
                (task,),
                timeout=5,
            )
            if task in done:
                # Polling task'i tugadi — sababni aniqlaymiz.
                exc = None
                with contextlib.suppress(Exception):
                    exc = task.exception()
                if stop_event.is_set():
                    return
                # Xato matnini ham ko'rsatamiz — faqat klassi yetarli emas.
                # Aks holda "noma" holatida sababni topib bo'lmaydi.
                if exc is not None:
                    log(
                        f"⚠️ Polling to'xtadi ({type(exc).__name__}: {exc})"
                        f" — {retry_delay}s dan keyin qayta boshlanadi",
                        "error",
                    )
                else:
                    log(
                        f"⚠️ Polling to'xtadi (xatosiz) — {retry_delay}s dan keyin "
                        "qayta boshlanadi",
                        "error",
                    )
                # Eski updater'ni tozalab, yangisini qayta ishga tushiramiz.
                #
                # Muhim: har bir qadamning xatosi YASHIRILMASIN. Oldinda
                # `contextlib.suppress` ishlatilardi — shunda `stop()` ning
                # "This Updater is not running!" xatosi yashirinib, keyingi
                # `start_polling()` "This Updater is already running!" bilan
                # uriladi va bot javob bermay qoladi (infinite loop).
                await _restart_polling(app)
                log("✅ Polling qayta boshlandi")
                retry_delay = 5
            else:
                # Polling hali ham yashayapti — xato bo'lsa intervalni
                # oshiramiz (Telegram'ga bosib qolmaymiz).
                retry_delay = min(60, max(5, retry_delay))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            log(f"⚠️ Polling supervisor xato: {type(exc).__name__}: {exc}", "error")
            await asyncio.sleep(retry_delay)


# ─────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────
async def _main() -> None:
    global application, client_pool, worker_manager, health_server

    log("🚀 AVTOBOT v2 ishga tushmoqda")

    # 1. Baza
    await db.init_db()

    # 2. Super admin
    await db.upsert_user(SUPER_ADMIN, is_admin=1)

    # 3. Client pool
    client_pool = ClientPool(
        api_id=API_ID,
        api_hash=API_HASH,
        max_clients=MAX_CLIENT_POOL,
        max_isolated=MAX_ISOLATED_CLIENTS,
    )
    await client_pool.start()

    # 4. Worker manager
    worker_manager = Worker.WorkerManager(max_workers=MAX_CONCURRENT_WORKERS)
    worker_manager.set_worker_factory(Worker.posting_loop)
    worker_manager.setup_signals()

    # 5. Bog'lanishlar
    Worker.set_deps(client_pool, None)
    Menu.set_worker_manager(worker_manager)

    # 6. Health server
    health_server = Health.HealthServer()
    health_server.set_stats_providers(
        worker_stats_fn=lambda: worker_manager.stats(),
        pool_stats_fn=lambda: client_pool.stats(),
    )
    with contextlib.suppress(Exception):
        await health_server.start()

    # 7. Telegram bot
    # Ulanish pool'i kengaytiriladi: long-polling connection'i boshqa
    # so'rovlarni (javob yuborish) bloklamasligi kerak. Aks holda bot
    # "javob bermaydi" bo'lib qoladi ("pool timeout").
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(32)
        .connection_pool_size(TELEGRAM_CONNECTION_POOL_SIZE)
        .read_timeout(TELEGRAM_READ_TIMEOUT)
        .write_timeout(TELEGRAM_WRITE_TIMEOUT)
        .connect_timeout(TELEGRAM_CONNECT_TIMEOUT)
        .pool_timeout(TELEGRAM_POOL_TIMEOUT)
        .get_updates_read_timeout(TELEGRAM_GET_UPDATES_READ_TIMEOUT)
        .get_updates_pool_timeout(TELEGRAM_GET_UPDATES_POOL_TIMEOUT)
        .build()
    )
    application = app

    # Bog'lanishlarni to'liq o'rnatish
    Worker.set_deps(client_pool, app)
    Login.set_application(app)
    CB.set_application(app)
    AP.set_application(app)
    AA.set_application(app)
    BC.set_application(app)
    AutoApprove.set_application(app)

    # Handlerlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(CB.handle_callback))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & (
                filters.TEXT
                | filters.PHOTO
                | filters.VIDEO
                | filters.AUDIO
                | filters.Document.ALL
            )
            & ~filters.COMMAND,
            on_message,
        )
    )
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    # PTB 21.6: set_my_commands Application'da emas, Bot obyektida.
    # Bu so'rov faqat menyu buyruqlarini ro'ylaydi — muvaffaqiyatsiz bo'lsa
    # ham bot ishlashda davom etishi kerak. Aks holda Telegram vaqtincha
    # javob bermasa, butun bot o'ladi (foydalanuvchilar javob olmaydi).
    await set_bot_commands(app)
    app.add_error_handler(on_error)

    # 8. Botni ishga tushirish
    # Telegram'ga ulanish — vaqtincha javob bermasa, bir necha urinish.
    # Aks holda bitta timeout butun botni o'ldiradi.
    await _with_retry(app.initialize)
    await app.start()
    await _with_retry(
        lambda: app.updater.start_polling(
            drop_pending_updates=True,
            error_callback=lambda exc: log(
                f"⚠️ Polling xato: {type(exc).__name__}: {exc}",
                "error",
            ),
        )
    )
    log("✅ Bot polling boshlandi")

    # 8b. Polling supervisor — polling task'i to'xtasa, qayta boshlaydi.
    polling_stop = asyncio.Event()
    polling_task = asyncio.create_task(
        polling_supervisor(app, polling_stop),
        name="polling-supervisor",
    )

    # 9. Restore
    await restore_running_workers()

    # 10. Janitorlar
    janitor_stop = asyncio.Event()
    janitor_task = asyncio.create_task(
        login_janitor_loop(janitor_stop),
        name="login-janitor",
    )

    tariff_stop = asyncio.Event()
    tariff_task = asyncio.create_task(
        tariff_janitor_loop(tariff_stop),
        name="tariff-janitor",
    )

    cleanup_stop = asyncio.Event()
    cleanup_task = asyncio.create_task(
        cleanup_janitor_loop(cleanup_stop),
        name="cleanup-janitor",
    )

    approve_stop = asyncio.Event()
    approve_task = asyncio.create_task(
        auto_approve_loop(approve_stop),
        name="auto-approve",
    )

    # 11. Shutdown kutish
    try:
        await worker_manager.wait_shutdown()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        log("🛑 To'xtatilmoqda...")

        # Jarayon butunlay to'xtayotganini **darhol** belgilaymiz. Shu
        # bayroq True bo'lsa worker'lar "running" holatini o'zgartirmaydi —
        # yangi process ishga tushganda ular avtomatik tiklanadi.
        # Aks holda har bir kod yangilanishida foydalanuvchi qaytadan
        # "Start" bosishi kerak bo'lardi va uning e'lonlari to'xtab qolardi.
        Worker.set_process_shutting_down(True)

        # Avval yangi update kelishini to'xtatamiz; mavjud handlerlar resurslar
        # yopilishidan oldin Application.stop orqali tugashini kutadi.
        polling_stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(polling_task, timeout=5)
        with contextlib.suppress(Exception):
            await app.updater.stop()

        janitor_stop.set()
        tariff_stop.set()
        cleanup_stop.set()
        approve_stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(janitor_task, timeout=5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(tariff_task, timeout=5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(cleanup_task, timeout=5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(approve_task, timeout=5)
        with contextlib.suppress(Exception):
            await app.stop()

        with contextlib.suppress(Exception):
            await BC.shutdown()
        with contextlib.suppress(Exception):
            await worker_manager.stop_all()
        with contextlib.suppress(Exception):
            await client_pool.stop()
        with contextlib.suppress(Exception):
            await health_server.stop()
        with contextlib.suppress(Exception):
            await app.shutdown()
        with contextlib.suppress(Exception):
            await db.close_db()

        log("👋 To'xtatildi")


async def main() -> None:
    """Startupning istalgan bosqichidagi xatoda ham resurslarni yopadi."""
    try:
        await _main()
    except BaseException:
        if application:
            updater = getattr(application, "updater", None)
            if updater:
                with contextlib.suppress(Exception):
                    await updater.stop()
            with contextlib.suppress(Exception):
                await application.stop()
        with contextlib.suppress(Exception):
            await BC.shutdown()
        if worker_manager:
            with contextlib.suppress(Exception):
                await worker_manager.stop_all()
        if client_pool:
            with contextlib.suppress(Exception):
                await client_pool.stop()
        if health_server:
            with contextlib.suppress(Exception):
                await health_server.stop()
        if application:
            with contextlib.suppress(Exception):
                await application.shutdown()
        with contextlib.suppress(Exception):
            await db.close_db()
        raise


# ─────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
