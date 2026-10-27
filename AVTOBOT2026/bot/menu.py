"""
Asosiy menyu handlerlari (yassi, ichki menyusiz klaviatura).

Tugmalar:
- ▶️ Start / ⛔ Stop
- 📊 Status / 📈 Hisobot / 📦 Paket
- 🔍 Guruhlarni topish / ➖ Guruh o'chirish
- ➕ Post qo'shish / 🗑 Post o'chirish
- ⏱ Posting oralig'i / 👥 Referal
"""

from __future__ import annotations

import time

from telegram import Update

from bot import action_tokens
from bot import keyboards as KB
from bot import texts as T
from core import database as db
from core.logger import log
from core.utils import format_expires, start_of_local_day_ts
from worker.client_pool import PoolBusyError, SessionInvalidError

# ─────────────────────────────────────────────────────────────────────────
# WORKER MANAGER (main.py da o'rnatiladi)
# ─────────────────────────────────────────────────────────────────────────
worker_manager = None


def set_worker_manager(wm) -> None:
    """main.py dan chaqiriladi."""
    global worker_manager
    worker_manager = wm


# ─────────────────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────────────────
async def _status_snapshot(uid: int) -> dict:
    """Status/Hisobot ekranlari uchun umumiy ma'lumot to'plami."""
    import time as _time

    chats = await db.get_chats(uid)
    posts = await db.get_posts(uid)
    interval = await db.get_interval(uid)
    expires = await db.get_tariff_expires(uid)
    limits = await db.get_limits(uid)
    day_start = start_of_local_day_ts()
    stats = await db.send_stats(uid, day_start)
    eta = await db.next_send_eta(uid)

    next_eta_text = ""
    if eta:
        delta = int(eta - _time.time())
        next_eta_text = "hozir" if delta <= 0 else _humanize(delta)

    daily_limit = int(limits.get("daily_limit") or 0)
    daily_left = ""
    if daily_limit > 0:
        left = max(0, daily_limit - int(stats.get("sent_ok") or 0))
        daily_left = f"{left} ta qoldi ({daily_limit} ta/kun)"

    return {
        "chats": chats,
        "posts": posts,
        "interval": interval,
        "expires": expires,
        "expired": await db.is_tariff_expired(uid),
        "limits": limits,
        "stats": stats,
        "next_eta": next_eta_text,
        "daily_left": daily_left,
        "active_hours": (limits.get("active_hours") or "").strip(),
        "running": bool(worker_manager and worker_manager.is_running(uid)),
    }


def _humanize(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} soniyadan so'ng"
    if seconds < 3600:
        return f"{seconds // 60} daqiqadan so'ng"
    if seconds < 86400:
        return f"{seconds // 3600} soat {seconds % 3600 // 60} daqikadan so'ng"
    return f"{seconds // 86400} kundan so'ng"


async def show_status(update: Update) -> None:
    """📊 Status tugmasi bosilganda."""
    uid = update.effective_user.id
    snapshot = await _status_snapshot(uid)
    limits = snapshot["limits"]
    stats = snapshot["stats"]

    text = T.status_text(
        running=snapshot["running"],
        expired=snapshot["expired"],
        groups=len(snapshot["chats"]),
        posts=len(snapshot["posts"]),
        interval=snapshot["interval"],
        expires=format_expires(snapshot["expires"]),
        today_ok=int(stats.get("sent_ok") or 0),
        today_failed=int(stats.get("sent_failed") or 0),
        next_eta=snapshot["next_eta"],
        last_error=stats.get("last_error") or "",
        max_groups=int(limits.get("max_groups") or 0),
        max_posts=int(limits.get("max_posts") or 0),
        daily_left=snapshot["daily_left"],
        active_hours=snapshot["active_hours"],
        plan_label=limits.get("label") or "",
    )
    if not snapshot["posts"] or not snapshot["chats"]:
        text += "\n\n" + T.status_next_step(
            groups=len(snapshot["chats"]), posts=len(snapshot["posts"])
        )

    await update.message.reply_text(text, reply_markup=KB.kb_main(running=snapshot["running"]))


