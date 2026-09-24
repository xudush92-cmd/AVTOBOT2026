"""
⏰ Vaqt (interval) ni sozlash.

Funksiyalar:
- Boshlash (⏰ Vaqt tugmasi bosilganda)
- Qiymatni qabul qilish
- Tekshirish va saqlash
"""

from __future__ import annotations

import time

from telegram import Update

from bot import action_tokens
from bot import keyboards as KB
from bot import texts as T
from core import database as db
from core.logger import log
from core.utils import is_valid_interval


# ─────────────────────────────────────────────────────────────────────────
# BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_set_interval(update: Update) -> None:
    """⏰ Vaqt tugmasi bosilganda."""
    uid = update.effective_user.id
    from bot.login import user_states

    current = await db.get_interval(uid)
    user_states[uid] = {"step": "set_interval", "ts": time.time()}

    await update.message.reply_text(
        T.ask_interval(current),
        reply_markup=KB.kb_input_cancel(),
    )


# ─────────────────────────────────────────────────────────────────────────
# QIYMATNI QABUL QILISH
# ─────────────────────────────────────────────────────────────────────────
async def handle_set_interval(update: Update, text: str) -> None:
    """Foydalanuvchi yangi interval qiymatini kiritdi."""
    uid = update.effective_user.id
    value_text = text.strip()

    # Son emasmi?
    try:
        minutes = int(value_text)
    except ValueError:
        await update.message.reply_text(T.INTERVAL_INVALID_NUMBER)
        return

    # Minimal tekshirish
    if not is_valid_interval(minutes):
        await update.message.reply_text(T.interval_invalid_min())
        return

    # Bir kundan oshsa qo'shimcha tasdiq so'raymiz.
    if minutes > 1440:
        # 1 kundan oshsa — tasdiq so'raymiz
        from bot.login import user_states as us

        token = action_tokens.issue(uid, "interval")
        us[uid] = {
            "step": "set_interval_confirm",
            "ts": time.time(),
            "value": minutes,
            "token": token,
        }
        await update.message.reply_text(
            f"⚠️ Siz {minutes} daqiqa (~{minutes // 60} soat) kiritdingiz.\n\n"
            "Bu juda katta qiymat. Davom etamizmi?",
            reply_markup=KB.kb_yes_no(
                f"intv:yes:{token}",
                f"intv:no:{token}",
            ),
        )
        return

    # Saqlash
    await save_interval(uid, minutes, update)


async def save_interval(uid: int, minutes: int, update: Update) -> None:
    """Intervalni bazaga saqlash va xabar yuborish."""
    from bot.login import user_states

    user_states.pop(uid, None)
    await db.set_interval(uid, minutes)
    log(f"⏰ Interval: {uid} → {minutes} daqiqa")

    user = await db.get_user(uid)
    running = bool(user and user.get("running")) if user else False

    await update.message.reply_text(
        T.interval_set(minutes),
        reply_markup=KB.kb_main(running=running),
    )
