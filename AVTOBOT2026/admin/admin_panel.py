"""
Super admin panel.

Funksiyalar:
- Foydalanuvchilar ro'yxati (sahifalash)
- Statistika
- Bloklangan foydalanuvchilar
- Ma'lumotlar bazasi paneli
- Tizim holati
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import Update

from bot import action_tokens
from bot import keyboards as KB
from config.config import SUPER_ADMIN
from core import database as db
from core.logger import log
from core.update_locks import user_update_lock

# ─────────────────────────────────────────────────────────────────────────
# APPLICATION (main.py da o'rnatiladi)
# ─────────────────────────────────────────────────────────────────────────
application = None


def set_application(app) -> None:
    global application
    application = app


# ─────────────────────────────────────────────────────────────────────────
# ASOSIY ROUTER
# ─────────────────────────────────────────────────────────────────────────
async def handle_admin_callback(update: Update, uid: int, data: str) -> None:
    """Admin panel callback'larini qayta ishlash."""
    q = update.callback_query

    if uid != SUPER_ADMIN:
        return

    # Eski panel tugmasi yangi/admin FSM holatini aralashtirib yubormasin.
    if data not in {"adm:noop", "adm:adduser:cancel"}:
        from admin import broadcast
        from bot.login import cleanup_login, user_states

        if user_states.get(uid):
            await cleanup_login(uid)
        broadcast.broadcast_pending.pop(uid, None)

    # Orqaga — asosiy panel
    if data == "adm:back":
        await show_panel(update)
        return

    # Yangi foydalanuvchi qo'shish / jarayonni to'xtatish
    if data == "adm:adduser:cancel":
        from admin import admin_actions

        await admin_actions.cancel_add_user(update, uid)
        return
    if data == "adm:adduser":
        from admin import admin_actions

        await admin_actions.begin_add_user(update, uid)
        return

    # Foydalanuvchilar ro'yxati (sahifalash bilan)
    if data == "adm:users":
        await show_users(update, page=0)
        return
    if data.startswith("adm:users:"):
        try:
            page = int(data.split(":")[2])
        except (ValueError, IndexError):
            page = 0
        await show_users(update, page=page)
        return

    if data == "adm:pending":
        await show_pending(update, page=0)
        return
    if data.startswith("adm:pending:"):
        try:
            page = int(data.split(":")[2])
        except (ValueError, IndexError):
            page = 0
        await show_pending(update, page=page)
        return

    # Statistika
    if data == "adm:stats":
        await show_stats(update)
        return

    # Broadcast
    if data == "adm:broadcast":
        from admin import broadcast

        await broadcast.begin_broadcast(update)
        return

    # Bloklanganlar
    if data == "adm:blocked":
        await show_blocked(update, page=0)
        return
    if data.startswith("adm:blocked:"):
        try:
            page = int(data.split(":")[2])
        except (ValueError, IndexError):
            page = 0
        await show_blocked(update, page=page)
        return

    # DB panel
    if data == "adm:db":
        action_tokens.clear(uid, "db:clearlogs")
        await q.edit_message_text(
            "💾 MA'LUMOTLAR BAZASI\n\nKerakli amalni tanlang:",
            reply_markup=KB.kb_db_panel(),
        )
        return

    # Tizim holati
    if data == "adm:system":
        await show_system(update)
        return

    # Blokdan chiqarish
    if data.startswith("unblock:"):
        await handle_unblock(update, uid, data)
        return

    # DB amallari
    if data.startswith("db:"):
        await handle_db_callback(update, uid, data)
        return


# ─────────────────────────────────────────────────────────────────────────
# ASOSIY PANEL
# ─────────────────────────────────────────────────────────────────────────
async def show_panel(update: Update) -> None:
    """Asosiy admin panelni ko'rsatadi va eski tasdiqlarni bekor qiladi."""
    q = update.callback_query
    action_tokens.clear(SUPER_ADMIN)

    stats = await db.get_stats()
    text = (
        "🖥 SUPER ADMIN PANEL\n\n"
        f"👥 Foydalanuvchilar: {stats['total_users']} ta\n"
        f"✅ Tasdiqlangan: {stats['admins']} ta\n"
        f"⏳ Kutayotgan: {stats['waiting']} ta\n"
        f"🟢 Faol: {stats['running']} ta\n"
        f"🚫 Bloklangan: {stats['blocked']} ta\n\n"
        "Kerakli bo'limni tanlang:"
    )
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=KB.kb_admin_panel())


