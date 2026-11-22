"""
Asosiy menyu handlerlari (yassi, ichki menyusiz klaviatura).

Tugmalar:
- ▶️ Start / ⛔ Stop
- 🔍 Guruhlarni topish / 💬 Guruhlar
- ➕ Post qo'shish / 🗑 Post o'chirish
- ⏱ Interval / 👥 Referal
- 👥 Jamoam (faqat jamoa a'zosi/adminida)
"""

from __future__ import annotations


from telegram import Update

from bot import action_tokens
from bot import keyboards as KB
from bot import texts as T
from core import database as db
from core.errlog import log_gap
from core.logger import log
from core.utils import reply_text_safe, start_of_local_day_ts
from worker.client_pool import PoolBusyError, SessionInvalidError

# ─────────────────────────────────────────────────────────────────────────
# WORKER MANAGER (main.py da o'rnatiladi)
# ─────────────────────────────────────────────────────────────────────────
worker_manager = None


def set_worker_manager(wm) -> None:
    """main.py dan chaqiriladi."""
    global worker_manager
    worker_manager = wm


def current_state(uid: int) -> bool:
    """Foydalanuvchining posting holati (jarayon ichidagi haqiqiy holat)."""
    return bool(worker_manager and worker_manager.is_running(uid))


def state_line(uid: int) -> str:
    """Asosiy menyu ustidagi holat qatori.

    ``▶️ Start`` va ``⛔ Stop`` tugmalari **doimiy va alohida** qoladi —
    holat faqat matnda ko'rsatiladi.
    """
    return T.STATE_ON if current_state(uid) else T.STATE_OFF


async def show_home(
    update: Update, uid: int, note: str = "", *, in_place: bool = False
) -> None:
    """Asosiy menyuni holat qatori bilan ko'rsatadi.

    Barcha "🏠 Asosiy menyu" chiqarish joylari shu funksiyadan
    foydalanadi — holat har doim bir xil ko'rinadi.

    ``reply_text_safe`` ishlatiladi — funksiya inline tugma bosilganda
    ham chaqiriladi (u yerda ``update.message`` bo'lmasligi mumkin).

    ``in_place=True`` — inline kontekstda mavjud xabarni o'zida
    tahrirlaydi (yangi xabar yubormaydi).
    """
    text = "🏠 Asosiy menyu"
    if note:
        text = f"{note}\n\n{text}"
    await reply_text_safe(
        update,
        f"{text}\n\n{state_line(uid)}",
        reply_markup=await KB.kb_main_for(uid, running=current_state(uid)),
        in_place=in_place,
    )


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




# ─────────────────────────────────────────────────────────────────────────
# ⏱ INTERVAL
# ─────────────────────────────────────────────────────────────────────────
async def show_interval_choice(update: Update, uid: int | None = None) -> None:
    """⏱ Interval oynasi — umumiy yoki bitta guruh uchun.

    Ikki xil interval bor va ikkalasi ham shu oynadan tanlanadi:
      * umumiy — barcha guruhlar uchun bir vaqtda;
      * alohida — bitta tanlangan guruh uchun.
    """
    if uid is None:
        uid = update.effective_user.id
    global_interval = await db.get_interval(uid)
    text = (
        "⏱ <b>INTERVAL</b>\n\n"
        f"Umumiy interval: {global_interval} daqiqa\n\n"
        "Qaysini o'zgartirmoqchisiz?"
    )
    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=KB.kb_interval_choice(),
    )


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

    # Jamoa admini muddati tugagan bo'lsa — jamoasi ham ishlamaydi.
    if await db.team_admin_expired(uid):
        return False, (
            "⛔️ Jamoangiz adminining muddati tugadi.\n\n"
            "💡 Administratoringiz super admin bilan bog'lanib, "
            "muddatni uzaytirishi kerak."
        )
    if await db.team_owner_expired(uid):
        return False, (
            "⛔️ Jamoangiz adminining muddati tugadi.\n\n"
            "💡 Administratoringiz super admin bilan bog'lanib, "
            "muddatni uzaytirishi kerak."
        )
    if await db.team_owner_disabled(uid):
        return False, (
            "⛔️ Jamoangiz administratori bloklandi.\n\n"
            "💡 Administratoringiz super admin bilan bog'laning."
        )

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

    uid = update.effective_user.id

    # ▶️ Start
    if text.startswith(T.BTN_START):
        await handle_start(update)
        return True

    # ⛔ Stop
    if text.startswith(T.BTN_STOP):
        await handle_stop(update)
        return True

    # 🔍 Guruhlarni avtomatik topish
    if text == T.BTN_FIND_GROUPS:
        await G.discover_groups(update)
        return True

    # 💬 Guruhlar — ro'yxat + o'chirish (bitta oyna)
    if text == T.BTN_GROUPS:
        from bot import my_groups as MG

        await MG.show_my_groups(update, uid)
        return True

    # ⏱ Interval — umumiy yoki bitta guruh uchun
    if text == T.BTN_INTERVAL:
        await show_interval_choice(update)
        return True

    # ⏱ Guruh intervali — eski tugma (interval oynasiga yo'naltiramiz)
    if text == T.BTN_GROUP_INTERVAL:
        await show_interval_choice(update)
        return True

    # ➖ Guruh o'chirish (eski tugma — o'z guruhlari oynasiga yo'naltiramiz)
    if text == T.BTN_DEL_GROUP:
        from bot import my_groups as MG

        await MG.show_my_groups(update, uid)
        return True

    # ➕ Post qo'shish
    if text == T.BTN_ADD_POST:
        await P.begin_add_post(update)
        return True

    # 🗑 Post o'chirish
    if text == T.BTN_DEL_POST:
        await P.begin_delete_posts(update)
        return True

    # ⏰ Posting oralig'i — eski tugma (interval oynasiga yo'naltiramiz)
    if text == T.BTN_TIMER:
        await show_interval_choice(update)
        return True

    # 👥 Referal
    if text == T.BTN_REFERRAL:
        await R.show_referral(update)
        return True

    # 👥 Jamoam — jamoa admini uchun panel, oddiy a'zo uchun jamoa kartasi
    if text == T.BTN_TEAM_MENU:
        from bot import teams as Tm

        uid = update.effective_user.id
        user = await db.get_user(uid) or {}
        if user.get("is_team_admin"):
            await Tm.show_team_admin_panel(update, uid)
        elif user.get("team_id"):
            await Tm.show_team_member_panel(update, uid)
        else:
            await Tm.show_team_admin_panel(update, uid)
        return True

    # 👑 Admin bo'lish — jamoa yaratish
    if text == T.BTN_TEAM_ADMIN:
        from bot import teams as Tm

        await Tm.begin_team_admin_register(update, update.effective_user.id)
        return True

    # 🎯 Jamoani tanlash — jamoasiz foydalanuvchi uchun.
    # Eski klaviaturalarda tugma matni "🎯 Jamoa tanlash" edi —
    # ikkalasini ham qabul qilamiz.
    if text in (T.BTN_TEAM_PICK, "🎯 Jamoa tanlash"):
        from bot import teams as Tm

        await Tm.show_team_picker(update, update.effective_user.id)
        return True

    # ⬅️ Kiritish oynasidan asosiy menyuga
    if text == T.BTN_BACK:
        await show_home(update, update.effective_user.id)
        return True

    # Noma'lum tugma — bu kamchilik: eski klaviatura matni yoki
    # boshqa savol. Logga yoziladi (text qisqa qilib).
    log_gap(uid, f"Noma'lum menyu tugmasi: {text[:40]!r}", action="menu")
    return False
