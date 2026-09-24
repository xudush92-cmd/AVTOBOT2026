"""
AVTOBOT v2 — asosiy ishga tushiruvchi fayl.

Ishga tushirish:
    python main.py
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import Update
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
from admin import broadcast as BC

# Bot modullari
from bot import callbacks as CB
from bot import keyboards as KB
from bot import login as Login
from bot import menu as Menu
from bot import texts as T

# Config
from config.config import (
    API_HASH,
    API_ID,
    BOT_TOKEN,
    EXPIRY_CHECK_INTERVAL_S,
    LOGIN_TIMEOUT_S,
    MAX_CLIENT_POOL,
    MAX_CONCURRENT_WORKERS,
    MAX_INTERVAL_MIN,
    SUPER_ADMIN,
)

# Core
from core import database as db
from core.logger import log
from core.rate_limit import RateLimiter
from core.update_locks import user_operation_lock, user_update_lock
from core.utils import is_valid_full_name, is_valid_phone, safe_unlink

# Worker
from worker import health as Health
from worker import worker as Worker
from worker.client_pool import ClientPool

# ─────────────────────────────────────────────────────────────────────────
# GLOBAL
# ─────────────────────────────────────────────────────────────────────────
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
# /start COMMAND
# ─────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    async with user_update_lock(uid):
        await _cmd_start_locked(update, context)


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
        with contextlib.suppress(Exception):
            from bot.referral import register_referral

            await register_referral(uid, arg)

    user = await db.get_user(uid)

    # Yangi user
    if not user:
        await update.message.reply_text(
            T.WELCOME_SHORT,
            reply_markup=KB.kb_login(),
        )
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
        await update.message.reply_text(
            T.WELCOME_SHORT,
            reply_markup=KB.kb_login(),
        )
        return

    # Sessiya yo'q
    if not user.get("session"):
        await update.message.reply_text(
            T.WELCOME_SHORT,
            reply_markup=KB.kb_login(),
        )
        return

    # Sessiya bor — menyu
    running = worker_manager.is_running(uid) if worker_manager else False

    name = user.get("name") or "Foydalanuvchi"
    await update.message.reply_text(
        f"🤖 AVTOBOT\n\n"
        f"👤 {name}\n"
        f"📊 Holat: {'🟢 Ishlamoqda' if running else '🔴 Toʻxtatilgan'}\n\n"
        f"Menyudan kerakli amalni tanlang:",
        reply_markup=KB.kb_main(running=running),
    )


# ─────────────────────────────────────────────────────────────────────────
# MESSAGE HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    async with user_update_lock(uid):
        await _on_message_locked(update, context)


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
        if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
            admin_flow = bool(state.get("admin_add_user")) or uid == SUPER_ADMIN
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

    # ── ADMIN FSM ──
    if step in (
        "admin_new_user_full_name",
        "admin_new_user_phone",
        "admin_add_group",
        "admin_add_post",
        "admin_set_interval",
        "admin_set_expire",
        "admin_broadcast",
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
            await Login.begin_login(update)
            return
        await msg.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
        return

    if user.get("awaiting_approval"):
        await msg.reply_text(T.LOGIN_ALREADY_PENDING, reply_markup=KB.kb_pending())
        return

    if not user.get("is_admin"):
        if text == T.BTN_LOGIN:
            await Login.begin_login(update)
        else:
            await msg.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
        return

    # ── SESSIYA YO'Q ──
    if not user.get("session"):
        if text == T.BTN_LOGIN:
            if not rate_limiter.is_allowed(uid, "login"):
                wait_min = rate_limiter.get_wait_time(uid, "login")
                await msg.reply_text(T.rate_limit_text(wait_min))
                return
            await Login.begin_login(update)
            return
        await msg.reply_text(T.WELCOME_SHORT, reply_markup=KB.kb_login())
        return

    # ── FSM: add_group / add_post / set_interval ──
    if step in ("add_group", "add_post", "set_interval", "set_interval_confirm"):
        menu_buttons = {
            T.BTN_START,
            T.BTN_STOP,
            T.BTN_GROUPS,
            T.BTN_POSTS,
            T.BTN_ADD_GROUP,
            T.BTN_DEL_GROUP,
            T.BTN_ADD_POST,
            T.BTN_DEL_POST,
            T.BTN_TIMER,
            T.BTN_REFERRAL,
            T.BTN_ACCOUNT,
        }
        if text in menu_buttons or text.startswith(T.BTN_STATUS):
            Login.user_states.pop(uid, None)
            await msg.reply_text("ℹ️ Oldingi kiritish oynasi bekor qilindi.")
            await Menu.handle_menu(update, text)
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
            if step == "add_group":
                markup = KB.kb_groups_menu()
            elif step == "add_post":
                markup = KB.kb_posts_menu()
            else:
                markup = await get_menu(uid)
            await msg.reply_text(T.ACTION_CANCELLED, reply_markup=markup)
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
    return KB.kb_main(running=running)


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

        from bot.groups import check_group_access
        from core.utils import parse_group_lines

        session = await db.get_session(target)
        if not session:
            Login.user_states.pop(uid, None)
            await msg.reply_text(
                f"❌ {target} sessiyasi yo'q.",
                reply_markup=await AA.user_card_markup(target),
            )
            return

        groups = parse_group_lines(text)
        if not groups:
            await msg.reply_text("❌ Guruh topilmadi. Qaytadan yuboring:")
            return

        Login.user_states.pop(uid, None)
        status = await msg.reply_text(f"⏳ {len(groups)} ta guruh tekshirilmoqda...")

        added, duplicates, errors = [], [], []
        existing = set(await db.get_chats(target))

        for g in groups:
            if g in existing:
                duplicates.append(g)
                continue
            ok, reason = await check_group_access(session, g)
            if not ok:
                errors.append(f"{g} ({reason})")
                continue
            saved, sr = await db.add_chat(target, g)
            if saved:
                added.append(g)
                existing.add(g)
            elif sr == "duplicate":
                duplicates.append(g)
            else:
                errors.append(f"{g} (saqlashda xato)")

        await status.edit_text(
            T.groups_added_report(added, duplicates, errors),
            reply_markup=KB.kb_admin_groups(target, await db.get_chats(target)),
        )
        log(f"📊 Admin {uid} → {target} guruhlar +{len(added)}")
        return

    # ── POST QO'SHISH ──
    if step == "admin_add_post":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        import os
        import uuid

        from bot.posts import entity_to_dict, user_media_dir

        post_text = msg.text or msg.caption or ""
        entities_src = list(msg.entities or []) + list(msg.caption_entities or [])

        photo_path = None
        if msg.photo:
            try:
                photo = msg.photo[-1]
                tg_file = await photo.get_file()
                user_dir = user_media_dir(target)
                photo_path = os.path.join(user_dir, f"{uuid.uuid4().hex}.jpg")
                await tg_file.download_to_drive(custom_path=photo_path)
            except Exception as e:
                log(f"admin_add_post rasm xato: {type(e).__name__}", "error")
                await msg.reply_text("❌ Rasmni saqlab bo'lmadi.")
                return

        if not post_text.strip() and not photo_path:
            await msg.reply_text("❌ Bo'sh post.")
            return

        entities_dict = [entity_to_dict(e) for e in entities_src]
        ok, reason, post_id = await db.add_post(
            target, post_text, entities_dict, photo_path
        )

        Login.user_states.pop(uid, None)

        if not ok:
            safe_unlink(photo_path)
            await msg.reply_text("❌ Saqlanmadi.")
            return

        await msg.reply_text(
            f"✅ Post qo'shildi: {target} (#{post_id})",
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
            f"✅ Taxminiy posting oralig'i {minutes} daqiqaga o'rnatildi.\n"
            "Anti-spam uchun real vaqt 5 daqiqagacha farq qiladi.",
            reply_markup=await AA.user_card_markup(target),
        )
        return

    # ── MUDDATNI QO'LDA KIRITISH ──
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

        from datetime import datetime, timedelta, timezone

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

        new_iso = (dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        await db.set_tariff_expires(target, new_iso)
        log(f"⏰ Admin {uid} → {target} +{days} kun")

        await msg.reply_text(
            f"✅ Muddat uzaytirildi: +{days} kun\nYangi muddat: {new_iso[:10]}",
            reply_markup=await AA.user_card_markup(target),
        )

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                target,
                f"✅ Tarifingiz uzaytirildi!\n\n📅 Yangi muddat: {new_iso[:10]}",
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
                            KB.kb_main(running=running)
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
            with contextlib.suppress(Exception):
                await expire_stale_logins()
            rate_limiter.cleanup_all()
            Login.cleanup_sms_attempts()
    except asyncio.CancelledError:
        pass


# ─────────────────────────────────────────────────────────────────────────
# TARIFF JANITOR
# ─────────────────────────────────────────────────────────────────────────
async def check_tariff_expiry() -> int:
    """Muddati tugagan foydalanuvchilarni to'xtatadi."""
    expired = await db.get_expired_users()
    if not expired:
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
                    reply_markup=KB.kb_main(),
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
    log(f"🔁 {restored} ta worker tiklandi")


# ─────────────────────────────────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    error = context.error
    log(f"💥 Handler xato: {type(error).__name__}", "error")


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
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(32).build()
    application = app

    # Bog'lanishlarni to'liq o'rnatish
    Worker.set_deps(client_pool, app)
    Login.set_application(app)
    CB.set_application(app)
    AP.set_application(app)
    AA.set_application(app)
    BC.set_application(app)

    # Handlerlar
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(CB.handle_callback))
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & (filters.TEXT | filters.PHOTO)
            & ~filters.COMMAND,
            on_message,
        )
    )
    app.add_error_handler(on_error)

    # 8. Botni ishga tushirish
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    log("✅ Bot polling boshlandi")

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

    # 11. Shutdown kutish
    try:
        await worker_manager.wait_shutdown()
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        log("🛑 To'xtatilmoqda...")

        # Avval yangi update kelishini to'xtatamiz; mavjud handlerlar resurslar
        # yopilishidan oldin Application.stop orqali tugashini kutadi.
        with contextlib.suppress(Exception):
            await app.updater.stop()

        janitor_stop.set()
        tariff_stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(janitor_task, timeout=5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(tariff_task, timeout=5)
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