# ─────────────────────────────────────────────────────────────────────────
# FOYDALANUVCHILAR RO'YXATI
# ─────────────────────────────────────────────────────────────────────────
async def show_users(update: Update, page: int = 0) -> None:
    """Foydalanuvchilar ro'yxati (sahifalash bilan)."""
    q = update.callback_query
    users = await db.get_all_users()

    if not users:
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                "👥 Foydalanuvchilar yo'q.",
                reply_markup=KB.kb_admin_back(),
            )
        return

    text = (
        f"👥 FOYDALANUVCHILAR ({len(users)} ta)\n\n"
        "Belgilar:\n"
        "🟢 — ishlayapti\n"
        "⚪ — sessiya bor, to'xtatilgan\n"
        "🔑 — sessiya yo'q (login kerak)\n"
        "⏳ — tasdiq kutilmoqda\n"
        "🚫 — bloklangan\n\n"
        "Tanlash uchun bosing:"
    )
    kb = KB.kb_users_list(users, page=page)
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=kb)


async def show_pending(update: Update, page: int = 0) -> None:
    """Admin tasdig'ini kutayotgan arizalar ro'yxati."""
    q = update.callback_query
    users = await db.get_pending_users()
    if not users:
        await q.edit_message_text(
            "✅ Tasdiq kutilayotgan arizalar yo'q.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    await q.edit_message_text(
        f"⏳ TASDIQ KUTILAYOTGANLAR ({len(users)} ta)\n\n"
        "Arizani ochib, ism va telefonni tekshiring:",
        reply_markup=KB.kb_pending_users(users, page=page),
    )


# ─────────────────────────────────────────────────────────────────────────
# STATISTIKA
# ─────────────────────────────────────────────────────────────────────────
async def show_stats(update: Update) -> None:
    """Umumiy statistika."""
    q = update.callback_query
    stats = await db.get_stats()

    # Worker statistikasi
    from bot.menu import worker_manager

    w_stats = worker_manager.stats() if worker_manager else {}

    # Pool statistikasi
    from worker.worker import client_pool

    p_stats = client_pool.stats() if client_pool else {}

    text = (
        "📊 UMUMIY STATISTIKA\n\n"
        f"👥 Foydalanuvchilar:\n"
        f"   • Jami: {stats['total_users']} ta\n"
        f"   • Tasdiqlangan: {stats['admins']} ta\n"
        f"   • Kutayotgan: {stats['waiting']} ta\n"
        f"   • Bloklangan: {stats['blocked']} ta\n\n"
        f"⚙️ Workerlar:\n"
        f"   • Faol: {w_stats.get('active_workers', 0)} ta\n"
        f"   • Limit: {w_stats.get('max', 0)} ta\n\n"
        f"🌊 Client pool:\n"
        f"   • Ishlatilmoqda: {p_stats.get('in_use', 0)} ta\n"
        f"   • Ulangan: {p_stats.get('total_clients', 0)} ta\n"
        f"   • Limit: {p_stats.get('max', 0)} ta\n\n"
        f"💬 Jami guruhlar: {stats['total_groups']} ta\n"
        f"📝 Jami postlar: {stats['total_posts']} ta"
    )

    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=KB.kb_admin_back())


# ─────────────────────────────────────────────────────────────────────────
# BLOKLANGANLAR
# ─────────────────────────────────────────────────────────────────────────
async def show_blocked(update: Update, page: int = 0) -> None:
    """Bloklangan foydalanuvchilar ro'yxati."""
    q = update.callback_query
    users = await db.get_all_users()
    blocked = [u for u in users if u.get("is_blocked")]

    if not blocked:
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                "✅ Bloklangan foydalanuvchilar yo'q.",
                reply_markup=KB.kb_admin_back(),
            )
        return

    text = f"🚫 BLOKLANGANLAR ({len(blocked)} ta)\n\nBlokdan chiqarish uchun bosing:"
    kb = KB.kb_blocked_list(blocked, page=page)
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=kb)


async def handle_unblock(update: Update, admin_uid: int, data: str) -> None:
    """Blokdan chiqarish."""
    if admin_uid != SUPER_ADMIN:
        return

    try:
        target = int(data.split(":")[1])
    except (ValueError, IndexError):
        return

    from admin.admin_actions import action_unblock

    target_lock = user_update_lock(target)
    if target_lock is user_update_lock(admin_uid):
        await action_unblock(update, admin_uid, target)
    else:
        async with target_lock:
            await action_unblock(update, admin_uid, target)


