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

import contextlib
import time

from telegram import Update

from bot import keyboards as KB
from config.config import SUPER_ADMIN
from core import database as db
from core.logger import log


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
        await show_blocked(update)
        return

    # DB panel
    if data == "adm:db":
        await q.edit_message_text(
            "💾 MA'LUMOTLAR BAZASI\n\n"
            "Kerakli amalni tanlang:",
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
    """Asosiy admin panelni ko'rsatadi."""
    q = update.callback_query

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
        "🚫 — bloklangan\n\n"
        "Tanlash uchun bosing:"
    )
    kb = KB.kb_users_list(users, page=page)
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=kb)


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
async def show_blocked(update: Update) -> None:
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
    kb = KB.kb_blocked_list(blocked)
    with contextlib.suppress(Exception):
        await q.edit_message_text(text, reply_markup=kb)


async def handle_unblock(update: Update, admin_uid: int, data: str) -> None:
    """Blokdan chiqarish."""
    q = update.callback_query

    if admin_uid != SUPER_ADMIN:
        return

    try:
        target = int(data.split(":")[1])
    except (ValueError, IndexError):
        return

    await db.set_blocked(target, False)
    log(f"🔓 Blokdan chiqarildi: {target}")
    await q.edit_message_text(f"🔓 Blokdan chiqarildi: {target}")

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            "✅ Hisobingiz blokdan chiqarildi.\n\n🔑 Login bosing.",
            reply_markup=KB.kb_login(),
        )


# ─────────────────────────────────────────────────────────────────────────
# TIZIM HOLATI
# ─────────────────────────────────────────────────────────────────────────
async def show_system(update: Update) -> None:
    """Tizim holati."""
    q = update.callback_query
    from worker.health import START_TIME, _get_memory_info, format_status_message
    from bot.menu import worker_manager
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

    # Eksport
    if data == "db:export":
        from config.config import DB_PATH
        import os
        if os.path.exists(str(DB_PATH)):
            size_kb = os.path.getsize(str(DB_PATH)) // 1024
            with contextlib.suppress(Exception):
                await application.bot.send_document(
                    admin_uid,
                    document=open(str(DB_PATH), "rb"),
                    filename="avtobot.db",
                    caption=f"📥 SQLite baza ({size_kb} KB)",
                )
            await q.edit_message_text(
                "✅ Baza yuborildi.",
                reply_markup=KB.kb_db_panel(),
            )
        else:
            await q.edit_message_text(
                "❌ Baza topilmadi.",
                reply_markup=KB.kb_db_panel(),
            )
        return

    # Zaxira nusxa
    if data == "db:backup":
        from config.config import DB_PATH
        from datetime import datetime
        import shutil
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup = str(DB_PATH).replace(".db", f"_backup_{ts}.db")
            shutil.copy2(str(DB_PATH), backup)
            await q.edit_message_text(
                f"✅ Zaxira nusxa yaratildi:\n`{backup}`",
                reply_markup=KB.kb_db_panel(),
            )
        except Exception as e:
            await q.edit_message_text(
                f"❌ Zaxira xato: {e}",
                reply_markup=KB.kb_db_panel(),
            )
        return

    # Loglarni tozalash
    if data == "db:clearlogs":
        from config.config import LOG_FILE
        import os
        try:
            if os.path.exists(str(LOG_FILE)):
                size_mb = os.path.getsize(str(LOG_FILE)) / 1024 / 1024
                open(str(LOG_FILE), "w").close()
                await q.edit_message_text(
                    f"✅ Log tozalandi ({size_mb:.1f} MB).",
                    reply_markup=KB.kb_db_panel(),
                )
            else:
                await q.edit_message_text(
                    "❌ Log fayli topilmadi.",
                    reply_markup=KB.kb_db_panel(),
                )
        except Exception as e:
            await q.edit_message_text(
                f"❌ Xato: {e}",
                reply_markup=KB.kb_db_panel(),
            )
        return
