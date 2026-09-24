"""Barcha inline callbacklar uchun xavfsiz router."""

from __future__ import annotations

import contextlib
import time

from telegram import Update
from telegram.ext import ContextTypes

from bot import action_tokens
from bot import keyboards as KB
from bot import texts as T
from bot.login import (
    attempt_signin,
    begin_qr_login,
    cleanup_login,
    login_ctx,
    user_states,
)
from bot.menu import confirm_start, confirm_stop
from config.config import (
    CODE_LENGTH,
    LOGIN_TIMEOUT_S,
    MAX_CODE_LENGTH,
    SUPER_ADMIN,
)
from core import database as db
from core.logger import log
from core.session_manager import revoke_telegram_session
from core.update_locks import user_operation_lock, user_update_lock
from core.utils import safe_unlink

application = None


def set_application(app) -> None:
    global application
    application = app


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.callback_query.from_user.id
    async with user_update_lock(uid):
        await _handle_callback_locked(update, uid)


async def _handle_callback_locked(update: Update, uid: int) -> None:
    q = update.callback_query
    data = q.data or ""

    try:
        await q.answer()

        effective_chat = getattr(update, "effective_chat", None)
        if effective_chat and effective_chat.type != "private":
            return
        if data in {"noop", "adm:noop"}:
            return

        # Bloklangan oddiy user eski inline tugmalar orqali cheklovni aylanmasin.
        if uid != SUPER_ADMIN and await db.is_blocked(uid):
            await cleanup_login(uid)
            with contextlib.suppress(Exception):
                await q.edit_message_text(T.BLOCKED)
            await application.bot.send_message(
                uid,
                T.BLOCKED,
                reply_markup=KB.kb_blocked(),
            )
            return

        if data.startswith("np:"):
            await handle_numpad(update, uid, data)
            return
        if data == "qr:cancel":
            await handle_qr_cancel(update, uid)
            return
        if data == "auth:cancel":
            await cleanup_login(uid)
            await q.edit_message_text(T.CODE_CANCELLED)
            await application.bot.send_message(
                uid,
                "Login bekor qilindi.",
                reply_markup=KB.kb_login(),
            )
            return

        ordinary_prefixes = ("go:", "stop:", "intv:", "delg:", "delp:", "self:")
        if uid != SUPER_ADMIN and data.startswith(ordinary_prefixes):
            # Admin lifecycle amali central tekshiruvdan keyin lock kutayotgan
            # paytda targetni o'zgartirishi mumkin. Shu sabab auth target lock
            # ichida yana tekshiriladi va action ham o'sha lockda bajariladi.
            async with user_operation_lock(uid):
                user = await db.get_user(uid)
                if (
                    not user
                    or not user.get("is_admin")
                    or user.get("is_blocked")
                    or user.get("awaiting_approval")
                    or not user.get("session")
                ):
                    action_tokens.clear(uid)
                    blocked = bool(user and user.get("is_blocked"))
                    stale_text = (
                        T.BLOCKED
                        if blocked
                        else "❌ Hisob yoki sessiya endi faol emas. Qaytadan Login qiling."
                    )
                    await q.edit_message_text(stale_text)
                    await application.bot.send_message(
                        uid,
                        stale_text,
                        reply_markup=KB.kb_blocked() if blocked else KB.kb_login(),
                    )
                    return
                if data.startswith("go:"):
                    await _handle_start_confirmation_locked(update, uid, data)
                elif data.startswith("stop:"):
                    await _handle_stop_confirmation_locked(update, uid, data)
                elif data.startswith(("intv:yes:", "intv:no:")):
                    await _handle_intv_confirmation_locked(update, uid, data)
                elif data.startswith("delg:"):
                    await _handle_del_group_locked(update, uid, data)
                elif data.startswith("delp:"):
                    await _handle_del_post_locked(update, uid, data)
                elif data.startswith("self:"):
                    await _handle_self_account_locked(update, uid, data)
            return

        if data.startswith("app:"):
            await handle_admin_approve(update, uid, data)
            return
        if data.startswith("adm:"):
            from admin import admin_panel

            await admin_panel.handle_admin_callback(update, uid, data)
            return
        if data.startswith("uc:"):
            from admin import admin_actions

            await admin_actions.handle_user_card(update, uid, data)
            return
        if data.startswith("aint:"):
            from admin import admin_actions

            await admin_actions.handle_interval(update, uid, data)
            return
        if data.startswith("exp:"):
            from admin import admin_actions

            await admin_actions.handle_expire(update, uid, data)
            return
        if data.startswith("unblock:"):
            from admin import admin_panel

            await admin_panel.handle_unblock(update, uid, data)
            return
        if data.startswith("bc:"):
            from admin import broadcast

            await broadcast.handle_broadcast_callback(update, uid, data)
            return
        if data.startswith("db:"):
            from admin import admin_panel

            await admin_panel.handle_db_callback(update, uid, data)
            return

    except Exception as exc:
        log(
            f"callback xatolik {uid}: {type(exc).__name__}",
            "error",
        )
        with contextlib.suppress(Exception):
            await q.edit_message_text(T.GENERIC_ERROR)