# ─────────────────────────────────────────────────────────────────────────
# TIZIM HOLATI
# ─────────────────────────────────────────────────────────────────────────
async def show_system(update: Update) -> None:
    """Tizim holati."""
    q = update.callback_query
    from bot.menu import worker_manager
    from worker.health import START_TIME, _get_memory_info, format_status_message
    from worker.worker import client_pool

    uptime = int(time.time() - START_TIME)
    w_stats = worker_manager.stats() if worker_manager else None
    p_stats = client_pool.stats() if client_pool else None
    memory = _get_memory_info()

    text = format_status_message(uptime, w_stats, p_stats, memory)

    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=KB.kb_admin_back())


# ─────────────────────────────────────────────────────────────────────────
# DB PANEL
# ─────────────────────────────────────────────────────────────────────────
async def handle_db_callback(update: Update, admin_uid: int, data: str) -> None:
    """DB panel callback'lari."""
    q = update.callback_query

    if admin_uid != SUPER_ADMIN:
        return

    # Sessiya sirlarisiz eksport
    if data == "db:export":
        from datetime import datetime, timezone

        from config.config import BACKUP_DIR
        from core.utils import safe_unlink

        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        export_path = BACKUP_DIR / (
            f"avtobot_sanitized_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}.db"
        )
        try:
            await db.backup_to(export_path, sanitize_sessions=True)
            size_kb = export_path.stat().st_size // 1024
            with export_path.open("rb") as document:
                await application.bot.send_document(
                    admin_uid,
                    document=document,
                    filename="avtobot_sanitized.db",
                    caption=(
                        f"📥 Sanitized SQLite baza ({size_kb} KB)\n"
                        "🔒 session va pending_session chiqarib tashlangan"
                    ),
                )
            await q.edit_message_text(
                "✅ Sanitized baza yuborildi.",
                reply_markup=KB.kb_db_panel(),
            )
        except Exception as exc:
            log(f"DB eksport xatosi: {type(exc).__name__}", "error")
            await q.edit_message_text(
                "❌ Eksport yaratilmadi.",
                reply_markup=KB.kb_db_panel(),
            )
        finally:
            safe_unlink(export_path)
        return

    # SQLite online backup va retention
    if data == "db:backup":
        from datetime import datetime, timezone

        from config.config import BACKUP_DIR, BACKUP_RETENTION

        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            backup = BACKUP_DIR / (
                f"avtobot_backup_{datetime.now(timezone.utc):%Y%m%d_%H%M%S_%f}.db"
            )
            await db.backup_to(backup)
            backups = sorted(
                BACKUP_DIR.glob("avtobot_backup_*.db"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
            for old in backups[BACKUP_RETENTION:]:
                old.unlink(missing_ok=True)
            await q.edit_message_text(
                f"✅ Izchil zaxira yaratildi: `{backup.name}`",
                reply_markup=KB.kb_db_panel(),
                parse_mode="Markdown",
            )
        except Exception as exc:
            log(f"DB backup xatosi: {type(exc).__name__}", "error")
            await q.edit_message_text(
                "❌ Zaxira yaratilmadi.",
                reply_markup=KB.kb_db_panel(),
            )
        return

    # Loglarni tozalash
    if data == "db:clearlogs:ask":
        token = action_tokens.issue(admin_uid, "db:clearlogs")
        await q.edit_message_text(
            "⚠️ Server loglari qaytarib bo'lmaydigan tarzda tozalansinmi?",
            reply_markup=KB.kb_clear_logs_confirm(token),
        )
        return

    if data.startswith("db:clearlogs:confirm:"):
        token = data.rsplit(":", 1)[-1]
        if not action_tokens.consume(admin_uid, "db:clearlogs", token):
            await q.edit_message_text(
                "⚠️ Bu tasdiqlash oynasi eskirgan.",
                reply_markup=KB.kb_db_panel(),
            )
            return

        from config.config import LOG_FILE

        try:
            if LOG_FILE.exists():
                size_mb = LOG_FILE.stat().st_size / 1024 / 1024
                await asyncio.to_thread(LOG_FILE.write_text, "", encoding="utf-8")
                await q.edit_message_text(
                    f"✅ Log tozalandi ({size_mb:.1f} MB).",
                    reply_markup=KB.kb_db_panel(),
                )
            else:
                await q.edit_message_text(
                    "❌ Log fayli topilmadi.",
                    reply_markup=KB.kb_db_panel(),
                )
        except OSError as exc:
            log(f"Log tozalash xatosi: {type(exc).__name__}", "error")
            await q.edit_message_text(
                "❌ Log faylini tozalab bo'lmadi.",
                reply_markup=KB.kb_db_panel(),
            )
        return