async def show_report(update: Update) -> None:
    """📈 Hisobot — statistika, guruh salomatligi VA paket/limitlar bitta ekranda."""
    uid = update.effective_user.id
    snapshot = await _status_snapshot(uid)
    stats = snapshot["stats"]
    limits = snapshot["limits"]
    since_day = start_of_local_day_ts()
    week_since = time.time() - 7 * 86400

    health: list[dict] = []
    week: dict = {}
    gstats: dict = {}
    expired_users: list[dict] = []
    try:
        health = await db.group_health(uid)
        week = await db.send_stats(uid, week_since)
        gstats = await db.global_send_stats(since_day)
        expired_users = [
            await db.get_user(u) or {"uid": u}
            for u in (await db.get_expired_users())[:10]
        ]
    except Exception as exc:  # noqa: BLE001 - hisobot menyuni buzmasin
        log(f"Hisobot o'qishda xato: {exc}", "warning")

    # Hali bir marta ham sinab ko'rilmagan guruhlar "xato" hisoblanmaydi.
    failed_groups = sum(1 for row in health if row.get("last_ok") == 0)
    report = T.report_text(
        today_ok=int(stats.get("sent_ok") or 0),
        today_failed=int(stats.get("sent_failed") or 0),
        week_ok=int(week.get("sent_ok") or 0),
        groups_total=len(snapshot["chats"]),
        groups_failed=failed_groups,
        next_eta=snapshot["next_eta"] or "—",
        last_error=str(stats.get("last_error") or ""),
        daily_left=snapshot["daily_left"],
        active_hours=snapshot["active_hours"],
        running=snapshot["running"],
        expired_users=expired_users,
        global_today=gstats,
    )

    # Paket va limitlar shu ekranning davomida ko'rsatiladi (alohida tugma yo'q).
    daily_limit = int(limits.get("daily_limit") or 0)
    used_today = int(stats.get("sent_ok") or 0)
    daily_left = (
        f"{used_today}/{daily_limit} ta ishlatilgan" if daily_limit else "cheksiz"
    )
    plan = T.plan_text(
        limits=limits,
        interval=snapshot["interval"],
        expires=format_expires(snapshot["expires"]),
        daily_left=daily_left,
    )
    text = f"{report}\n\n──────────────────\n\n{plan}"
    await update.message.reply_text(
        text, reply_markup=KB.kb_main(running=snapshot["running"])
    )


async def show_plan(update: Update) -> None:
    """📦 Paket va limitlar ekrani."""
    uid = update.effective_user.id
    snapshot = await _status_snapshot(uid)
    limits = snapshot["limits"]
    daily_limit = int(limits.get("daily_limit") or 0)
    used_today = int(snapshot["stats"].get("sent_ok") or 0)
    daily_left = (
        f"{used_today}/{daily_limit} ta ishlatilgan" if daily_limit else "cheksiz"
    )
    text = T.plan_text(
        limits=limits,
        interval=snapshot["interval"],
        expires=format_expires(snapshot["expires"]),
        daily_left=daily_left,
    )
    await update.message.reply_text(text, reply_markup=KB.kb_main(running=snapshot["running"]))


# ─────────────────────────────────────────────────────────────────────────
# START (▶️)
# ─────────────────────────────────────────────────────────────────────────
async def handle_start(update: Update) -> None:
    """▶️ Start tugmasi bosilganda."""
    uid = update.effective_user.id

    # Allaqachon ishlayaptimi?
    if worker_manager and worker_manager.is_running(uid):
        await update.message.reply_text(T.START_ALREADY)
        return

    user = await db.get_user(uid)
    if not user or not user.get("is_admin") or not user.get("session"):
        await update.message.reply_text(
            "❌ Avval tasdiqlangan hisob bilan 🔑 Login qiling.",
            reply_markup=KB.kb_login(),
        )
        return
    if user.get("is_blocked"):
        await update.message.reply_text(T.BLOCKED, reply_markup=KB.kb_blocked())
        return

    # Muddat tugaganmi?
    if await db.is_tariff_expired(uid):
        await update.message.reply_text(T.EXPIRED_TEXT)
        return

    chats = await db.get_chats(uid)
    posts = await db.get_posts(uid)

    if not chats:
        await update.message.reply_text(T.START_NO_GROUPS)
        return

    if not posts:
        await update.message.reply_text(T.START_NO_POSTS)
        return

    interval = await db.get_interval(uid)

    text = T.START_CONFIRM.format(
        groups=len(chats),
        posts=len(posts),
        interval=interval,
    )

    token = action_tokens.issue(uid, "start")
    await update.message.reply_text(
        text,
        reply_markup=KB.kb_start_confirm(token),
    )


# ─────────────────────────────────────────────────────────────────────────
# STOP (⛔)
# ─────────────────────────────────────────────────────────────────────────
async def handle_stop(update: Update) -> None:
    """⛔ Stop tugmasi bosilganda."""
    uid = update.effective_user.id

    if not (worker_manager and worker_manager.is_running(uid)):
        await update.message.reply_text(T.STOP_NOT_RUNNING)
        return

    token = action_tokens.issue(uid, "stop")
    await update.message.reply_text(
        T.STOP_CONFIRM,
        reply_markup=KB.kb_stop_confirm(token),
    )


# ─────────────────────────────────────────────────────────────────────────
# START TASDIQLANGANDA (callback)
# ─────────────────────────────────────────────────────────────────────────
async def check_start_session(uid: int, session: str) -> tuple[bool, str]:
    """Start'da bitta get_me bilan sessiyani tekshiradi, uni hech qachon o'chirmaydi."""
    from worker.worker import client_pool

    if not client_pool:
        return False, T.START_BUSY
    try:
        await client_pool.verify_session(uid, session)
    except SessionInvalidError:
        return False, T.START_SESSION_INVALID
    except PoolBusyError:
        return False, T.START_SESSION_RETRY
    return True, ""


