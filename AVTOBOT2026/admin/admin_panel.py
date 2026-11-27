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
from bot import texts as T
from config.config import (
    DURATION_OPTIONS,
    SUPER_ADMIN,
    TEAM_ADMIN_DEFAULT_DAYS,
    TEAM_DEFAULT_MAX_USERS,
)
from core import database as db
from core.logger import log
from core.update_locks import user_update_lock
from core.utils import (
    calc_expires,
    edit_text_safe,
    format_expires,
    reply_text_safe,
    shift_expires,
)

# Jamoa admini sig'imi uchun taklif qilinadigan variantlar.
TEAM_LIMIT_OPTIONS = [2, 5, 10, 20, 50, 100]

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

    # Orqaga — admin oynasini YOPISH (yangi menyu ochilmaydi).
    if data == "adm:back":
        await q.answer()
        await close_admin_window(update)
        # Yo'lni ko'rsatamiz — admin panelga qaytish ochiq qoladi.
        # ⚠️ ``reply_text_safe`` — inline kontekstda ham ishlaydi
        # (``q.message`` inline callback'da None bo'lishi mumkin).
        await reply_text_safe(
            update,
            "✅ Admin panel yopildi.",
            reply_markup=KB.kb_admin_panel(),
        )
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

    # Jamoa adminlari (super admin)
    if data == "adm:teamadmins":
        await q.answer()
        # Oyna yopiladi — ro'yxat yangi xabarda ochiladi.
        await close_admin_window(update)
        await reply_text_safe(
            update,
            "👑 Jamoa adminlari",
            reply_markup=KB.kb_team_admins(await db.get_team_admins()),
        )
        return
    if data == "adm:addteamadmin":
        await begin_add_team_admin(update)
        return
    if data.startswith("adm:teamadmin:"):
        try:
            target = int(data.split(":")[2])
        except (ValueError, IndexError):
            return
        await show_team_admin_card(update, target)
        return
    if data.startswith("adm:teamterm:"):
        try:
            target = int(data.split(":")[2])
        except (ValueError, IndexError):
            return
        await edit_text_safe(q, 
            "📅 Jamoa adminining muddatini o'zgartiring:\n\n"
            "**+** — muddatni uzaytirish.\n"
            "**−** — muddatni kamaytirish.\n\n"
            "Muddat berilganda adminning jamoasi va o'zi qayta ishga tushadi.",
            parse_mode="HTML",
            reply_markup=KB.kb_team_admin_term(target, DURATION_OPTIONS),
        )
        return
    if data.startswith("adm:teamshrinkterm:"):
        try:
            target = int(data.split(":")[2])
        except (ValueError, IndexError):
            return
        admin = await db.get_user(target)
        current = format_expires(
            admin.get("admin_expires_at") if admin else None
        )
        await edit_text_safe(q, 
            "⏳ Muddatni kamaytirish\n\n"
            f"📅 Hozirgi muddat: {current}\n\n"
            "Kamaytirmoqchi bo'lgan kunni tanlang.",
            reply_markup=KB.kb_team_admin_shrink_term(target, DURATION_OPTIONS),
        )
        return
    if data.startswith("adm:teamsetterm:"):
        try:
            target = int(data.split(":")[2])
            days = int(data.split(":")[3])
        except (ValueError, IndexError):
            return
        await set_team_admin_term(update, target, days)
        return
    if data.startswith("adm:teamlimit:"):
        try:
            target = int(data.split(":")[2])
        except (ValueError, IndexError):
            return
        await edit_text_safe(q, 
            "👥 Jamoa adminining sig'imini o'zgartiring:\n\n"
            "Bu — jamoasiga qo'shilishi mumkin bo'lgan foydalanuvchilar "
            "maksimal soni.",
            reply_markup=KB.kb_team_admin_limit(target, TEAM_LIMIT_OPTIONS),
        )
        return
    if data.startswith("adm:teamsetlimit:"):
        try:
            target = int(data.split(":")[2])
            size = int(data.split(":")[3])
        except (ValueError, IndexError):
            return
        await set_team_admin_limit(update, target, size)
        return
    if data.startswith("adm:teamhandover:"):
        try:
            target = int(data.split(":")[2])
        except (ValueError, IndexError):
            return
        await begin_team_handover(update, target)
        return
    if data.startswith("adm:teamhandoverset:"):
        parts = data.split(":")
        try:
            target = int(parts[2])
            new_admin = int(parts[3])
        except (ValueError, IndexError):
            return
        await set_team_handover(update, target, new_admin)
        return

    # Broadcast
    if data == "adm:broadcast":
        from admin import broadcast

        await broadcast.begin_broadcast(update)
        return

    # Muddati tugaganlar
    if data == "adm:expired":
        await show_expired(update)
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
        await edit_text_safe(q, 
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
async def close_admin_window(update: Update) -> None:
    """Admin oynasini **yopadi** — yangi menyu ochilmaydi.

    Super admin «⬅️ Orqaga» bosganida oyna yopilishi kerak: panel
    klaviaturasi ochiq qolmasin, foydalanuvchi asosiy menyuga qaytsin.
    """
    q = update.callback_query
    action_tokens.clear(SUPER_ADMIN)
    deleted = False
    with contextlib.suppress(Exception):
        await q.delete_message()
        deleted = True
    if not deleted:
        with contextlib.suppress(Exception):
            await q.edit_message_reply_markup(reply_markup=None)


async def show_panel(update: Update) -> None:
    """Asosiy admin panelni ko'rsatadi va eski tasdiqlarni bekor qiladi."""
    q = update.callback_query
    action_tokens.clear(SUPER_ADMIN)

    stats = await db.get_stats()
    text = (
        "🖥 SUPER ADMIN PANEL\n\n"
        f"👥 Userlar: {stats['total_users']} | ✅ Admin: {stats['admins']} | "
        f"⏳ Kutilmoqda: {stats['waiting']}\n"
        f"🟢 Ishlayapti: {stats['running']} | 🚫 Bloklangan: {stats['blocked']}\n\n"
        "Bo'limni tanlang:"
    )
    with contextlib.suppress(Exception):
        await edit_text_safe(q, text, reply_markup=KB.kb_admin_panel())


# ─────────────────────────────────────────────────────────────────────────
# FOYDALANUVCHILAR RO'YXATI
# ─────────────────────────────────────────────────────────────────────────
async def show_users(update: Update, page: int = 0) -> None:
    """Foydalanuvchilar ro'yxati (sahifalash bilan)."""
    q = update.callback_query
    users = await db.get_all_users()

    if not users:
        with contextlib.suppress(Exception):
            await edit_text_safe(q, 
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
        await edit_text_safe(q, text, reply_markup=kb)


async def show_pending(update: Update, page: int = 0) -> None:
    """Admin tasdig'ini kutayotgan arizalar ro'yxati."""
    q = update.callback_query
    users = await db.get_pending_users()
    if not users:
        await edit_text_safe(q, 
            "✅ Tasdiq kutilayotgan arizalar yo'q.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    await edit_text_safe(q, 
        f"⏳ TASDIQ KUTILAYOTGANLAR ({len(users)} ta)\n\n"
        "Arizani ochib, ism va telefonni tekshiring:",
        reply_markup=KB.kb_pending_users(users, page=page),
    )


# ─────────────────────────────────────────────────────────────────────────
# MUDDATI TUGAGANLAR
# ─────────────────────────────────────────────────────────────────────────
async def show_expired(update: Update) -> None:
    """Muddati tugagan foydalanuvchilar ro'yxati."""
    q = update.callback_query
    from core.utils import is_expired

    users = await db.get_all_users()
    expired = [u for u in users if is_expired(u.get("tariff_expires_at"))]

    if not expired:
        with contextlib.suppress(Exception):
            await edit_text_safe(q, 
                "✅ Muddati tugagan foydalanuvchilar yo'q.",
                reply_markup=KB.kb_admin_back(),
            )
        return

    text = (
        f"🕓 MUDDATI TUGAGANLAR ({len(expired)} ta)\n\n"
        "Yangi muddat berish uchun foydalanuvchini tanlang:"
    )
    kb = KB.kb_users_list(expired)
    with contextlib.suppress(Exception):
        await edit_text_safe(q, text, reply_markup=kb)


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
        await edit_text_safe(q, text, reply_markup=KB.kb_admin_back())


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
            await edit_text_safe(q, 
                "✅ Bloklangan foydalanuvchilar yo'q.",
                reply_markup=KB.kb_admin_back(),
            )
        return

    text = f"🚫 BLOKLANGANLAR ({len(blocked)} ta)\n\nBlokdan chiqarish uchun bosing:"
    kb = KB.kb_blocked_list(blocked, page=page)
    with contextlib.suppress(Exception):
        await edit_text_safe(q, text, reply_markup=kb)


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
        await edit_text_safe(q, text, reply_markup=KB.kb_admin_back())


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
            await edit_text_safe(q, 
                "✅ Sanitized baza yuborildi.",
                reply_markup=KB.kb_db_panel(),
            )
        except Exception as exc:
            log(f"DB eksport xatosi: {type(exc).__name__}", "error")
            await edit_text_safe(q, 
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
            await edit_text_safe(q, 
                f"✅ Izchil zaxira yaratildi: `{backup.name}`",
                reply_markup=KB.kb_db_panel(),
                parse_mode="Markdown",
            )
        except Exception as exc:
            log(f"DB backup xatosi: {type(exc).__name__}", "error")
            await edit_text_safe(q, 
                "❌ Zaxira yaratilmadi.",
                reply_markup=KB.kb_db_panel(),
            )
        return

    # Loglarni tozalash
    if data == "db:clearlogs:ask":
        token = action_tokens.issue(admin_uid, "db:clearlogs")
        await edit_text_safe(q, 
            "⚠️ Server loglari qaytarib bo'lmaydigan tarzda tozalansinmi?",
            reply_markup=KB.kb_clear_logs_confirm(token),
        )
        return

    if data.startswith("db:clearlogs:confirm:"):
        token = data.rsplit(":", 1)[-1]
        if not action_tokens.consume(admin_uid, "db:clearlogs", token):
            await edit_text_safe(q, 
                "⚠️ Bu tasdiqlash oynasi eskirgan.",
                reply_markup=KB.kb_db_panel(),
            )
            return

        from config.config import LOG_FILE
        from core.logger import clear_log_file

        try:
            if LOG_FILE.exists():
                size_mb = LOG_FILE.stat().st_size / 1024 / 1024
                # Faylni tashqaridan ustidan yozish handler'ni buzadi; ochiq
                # oqimni truncate qilamiz.
                await asyncio.to_thread(clear_log_file)
                await edit_text_safe(q, 
                    f"✅ Log tozalandi ({size_mb:.1f} MB).",
                    reply_markup=KB.kb_db_panel(),
                )
            else:
                await edit_text_safe(q, 
                    "❌ Log fayli topilmadi.",
                    reply_markup=KB.kb_db_panel(),
                )
        except OSError as exc:
            log(f"Log tozalash xatosi: {type(exc).__name__}", "error")
            await edit_text_safe(q, 
                "❌ Log faylini tozalab bo'lmadi.",
                reply_markup=KB.kb_db_panel(),
            )
        return


# ─────────────────────────────────────────────────────────────────────────
# JAMOA ADMINLARI (super admin)
# ─────────────────────────────────────────────────────────────────────────
async def _attach_team_for_admin(target: int) -> dict | None:
    """Jamoa adminiga **haqiqiy** jamoa yaratib bog'laydi.

    Super admin jamoa adminini tayyorlaganda admin darhol o'z jamoasiga
    ega bo'lishi kerak — jamoani keyincha o'zi yaratmasligi uchun.
    Agar admin allaqachon jamoaga bog'langan bo'lsa — mavjud jamoa
    saqlanadi (yangi jamoa yaratilmaydi).
    """
    user = await db.get_user(target) or {}
    current_team_id = int(user.get("team_id") or 0)

    if current_team_id:
        team = await db.get_team(current_team_id)
        if team:
            # Jamoa allaqachon bor — faqat admin belgilarini yangilaymiz.
            await db.set_team_admin(
                target,
                current_team_id,
                max_users=int(user.get("admin_max_users") or TEAM_DEFAULT_MAX_USERS),
                admin_expires_at=calc_expires(TEAM_ADMIN_DEFAULT_DAYS),
            )
            return team

    team = await db.create_team_for_admin(
        target,
        "",
        max_users=TEAM_DEFAULT_MAX_USERS,
        admin_expires_at=calc_expires(TEAM_ADMIN_DEFAULT_DAYS),
    )
    if team:
        log(f"👥 Yaratildi: jamoa #{team['id']} (admin uid={target})")
    else:
        log(f"⚠️ Jamoa yaratilmadi: admin uid={target}")
    return team


async def begin_add_team_admin(update: Update) -> None:
    """Yangi jamoa admini qo'shish — telefon raqam kiritish."""
    from bot.login import user_states

    user_states[update.effective_user.id] = {
        "step": "super_add_team_admin",
        "ts": time.time(),
    }
    await reply_text_safe(
        update,
        T.ADMIN_ADD_ADMIN_ASK,
        reply_markup=KB.kb_input_cancel(),
    )


async def handle_add_team_admin_phone(update: Update, uid: int, text: str) -> None:
    """Super admin yangi jamoa adminining telefon raqamini kiritadi."""
    from bot.login import user_states
    from core.utils import is_valid_phone, normalize_phone

    raw = (text or "").strip()
    phone = normalize_phone(raw)
    if not phone or not is_valid_phone(phone):
        await update.message.reply_text(
            T.ADMIN_ADD_ADMIN_INVALID,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    user_states.pop(uid, None)

    # Allaqachon ro'yxatdan o'tgan bo'lsa — uni hozir jamoa admini qilib
    # tayinlaymiz va **haqiqiy jamoa** yaratib bog'laymiz.
    existing = await db.get_user_by_phone(phone)
    if existing:
        target = int(existing["uid"])
        await _attach_team_for_admin(target)
        # Jamoa admini ham oddiy foydalanuvchi kabi bot imkoniyatlaridan
        # foydalanadi — tasdiqlanmagan bo'lsa, tasdiqlaymiz.
        if not existing.get("is_admin") or existing.get("awaiting_approval"):
            await db.approve_user(target, calc_expires(TEAM_ADMIN_DEFAULT_DAYS))
            await db.set_awaiting_approval(target, False)
        await update.message.reply_text(
            T.ADMIN_ADD_ADMIN_ALREADY.format(
                phone=phone,
                name=existing.get("name") or "Noma'lum",
            )
            + "\n\n✅ U endi jamoa admini bo'ldi.",
            reply_markup=KB.kb_team_admins(await db.get_team_admins()),
        )
        log(f"👑 Ro'yxatdan o'tgan user jamoa admini qilindi: {phone}")
        return

    await db.add_team_invite(phone, uid, team_id=None, kind="admin")
    await update.message.reply_text(
        T.ADMIN_ADD_ADMIN_DONE.format(phone=phone),
        reply_markup=KB.kb_admin_back(),
    )
    log(f"👑 Yangi jamoa admini qo'shildi: {phone}")


async def show_team_admins(update: Update) -> None:
    """Jamoa adminlari ro'yxati."""
    q = update.callback_query
    admins = await db.get_team_admins()
    if not admins:
        # Bo'sh ro'yxatda ham «➕ Admin qo'shish» tugmasi ko'rinishi kerak —
        # aks holda super admin birinchi jamoa adminini qo'shira olmaydi.
        await edit_text_safe(q, 
            "👑 Hozircha jamoa admini yo'q.\n\n"
            "Jamoa adminini **faqat siz** tayyorlaysiz — «➕ Admin "
            "qo'shish» tugmasi orqali telefon raqamini kiriting.\n\n"
            "Admin ro'yxatdan o'tgach uning uchun avtomatik ravishda "
            "**jamoa yaratib qo'yiladi** — u darhol o'z jamoasiga ega bo'ladi.",
            reply_markup=KB.kb_team_admins([]),
        )
        return

    lines = [f"👑 JAMOA ADMINLARI ({len(admins)} ta)", ""]
    for admin in admins:
        name = admin.get("name") or f"uid {admin.get('uid')}"
        expires = format_expires(admin.get("admin_expires_at"))
        limit = int(admin.get("admin_max_users") or 0)
        limit_text = f"{limit} ta" if limit else "cheksiz"
        icon = "👑"
        if admin.get("is_blocked"):
            icon = "🚫"
        elif admin.get("awaiting_approval"):
            icon = "⏳"
        elif KB._admin_expired(admin):
            icon = "⌛"
        lines.append(f"{icon} {name} — muddat: {expires}, sig'im: {limit_text}")
    lines.append("")
    lines.append(
        "👑 faol | ⌛ muddati tugagan | ⏳ tasdiq kutilmoqda | 🚫 bloklangan"
    )
    lines.append("")
    lines.append("Boshqarish uchun adminni tanlang:")
    lines.append("")
    lines.append(
        "➕ Yangi jamoa admini qo'shish uchun — «➕ Admin qo'shish» "
        "tugmasini bosing (telefon raqamini kiriting)."
    )

    await edit_text_safe(q, 
        "\n".join(lines),
        reply_markup=KB.kb_team_admins(admins),
    )


async def show_team_admin_card(update: Update, target: int) -> None:
    """Jamoa admini kartasi."""
    q = update.callback_query
    admin = await db.get_user(target)
    if not admin or not admin.get("is_team_admin"):
        await edit_text_safe(q, 
            "❌ Jamoa admini topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    teams = await db.get_teams(target)
    team_name = teams[0].get("name") if teams else None
    limit = int(admin.get("admin_max_users") or 0)
    limit_text = f"{limit} ta" if limit else "cheksiz"

    # Jamoasi avtomatik yaratilgan admin — jamoa nomi ko'rsatiladi.
    team_line = (
        f"📋 Jamoa: {team_name}"
        if team_name
        else "📋 Jamoa: ⏳ hali yaratilmagan — super admin uni tayyorlaganda "
        "avtomatik yaratiladi"
    )

    text = (
        f"👑 {admin.get('name') or 'Noma`lum'}\n\n"
        f"🆔 {target}\n"
        f"{team_line}\n"
        f"📅 Muddat: {format_expires(admin.get('admin_expires_at'))}\n"
        f"👥 Sig'im: {limit_text}\n\n"
        "Kerakli amalni tanlang:"
    )
    await edit_text_safe(q, text, reply_markup=KB.kb_team_admin_card(target))


async def set_team_admin_term(update: Update, target: int, days: int) -> None:
    """Jamoa adminining muddatini o'zgartiradi.

    ``days > 0`` — muddatni uzaytiradi (mavjud muddat ustiga qo'shiladi).
    ``days < 0`` — muddatni kamaytiradi (mavjud muddatdan ayiriladi).
    """
    q = update.callback_query
    admin = await db.get_user(target)
    if not admin or not admin.get("is_team_admin"):
        await edit_text_safe(q, 
            "❌ Jamoa admini topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    base = admin.get("admin_expires_at")
    expires = shift_expires(base, days)

    # ⚠️ Cheksiz muddatni kamaytirib bo'lmaydi — ``shift_expires``
    # ``None`` qaytaradi. Aks holda muddat "kamaytirish" o'rniga
    # **darhol tugatilardi**, bu esa tasdig'emas edi.
    if expires is None:
        await edit_text_safe(q, 
            "❌ Cheksiz muddatni kamaytirib bo'lmaydi.\n\n"
            "💡 Avval muddat bering (+ tugmasi), keyin kamaytiring.",
            reply_markup=KB.kb_team_admin_card(target),
        )
        return

    await db.set_admin_expires(target, expires)
    # Jamoaning o'z muddatini ham yangilaymiz (jamoa ham to'xtamaydi).
    teams = await db.get_teams(target)
    if teams:
        await db.update_team(int(teams[0]["id"]), expires_at=expires)
    # Jamoa adminining o'z tarif muddati ham yangilanadi — aks holda u
    # muddat uzaytirilgandan keyin ham "muddati tugagan" bo'lib qoladi.
    await db.set_user_limits(target, tariff_expires_at=expires)

    verb = "uzaytirildi" if days > 0 else "kamaytirildi"
    await edit_text_safe(q, 
        f"✅ Muddat {verb}: {admin.get('name') or target}\n\n"
        f"📅 Yangi muddat: {format_expires(expires)}",
        reply_markup=KB.kb_team_admin_card(target),
    )
    log(f"📅 Jamoa admini muddati {verb}: {target} ({days:+d} kun)")


async def set_team_admin_limit(update: Update, target: int, size: int) -> None:
    """Jamoa adminining sig'imini (user soni) o'zgartiradi."""
    q = update.callback_query
    admin = await db.get_user(target)
    if not admin or not admin.get("is_team_admin"):
        await edit_text_safe(q, 
            "❌ Jamoa admini topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    await db.set_admin_max_users(target, size)
    teams = await db.get_teams(target)
    if teams:
        await db.update_team(int(teams[0]["id"]), max_users=size)

    await edit_text_safe(q, 
        f"✅ Sig'im yangilandi: {admin.get('name') or target}\n\n"
        f"👥 Yangi sig'im: {size} ta foydalanuvchi\n"
        "ℹ️ Jamoada hozirgi a'zolar soni limitdan ko'p bo'lsa, "
        "ular saqlanib qoladi — yangi user qo'shilmaydi.",
        reply_markup=KB.kb_team_admin_card(target),
    )
    log(f"👥 Jamoa admini sig'imi yangilandi: {target} → {size}")


async def begin_team_handover(update: Update, target: int) -> None:
    """Jamoani boshqa adminga topshirishni boshlaydi (super admin)."""
    q = update.callback_query
    admin = await db.get_user(target)
    if not admin or not admin.get("is_team_admin"):
        await edit_text_safe(q, 
            "❌ Jamoa admini topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    teams = await db.get_teams(target)
    team_name = teams[0].get("name") if teams else "—"
    admins = [
        a
        for a in await db.get_team_admins()
        if int(a.get("uid") or 0) != int(target)
    ]
    if not admins:
        await edit_text_safe(q, 
            "ℹ️ Topshirish uchun boshqa jamoa admini yo'q.\n\n"
            "Avval «➕ Admin qo'shish» orqali yangi jamoa adminini tayinlang, "
            "keyin jamoani topshirishingiz mumkin.",
            reply_markup=KB.kb_team_admin_card(target),
        )
        return

    await edit_text_safe(q, 
        f"🔄 <b>{team_name}</b> jamoasini kimga topshiramiz?\n\n"
        "ℹ️ Tanlangan admin jamoaning egasi bo'ladi — a'zolar va jamoa "
        "muddatiga ega bo'ladi. Eski admin jamoa boshqaruvidan chiqadi.",
        parse_mode="HTML",
        reply_markup=KB.kb_team_handover_options(target, admins),
    )


async def set_team_handover(update: Update, target: int, new_admin: int) -> None:
    """Jamoani boshqa jamoa adminga topshiradi (super admin)."""
    q = update.callback_query
    old_admin = await db.get_user(target)
    new = await db.get_user(new_admin)
    if not old_admin or not old_admin.get("is_team_admin"):
        await edit_text_safe(q, 
            "❌ Jamoa admini topilmadi.",
            reply_markup=KB.kb_admin_back(),
        )
        return
    if not new or not new.get("is_team_admin"):
        await edit_text_safe(q, 
            "❌ Yangi admin jamoa admini emas.",
            reply_markup=KB.kb_team_admin_card(target),
        )
        return
    if int(new_admin) == int(target):
        await edit_text_safe(q, 
            "ℹ️ Bu jamoa allaqachon shu adminning.",
            reply_markup=KB.kb_team_admin_card(target),
        )
        return

    teams = await db.get_teams(target)
    if not teams:
        await edit_text_safe(q, 
            "❌ Topshiriladigan jamoa topilmadi.",
            reply_markup=KB.kb_team_admin_card(target),
        )
        return
    team_id = int(teams[0]["id"])
    team_name = teams[0].get("name") or "Jamoa"

    # Jamoaning egasi yangi admin bo'ladi.
    await db.update_team_owner(team_id, new_admin)

    # Yangi admin jamoani boshqaradi — muddat va sig'im o'tadi.
    expires = old_admin.get("admin_expires_at")
    max_users = int(old_admin.get("admin_max_users") or 0) or TEAM_DEFAULT_MAX_USERS
    await db.set_team_admin(
        new_admin,
        team_id,
        max_users=max_users,
        admin_expires_at=expires,
    )
    await db.set_awaiting_approval(new_admin, False)
    if not new.get("is_admin"):
        await db.approve_user(new_admin, expires)
    # Admin muddati o'z tarifiga ham ko'chiriladi.
    await db.set_user_limits(new_admin, tariff_expires_at=expires)

    # Eski admin endi jamoa admini emas.
    await db.clear_team_admin(target)

    # Barcha a'zolar yangi admin ostiga o'tadi.
    await db.reassign_team_members(team_id, new_admin)

    await edit_text_safe(q, 
        f"✅ Jamoa topshirildi!\n\n"
        f"📋 Jamoa: {team_name}\n"
        f"👤 Yangi admin: {new.get('name') or new_admin}\n"
        f"👤 Eski admin: {old_admin.get('name') or target}\n\n"
        "ℹ️ Barcha a'zolar yangi admin ostiga o'tdi. Eski admin jamoa "
        "boshqaruvidan chiqdi.",
        reply_markup=KB.kb_team_admin_card(new_admin),
    )
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            new_admin,
            f"🎉 Siz <b>{team_name}</b> jamoasining yangi admini bo'ldingiz!\n\n"
            "👥 A'zolar sizga o'tdi. Jamoani «👥 Jamoam» orqali boshqaring.",
            parse_mode="HTML",
        )
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target,
            f"ℹ️ Sizning jamoangiz <b>{team_name}</b> boshqa adminga "
            "topshirildi.\n\n"
            "Endi siz faqat oddiy foydalanuvchi sifatida ishlaysiz.",
            parse_mode="HTML",
        )
    log(f"🔄 Jamoa topshirildi: {team_name} — {target} → {new_admin}")
