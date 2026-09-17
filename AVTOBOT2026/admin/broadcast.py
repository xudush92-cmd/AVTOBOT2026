"""
Ommaviy xabar yuborish (broadcast).

Funksiyalar:
- Boshlash (matn kutilmoqda)
- Yuborish (barchaga)
- Hisobot
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as KB
from bot import texts as T
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
# BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_broadcast(update: Update) -> None:
    """📢 Xabar yuborish tugmasi bosilganda."""
    q = update.callback_query
    uid = q.from_user.id

    if uid != SUPER_ADMIN:
        return

    from bot.login import user_states
    user_states[uid] = {
        "step": "admin_broadcast",
        "ts": time.time(),
    }

    await q.edit_message_text(
        "📢 XABAR YUBORISH\n\n"
        "Yubormoqchi bo'lgan xabaringizni kiriting.\n\n"
        "Qo'llab-quvvatlanadi:\n"
        "• Matn\n"
        "• Rasm + caption\n\n"
        "⚠️ Xabar BARCHA foydalanuvchilarga yuboriladi.\n"
        "Bloklagan foydalanuvchilarni hisobga olmaganda.",
        reply_markup=KB.kb_broadcast_confirm(),
    )


# ─────────────────────────────────────────────────────────────────────────
# YUBORISH — HANDLER
# ─────────────────────────────────────────────────────────────────────────
async def handle_broadcast_message(update: Update) -> None:
    """Admin xabar yubordi — tasdiq so‘raymiz."""
    from bot.login import user_states

    uid = update.effective_user.id
    if uid != SUPER_ADMIN:
        return

    msg = update.message
    text = msg.text or msg.caption or ""
    photo = None

    # Rasm bo‘lsa — file_id olamiz
    if msg.photo:
        photo = msg.photo[-1].file_id

    if not text.strip() and not photo:
        await msg.reply_text("❌ Bo'sh xabar. Qaytadan kiriting.")
        return

    # Vaqtinchalik saqlash
    state = user_states.get(uid, {})
    state["broadcast_text"] = text
    state["broadcast_photo"] = photo
    user_states[uid] = state

    # Tasdiq so‘rash
    preview = text[:200] if text else "(rasm)"
    await msg.reply_text(
        f"📢 XABAR TAYYOR\n\n"
        f"Matn:\n{preview}\n\n"
        f"Barcha foydalanuvchilarga yuborilsinmi?",
        reply_markup=KB.kb_broadcast_confirm(),
    )


# ─────────────────────────────────────────────────────────────────────────
# CALLBACK — YUBORISH / BEKOR
# ─────────────────────────────────────────────────────────────────────────
async def handle_broadcast_callback(update: Update, uid: int, data: str) -> None:
    """bc:send / bc:cancel callback."""
    q = update.callback_query

    if uid != SUPER_ADMIN:
        return

    # Bekor qilish
    if data == "bc:cancel":
        from bot.login import user_states
        user_states.pop(uid, None)
        await q.edit_message_text("❌ Broadcast bekor qilindi.")
        return

    # Yuborish
    if data == "bc:send":
        from bot.login import user_states
        state = user_states.get(uid, {})
        text = state.get("broadcast_text", "")
        photo = state.get("broadcast_photo")

        if not text and not photo:
            await q.edit_message_text("❌ Xabar topilmadi.")
            user_states.pop(uid, None)
            return

        user_states.pop(uid, None)
        await q.edit_message_text("⏳ Xabar yuborilmoqda...")
        await run_broadcast(uid, text, photo)


# ─────────────────────────────────────────────────────────────────────────
# YUBORISH — ASOSIY
# ─────────────────────────────────────────────────────────────────────────
async def run_broadcast(admin_uid: int, text: str, photo: str | None) -> None:
    """
    Barcha foydalanuvchilarga xabar yuboradi.

    Xatolar yig‘iladi, oxirida hisobot yuboriladi.
    """
    users = await db.get_all_users()
    if not users:
        await application.bot.send_message(admin_uid, "❌ Foydalanuvchilar yo'q.")
        return

    total = len(users)
    sent = 0
    failed = 0
    blocked = 0

    log(f"📢 Broadcast boshlandi: {total} ta foydalanuvchi")

    start_msg = await application.bot.send_message(
        admin_uid,
        f"📢 Yuborilmoqda...\n\n"
        f"Jami: {total} ta\n"
        f"✅ Yuborildi: 0\n"
        f"❌ Xato: 0",
    )

    # Har 20 ta foydalanuvchida progress yangilash
    for i, u in enumerate(users, 1):
        target = u.get("uid")
        if not target:
            continue

        # Super adminni o‘tkazib yuboramiz
        if target == admin_uid:
            continue

        try:
            if photo:
                await application.bot.send_photo(
                    chat_id=target,
                    photo=photo,
                    caption=text or None,
                )
            else:
                await application.bot.send_message(
                    chat_id=target,
                    text=text,
                )
            sent += 1
        except Exception as e:
            err = type(e).__name__
            if "blocked" in err.lower() or "Forbidden" in err or "deactivated" in err.lower():
                blocked += 1
            else:
                failed += 1
            log(f"broadcast xato {target}: {err}", "warning")

        # Har 20 tadan keyin yangilash
        if i % 20 == 0:
            with contextlib.suppress(Exception):
                await start_msg.edit_text(
                    f"📢 Yuborilmoqda...\n\n"
                    f"Jami: {total} ta\n"
                    f"✅ Yuborildi: {sent}\n"
                    f"🚫 Bloklagan: {blocked}\n"
                    f"❌ Xato: {failed}"
                )
            # Flood oldini olish
            await asyncio.sleep(1)

    # Yakuniy hisobot
    report = (
        f"✅ BROADCAST TUGADI\n\n"
        f"📊 Hisobot:\n"
        f"• Jami: {total} ta\n"
        f"• ✅ Yuborildi: {sent} ta\n"
        f"• 🚫 Bloklagan: {blocked} ta\n"
        f"• ❌ Xato: {failed} ta"
    )

    with contextlib.suppress(Exception):
        await start_msg.edit_text(report)

    log(f"📢 Broadcast tugadi: {sent}/{total} (🚫{blocked} ❌{failed})")