# ─────────────────────────────────────────
# NUMPAD / QR
# ─────────────────────────────────────────
async def handle_numpad(update: Update, uid: int, data: str) -> None:
    q = update.callback_query
    state = user_states.get(uid, {})

    if state.get("step") != "code":
        await q.edit_message_text("⚠️ Bu kod oynasi eskirgan. Qaytadan Login bosing.")
        return

    expected_message = state.get("numpad_msg_id")
    actual_message = getattr(q.message, "message_id", None)
    if (
        expected_message
        and actual_message
        and int(expected_message) != int(actual_message)
    ):
        return

    if time.time() - state.get("ts", 0) > LOGIN_TIMEOUT_S:
        is_admin_flow = bool(state.get("admin_add_user"))
        target = state.get("admin_session_target")
        await cleanup_login(uid)
        await q.edit_message_text(T.CODE_TIMEOUT)
        if target:
            from admin.admin_actions import user_card_markup

            markup = await user_card_markup(int(target), has_session=False)
        else:
            markup = KB.kb_super_admin() if is_admin_flow else KB.kb_login()
        await application.bot.send_message(
            uid,
            "Holat yangilandi.",
            reply_markup=markup,
        )
        return

    action = data.split(":", 1)[1]
    buffer = state.get("code_buffer", "")
    admin_add_user = bool(state.get("admin_add_user"))

    if action == "cancel":
        target = state.get("admin_session_target")
        await cleanup_login(uid)
        await q.edit_message_text(T.CODE_CANCELLED)
        if target:
            from admin.admin_actions import user_card_markup

            markup = await user_card_markup(int(target), has_session=False)
        else:
            markup = KB.kb_super_admin() if admin_add_user else KB.kb_login()
        await application.bot.send_message(
            uid,
            "Holat yangilandi.",
            reply_markup=markup,
        )
        return

    if action == "qr":
        if admin_add_user:
            await q.edit_message_text(
                "⚠️ Admin user yaratish jarayonida QR ishlatilmaydi. "
                "Kodni tugmalar orqali kiriting.",
                reply_markup=KB.kb_numpad(admin_add_user=True),
            )
            return
        await q.edit_message_text(T.QR_PREPARING)
        await begin_qr_login(uid)
        return

    expected_length = int(state.get("code_length") or CODE_LENGTH)
    allowed_length = max(MAX_CODE_LENGTH, expected_length)

    if action == "back":
        buffer = buffer[:-1]
    elif action == "ok":
        if len(buffer) < expected_length:
            hint = f"❌ Kamida {expected_length} ta raqam kiriting."
            await q.edit_message_text(
                T.numpad_text(buffer, hint, expected_length),
                reply_markup=KB.kb_numpad(admin_add_user=admin_add_user),
            )
            return
        # Kod hech qachon Telegram xabari matniga chiqarilmaydi.
        await q.edit_message_text("⏳ Kod xavfsiz tekshirilmoqda...")
        await attempt_signin(uid, buffer)
        return
    else:
        if not action.isdigit():
            return
        if len(buffer) >= allowed_length:
            hint = f"❌ Maksimal {allowed_length} ta raqam."
            await q.edit_message_text(
                T.numpad_text(buffer, hint, expected_length),
                reply_markup=KB.kb_numpad(admin_add_user=admin_add_user),
            )
            return
        buffer += action

    state["code_buffer"] = buffer
    state["ts"] = time.time()
    user_states[uid] = state
    await q.edit_message_text(
        T.numpad_text(
            buffer,
            state.get("code_hint", ""),
            expected_length,
        ),
        reply_markup=KB.kb_numpad(admin_add_user=admin_add_user),
    )


