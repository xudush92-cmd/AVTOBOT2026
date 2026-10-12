"""To'lov — A reja: qo'lda tasdiqlash + kvitansiya.

Oqim:
1. Mijoz 💳 Obuna (yoki /pay) → «💳» tugmasi.
2. Bot summa, karta rekvizitlari va izoh kodi ``AVTO-<uid>-<PAKET>`` ni
   ko'rsatadi; so'rov ``pending`` bo'lib bazaga tushadi.
3. Mijoz kvitansiya rasmini shu chatga yuboradi → admin (super admin)ga
   rasm + ma'lumot + ✅/❌ tugmalari bilan keladi.
4. ✅ → ``db.approve_payment`` (idempotent): paket, muddat uzaytiriladi,
   ``paid_total`` oshadi, posting (agar muddat tufayli to'xtagan bo'lsa)
   tiklanadi, mijozga xabar ketadi.
5. Janitor: javobsiz so'rovni ``expired`` qiladi, muddat tugashidan oldin
   bir marta eslatadi, eski kvitansiya fayllarini o'chiradi, navbat
   to'lib qolsa adminni ogohlantiradi.

``PAYMENTS_ENABLED=0`` (standart) bo'lsa bu modulning hech bir yo'li
foydalanuvchiga ko'rinmaydi.
"""

from __future__ import annotations

import contextlib
import hashlib
import math
import os
import time
from datetime import datetime, timezone

from bot import keyboards as KB
from bot import texts as T
from config import config as CFG
from config.config import SUPER_ADMIN
from core import database as db
from core.logger import log
from core.update_locks import user_operation_lock
from core.utils import format_expires, safe_unlink

application = None

# Navbat ogohlantirishi bir soatda bir martadan ko'p bormasin.
_QUEUE_ALERT_EVERY_S = 3600
_last_queue_alert_at: float | None = None  # None = hali ogohlantirilmagan


def set_application(app) -> None:
    global application
    application = app


# ─────────────────────────────────────────────────────────────────────────
# YORDAMCHILAR
# ─────────────────────────────────────────────────────────────────────────
def enabled() -> bool:
    """To'lov yoqilganmi (flag + kamida bitta narx)."""
    return bool(CFG.PAYMENTS_ENABLED and CFG.PLAN_PRICES)


def plan_items() -> list[tuple[str, int]]:
    return list(CFG.PLAN_PRICES.items())


def plan_panel_markup():
    """📦 Paket ekranining inline tugmalari; to'lov o'chiq bo'lsa ``None``."""
    if not enabled():
        return None
    return KB.kb_plan_pay(plan_items())


def plan_panel_text() -> str:
    return T.plans_price_block() if enabled() else ""


async def _payable_user(uid: int) -> bool:
    user = await db.get_user(uid)
    return bool(
        user
        and user.get("is_admin")
        and not user.get("is_blocked")
        and not user.get("awaiting_approval")
        and user.get("session")
    )


def _reply_target(update):
    """Callback bo'lsa uning xabari, aks holda oddiy xabar."""
    if getattr(update, "callback_query", None) is not None:
        return update.callback_query.message
    return update.message


async def _notify(uid: int, text: str, markup=None) -> None:
    if application is None:
        return
    with contextlib.suppress(Exception):
        await application.bot.send_message(uid, text, reply_markup=markup)


def _age_minutes(created_at: str | None) -> float:
    if not created_at:
        return 0.0
    try:
        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 60)


async def _resume_after_payment(uid: int) -> bool:
    """Muddat tugagani uchun to'xtatilgan postingni qayta ishga tushiradi.

    Chaqiruvchi ``user_operation_lock(uid)`` ni ushlab turishi shart.
    """
    from bot import menu as Menu

    wm = Menu.worker_manager
    user = await db.get_user(uid)
    if (
        wm is None
        or not user
        or not user.get("is_admin")
        or user.get("is_blocked")
        or not user.get("session")
        or await db.is_tariff_expired(uid)
    ):
        return False
    if not await db.get_chats(uid) or not await db.get_posts(uid):
        return False
    if wm.is_running(uid):
        return False
    await db.set_running(uid, True)
    if await wm.start_worker(uid):
        log(f"▶️ To'lovdan keyin posting tiklandi: {uid}")
        return True
    await db.set_running(uid, False)
    return False


