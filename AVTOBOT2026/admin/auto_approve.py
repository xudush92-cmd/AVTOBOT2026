"""Tez (avtomatik) tasdiqlash — admin navbatida kutishni kamaytirish.

Siyosat:
- o'chirilgan standart holat (``AUTO_APPROVE_ENABLED=0``) — hamma ariza admin
  qo'lidan o'tadi (eski xatti-harakat);
- yoqilganda FAQAT past riskli arizalar tasdiqlanadi va hamma holda
  pending sessiya Telegramda qayta tekshiriladi (UID bindingi);
- har bir avto-tasdiq super adminga xabar qilinadi — u istalgan payt
  bloklay yoki o'chira oladi;
- shubha bo'lsa (FloodWait/tarmoq xatosi, risk yuqori) ariza admin navbatida
  qoladi, HECH QACHON o'chirilmaydi.
"""

from __future__ import annotations

import contextlib

from bot import keyboards as KB
from bot import texts as T
from config.config import (
    AUTO_APPROVE_BATCH,
    DEFAULT_DURATION_DAYS,
    SUPER_ADMIN,
)
from core import database as db
from core.logger import log
from core.risk import auto_approve_threshold, compute_risk_score, risk_label
from core.session_manager import (
    MISMATCH,
    TEMPORARY,
    VALID,
    revoke_telegram_session,
    validate_telegram_session_owner,
)
from core.update_locks import user_operation_lock
from core.utils import calc_expires

application = None


def set_application(app) -> None:
    global application
    application = app


async def _risk_for(user: dict) -> tuple[int, list[str]]:
    referrer_uid = user.get("referrer_uid")
    referrer_blocked = False
    referrer_today = 0
    if referrer_uid:
        referrer = await db.get_user(int(referrer_uid))
        referrer_blocked = bool(referrer and referrer.get("is_blocked"))
        referrer_today = await db.count_referrals_today(int(referrer_uid))
    return compute_risk_score(
        user,
        phone_cluster=await db.count_phone_prefix_users(user.get("phone") or ""),
        referrer_blocked=referrer_blocked,
        referrer_today=referrer_today,
        duplicate_name_users=await db.count_users_named(user.get("name") or ""),
    )


async def auto_approve_once(limit: int | None = None) -> int:
    """Navbatdagi past riskli arizalardan bir qismini tasdiqlaydi.

    Returns:
        Tasdiqlangan arizalar soni (funksiya o'chirilgan bo'lsa 0).
    """
    threshold = auto_approve_threshold()
    if threshold < 0:
        return 0

    candidates = await db.get_auto_approvable_candidates(
        limit or AUTO_APPROVE_BATCH
    )
    approved = 0
    for snapshot in candidates:
        uid = int(snapshot["uid"])
        async with user_operation_lock(uid):
            if await _approve_candidate(uid, threshold):
                approved += 1
    if approved:
        log(f"⚡ Avto-tasdiq: {approved} ta ariza")
    return approved


async def _approve_candidate(uid: int, threshold: int) -> bool:
    user = await db.get_user(uid)
    if (
        not user
        or not user.get("awaiting_approval")
        or not user.get("pending_session")
        or user.get("is_blocked")
        or user.get("is_admin")
    ):
        return False

    score, reasons = await _risk_for(user)
    if score > threshold:
        log(
            f"⏸ Avto-tasdiq o'tkazib yuborildi: {uid} (risk {score} > {threshold})",
            "warning",
        )
        return False

    pending = user.get("pending_session") or ""
    verdict = await validate_telegram_session_owner(pending, uid)
    if verdict == TEMPORARY:
        # Telegram javob bermadi — pending holat saqlanadi, keyingi sikl.
        return False

    if verdict == MISMATCH:
        # Sessiya boshqa akkauntga tegishli: revoke qilamiz, ariza tozalanadi.
        if not await revoke_telegram_session(pending, uid):
            return False
        await db.clear_pending_approval(uid)
        log(f"⚠️ Avto-tasdiq bekor qilindi: {uid} — sessiya egasi mos kelmadi", "warning")
        with contextlib.suppress(Exception):
            if application:
                await application.bot.send_message(
                    uid, T.PENDING_SESSION_MISMATCH, reply_markup=KB.kb_login()
                )
        return False

    if verdict != VALID:
        # Sessiya yaroqsiz — pending tozalanadi, ariza admin navbatida qoladi.
        await db.del_pending(uid)
        log(f"ℹ️ Avto-tasdiq: {uid} pending sessiyasi yaroqsiz, admin kutadi", "warning")
        return False

    if not await db.approve_pending_user(uid, calc_expires(DEFAULT_DURATION_DAYS)):
        return False

    from admin.admin_actions import notify_after_approval

    await notify_after_approval(uid, session_activated=True)
    await _notify_admin(uid, score, reasons)
    return True


async def _notify_admin(uid: int, score: int, reasons: list[str]) -> None:
    """Har bir avto-tasdiq adminga ko'rsatib turiladi (nazorat uchun)."""
    if not application:
        return
    user = await db.get_user(uid) or {}
    lines = [
        "⚡ AVTO-TASDIQ (admin tasdig'isiz)",
        "",
        f"🆔 {uid}",
        f"👤 {user.get('name') or '—'}",
        f"📱 {user.get('phone') or '—'}",
        f"🎯 Risk: {score} ball — {risk_label(score)}",
    ]
    if reasons:
        lines.append("📋 Izoh: " + "; ".join(reasons))
    lines.append("")
    lines.append(
        "Xato deb hisoblasangiz: 👥 Foydalanuvchilar → 🚫 Bloklash "
        "yoki 🗑 O'chirish."
    )
    with contextlib.suppress(Exception):
        await application.bot.send_message(SUPER_ADMIN, "\n".join(lines))
