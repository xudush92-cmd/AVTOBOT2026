"""
Asosiy menyu handlerlari.

Tugmalar:
- ▶️ Start
- ⛔ Stop
- 📊 Status
- 💬 Guruhlar
"""

from __future__ import annotations

from telegram import Update

from bot import keyboards as KB
from bot import texts as T
from core import database as db
from core.logger import log
from core.utils import format_expires


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
async def show_status(update: Update) -> None:
    """📊 Status tugmasi bosilganda."""
    uid = update.effective_user.id

    chats = await db.get_chats(uid)
    posts = await db.get_posts(uid)
    interval = await db.get_interval(uid)
    expires = await db.get_tariff_expires(uid)
    expired = await db.is_tariff_expired(uid)

    running = False
    if worker_manager:
        running = worker_manager.is_running(uid)

    text = T.status_text(
        running=running,
        expired=expired,
        groups=len(chats),
        posts=len(posts),
        interval=interval,
        expires=format_expires(expires),
    )

    await update.message.reply_text(
        text,
        reply_markup=KB.kb_main(running=running),
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

    await update.message.reply_text(
        text,
        reply_markup=KB.kb_start_confirm(),
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

    await update.message.reply_text(
        T.STOP_CONFIRM,
        reply_markup=KB.kb_stop_confirm(),
  )
  

# ─────────────────────────────────────────────────────────────────────────
# START TASDIQLANGANDA (callback)
# ─────────────────────────────────────────────────────────────────────────
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

    if await db.is_tariff_expired(uid):
        return False, T.EXPIRED_TEXT

    chats = await db.get_chats(uid)
    posts = await db.get_posts(uid)

    if not chats or not posts:
        return False, "❌ Guruh yoki post yo'q."

    started = await worker_manager.start_worker(uid)
    if not started:
        return False, T.START_BUSY

    await db.set_running(uid, True)
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
    from bot import timer as Tm
    from bot import referral as R

    # ▶️ Start
    if text == T.BTN_START:
        await handle_start(update)
        return True

    # ⛔ Stop
    if text == T.BTN_STOP:
        await handle_stop(update)
        return True

    # 📊 Status
    if text.startswith(T.BTN_STATUS):
        await show_status(update)
        return True

    # 💬 Guruhlar
    if text == T.BTN_GROUPS:
        await G.show_groups(update)
        return True

    # 📝 Postlar
    if text == T.BTN_POSTS:
        await P.show_posts(update)
        return True

    # ➕ Guruh qo'shish
    if text == T.BTN_ADD_GROUP:
        await G.begin_add_groups(update)
        return True

    # ➖ Guruh o'chirish
    if text == T.BTN_DEL_GROUP:
        await G.begin_delete_groups(update)
        return True

    # 📝 Post qo'shish
    if text == T.BTN_ADD_POST:
        await P.begin_add_post(update)
        return True

    # 🗑 Post o'chirish
    if text == T.BTN_DEL_POST:
        await P.begin_delete_posts(update)
        return True

    # ⏰ Vaqt
    if text == T.BTN_TIMER:
        await Tm.begin_set_interval(update)
        return True

    # 👥 Referal
    if text == T.BTN_REFERRAL:
        await R.show_referral(update)
        return True

    # ⬅️ Ichki menyudan asosiy menyuga
    if text == T.BTN_BACK:
        uid = update.effective_user.id
        running = bool(worker_manager and worker_manager.is_running(uid))
        await update.message.reply_text(
            "🏠 Asosiy menyu",
            reply_markup=KB.kb_main(running=running),
        )
        return True

    return False