# ─────────────────────────────────────────────────────────────────────────
# MIJOZ: PAKET TANLASH VA SO'ROV
# ─────────────────────────────────────────────────────────────────────────
async def start_payment(update, uid: int, plan: str) -> None:
    """💳 bosilganda: yangi so'rov yoki ochiq so'rovni ko'rsatish."""
    target = _reply_target(update)
    if not enabled():
        await target.reply_text(T.PAY_DISABLED)
        return
    plan = (plan or "").strip().upper()
    amount = CFG.PLAN_PRICES.get(plan)
    if not amount:
        await target.reply_text(T.PAY_PLAN_UNKNOWN)
        return
    if not await _payable_user(uid):
        await target.reply_text(T.PAY_NOT_ALLOWED, reply_markup=KB.kb_login())
        return

    open_payment = await db.get_open_payment(uid)
    if open_payment:
        # Bitta vaqtda faqat bitta ochiq so'rov — yangisini ochmaymiz.
        if open_payment.get("proof_path"):
            body = T.pay_status_text(open_payment, await db.get_payment_history(uid))
        else:
            body = T.pay_instruction_text(open_payment)
        await target.reply_text(
            "ℹ️ Sizda hali yakunlanmagan so'rov bor. Uni yakunlang yoki bekor qiling.\n\n" + body,
            reply_markup=KB.kb_pay_request(open_payment["id"]),
        )
        return

    reference = f"{CFG.PAY_REF_PREFIX}-{uid}-{plan}"
    pid = await db.create_payment_request(uid, plan, amount, CFG.PAYMENT_DAYS, reference)
    payment = await db.get_payment(pid)
    log(f"💳 To'lov so'rovi #{pid}: {uid} {plan} {amount}")
    await target.reply_text(
        T.pay_instruction_text(payment),
        reply_markup=KB.kb_pay_request(pid),
    )


async def show_status(update, uid: int) -> None:
    target = _reply_target(update)
    if not enabled():
        await target.reply_text(T.PAY_DISABLED)
        return
    open_payment = await db.get_open_payment(uid)
    history = await db.get_payment_history(uid, limit=5)
    await target.reply_text(
        T.pay_status_text(open_payment, history),
        reply_markup=KB.kb_pay_request(open_payment["id"]) if open_payment else None,
    )


async def cancel_request(update, uid: int, pid: int) -> None:
    target = _reply_target(update)
    proof_path = await db.cancel_payment(uid, pid)
    if proof_path is None:
        await target.reply_text(T.PAY_CANCEL_GONE)
        return
    safe_unlink(proof_path)
    await target.reply_text(T.PAY_CANCELLED)
    if proof_path:
        # Admin navbatida turgan kvitansiya — adminni xabardor qilamiz.
        await _notify(SUPER_ADMIN, f"🚫 Foydalanuvchi so'rovni bekor qildi: #{pid} ({uid})")


