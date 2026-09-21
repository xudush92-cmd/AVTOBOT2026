"""
Callback query router.

Barcha inline tugmalar shu yerda qayta ishlanadi:
- np: (numpad)
- go:/stop: (start/stop tasdiq)
- delg:/delp: (guruh/post o'chirish)
- app: (admin tasdiq)
- adm: (admin panel)
- uc: (user kartasi)
- exp: (muddat uzaytirish)
- bc: (broadcast)
- db: (database)
- intv: (interval tasdiq)
"""

from __future__ import annotations

import contextlib
import time

from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as KB
from bot import texts as T
from bot.login import (
    attempt_signin,
    begin_qr_login,
    cleanup_login,
    user_states,
)
from bot.menu import confirm_start, confirm_stop
from bot.posts import delete_post_by_index
from config.config import CODE_LENGTH, LOGIN_TIMEOUT_S, MAX_CODE_LENGTH
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
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Barcha callback query'larni qabul qiladi."""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data or ""

    try:
        # NUMPAD
        if data.startswith("np:"):
            await handle_numpad(update, uid, data)
            return

        # QR LOGIN
        if data == "qr:cancel":
            await handle_qr_cancel(update, uid)
            return

        # START/STOP TASDIQ
        if data == "go:yes":
            await handle_go_yes(update, uid)
            return
        if data == "go:no":
            await q.edit_message_text(T.ACTION_CANCELLED)
            return
        if data == "stop:yes":
            await handle_stop_yes(update, uid)
            return
        if data == "stop:no":
            await q.edit_message_text("✅ Posting davom etmoqda.")
            return

        # INTERVAL TASDIQ
        if data == "intv:yes":
            await handle_intv_yes(update, uid)
            return
        if data == "intv:no":
            user_states.pop(uid, None)
            await q.edit_message_text(T.ACTION_CANCELLED)
            return

        # GURUH O'CHIRISH
        if data.startswith("delg:"):
            await handle_del_group(update, uid, data)
            return

        # POST O'CHIRISH
        if data.startswith("delp:"):
            await handle_del_post(update, uid, data)
            return

        # ADMIN TASDIQ (yangi foydalanuvchi)
        if data.startswith("app:"):
            await handle_admin_approve(update, uid, data)
            return

        # ADMIN PANEL
        if data.startswith("adm:"):
            from admin import admin_panel
            await admin_panel.handle_admin_callback(update, uid, data)
            return

        # USER KARTASI
        if data.startswith("uc:"):
            from admin import admin_actions
            await admin_actions.handle_user_card(update, uid, data)
            return

        # MUDDAT UZAYTIRISH
        if data.startswith("exp:"):
            from admin import admin_actions
            await admin_actions.handle_expire(update, uid, data)
            return

        # BLOKDAN CHIQARISH
        if data.startswith("unblock:"):
            from admin import admin_panel
            await admin_panel.handle_unblock(update, uid, data)
            return

        # BROADCAST
        if data.startswith("bc:"):
            from admin import broadcast
            await broadcast.handle_broadcast_callback(update, uid, data)
            return

        # DATABASE
        if data.startswith("db:"):
            from admin import admin_panel
            await admin_panel.handle_db_callback(update, uid, data)
            return

        # NOOP (bosilmaydigan tugma)
        if data == "adm:noop":
            return

    except Exception as e:
        log(f"callback xatolik {uid} [{data}]: {type(e).__name__}: {e}", "error")
        with contextlib.suppress(Exception):
            await q.edit_message_text(T.GENERIC_ERROR)
          

# ─────────────────────────────────────────────────────────────────────────
# NUMPAD HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def handle_numpad(update: Update, uid: int, data: str) -> None:
    """Telegram tasdiq kodi uchun raqamli tugmalar va QR fallback."""
    q = update.callback_query
    state = user_states.get(uid, {})

    # Login jarayonida emasmi?
    if state.get("step") != "code":
        with contextlib.suppress(Exception):
            await q.edit_message_text("⚠️ Login jarayonida emassiz.")
        return

    # Vaqt tugaganmi?
    if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
        await cleanup_login(uid)
        with contextlib.suppress(Exception):
            await q.edit_message_text(T.CODE_TIMEOUT)
        await application.bot.send_message(
            uid, "Holat yangilandi.", reply_markup=KB.kb_login()
        )
        return

    action = data.split(":", 1)[1]
    buffer = state.get("code_buffer", "")

    # BEKOR QILISH
    if action == "cancel":
        await cleanup_login(uid)
        with contextlib.suppress(Exception):
            await q.edit_message_text(T.CODE_CANCELLED)
        await application.bot.send_message(
            uid, "Holat yangilandi.", reply_markup=KB.kb_login()
        )
        return

    # AWS/VPS IP sabab kod kelmasa — QR orqali sessiya ochish
    if action == "qr":
        with contextlib.suppress(Exception):
            await q.edit_message_text(T.QR_PREPARING)
        await begin_qr_login(uid)
        return

    expected_length = int(state.get("code_length") or CODE_LENGTH)
    allowed_length = max(MAX_CODE_LENGTH, expected_length)

    # O'CHIRISH (backspace)
    if action == "back":
        buffer = buffer[:-1]

    # TASDIQLASH (ok)
    elif action == "ok":
        if len(buffer) < expected_length:
            await q.answer(
                f"Kamida {expected_length} ta raqam kiriting!", show_alert=True
            )
            return
        with contextlib.suppress(Exception):
            await q.edit_message_text(f"⏳ Kod tekshirilmoqda...\n\n🔢 {buffer}")
        await attempt_signin(uid, buffer)
        return

    # RAQAM
    else:
        if not action.isdigit():
            return
        if len(buffer) >= allowed_length:
            await q.answer(
                f"Maksimal {allowed_length} ta raqam!", show_alert=True
            )
            return
        buffer += action

    state["code_buffer"] = buffer
    state["ts"] = time.time()
    user_states[uid] = state

    with contextlib.suppress(Exception):
        await q.edit_message_text(
            T.numpad_text(buffer, state.get("code_hint", "")),
            reply_markup=KB.kb_numpad(),
        )


