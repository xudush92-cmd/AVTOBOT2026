"""
AVTOBOT v2 — asosiy ishga tushiruvchi fayl.

Ishga tushirish:
    python main.py

Nima qiladi:
1. Bazani ishga tushiradi
2. Client pool yaratadi
3. Worker manager yaratadi
4. Health serverni ishga tushiradi
5. Telegram botni ishga tushiradi
6. Handlerlarni ro'yxatdan o'tkazadi
7. Janitorlarni (login, tariff) ishga tushiradi
8. Avval ishlagan workerlarni tiklaydi
9. Shutdown signalini kutadi
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

# Core
from config.config import BOT_TOKEN, SUPER_ADMIN
from core import database as db
from core.logger import log
from core.rate_limit import RateLimiter
from core.utils import iso_now

# Worker
from worker import health as Health
from worker import worker as Worker
from worker.client_pool import ClientPool

from config.config import MAX_CLIENT_POOL, MAX_CONCURRENT_WORKERS


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

    # Yangi user — xush kelibsiz + Login tugmasi
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

    # Sessiya yo'q — Login kerak
    if not user.get("session"):
        await update.message.reply_text(
            T.WELCOME_SHORT,
            reply_markup=KB.kb_login(),
        )
        return

    # Sessiya bor — asosiy menyu
    running = worker_manager.is_running(uid) if worker_manager else False
    super_flag = uid == SUPER_ADMIN

    name = user.get("name") or "Foydalanuvchi"
    await update.message.reply_text(
        f"🤖 AVTOBOT\n\n"
        f"👤 {name}\n"
        f"📊 Holat: {'🟢 Ishlamoqda' if running else '🔴 To\'xtatilgan'}\n\n"
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

    # ── LOGIN FSM (rate limitdan OLDIN) ──
    if step in ("name", "surname", "phone", "code", "password"):
        # Timeout
        if time.time() - state.get("ts", 0) > 600:
            await Login.cleanup_login(uid)
            await msg.reply_text(
                T.CODE_TIMEOUT,
                reply_markup=KB.kb_login(),
            )
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
    if step in ("admin_open_session", "admin_add_group", "admin_add_post",
                "admin_set_expire", "admin_broadcast"):
        if uid != SUPER_ADMIN:
            return
        await handle_admin_fsm(update, uid, step, text)
        return

    # ── ADMIN BROADCAST (alohida) ──
    if step == "admin_broadcast" and (text or msg.photo):
        await BC.handle_broadcast_message(update)
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

    # ── TASDIQ KUTILMOQDA ──
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

    # ── ADMIN BROADCAST uchun rasm bo'lsa ──
    if msg.photo and uid == SUPER_ADMIN:
        admin_state = Login.user_states.get(uid, {})
        if admin_state.get("step") == "admin_broadcast":
            await BC.handle_broadcast_message(update)
            return

    # ── LOGIN TUGMASI ──
    if text == T.BTN_LOGIN:
        await msg.reply_text("✅ Siz allaqachon kirgansiz.", reply_markup=await get_menu(uid))
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

    # ── MENYU TUGMALARI ──
    ok = await Menu.route_menu_button(update, text)
    if ok:
        return

    # ── ADMIN FSM (guruh/post qo'shish) ──
    if step in ("add_group", "add_post", "set_interval"):
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
# ADMIN FSM (sessiya ochish, guruh/post, muddat, broadcast)
# ─────────────────────────────────────────────────────────────────────────
async def handle_admin_fsm(update: Update, uid: int, step: str, text: str) -> None:
    """Admin FSM handlerlari."""
    msg = update.message
    state = Login.user_states.get(uid, {})
    target = state.get("target_uid")

    # ── SESSIYA OCHISH (kod kutilmoqda) ──
    if step == "admin_open_session":
        # Kodni qabul qilamiz
        code = text.strip()
        if not code.isdigit() or len(code) < 5:
            await msg.reply_text("❌ Kod 5-6 raqamdan iborat bo'lishi kerak.")
            return
        await Login.attempt_signin(uid, code)
        return

    # ── GURUH QO'SHISH ──
    if step == "admin_add_group":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return
        Login.user_states.pop(uid, None)
        # Foydalanuvchi nomidan guruh qo'shamiz
        session = await db.get_session(target)
        if not session:
            await msg.reply_text(f"❌ {target} sessiyasi yo'q.")
            return
        # Vaqtinchalik target user_states ga yozamiz va handle_add_groups chaqiramiz
        # Buning uchun maxsus funksiya yozamiz (keyingi faylda)
        await msg.reply_text(f"⏳ {target} nomidan guruh qo'shilmoqda...")
        # TODO: to'liq implementatsiya (kelasi versiyada)
        return

    # ── POST QO'SHISH ──
    if step == "admin_add_post":
        if not target:
            Login.user_states.pop(uid, None)
            await msg.reply_text("❌ Xatolik.")
            return
        Login.user_states.pop(uid, None)
        await msg.reply_text(f"⏳ {target} nomidan post qo'shilmoqda...")
        # TODO: to'liq implementatsiya (kelasi versiyada)
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
                dt = datetime.strptime(current, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
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
            reply_markup=KB.kb_admin_back(),
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
async def expire_stale_logins() -> int:
    """Muddati o'tgan login jarayonlarini tozalaydi."""
    now = time.time()
    expired: set[int] = set()

    for uid, ctx in list(Login.login_ctx.items()):
        if now - ctx.started_at > 600:
            expired.add(uid)

    for uid, state in list(Login.user_states.items()):
        step = state.get("step")
        if step in ("name", "surname", "phone", "code", "password"):
            if now - state.get("ts", 0) > 600:
                expired.add(uid)

    for uid in expired:
        with contextlib.suppress(Exception):
            await Login.cleanup_login(uid)
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid,
                T.CODE_TIMEOUT,
                reply_markup=KB.kb_login(),
            )

    if expired:
        log(f"🧹 Stale login: {len(expired)} ta tozalandi")
    return len(expired)


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
# TARIFF JANITOR — oxirgi kun ogohlantirishi va muddat tugashi
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

    # Barcha faol foydalanuvchilarni tekshiramiz
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

        # Faqat oxirgi kun
        if not is_last_day(expires):
            continue

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid,
                T.LAST_DAY_WARNING,
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
# RESTORE — avval ishlagan workerlarni tiklash
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

    # 2. Super admin bazada borligini ta'minlash
    await db.upsert_user(SUPER_ADMIN, is_admin=1)

    # 3. Client pool
    client_pool = ClientPool(
        api_id=__import__("config.config", fromlist=["API_ID"]).API_ID,
        api_hash=__import__("config.config", fromlist=["API_HASH"]).API_HASH,
        max_clients=MAX_CLIENT_POOL,
    )
    await client_pool.start()

    # 4. Worker manager
    worker_manager = Worker.WorkerManager(max_workers=MAX_CONCURRENT_WORKERS)
    worker_manager.set_worker_factory(Worker.posting_loop)
    worker_manager.setup_signals()

    # 5. Bog'lanishlarni o'rnatish
    Worker.set_deps(client_pool, None)  # application keyin
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

    # 9. Restore workers
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

    # 11. Shutdown signalini kutish
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
