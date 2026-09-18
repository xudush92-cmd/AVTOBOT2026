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

# Bot modullari
from bot import callbacks as CB
from bot import keyboards as KB
from bot import login as Login
from bot import menu as Menu
from bot import texts as T

# Admin modullari
from admin import admin_actions as AA
from admin import admin_panel as AP
from admin import broadcast as BC

# Config
from config.config import (
    API_HASH,
    API_ID,
    BOT_TOKEN,
    MAX_CLIENT_POOL,
    MAX_CONCURRENT_WORKERS,
    SUPER_ADMIN,
)

# Core
from core import database as db
from core.logger import log
from core.rate_limit import RateLimiter

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
# /start COMMAND
# ─────────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/start buyrug'i."""
    uid = update.effective_user.id

    # Rate limit
    if not rate_limiter.is_allowed(uid, "command"):
        wait_min = rate_limiter.get_wait_time(uid, "command")
        await update.message.reply_text(T.rate_limit_text(wait_min))
        return

    # Referal
    if context.args:
        arg = context.args[0]
        with contextlib.suppress(Exception):
            from bot.referral import register_referral
            await register_referral(uid, arg)

    # Bloklangan?
    if await db.is_blocked(uid):
        await update.message.reply_text(
            T.BLOCKED,
            reply_markup=KB.kb_blocked(),
        )
        return

    user = await db.get_user(uid)

    # Yangi user
    if not user:
        await update.message.reply_text(
            T.WELCOME_SHORT,
            reply_markup=KB.kb_login(),
        )
        return

    # Tasdiq kutilmoqda
    if user.get("awaiting_approval"):
        await update.message.reply_text(
            T.LOGIN_ALREADY_PENDING,
            reply_markup=KB.kb_pending(),
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
    super_flag = uid == SUPER_ADMIN

    name = user.get("name") or "Foydalanuvchi"
    await update.message.reply_text(
        f"🤖 AVTOBOT\n\n"
        f"👤 {name}\n"
        f"📊 Holat: {'🟢 Ishlamoqda' if running else '🔴 Toʻxtatilgan'}\n\n"
        f"Menyudan kerakli amalni tanlang:",
        reply_markup=KB.kb_main(running=running, super_admin=super_flag),
    )


# ─────────────────────────────────────────────────────────────────────────
# MESSAGE HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha oddiy xabarlar."""
    uid = update.effective_user.id
    msg = update.message
    text = (msg.text or "").strip()
    state = Login.user_states.get(uid, {})
    step = state.get("step")

    # ── BLOKLANGAN (hamma narsadan OLDIN — bloklangan user hech
    #    qanday FSM bosqichini yuritib olmasin) ──
    if await db.is_blocked(uid):
        if step:
            Login.user_states.pop(uid, None)
        await msg.reply_text(T.BLOCKED, reply_markup=KB.kb_blocked())
        return

    # ── LOGIN FSM (rate limitdan OLDIN) ──
    if step in ("name", "surname", "phone", "code", "password"):
        if time.time() - state.get("ts", 0) > 600:
            await Login.cleanup_login(uid)
            await msg.reply_text(T.CODE_TIMEOUT, reply_markup=KB.kb_login())
            return

        if step == "name":
            await Login.handle_name(update, text)
            return
        if step == "surname":
            await Login.handle_surname(update, text)
            return
        if step == "phone":
            await Login.handle_phone(update, text)
            return
        if step == "code":
            await Login.handle_code(update, text)
            return
        if step == "password":
            await Login.handle_password(update, text)
            return

    # ── ADMIN FSM ──
    if step in ("admin_code_input", "admin_add_group", "admin_add_post",
                "admin_set_expire", "admin_broadcast"):
        if uid != SUPER_ADMIN:
            return
        await handle_admin_fsm(update, uid, step, text)
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

    # ── ADMIN BROADCAST (rasm bilan) ──
    if msg.photo and uid == SUPER_ADMIN:
        admin_state = Login.user_states.get(uid, {})
        if admin_state.get("step") == "admin_broadcast":
            await BC.handle_broadcast_message(update)
            return

    # ── LOGIN TUGMASI ──
    if text == T.BTN_LOGIN:
        await msg.reply_text(
            "✅ Siz allaqachon kirgansiz.",
            reply_markup=await get_menu(uid),
        )
        return

    # ── SUPER ADMIN tugmasi ──
    if text == T.BTN_ADMIN and uid == SUPER_ADMIN:
        stats = await db.get_stats()
        await msg.reply_text(
            "🖥 SUPER ADMIN PANEL\n\n"
            f"👥 Foydalanuvchilar: {stats['total_users']} ta\n"
            f"✅ Tasdiqlangan: {stats['admins']} ta\n"
            f"⏳ Kutayotgan: {stats['waiting']} ta\n"
            f"🟢 Faol: {stats['running']} ta\n"
            f"🚫 Bloklangan: {stats['blocked']} ta\n\n"
            "Kerakli bo'limni tanlang:",
            reply_markup=KB.kb_admin_panel(),
        )
        return

    # ── USER FSM (add_group / add_post / set_interval) ──
    # MENYU TUGMALARIDAN OLDIN tekshiriladi: aks holda post matni
    # tasodifan tugma matniga teng bo'lib qolsa (masalan "📊 Status")
    # noto'g'ri ishlov beriladi.
    if step in ("add_group", "add_post", "set_interval", "set_interval_confirm"):
        # Bekor qilish so'zi
        if text.lower() in T.CANCEL_WORDS:
            Login.user_states.pop(uid, None)
            await msg.reply_text(T.FSM_CANCELLED, reply_markup=await get_menu(uid))
            return

        if step == "add_group":
            from bot.groups import handle_add_groups
            await handle_add_groups(update, text)
            return
        if step == "add_post":
            from bot.posts import handle_add_post
            await handle_add_post(update)
            return
        if step == "set_interval":
            from bot.timer import handle_set_interval
            await handle_set_interval(update, text)
            return

        # set_interval_confirm — faqat tugma yoki "bekor"
        await msg.reply_text(
            T.USE_MENU_BUTTONS + "\n\n❌ Bekor qilish uchun: bekor"
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
# YORDAMCHI — MENYU
# ─────────────────────────────────────────────────────────────────────────
async def get_menu(uid: int):
    """Foydalanuvchi uchun menyu."""
    running = worker_manager.is_running(uid) if worker_manager else False
    super_flag = uid == SUPER_ADMIN
    return KB.kb_main(running=running, super_admin=super_flag)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN FSM
# ─────────────────────────────────────────────────────────────────────────
async def handle_admin_fsm(update: Update, uid: int, step: str, text: str) -> None:
    """Admin FSM handlerlari."""
    msg = update.message
    state = Login.user_states.get(uid, {})
    target = state.get("target_uid")

    # ── SESSIYA OCHISH (kod kutilmoqda) ──
    if step == "admin_code_input":
        code = text.strip()

        if not code.isdigit():
            await msg.reply_text(
                "❌ Kod faqat raqamlardan iborat bo'lishi kerak.\n\n"
                "Qaytadan kiriting:"
            )
            return

        if len(code) < 5 or len(code) > 6:
            await msg.reply_text(
                "❌ Kod 5 yoki 6 raqamdan iborat bo'lishi kerak.\n\n"
                "Qaytadan kiriting:"
            )
            return

        await msg.reply_text("⏳ Kod tekshirilmoqda...")
        await Login.attempt_signin(uid, code)
        return

    # ── GURUH QO'SHISH ──
    if step == "admin_add_group":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        from bot.groups import add_groups_for
        from core.utils import parse_group_lines

        groups = parse_group_lines(text)
        if not groups:
            await msg.reply_text("❌ Guruh topilmadi. Qaytadan yuboring:")
            return

        Login.user_states.pop(uid, None)
        status = await msg.reply_text(f"⏳ {len(groups)} ta guruh tekshirilmoqda...")

        async def _progress(i, added, duplicates, errors):
            await status.edit_text(
                f"⏳ {i}/{len(groups)} tekshirildi...\n"
                f"✅ {len(added)} | ⚠️ {len(duplicates)} | ❌ {len(errors)}"
            )

        # Butun batch bitta client bilan tekshiriladi
        added, duplicates, errors, fatal = await add_groups_for(
            target, groups, progress_fn=_progress
        )

        if fatal:
            await status.edit_text(
                f"❌ {fatal}",
                reply_markup=KB.kb_user_card(target),
            )
            return

        await status.edit_text(
            T.groups_added_report(added, duplicates, errors),
            reply_markup=KB.kb_user_card(target),
        )
        log(f"📊 Admin {uid} → {target} guruhlar +{len(added)}")
        return

    # ── POST QO'SHISH ──
    if step == "admin_add_post":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return

        from bot.posts import entity_to_dict, user_media_dir
        import os
        import uuid

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
                log(f"admin_add_post rasm xato: {e}", "error")
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
            await msg.reply_text("❌ Saqlanmadi.")
            return

        await msg.reply_text(
            f"✅ Post qo'shildi: {target} (#{post_id})",
            reply_markup=KB.kb_user_card(target),
        )

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                target,
                f"📝 Admin sizga yangi post qo'shdi.\n\n"
                f"Jami postlar: {await db.count_posts(target)} ta",
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
                if dt < datetime.now(timezone.utc):
                    dt = datetime.now(timezone.utc)
            except Exception:
                dt = datetime.now(timezone.utc)
        else:
            dt = datetime.now(timezone.utc)

        new_iso = (dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        await db.set_tariff_expires(target, new_iso)
        log(f"⏰ Admin {uid} → {target} +{days} kun")

        await msg.reply_text(
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
        return

    # ── BROADCAST ──
    if step == "admin_broadcast":
        await BC.handle_broadcast_message(update)
        return
      

# ─────────────────────────────────────────────────────────────────────────
# STALE LOGIN JANITOR
# ─────────────────────────────────────────────────────────────────────────
# Login bosqichlari (client bilan — cleanup_login kerak)
LOGIN_STEPS = ("name", "surname", "phone", "code", "password")
# Admin bosqichlari
ADMIN_FSM_STEPS = (
    "admin_add_group", "admin_add_post", "admin_set_expire", "admin_broadcast",
)
# Foydalanuvchi bosqichlari
USER_FSM_STEPS = ("add_group", "add_post", "set_interval", "set_interval_confirm")

FSM_TIMEOUT_S = 600  # 10 daqiqa


async def expire_stale_logins() -> int:
    """Muddati o'tgan login va FSM jarayonlarini tozalaydi."""
    now = time.time()
    expired_login: set[int] = set()   # cleanup_login kerak
    expired_fsm: set[int] = set()     # faqat user_states.pop

    for uid, ctx in list(Login.login_ctx.items()):
        if now - ctx.started_at > FSM_TIMEOUT_S:
            expired_login.add(uid)

    for uid, state in list(Login.user_states.items()):
        step = state.get("step")
        if now - state.get("ts", 0) <= FSM_TIMEOUT_S:
            continue
        if step in LOGIN_STEPS or step == "admin_code_input":
            # admin_code_input orqasida ham client bor — cleanup_login
            expired_login.add(uid)
        elif step in ADMIN_FSM_STEPS or step in USER_FSM_STEPS:
            expired_fsm.add(uid)

    # Eskirgan SMS urinish yozuvlari (xotira tozalash)
    from bot.login import prune_sms_attempts
    pruned_sms = prune_sms_attempts()

    # Login jarayonlari — clientni ham yopish
    for uid in expired_login:
        with contextlib.suppress(Exception):
            await Login.cleanup_login(uid)
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid,
                T.CODE_TIMEOUT,
                reply_markup=KB.kb_login(),
            )

    # Oddiy FSM jarayonlari — holatni tozalash
    for uid in expired_fsm:
        with contextlib.suppress(Exception):
            Login.user_states.pop(uid, None)
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid,
                T.FSM_TIMEOUT,
                reply_markup=await get_menu(uid),
            )

    if expired_login or expired_fsm or pruned_sms:
        log(
            f"🧹 Janitor: login={len(expired_login)}, "
            f"fsm={len(expired_fsm)}, sms_yozuv={pruned_sms}"
        )
    return len(expired_login) + len(expired_fsm)


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
        if worker_manager and worker_manager.is_running(uid):
            await worker_manager.stop_worker(uid)
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
                f"⏰ Muddat tugadi\n\n"
                f"👤 {name} ({uid})\n"
                f"Posting to'xtatildi.",
            )

    if stopped:
        log(f"⏰ Tariff expiry: {stopped} ta to'xtatildi")
    return stopped


async def warn_last_day() -> None:
    """Oxirgi kun ogohlantirishini yuboradi (faqat bir marta)."""
    from core.utils import is_last_day

    users = await db.get_all_users()
    for u in users:
        uid = u.get("uid")
        if not uid:
            continue
        expires = u.get("tariff_expires_at")
        if not expires:
            continue
        if u.get("warned_at"):
            continue

        if not is_last_day(expires):
            continue

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid, T.LAST_DAY_WARNING
            )
            await db.mark_warned(uid)
            log(f"⚠️ Oxirgi kun ogohlantirishi: {uid}")