async def confirm_start(uid: int) -> tuple[bool, str]:
    """
    Start tasdiqlanganda workerni boshlash.

    Returns:
        (True, xabar)   — boshlandi
        (False, xabar)  — xato
    """
    if not worker_manager:
        return False, T.GENERIC_ERROR

    if worker_manager.is_running(uid):
        return False, T.START_ALREADY

    user = await db.get_user(uid)
    if not user or not user.get("is_admin"):
        return False, "❌ Hisob tasdiqlanmagan."
    if user.get("is_blocked"):
        return False, T.BLOCKED
    if not user.get("session"):
        return False, "❌ Sessiya yo'q. Qaytadan 🔑 Login qiling."
    if await db.is_tariff_expired(uid):
        return False, T.EXPIRED_TEXT

    chats = await db.get_chats(uid)
    posts = await db.get_posts(uid)

    if not chats or not posts:
        return False, "❌ Guruh yoki post yo'q."

    valid, reason = await check_start_session(uid, user["session"])
    if not valid:
        return False, reason

    await db.set_running(uid, True)
    started = await worker_manager.start_worker(uid)
    if not started:
        await db.set_running(uid, False)
        return False, T.START_BUSY
    interval = await db.get_interval(uid)
    log(f"▶️ Start: {uid}")

    return True, T.START_DONE.format(
        groups=len(chats),
        posts=len(posts),
        interval=interval,
    )


# ─────────────────────────────────────────────────────────────────────────
# STOP TASDIQLANGANDA (callback)
# ─────────────────────────────────────────────────────────────────────────
async def confirm_stop(uid: int) -> tuple[bool, str]:
    """Stop tasdiqlanganda workerni to'xtatish."""
    if worker_manager:
        await worker_manager.stop_worker(uid)
    from worker.worker import client_pool

    if client_pool:
        await client_pool.remove(uid)
    await db.set_running(uid, False)
    log(f"⛔ Stop: {uid}")
    return True, T.STOP_DONE


# ─────────────────────────────────────────────────────────────────────────
# ASOSIY MENYU — ROUTER
# ─────────────────────────────────────────────────────────────────────────
async def route_menu_button(update: Update, text: str) -> bool:
    """
    Menyu tugmasini tegishli handlerga yo'naltiradi.

    Returns:
        True  — tugma topildi va bajarildi
        False — tugma noma'lum
    """
    # Import ichida — circular import oldini olish uchun
    from bot import groups as G
    from bot import posts as P
    from bot import referral as R
    from bot import timer as Tm

    # ▶️ Start — yorliq holatni ham o'zida olib yuradi: "▶️ Start (🔴 OFF)"
    if text.startswith(T.BTN_START):
        await handle_start(update)
        return True

    # ⛔ Stop — yorliq: "⛔ Stop (🟢 ON)"
    if text.startswith(T.BTN_STOP):
        await handle_stop(update)
        return True

    # 📊 Status (eski klaviaturalarda qolgan bo'lishi mumkin — yo'naltirish ishlaydi)
    if text.startswith(T.BTN_STATUS):
        await show_status(update)
        return True

    # 🔍 Guruhlarni avtomatik topish
    if text == T.BTN_FIND_GROUPS:
        await G.discover_groups(update)
        return True

    # ➖ Guruh o'chirish (ro'yxat inline tugma bo'lib chiqadi)
    if text == T.BTN_DEL_GROUP:
        await G.begin_delete_groups(update)
        return True

    # ➕ Post qo'shish
    if text == T.BTN_ADD_POST:
        await P.begin_add_post(update)
        return True

    # 🗑 Post o'chirish
    if text == T.BTN_DEL_POST:
        await P.begin_delete_posts(update)
        return True

    # ⏰ Posting oralig'i — to'g'ridan-to'g'ri qo'lda qiymat so'raladi
    if text == T.BTN_TIMER:
        await Tm.begin_set_interval(update)
        return True

    # 📈 Hisobot
    if text == T.BTN_REPORT:
        await show_report(update)
        return True

    # 📦 Paket va limitlar
    if text == T.BTN_PLAN:
        await show_plan(update)
        return True

    # 👥 Referal
    if text == T.BTN_REFERRAL:
        await R.show_referral(update)
        return True

    # ⬅️ Kiritish oynasidan asosiy menyuga
    if text == T.BTN_BACK:
        uid = update.effective_user.id
        running = bool(worker_manager and worker_manager.is_running(uid))
        await update.message.reply_text(
            "🏠 Asosiy menyu",
            reply_markup=KB.kb_main(running=running),
        )
        return True

    return False