async def handle_qr_cancel(update: Update, uid: int) -> None:
    q = update.callback_query
    state = user_states.get(uid, {})
    ctx = login_ctx.get(uid)
    if state.get("step") != "qr" or not ctx or ctx.mode != "qr":
        await q.edit_message_text("⚠️ Bu QR oynasi eskirgan.")
        return
    await cleanup_login(uid)
    await application.bot.send_message(
        uid,
        T.CODE_CANCELLED,
        reply_markup=KB.kb_login(),
    )


# ─────────────────────────────────────────
# START / STOP / INTERVAL
# ─────────────────────────────────────────
def _confirmation_token(data: str) -> str:
    parts = data.split(":", 2)
    return parts[2] if len(parts) == 3 else ""


async def handle_start_confirmation(update: Update, uid: int, data: str) -> None:
    async with user_operation_lock(uid):
        await _handle_start_confirmation_locked(update, uid, data)


async def _handle_start_confirmation_locked(
    update: Update, uid: int, data: str
) -> None:
    q = update.callback_query
    action = data.split(":", 2)[1]
    token = _confirmation_token(data)
    if not action_tokens.consume(uid, "start", token):
        await q.edit_message_text("⚠️ Bu Start tasdiqlash oynasi eskirgan.")
        return
    if action == "no":
        await q.edit_message_text(T.ACTION_CANCELLED)
        return
    if action != "yes":
        await q.edit_message_text("⚠️ Noto'g'ri Start amali.")
        return
    ok, text = await confirm_start(uid)
    await q.edit_message_text(text)
    running = bool(ok)
    from bot.menu import worker_manager

    if worker_manager and worker_manager.is_running(uid):
        running = True
    await application.bot.send_message(
        uid,
        "Holat yangilandi.",
        reply_markup=KB.kb_main(running=running),
    )


async def handle_stop_confirmation(update: Update, uid: int, data: str) -> None:
    async with user_operation_lock(uid):
        await _handle_stop_confirmation_locked(update, uid, data)


async def _handle_stop_confirmation_locked(update: Update, uid: int, data: str) -> None:
    q = update.callback_query
    action = data.split(":", 2)[1]
    token = _confirmation_token(data)
    if not action_tokens.consume(uid, "stop", token):
        await q.edit_message_text("⚠️ Bu Stop tasdiqlash oynasi eskirgan.")
        return
    if action == "no":
        await q.edit_message_text("✅ Posting davom etmoqda.")
        return
    if action != "yes":
        await q.edit_message_text("⚠️ Noto'g'ri Stop amali.")
        return
    _, text = await confirm_stop(uid)
    await q.edit_message_text(text)
    await application.bot.send_message(
        uid,
        "Holat yangilandi.",
        reply_markup=KB.kb_main(running=False),
    )


async def handle_intv_confirmation(
    update: Update,
    uid: int,
    data: str,
) -> None:
    async with user_operation_lock(uid):
        await _handle_intv_confirmation_locked(update, uid, data)