async def tariff_janitor_loop(stop: asyncio.Event) -> None:
    """Har soatda muddatni tekshiradi."""
    log("⏰ Tariff janitor boshlandi")
    try:
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=3600)
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
        chats = await db.get_chats(uid)
        posts = await db.get_posts(uid)
        if not chats or not posts:
            await db.set_running(uid, False)
            continue
        if await db.is_tariff_expired(uid):
            await db.set_running(uid, False)
            continue
        if await worker_manager.start_worker(uid):
            restored += 1
    log(f"🔁 {restored} ta worker tiklandi")


# ─────────────────────────────────────────────────────────────────────────
# ERROR HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log(f"💥 Handler xato: {context.error}", "error")


# ─────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────
async def main() -> None:
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
    app = Application.builder().token(BOT_TOKEN).build()
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
            (filters.TEXT | filters.PHOTO) & ~filters.COMMAND,
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

        janitor_stop.set()
        tariff_stop.set()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(janitor_task, timeout=5)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(tariff_task, timeout=5)

        with contextlib.suppress(Exception):
            await worker_manager.stop_all()
        with contextlib.suppress(Exception):
            await client_pool.stop()
        with contextlib.suppress(Exception):
            await health_server.stop()
        with contextlib.suppress(Exception):
            await app.updater.stop()
            await app.stop()
            await app.shutdown()
        with contextlib.suppress(Exception):
            await db.close_db()

        log("👋 To'xtatildi")


# ─────────────────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())