async def handle_receipt(update) -> bool:
    """Oddiy chatdagi rasm: ochiq so'rov bo'lsa kvitansiya sifatida qabul qiladi.

    Returns: ``True`` — rasm to'lov kvitansiyasi sifatida ishlandi;
    ``False`` — ochiq so'rov yo'q, chaqiruvchi oddiy yo'lni davom ettirsin.
    """
    if not enabled():
        return False
    uid = update.effective_user.id
    msg = update.message
    open_payment = await db.get_open_payment(uid)
    if not open_payment:
        return False

    if not msg.photo:
        await msg.reply_text(T.PAY_PROOF_NEED_PHOTO)
        return True
    if open_payment.get("proof_path"):
        await msg.reply_text(T.PAY_PROOF_ALREADY)
        return True
    if _age_minutes(open_payment.get("created_at")) > CFG.PAYMENT_REQUEST_TTL_MIN:
        await db.expire_stale_payments(CFG.PAYMENT_REQUEST_TTL_MIN)
        await msg.reply_text(T.PAY_PROOF_EXPIRED.format(ttl=CFG.PAYMENT_REQUEST_TTL_MIN))
        return True

    pid = int(open_payment["id"])
    photo = msg.photo[-1]  # eng yuqori sifat
    tg_file = await photo.get_file()
    folder = os.path.join(str(CFG.MEDIA_DIR), "payments", str(uid))
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{pid}.jpg")
    await tg_file.download_to_drive(custom_path=path)
    with open(path, "rb") as fh:
        proof_hash = hashlib.sha256(fh.read()).hexdigest()

    if not await db.set_payment_proof(pid, uid, path, proof_hash):
        # Poyga: boshqa so'rov shu paytda o'zgargan — faylni tashlaymiz.
        safe_unlink(path)
        await msg.reply_text(T.PAY_PROOF_ALREADY)
        return True

    payment = await db.get_payment(pid) or open_payment
    user = await db.get_user(uid) or {}
    caption = T.admin_payment_caption(
        payment,
        user_name=user.get("name") or "",
        username=user.get("username") or "",
        expires_text=format_expires(user.get("tariff_expires_at")),
        dup_count=await db.count_proof_hash_uses(proof_hash, pid),
        blocked=bool(user.get("is_blocked")),
    )
    await _send_admin_card(payment, caption, photo_ref=photo.file_id)
    log(f"🧾 Kvitansiya qabul qilindi: #{pid} ({uid})")
    await msg.reply_text(T.PAY_PROOF_RECEIVED.format(pid=pid))
    return True


# ─────────────────────────────────────────────────────────────────────────
# ADMIN: KARTA, NAVBAT, TASDIQLASH / RAD ETISH
# ─────────────────────────────────────────────────────────────────────────
async def _send_admin_card(payment: dict, caption: str, photo_ref: str | None = None) -> None:
    """Admin (super admin)ga kvitansiya rasmi + tugmalar bilan xabar.

    ``photo_ref`` — Telegram file_id; bo'lmasa diskdagi kvitansiya ishlatiladi.
    Rasm yuborilmasa matn ko'rinishida yuboriladi (hech bo'lmasa admin xabardor bo'ladi).
    """
    if application is None:
        return
    markup = KB.kb_admin_payment(int(payment["id"]), int(payment["uid"]))
    try:
        if photo_ref:
            await application.bot.send_photo(
                SUPER_ADMIN, photo=photo_ref, caption=caption[:1024], reply_markup=markup
            )
            return
        proof = payment.get("proof_path") or ""
        if proof and os.path.exists(proof):
            with open(proof, "rb") as fh:
                await application.bot.send_photo(
                    SUPER_ADMIN, photo=fh, caption=caption[:1024], reply_markup=markup
                )
            return
        await application.bot.send_message(
            SUPER_ADMIN, caption + "\n\n⚠️ Kvitansiya rasmi topilmadi.", reply_markup=markup
        )
    except Exception as exc:  # noqa: BLE001 - bitta xabar xatosi navbatni to'xtatmasin
        log(f"To'lov kartasi yuborilmadi #{payment.get('id')}: {type(exc).__name__}", "error")


def queue_line_from_stats(stats: dict) -> str:
    """Asosiy admin panel uchun qisqa satr; navbat bo'sh bo'lsa bo'sh qaytadi."""
    count = int(stats.get("count") or 0)
    if not enabled() or count <= 0:
        return ""
    age = int(_age_minutes(stats.get("oldest")))
    return f"💰 Kutilayotgan to'lovlar: {count} ta (eng eskisi {age} daqiqa oldin)"


async def queue_line() -> str:
    """Admin panel satri. Xato bo'lsa panelning o'zi ishlashda davom etadi."""
    if not enabled():
        return ""
    try:
        return queue_line_from_stats(await db.payment_queue_stats())
    except Exception as exc:  # noqa: BLE001 - panel satri asosiy panelni to'xtatmasin
        log(f"To'lov navbati statistikasi o'qilmadi: {type(exc).__name__}", "warning")
        return ""


