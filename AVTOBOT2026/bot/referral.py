"""Referal (taklif) tizimi va anti-fraud qoidalari.

Imkoniyatlar:
- taklif havolasi va uni ulashish matni;
- faol referallar ro'yxati (hisoblangan / mukofot olgan / kutayotgan);
- mukofot: faqat HAQIQI foydalanuvchi uchun — kamida 1 ta guruh, 1 ta post va
  belgilangan sondagi muvaffaqiyatli yuborishdan keyin bonus kun beriladi;
- clawback: firibgar aniqlansa hisob va bonus kun qaytarib olinadi;
- anomaliya signali: bir kunda juda ko'p referal → super adminga xabar.
"""

from __future__ import annotations

import contextlib

from telegram import Update

from bot import keyboards as KB
from bot import texts as T
from config.config import (
    ADMIN_CONTACT_PHONE,
    BOT_USERNAME,
    REFERRAL_BONUS_DAYS,
    REFERRAL_BONUS_MONTHLY_CAP_DAYS,
    REFERRAL_DAILY_ALERT,
    REFERRAL_QUALIFY_MIN_SENDS,
    SUPER_ADMIN,
)
from core import database as db
from core.errlog import log_gap
from core.logger import log


# ─────────────────────────────────────────────────────────────────────────
# REFERAL SAHIFASI
# ─────────────────────────────────────────────────────────────────────────
async def show_referral(update: Update) -> None:
    """👥 Referal tugmasi bosilganda — havola, hisob va qoidalar."""
    uid = update.effective_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"

    user = await db.get_user(uid) or {}

    # Jamoa admini — faqat umumiy jamoa havolasi ko'rsatiladi.
    # Shaxsiy referal tugmalari va statistikasi kerak emas: jamoa
    # a'zolari jamoa havolasi orqali keladi.
    if user.get("is_team_admin") and user.get("team_id"):
        from bot.teams import team_link as make_team_link

        team_url = make_team_link(int(user["team_id"]))
        await update.message.reply_text(
            T.team_link_text(team_url),
            parse_mode="HTML",
            reply_markup=KB.kb_team_link_only(team_url),
        )
        return

    total = await db.count_referrals(uid)
    refs = await db.get_referrals(uid)
    granted = int(user.get("referral_bonus_days") or 0)
    today = await db.count_referrals_today(uid)

    text = T.referral_text(
        link=link,
        total=total,
        refs=refs,
        bonus_days=REFERRAL_BONUS_DAYS,
        min_sends=REFERRAL_QUALIFY_MIN_SENDS,
        granted_days=granted,
        today=today,
    )

    await update.message.reply_text(
        text,
        reply_markup=KB.kb_referral(link),
    )


async def share_referral_message(uid: int) -> str:
    """Do'stlarga yuborish uchun tayyor matn (bilan birga havola).

    Jamoa admini uchun — jamoa havolasi (shaxsiy havola emas).
    """
    user = await db.get_user(uid) or {}
    if user.get("is_team_admin") and user.get("team_id"):
        from bot.teams import team_link as make_team_link

        return T.referral_share_text(make_team_link(int(user["team_id"])))
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}"
    return T.referral_share_text(link)


# ─────────────────────────────────────────────────────────────────────────
# REFERALNI QAYD ETISH (cmd_start ichida chaqiriladi)
# ─────────────────────────────────────────────────────────────────────────
async def register_referral(uid: int, ref_arg: str) -> bool:
    """``/start ref_XXXX`` orqali kelgan foydalanuvchini qayd etadi.

    Faqat yangi yoki hali biriktirilmagan foydalanuvchiga, faqat tasdiqlangan
    va bloklanmagan referrer uchun ishlaydi.
    """
    if not isinstance(ref_arg, str) or not ref_arg.startswith("ref_"):
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
        log_gap(uid, "Foydalanuvchi allaqachon ro'yxatda — referal qayd etilmadi")
        return False

    saved = await db.set_referrer(uid, referrer_uid)
    if not saved:
        log_gap(uid, "Referal qayd etilmadi (referrer tasdiqlanmagan yoki bloklangan)")
        return False

    # Referrer jamoa admini bo'lsa — kelgan foydalanuvchi uning jamoasiga
    # avtomatik biriktiriladi (jamoa to'ldiq bo'lmasa).
    await _auto_join_referrer_team(uid, referrer_uid)

    log(f"👥 Referal qayd etildi: {uid} ← {referrer_uid}")
    await _flag_anomaly(referrer_uid)
    return True