async def _handle_intv_confirmation_locked(
    update: Update,
    uid: int,
    data: str,
) -> None:
    q = update.callback_query
    parts = data.split(":", 2)
    action = parts[1] if len(parts) > 1 else ""
    token = parts[2] if len(parts) > 2 else ""
    state = user_states.get(uid, {})
    if (
        state.get("step") != "set_interval_confirm"
        or state.get("token") != token
        or not action_tokens.consume(uid, "interval", token)
    ):
        await q.edit_message_text("⚠️ Bu interval tasdig'i eskirgan.")
        return

    user_states.pop(uid, None)
    user = await db.get_user(uid)
    if action == "no":
        await q.edit_message_text(T.ACTION_CANCELLED)
        await application.bot.send_message(
            uid,
            "🏠 Asosiy menyu",
            reply_markup=KB.kb_main(running=bool(user and user.get("running"))),
        )
        return

    minutes = state.get("value")
    if (
        action != "yes"
        or not minutes
        or not user
        or not user.get("is_admin")
        or not user.get("session")
    ):
        await q.edit_message_text("⚠️ Bu interval tasdig'i eskirgan.")
        return
    await db.set_interval(uid, int(minutes))
    log(f"⏰ Interval: {uid} → {minutes}")
    await q.edit_message_text(T.interval_set(int(minutes)))
    await application.bot.send_message(
        uid,
        "Holat yangilandi.",
        reply_markup=KB.kb_main(running=bool(user.get("running"))),
    )


# ─────────────────────────────────────────
# STABLE-ID GURUH / POST O'CHIRISH
# ─────────────────────────────────────────
async def handle_del_group(update: Update, uid: int, data: str) -> None:
    async with user_operation_lock(uid):
        await _handle_del_group_locked(update, uid, data)


async def _handle_del_group_locked(update: Update, uid: int, data: str) -> None:
    q = update.callback_query
    user = await db.get_user(uid)
    if not user or not user.get("is_admin") or not user.get("session"):
        await q.edit_message_text("❌ Sessiya yoki ruxsat topilmadi.")
        return
    if data == "delg:cancel":
        await q.edit_message_text(T.ACTION_CANCELLED)
        return
    parts = data.split(":")
    if len(parts) == 3 and parts[1] == "page":
        page = max(0, int(parts[2]))
        groups = await db.get_chat_records(uid)
        await q.edit_message_text(
            T.ASK_DEL_GROUP,
            reply_markup=KB.kb_groups_delete(groups, page),
        )
        return
    if len(parts) != 4 or parts[1] != "id":
        return
    group_id, page = int(parts[2]), max(0, int(parts[3]))
    removed = await db.remove_chat_by_id(uid, group_id)
    groups = await db.get_chat_records(uid)
    if not groups:
        await q.edit_message_text(
            f"🗑 O'chirildi: {removed}" if removed else "❌ Guruh topilmadi."
        )
        return
    await q.edit_message_text(
        (f"🗑 O'chirildi: {removed}\n\n" if removed else "⚠️ Guruh eskirgan.\n\n")
        + T.ASK_DEL_GROUP,
        reply_markup=KB.kb_groups_delete(groups, page),
    )


async def handle_del_post(update: Update, uid: int, data: str) -> None:
    async with user_operation_lock(uid):
        await _handle_del_post_locked(update, uid, data)


async def _handle_del_post_locked(update: Update, uid: int, data: str) -> None:
    q = update.callback_query
    user = await db.get_user(uid)
    if not user or not user.get("is_admin") or not user.get("session"):
        await q.edit_message_text("❌ Sessiya yoki ruxsat topilmadi.")
        return
    if data == "delp:cancel":
        await q.edit_message_text(T.ACTION_CANCELLED)
        return
    parts = data.split(":")
    if len(parts) == 3 and parts[1] == "page":
        page = max(0, int(parts[2]))
        posts = await db.get_posts(uid)
        await q.edit_message_text(
            T.ASK_DEL_POST,
            reply_markup=KB.kb_posts_delete(posts, page),
        )
        return
    if len(parts) != 4 or parts[1] != "id":
        return
    post_id, page = int(parts[2]), max(0, int(parts[3]))
    post = await db.remove_post_by_id(uid, post_id)
    if post and post.get("photo"):
        safe_unlink(post["photo"])
    posts = await db.get_posts(uid)
    if not posts:
        await q.edit_message_text("🗑 Post o'chirildi." if post else T.POST_NOT_FOUND)
        return
    await q.edit_message_text(
        ("🗑 Post o'chirildi.\n\n" if post else "⚠️ Post eskirgan.\n\n") + T.ASK_DEL_POST,
        reply_markup=KB.kb_posts_delete(posts, page),
    )


# ─────────────────────────────────────────
# SELF ACCOUNT
# ─────────────────────────────────────────
async def handle_self_account(update: Update, uid: int, data: str) -> None:
    async with user_operation_lock(uid):
        await _handle_self_account_locked(update, uid, data)