async def show_admin_queue(update) -> None:
    """💰 To'lovlar navbati — har kvitansiya alohida kartada."""
    q = update.callback_query
    rows = await db.payment_queue(limit=10)
    stats = await db.payment_queue_stats()
    if not rows:
        await q.edit_message_text(T.PAY_QUEUE_EMPTY, reply_markup=KB.kb_admin_back())
        return
    await q.edit_message_text(
        f"💰 TO'LOVLAR NAVBATI: {stats['count']} ta kutmoqda\n\n"
        "Quyida har bir kvitansiya. ✅ tasdiqlasangiz muddat avtomatik uzaytiriladi.",
        reply_markup=KB.kb_admin_back(),
    )
    for row in rows:
        payment = dict(row)
        caption = T.admin_payment_caption(
            payment,
            user_name=row.get("user_name") or "",
            username=row.get("user_username") or "",
            expires_text=format_expires(row.get("user_expires")),
            dup_count=await db.count_proof_hash_uses(row.get("proof_hash") or "", row["id"]),
            blocked=bool(row.get("user_blocked")),
        )
        await _send_admin_card(payment, caption)


async def _edit_card(q, text: str) -> None:
    """Admin kartasini yangilaydi (rasmli xabarda caption, matnda text)."""
    with contextlib.suppress(Exception):
        if q.message is not None and q.message.photo:
            await q.edit_message_caption(caption=text[:1024], reply_markup=None)
        else:
            await q.edit_message_text(text, reply_markup=None)


async def _admin_card_text(q, status_line: str) -> str:
    base = ""
    if q.message is not None:
        base = q.message.caption or q.message.text or ""
    return (base + "\n\n" + status_line).strip()


async def handle_pay_callback(update, uid: int, data: str) -> None:
    """``pay:`` bilan boshlanadigan barcha callbacklar (``q.answer`` chaqiruvchida)."""
    parts = data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]

    # ── Admin amallari ──
    if action in {"ok", "no", "card"}:
        if uid != SUPER_ADMIN:
            return
        await _admin_action(update, action, parts)
        return

    # ── Mijoz amallari ──
    if action == "new" and len(parts) >= 3:
        async with user_operation_lock(uid):
            await start_payment(update, uid, parts[2])
        return
    if action == "status":
        async with user_operation_lock(uid):
            await show_status(update, uid)
        return
    if action == "cancel" and len(parts) >= 3:
        try:
            pid = int(parts[2])
        except ValueError:
            return
        async with user_operation_lock(uid):
            await cancel_request(update, uid, pid)
        return


async def _admin_action(update, action: str, parts: list[str]) -> None:
    q = update.callback_query
    if len(parts) < 3:
        return
    try:
        arg = int(parts[2])
    except ValueError:
        return

    if action == "card":
        from admin import admin_actions as AA

        user = await db.get_user(arg)
        if not user:
            await q.message.reply_text("❌ Foydalanuvchi topilmadi.")
            return
        text = (
            f"👤 {user.get('name') or '—'} ({arg})\n"
            f"📦 Paket: {user.get('plan') or '—'}\n"
            f"📅 Muddat: {format_expires(user.get('tariff_expires_at'))}\n"
            f"💰 Jami to'lov: {T.fmt_som(user.get('paid_total') or 0)}"
        )
        await q.message.reply_text(text, reply_markup=await AA.user_card_markup(arg))
        return

    payment = await db.get_payment(arg)
    if not payment:
        await _edit_card(q, "❌ So'rov topilmadi.")
        return
    pid = int(payment["id"])
    target = int(payment["uid"])

    if action == "ok":
        async with user_operation_lock(target):
            result = await db.approve_payment(pid, SUPER_ADMIN)
            if not result["ok"]:
                status = result.get("status") or "?"
                await _edit_card(
                    q, await _admin_card_text(q, f"ℹ️ So'rov #{pid} allaqachon: {_status_word(status)}")
                )
                return
            resumed = False
            if result.get("was_paused"):
                resumed = await _resume_after_payment(target)
        expires_text = format_expires(result["expires"])
        label = T.plan_label(payment["plan"])
        user_text = T.PAY_APPROVED_USER.format(label=label, expires=expires_text)
        if resumed:
            user_text += "\n\n" + T.PAY_RESUMED_USER
        await _notify(target, user_text, KB.kb_main())
        await _edit_card(
            q,
            await _admin_card_text(q, f"✅ TASDIQLANDI #{pid} · yangi muddat: {expires_text}"),
        )
        log(f"✅ To'lov tasdiqlandi #{pid}: {target} ({payment['plan']})")
        return

    if action == "no":
        async with user_operation_lock(target):
            ok = await db.reject_payment(pid, SUPER_ADMIN)
        if not ok:
            current = await db.get_payment(pid) or {}
            await _edit_card(
                q,
                await _admin_card_text(
                    q, f"ℹ️ So'rov #{pid} allaqachon: {_status_word(current.get('status', '?'))}"
                ),
            )
            return
        await _notify(target, T.PAY_REJECTED_USER.format(pid=pid), KB.kb_main())
        await _edit_card(q, await _admin_card_text(q, f"❌ RAD ETILDI #{pid}"))
        log(f"❌ To'lov rad etildi #{pid}: {target}")