async def handle_qr_cancel(update: Update, uid: int) -> None:
    """QR loginni, kutish taskini va vaqtinchalik clientni bekor qiladi."""
    await cleanup_login(uid)
    await application.bot.send_message(
        uid, T.CODE_CANCELLED, reply_markup=KB.kb_login()
    )


# ─────────────────────────────────────────────────────────────────────────
# START TASDIQ
# ─────────────────────────────────────────────────────────────────────────
async def handle_go_yes(update: Update, uid: int) -> None:
    q = update.callback_query
    ok, text = await confirm_start(uid)
    await q.edit_message_text(text)
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            uid, "Holat yangilandi.", reply_markup=KB.kb_main(running=ok)
        )


# ─────────────────────────────────────────────────────────────────────────
# STOP TASDIQ
# ─────────────────────────────────────────────────────────────────────────
async def handle_stop_yes(update: Update, uid: int) -> None:
    q = update.callback_query
    ok, text = await confirm_stop(uid)
    await q.edit_message_text(text)
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            uid, "Holat yangilandi.", reply_markup=KB.kb_main(running=False)
        )


# ─────────────────────────────────────────────────────────────────────────
# INTERVAL TASDIQ
# ─────────────────────────────────────────────────────────────────────────
async def handle_intv_yes(update: Update, uid: int) -> None:
    q = update.callback_query
    state = user_states.get(uid, {})
    minutes = state.get("value")

    if not minutes:
        await q.edit_message_text(T.ACTION_CANCELLED)
        return

    user_states.pop(uid, None)
    await db.set_interval(uid, minutes)
    log(f"⏰ Interval (katta qiymat): {uid} → {minutes}")

    await q.edit_message_text(T.interval_set(minutes))
    user = await db.get_user(uid)
    running = bool(user and user.get("running")) if user else False
    with contextlib.suppress(Exception):
        await application.bot.send_message(
            uid, "Holat yangilandi.", reply_markup=KB.kb_main(running=running)
      )
      

# ─────────────────────────────────────────────────────────────────────────
# GURUH O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def handle_del_group(update: Update, uid: int, data: str) -> None:
    q = update.callback_query

    if data == "delg:cancel":
        await q.edit_message_text(T.ACTION_CANCELLED)
        return

    try:
        index = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        return

    removed = await db.remove_chat(uid, index)
    if removed:
        log(f"🗑 Guruh o'chirildi: {uid} → {removed}")
        await q.edit_message_text(f"🗑 O'chirildi:\n{removed}")
        user = await db.get_user(uid)
        running = bool(user and user.get("running")) if user else False
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid, "Holat yangilandi.", reply_markup=KB.kb_main(running=running)
            )
    else:
        await q.edit_message_text("❌ Guruh topilmadi.")


# ─────────────────────────────────────────────────────────────────────────
# POST O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def handle_del_post(update: Update, uid: int, data: str) -> None:
    q = update.callback_query

    if data == "delp:cancel":
        await q.edit_message_text(T.ACTION_CANCELLED)
        return

    try:
        index = int(data.split(":", 1)[1])
    except (ValueError, IndexError):
        return

    ok, preview = await delete_post_by_index(uid, index)
    if ok:
        await q.edit_message_text(f"🗑 O'chirildi:\n{preview}")
        user = await db.get_user(uid)
        running = bool(user and user.get("running")) if user else False
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid, "Holat yangilandi.", reply_markup=KB.kb_main(running=running)
            )
    else:
        await q.edit_message_text(T.POST_NOT_FOUND)


# ─────────────────────────────────────────────────────────────────────────
# ADMIN TASDIQ (yangi foydalanuvchi)
# ─────────────────────────────────────────────────────────────────────────
async def handle_admin_approve(update: Update, uid: int, data: str) -> None:
    q = update.callback_query

    # Faqat super admin
    from config.config import SUPER_ADMIN
    if uid != SUPER_ADMIN:
        return

    parts = data.split(":")
    action = parts[1]  # yes / no
    target = int(parts[2])

    if action == "yes":
        # Sessiyani faollashtirish
        pending = await db.get_pending(target)
        if pending:
            await db.set_session(target, pending)
            await db.del_pending(target)

        await db.add_admin(target)
        await db.set_awaiting_approval(target, False)

        log(f"✅ Tasdiqlandi: {target}")
        await q.edit_message_text(f"✅ Tasdiqlandi: {target}")

        # Yangi oqimda hali sessiya yo'q: user endi o'zi Login bosadi.
        # `pending` faqat eski oqim bilan moslik uchun qolgan.
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                target,
                T.LOGIN_SUCCESS_APPROVED if pending else T.USER_APPROVED,
                reply_markup=KB.kb_main() if pending else KB.kb_login(),
            )

        # Referal hisoblash
        with contextlib.suppress(Exception):
            from bot.referral import on_referral_counted
            await on_referral_counted(target)

    else:  # no
        await db.del_pending(target)
        await db.set_awaiting_approval(target, False)
        log(f"❌ Rad etildi: {target}")
        await q.edit_message_text(f"❌ Rad etildi: {target}")

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                target,
                T.USER_REJECTED,
                reply_markup=KB.kb_login(),
            )
