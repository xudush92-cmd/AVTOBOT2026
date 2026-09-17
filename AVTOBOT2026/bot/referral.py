"""
Referal tizimi.

Funksiyalar:
- Referal havola ko'rsatish
- Yangi referal haqida xabar
- Referal ro'yxati
"""

from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as KB
from bot import texts as T
from config.config import BOT_USERNAME
from core import database as db
from core.logger import log


# ─────────────────────────────────────────────────────────────────────────
# REFERAL SAHIFASI
# ─────────────────────────────────────────────────────────────────────────
async def show_referral(update: Update) -> None:
    """👥 Referal tugmasi bosilganda."""
    uid = update.effective_user.id

    # Havolani yasash
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"

    # Ma'lumotlarni olish
    total = await db.count_referrals(uid)
    refs = await db.get_referrals(uid)

    # Matnni tayyorlash
    text = T.referral_text(link, total, refs)

    user = await db.get_user(uid)
    running = bool(user and user.get("running")) if user else False

    await update.message.reply_text(
        text,
        reply_markup=KB.kb_main(running=running),
    )


# ─────────────────────────────────────────────────────────────────────────
# REFERALNI QAYD ETISH (cmd_start ichida chaqiriladi)
# ─────────────────────────────────────────────────────────────────────────
async def register_referral(uid: int, ref_arg: str) -> bool:
    """
    /start ref_XXXX orqali kelgan foydalanuvchini referal sifatida qayd etadi.

    Faqat yangi foydalanuvchilar uchun ishlaydi.

    Returns:
        True  — referal qayd etildi
        False — qayd etilmadi
    """
    if not ref_arg.startswith("ref_"):
        return False

    ref_part = ref_arg[4:]
    if not ref_part.isdigit():
        return False

    referrer_uid = int(ref_part)

    # O'zini o'zi taklif qilmasin
    if referrer_uid == uid:
        return False

    # Foydalanuvchi allaqachon mavjudmi?
    existing = await db.get_user(uid)
    if existing:
        return False

    # Referrerni saqlash
    await db.set_referrer(uid, referrer_uid)
    log(f"👥 Referal qayd etildi: {uid} ← {referrer_uid}")
    return True


# ─────────────────────────────────────────────────────────────────────────
# REFERAL TASDIQLANGANDA (admin tasdiqlaganda chaqiriladi)
# ─────────────────────────────────────────────────────────────────────────
async def on_referral_counted(uid: int) -> None:
    """
    Foydalanuvchi tasdiqlanganda referalni hisoblash va
    taklif qilganga xabar yuborish.
    """
    from bot.login import application

    referrer = await db.try_count_referral(uid)
    if not referrer:
        return

    total = await db.count_referrals(referrer)
    info = await db.get_user_info(uid)
    name = info.get("name") or "Yangi foydalanuvchi"

    with __import__("contextlib").suppress(Exception):
        await application.bot.send_message(
            referrer,
            T.REFERRAL_NEW.format(name=name, total=total),
        )
        log(f"🎉 Referal hisoblandi: {referrer} ← {uid}")