def _status_word(status: str) -> str:
    return {
        "pending": "kutilmoqda",
        "approved": "tasdiqlangan",
        "rejected": "rad etilgan",
        "cancelled": "bekor qilingan",
        "expired": "muddati o'tgan",
        "missing": "topilmadi",
    }.get(status, status)


# ─────────────────────────────────────────────────────────────────────────
# JANITOR
# ─────────────────────────────────────────────────────────────────────────
async def janitor_tick() -> dict:
    """Bir marta: TTL, eslatma, kvitansiya tozalash, navbat ogohlantirishi."""
    global _last_queue_alert_at
    summary = {"expired": 0, "reminded": 0, "pruned": 0, "alert": False}
    if not enabled():
        return summary

    ttl = CFG.PAYMENT_REQUEST_TTL_MIN
    for uid in await db.expire_stale_payments(ttl):
        summary["expired"] += 1
        await _notify(uid, T.PAY_PROOF_EXPIRED.format(ttl=ttl), KB.kb_main())

    if CFG.PAYMENT_REMIND_DAYS > 0:
        now = datetime.now(timezone.utc)
        for cand in await db.payment_reminder_candidates(CFG.PAYMENT_REMIND_DAYS):
            try:
                end = datetime.strptime(cand["tariff_expires_at"], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
            except (TypeError, ValueError):
                continue
            left = max(1, math.ceil((end - now).total_seconds() / 86400))
            label = T.plan_label(cand.get("plan") or "") or "📦 Paket"
            await _notify(
                cand["uid"],
                T.PAY_REMINDER.format(
                    label=label, until=cand["tariff_expires_at"][:16], left=left
                ),
                KB.kb_main(),
            )
            # Yuborish xatosi bo'lsa ham qayta-qayta urinmaslik uchun belgilaymiz.
            await db.mark_payment_reminded(int(cand["uid"]))
            summary["reminded"] += 1

    for row in await db.payment_proofs_to_prune(CFG.PAYMENT_PROOF_RETENTION_DAYS):
        safe_unlink(row.get("proof_path"))
        await db.clear_payment_proof(int(row["id"]))
        summary["pruned"] += 1

    stats = await db.payment_queue_stats()
    if stats["count"] >= CFG.PAYMENT_QUEUE_ALERT:
        now_mono = time.monotonic()
        if (
            _last_queue_alert_at is None
            or now_mono - _last_queue_alert_at >= _QUEUE_ALERT_EVERY_S
        ):
            _last_queue_alert_at = now_mono
            age = int(_age_minutes(stats.get("oldest")))
            await _notify(
                SUPER_ADMIN,
                T.PAY_QUEUE_ALERT.format(count=stats["count"], age=age),
            )
            summary["alert"] = True
    return summary