async def _auto_join_referrer_team(uid: int, referrer_uid: int) -> bool:
    """Referrer jamoa admini bo'lsa — kelgan user jamoaga biriktiriladi."""
    referrer = await db.get_user(referrer_uid)
    if not referrer or not referrer.get("is_team_admin"):
        return False

    team_id = referrer.get("team_id")
    if not team_id:
        return False

    team = await db.get_team(int(team_id))
    if not team:
        return False

    # Jamoa to'ldiq bo'lsa — biriktirilmaydi.
    if not await db.team_has_free_slot(int(team_id)):
        return False

    return await db.set_team_pending(uid, int(team_id), referrer_uid)


async def _flag_anomaly(referrer_uid: int) -> None:
    """Bir kunda ko'p referal — adminga ogohlantirish (mukofot suiste'moli)."""
    with contextlib.suppress(Exception):
        count = await db.count_referrals_today(referrer_uid)
        if count < REFERRAL_DAILY_ALERT:
            return
        if count != REFERRAL_DAILY_ALERT:
            # Har bir keyingi qo'shilishda spam qilmaslik uchun bir marta.
            return
        from bot.login import application

        if not application:
            return
        await application.bot.send_message(
            SUPER_ADMIN,
            f"⚠️ Referal anomaliyasi\n\n🆔 {referrer_uid}\n"
            f"👥 Bugun qo'shilgan referallar: {count} ta\n\n"
            f"Mukofot kunlarini tekshiring: {ADMIN_CONTACT_PHONE}",
        )
        log(f"⚠️ Referal anomaliyasi: {referrer_uid} ({count} ta/kun)", "warning")


# ─────────────────────────────────────────────────────────────────────────
# REFERAL TASDIQLANGANDA (admin tasdiqlaganda chaqiriladi)
# ─────────────────────────────────────────────────────────────────────────
async def on_referral_counted(uid: int) -> None:
    """Foydalanuvchi tasdiqlanganda referalni hisoblash va xabar yuborish.

    Mukofot bu bosqichda BERILMAYDI — faqat haqiqiy faollikdan keyin
    (``maybe_grant_referral_bonus``).
    """
    from bot.login import application

    referrer = await db.try_count_referral(uid)
    if not referrer:
        return

    total = await db.count_referrals(referrer)
    info = await db.get_user_info(uid)
    name = info.get("name") or "Yangi foydalanuvchi"

    with contextlib.suppress(Exception):
        if application:
            await application.bot.send_message(
                referrer,
                T.referral_counted_text(
                    name=name,
                    total=total,
                    bonus_days=REFERRAL_BONUS_DAYS,
                    min_sends=REFERRAL_QUALIFY_MIN_SENDS,
                ),
            )
        log(f"🎉 Referal hisoblandi: {referrer} ← {uid}")


# ─────────────────────────────────────────────────────────────────────────
# MUKOFOT: FAQAT HAQIQI FAOLIYAT UCHUN
# ─────────────────────────────────────────────────────────────────────────
async def maybe_grant_referral_bonus(uid: int, min_sends: int | None = None) -> bool:
    """Referal bonusini beradi — hozircha bonus kunlari umuman berilmaydi.

    Reja: referal endi faqat statistika (kim kimni taklif qilgani) uchun.
    Bonus kunlari olib tashlangan, shuning uchun bu funksiya hech qachon
    ``True`` qaytarmaydi va muddatga qo'shish amalini bajaradi.
    """
    return False


async def _notify_bonus(referrer: int, referred: int, applied: int) -> None:
    """Eski bonus xabari — endi bonus kunlari berilmaydi, funksiya chaqirilmaydi."""
    return None


async def revoke_referral_bonus(uid: int, reason: str = "") -> dict | None:
    """Firibgar/soxta akkaunt aniqlanganda hisob va bonus kunni qaytaradi.

    Returns:
        ``{"referrer_uid": int, "bonus_days": int}`` yoki bekor qilinadigan
        narsa bo'lmasa ``None``.
    """
    info = await db.revoke_referral(uid)
    if not info:
        return None

    referrer = int(info["referrer_uid"])
    if info["was_granted"] and info["bonus_days"] > 0:
        await db.remove_bonus_days(referrer, int(info["bonus_days"]))

    from bot.login import application

    with contextlib.suppress(Exception):
        if application:
            await application.bot.send_message(
                referrer,
                T.referral_revoked_note(
                    name=str(uid),
                    days=int(info["bonus_days"] or 0),
                    reason=reason,
                ),
            )
    log(
        f"↩️ Referal bekor qilindi: {referrer} ← {uid} "
        f"(-{info['bonus_days']} kun, sabab: {reason or '—'})",
        "warning",
    )
    return {"referrer_uid": referrer, "bonus_days": int(info["bonus_days"] or 0)}


async def reconcile_after_unblock(uid: int) -> int | None:
    """Referrer blokdan chiqqanda hisoblanmay qolgan referalni qayta oladi."""
    referrer = await db.reconcile_referral(uid)
    if referrer:
        log(f"👥 Referal qayta hisoblandi: {referrer} ← {uid}")
    return referrer