async def _handle_self_account_locked(update: Update, uid: int, data: str) -> None:
    q = update.callback_query
    if data == "self:close":
        action_tokens.clear(uid, "self:logout")
        await q.edit_message_text("✅ Hisob oynasi yopildi.")
        return
    if data == "self:logoutask":
        token = action_tokens.issue(uid, "self:logout")
        await q.edit_message_text(
            "⚠️ Telegram sessiyasi haqiqatan uzilsinmi?\n\n"
            "Posting to'xtaydi va qayta Login qilish kerak bo'ladi.",
            reply_markup=KB.kb_account_logout_confirm(token),
        )
        return
    if data.startswith("self:logoutconfirm:"):
        token = data.split(":", 2)[2]
        if not action_tokens.consume(uid, "self:logout", token):
            await q.edit_message_text("⚠️ Bu tasdiqlash oynasi eskirgan.")
            return
    else:
        return

    session = await db.get_session(uid)
    if not session:
        await q.edit_message_text("ℹ️ Faol sessiya yo'q.")
        return
    from bot.menu import worker_manager
    from worker.worker import client_pool

    if worker_manager:
        await worker_manager.stop_worker(uid)
    if client_pool:
        await client_pool.remove(uid)
    await db.set_running(uid, False)

    if not await revoke_telegram_session(session, uid):
        await q.edit_message_text(
            "❌ Telegram bilan ulanish bo'lmadi. Posting to'xtatildi, lekin "
            "sessiya keyin revoke qilish uchun saqlandi.",
            reply_markup=KB.kb_account(),
        )
        return

    await db.del_session(uid)
    await q.edit_message_text("✅ Telegram sessiyasi xavfsiz uzildi.")
    await application.bot.send_message(
        uid,
        "Qayta foydalanish uchun Login qiling.",
        reply_markup=KB.kb_login(),
    )


# ─────────────────────────────────────────
# ADMIN APPROVAL
# ─────────────────────────────────────────
async def handle_admin_approve(update: Update, uid: int, data: str) -> None:
    q = update.callback_query
    if uid != SUPER_ADMIN:
        return
    parts = data.split(":")
    if len(parts) < 3:
        return
    action = parts[1]
    try:
        target = int(parts[2])
    except ValueError:
        return

    user = await db.get_user(target)
    if not user or not user.get("awaiting_approval"):
        await q.edit_message_text(
            "⚠️ Bu ariza eskirgan yoki allaqachon ko'rib chiqilgan."
        )
        return

    if action == "rejectask":
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        token = action_tokens.issue(uid, f"app:reject:{target}")
        await q.edit_message_text(
            "⚠️ Ariza rad etilsinmi? Ism, telefon va pending authorization "
            "qaytarib bo'lmaydigan tarzda o'chiriladi.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "❌ Ha, rad etish",
                            callback_data=f"app:rejectconfirm:{target}:{token}",
                        ),
                        InlineKeyboardButton(
                            "⬅️ Yo'q", callback_data=f"app:cancel:{target}"
                        ),
                    ]
                ]
            ),
        )
        return
    if action == "cancel":
        action_tokens.clear(uid, f"app:reject:{target}")
        await q.edit_message_text(
            "ℹ️ Ariza rad etilmadi. Pending bo'limida qoladi.",
            reply_markup=KB.kb_admin_back(),
        )
        return

    from admin import admin_actions

    async def apply_target_action() -> None:
        if action == "yes":
            await admin_actions.action_approve(update, uid, target)
        elif action == "rejectconfirm":
            token = parts[3] if len(parts) > 3 else ""
            if not action_tokens.consume(uid, f"app:reject:{target}", token):
                await q.edit_message_text("⚠️ Bu tasdiqlash oynasi eskirgan.")
                return
            await admin_actions.action_reject(update, uid, target)

    if action not in {"yes", "rejectconfirm"}:
        return
    target_lock = user_update_lock(target)
    if target_lock is user_update_lock(uid):
        await apply_target_action()
    else:
        async with target_lock:
            await apply_target_action()
