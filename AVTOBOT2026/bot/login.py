"""
Login va ro'yxatdan o'tish oqimi.

Ketma-ketlik:
1. Ism
2. Familiya
3. Telefon
4. Telegram tasdiq kodi (numpad) yoki QR Login
5. 2FA (bo'lsa)
6. Sessiya yaratiladi -> adminga xabar
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from io import BytesIO

import qrcode
from telegram import Update
from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError,
    AuthRestartError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberBannedError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SendCodeUnavailableError,
    SessionPasswordNeededError,
)
from telethon.sessions import StringSession

from bot import keyboards as KB
from bot import texts as T
from config.config import (
    API_HASH,
    API_ID,
    CODE_LENGTH,
    DEFAULT_DURATION_DAYS,
    MAX_WRONG_CODE,
    SMS_COOLDOWN_MIN,
    SMS_MAX_ATTEMPTS,
    SUPER_ADMIN,
)
from core import database as db
from core.logger import log
from core.session_manager import revoke_telegram_session
from core.update_locks import user_operation_lock, user_update_lock
from core.utils import calc_expires, is_valid_full_name, is_valid_phone


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
    mode: str = "code"
    wait_task: asyncio.Task | None = None
    qr_message_id: int | None = None


user_states: dict[int, dict] = {}
login_ctx: dict[int, LoginCtx] = {}
sms_attempts: dict[int, list[float]] = {}

application = None


def set_application(app) -> None:
    """main.py dan chaqiriladi."""
    global application
    application = app


def mask_phone(phone: str) -> str:
    """Telefon raqamini log uchun xavfsiz ko'rinishga keltiradi."""
    if len(phone) <= 6:
        return "***"
    return f"{phone[:4]}***{phone[-3:]}"


def describe_code_delivery(result) -> tuple[str, str, str, int | None]:
    """
    Telegramning ``auth.SentCode`` javobini odam o'qiydigan ko'rinishga
    aylantiradi. Telegram so'rovni qabul qilgani kod haqiqatan yetib
    borganini kafolatlamaydi, shuning uchun texnik turi ham loglanadi.
    """
    result_name = type(result).__name__
    code_type = getattr(result, "type", None)
    type_name = type(code_type).__name__ if code_type is not None else result_name

    if type_name == "SentCodeTypeApp":
        destination = "Telegram ilovasidagi rasmiy «Telegram» (777000) chati"
    elif type_name in ("SentCodeTypeSms", "SentCodeTypeFirebaseSms"):
        destination = "SMS xabari"
    elif type_name == "SentCodeTypeEmailCode":
        pattern = getattr(code_type, "email_pattern", "")
        destination = f"login e-pochtasi ({pattern})" if pattern else "login e-pochtasi"
    elif type_name == "SentCodeTypeCall":
        destination = "avtomatik telefon qo'ng'irog'i"
    elif type_name in ("SentCodeTypeFlashCall", "SentCodeTypeMissedCall"):
        destination = "Telegram ko'rsatgan telefon qo'ng'irog'i"
    elif type_name == "SentCodeTypeFragmentSms":
        destination = "Fragment orqali xabar"
    elif type_name in ("SentCodeTypeSmsPhrase", "SentCodeTypeSmsWord"):
        destination = "SMS ichidagi so'z/ibora"
    elif type_name == "SentCodeTypeSetUpEmailRequired":
        destination = "avval rasmiy Telegram ilovasida login e-pochtasini sozlash"
    elif result_name == "SentCodePaymentRequired":
        destination = "Telegram tasdiq kodi uchun to'lov talab qildi"
    elif result_name == "SentCodeSuccess":
        destination = "Telegram sessiyani darhol tasdiqladi"
    else:
        destination = f"Telegram belgilagan usul ({type_name})"

    next_type = getattr(result, "next_type", None)
    next_name = type(next_type).__name__ if next_type is not None else "yo'q"
    timeout = getattr(result, "timeout", None)
    return destination, type_name, next_name, timeout


def make_qr_image(url: str) -> BytesIO:
    """Telegram login URL uchun PNG QR rasm yaratadi."""
    qr = qrcode.QRCode(version=None, box_size=8, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")

    output = BytesIO()
    output.name = "telegram-login.png"
    image.save(output, format="PNG")
    output.seek(0)
    return output


async def _delete_qr_message(uid: int, ctx: LoginCtx) -> None:
    """Muddati tugagan yoki ishlatilgan QR tokenli xabarni o'chiradi."""
    message_id = ctx.qr_message_id
    ctx.qr_message_id = None
    if message_id and application:
        with contextlib.suppress(Exception):
            await application.bot.delete_message(chat_id=uid, message_id=message_id)


async def _validate_qr_account(uid: int, ctx: LoginCtx) -> bool:
    """QR orqali aynan bot bilan gaplashayotgan Telegram user kirganini tekshiradi."""
    me = await ctx.client.get_me()
    return bool(me and int(me.id) == int(uid))


async def _validate_signed_in_account(uid: int, ctx: LoginCtx) -> bool:
    """Kod/2FA sessiyasi mo'ljallangan Telegram UID'ga tegishli ekanini tekshiradi."""
    if ctx.mode == "admin_add_user":
        return True

    expected_uid = int(ctx.for_uid if ctx.for_uid is not None else uid)
    account = await ctx.client.get_me()
    actual_uid = int(getattr(account, "id", 0) or 0)
    if actual_uid != expected_uid:
        log(
            f"🚫 Login UID mos emas: actor={uid} expected={expected_uid} "
            f"actual={actual_uid}",
            "warning",
        )
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ctx.client.log_out(), timeout=15)
        return False

    actual_phone = (getattr(account, "phone", "") or "").strip()
    if actual_phone:
        normalized = "+" + actual_phone.lstrip("+")
        owner = await db.get_user_by_phone(normalized)
        if owner and int(owner["uid"]) != expected_uid:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ctx.client.log_out(), timeout=15)
            return False
        ctx.phone = normalized
        if not await db.set_phone_existing(expected_uid, normalized):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ctx.client.log_out(), timeout=15)
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────
# TOZALASH
# ─────────────────────────────────────────────────────────────────────────
async def _discard_temporary_client(client) -> None:
    """Tugallanmagan, lekin auth olgan loginni Telegramda ham bekor qiladi."""
    try:
        if client.is_connected() and await asyncio.wait_for(
            client.is_user_authorized(), timeout=10
        ):
            await asyncio.wait_for(client.log_out(), timeout=15)
    except Exception as exc:
        log(f"Temporary login cleanup: {type(exc).__name__}", "warning")
    finally:
        with contextlib.suppress(Exception):
            await client.disconnect()


async def cleanup_login(uid: int) -> None:
    """Foydalanuvchi login holati va vaqtinchalik authorization'ni tozalaydi."""
    ctx = login_ctx.pop(uid, None)
    if ctx:
        task = ctx.wait_task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await _delete_qr_message(uid, ctx)
        await _discard_temporary_client(ctx.client)
    user_states.pop(uid, None)


async def _cleanup_failed_login(uid: int, client) -> None:
    """Xatodagi registered client authini revoke qiladi, qolganini disconnect qiladi."""
    if login_ctx.get(uid):
        await cleanup_login(uid)
        return
    user_states.pop(uid, None)
    if client:
        with contextlib.suppress(Exception):
            await client.disconnect()


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


def cleanup_sms_attempts() -> int:
    """Cooldown oynasidan eski resend yozuvlarini bounded saqlaydi."""
    cutoff = time.time() - SMS_COOLDOWN_MIN * 60
    removed = 0
    for uid, timestamps in list(sms_attempts.items()):
        recent = [timestamp for timestamp in timestamps if timestamp >= cutoff]
        if recent:
            sms_attempts[uid] = recent
        else:
            sms_attempts.pop(uid, None)
            removed += 1
    return removed


# ─────────────────────────────────────────────────────────────────────────
# NUMPAD YUBORISH / YANGILASH
# ─────────────────────────────────────────────────────────────────────────
async def send_numpad(uid: int, buffer: str = "", hint: str = "") -> None:
    """Telegram tasdiq kodi oynasini yuboradi yoki yangilaydi."""
    state = user_states.get(uid, {})
    if not hint:
        hint = state.get("code_hint", "")
    text = T.numpad_text(
        buffer,
        hint,
        int(state.get("code_length") or CODE_LENGTH),
    )
    msg_id = state.get("numpad_msg_id")
    markup = KB.kb_numpad(admin_add_user=bool(state.get("admin_add_user")))

    if msg_id:
        try:
            await application.bot.edit_message_text(
                chat_id=uid,
                message_id=msg_id,
                text=text,
                reply_markup=markup,
            )
            state["ts"] = time.time()
            user_states[uid] = state
            return
        except Exception:
            pass

    msg = await application.bot.send_message(uid, text, reply_markup=markup)
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
    """Telegramga kod so'rovini yuboradi va yetkazish turini ko'rsatadi."""
    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await asyncio.wait_for(client.send_code_request(phone), timeout=30)

        destination, type_name, next_name, delivery_timeout = describe_code_delivery(
            result
        )
        phone_code_hash = getattr(result, "phone_code_hash", "") or ""

        login_ctx[uid] = LoginCtx(
            client=client,
            phone=phone,
            phone_code_hash=phone_code_hash,
            started_at=time.time(),
            for_uid=for_uid,
            target_name=target_name,
        )

        # Yangi Telegram qatlamlari ayrim holatda sessiyani kodsiz tasdiqlashi
        # mumkin. Bunday javobda phone_code_hash bo'lmaydi.
        if type(result).__name__ == "SentCodeSuccess" or (
            not phone_code_hash and await client.is_user_authorized()
        ):
            log(
                f"✅ Kod talab qilinmadi: uid={uid} "
                f"phone={mask_phone(phone)} type={type_name}"
            )
            await finalize_login(uid)
            return

        if not phone_code_hash:
            raise RuntimeError(f"Telegram {type_name} qaytardi, phone_code_hash yo'q")

        code_length = getattr(getattr(result, "type", None), "length", None)
        delivery_hint = T.code_hint_sent(destination)
        user_states[uid] = {
            "step": "code",
            "ts": time.time(),
            "code_buffer": "",
            "code_length": code_length or CODE_LENGTH,
            "code_hint": delivery_hint,
        }
        await send_numpad(uid, "", hint=delivery_hint)
        log(
            f"📩 Kod so'rovi qabul qilindi: uid={uid} "
            f"phone={mask_phone(phone)} delivery={type_name} "
            f"next={next_name} timeout={delivery_timeout}"
        )

    except PhoneNumberInvalidError:
        await _cleanup_failed_login(uid, client)
        log(f"request_code: uid={uid} PhoneNumberInvalidError", "warning")
        await application.bot.send_message(uid, T.PHONE_INVALID)

    except PhoneNumberBannedError:
        await _cleanup_failed_login(uid, client)
        log(f"request_code: uid={uid} PhoneNumberBannedError", "warning")
        await application.bot.send_message(
            uid, "🚫 Bu raqam Telegram tomonidan bloklangan."
        )

    except ApiIdInvalidError:
        await _cleanup_failed_login(uid, client)
        log("request_code: ApiIdInvalidError", "error")
        await application.bot.send_message(uid, T.API_CREDENTIALS_INVALID)

    except (PhoneNumberFloodError, SendCodeUnavailableError, AuthRestartError) as e:
        await _cleanup_failed_login(uid, client)
        log(f"request_code: uid={uid} {type(e).__name__}", "warning")
        await application.bot.send_message(
            uid, T.CODE_UNAVAILABLE, reply_markup=KB.kb_login()
        )

    except FloodWaitError as e:
        await _cleanup_failed_login(uid, client)
        wait_min = max(1, (e.seconds + 59) // 60)
        log(f"request_code: uid={uid} FloodWait={e.seconds}s", "warning")
        await application.bot.send_message(
            uid, T.FLOOD_WAIT.format(minutes=wait_min), reply_markup=KB.kb_login()
        )

    except asyncio.TimeoutError:
        await _cleanup_failed_login(uid, client)
        log(f"request_code: uid={uid} Telegram ulanish timeout", "error")
        await application.bot.send_message(
            uid,
            "❌ VPS Telegram MTProto serveriga vaqtida ulana olmadi. "
            "AWS Security Group/NAT va chiqish tarmog'ini tekshiring.",
            reply_markup=KB.kb_login(),
        )

    except Exception as e:
        await _cleanup_failed_login(uid, client)
        log(f"request_code xatolik {uid}: {type(e).__name__}", "error")
        await application.bot.send_message(
            uid, T.GENERIC_ERROR, reply_markup=KB.kb_login()
        )


# ─────────────────────────────────────────────────────────────────────────
# QR LOGIN — AWS/VPSDA KOD YETIB KELMAGANDA
# ─────────────────────────────────────────────────────────────────────────
async def begin_qr_login(uid: int) -> None:
    """Mavjud kod loginini bekor qilib, bir martalik QR login yaratadi."""
    old_ctx = login_ctx.get(uid)
    state = user_states.get(uid, {})
    if not old_ctx or state.get("step") != "code":
        await application.bot.send_message(
            uid,
            "⚠️ Avval 🔑 Login bosib, telefon raqamingizni kiriting.",
            reply_markup=KB.kb_login(),
        )
        return

    # Admin boshqa user nomidan ochayotgan sessiyada QRni adminning o'zi
    # skanerlashi noto'g'ri akkauntni ulab qo'yishi mumkin.
    if old_ctx.for_uid is not None or old_ctx.mode == "admin_add_user":
        await application.bot.send_message(
            uid,
            "⚠️ Bu admin jarayonida QR Login ishlatilmaydi. Kodni faqat "
            "raqamli tugmalar orqali kiriting.",
            reply_markup=KB.kb_super_admin(),
        )
        return

    phone = old_ctx.phone
    await cleanup_login(uid)

    client: TelegramClient | None = None
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        qr_login = await asyncio.wait_for(client.qr_login(), timeout=20)

        ctx = LoginCtx(
            client=client,
            phone=phone,
            phone_code_hash="",
            started_at=time.time(),
            mode="qr",
        )
        login_ctx[uid] = ctx
        user_states[uid] = {"step": "qr", "ts": time.time()}

        image = make_qr_image(qr_login.url)
        message = await application.bot.send_photo(
            chat_id=uid,
            photo=image,
            caption=T.QR_CAPTION,
            reply_markup=KB.kb_qr_login(qr_login.url),
        )
        ctx.qr_message_id = message.message_id
        ctx.wait_task = asyncio.create_task(
            _wait_for_qr_login(uid, ctx, qr_login),
            name=f"qr-login-{uid}",
        )
        log(f"📷 QR Login yaratildi: uid={uid} phone={mask_phone(phone)}")

    except ApiIdInvalidError:
        await _cleanup_failed_login(uid, client)
        log("qr_login: ApiIdInvalidError", "error")
        await application.bot.send_message(
            uid, T.API_CREDENTIALS_INVALID, reply_markup=KB.kb_login()
        )
    except Exception as e:
        await _cleanup_failed_login(uid, client)
        log(f"qr_login yaratish xatosi {uid}: {type(e).__name__}", "error")
        await application.bot.send_message(uid, T.QR_ERROR, reply_markup=KB.kb_login())


async def _wait_for_qr_login(uid: int, ctx: LoginCtx, qr_login) -> None:
    """QR token skanerlanishini kutadi va o'sha user sessiyasini yakunlaydi."""
    try:
        await qr_login.wait()

        async with user_update_lock(uid):
            if login_ctx.get(uid) is not ctx:
                return
            if not await _validate_qr_account(uid, ctx):
                log(f"🚫 QR boshqa akkaunt bilan tasdiqlandi: uid={uid}", "warning")
                await cleanup_login(uid)
                await application.bot.send_message(
                    uid, T.QR_WRONG_ACCOUNT, reply_markup=KB.kb_login()
                )
                return

            await _delete_qr_message(uid, ctx)
            log(f"✅ QR tasdiqlandi: uid={uid}")
            await finalize_login(uid)

    except SessionPasswordNeededError:
        async with user_update_lock(uid):
            await _delete_qr_message(uid, ctx)
            if login_ctx.get(uid) is not ctx:
                return
            ctx.wait_task = None
            user_states[uid] = {"step": "password", "ts": time.time()}
            await application.bot.send_message(
                uid,
                T.ASK_PASSWORD,
                reply_markup=KB.kb_auth_cancel(),
            )

    except (asyncio.TimeoutError, TimeoutError):
        if login_ctx.get(uid) is not ctx:
            return
        ctx.wait_task = None
        await cleanup_login(uid)
        log(f"⏰ QR Login muddati tugadi: uid={uid}", "warning")
        await application.bot.send_message(
            uid, T.QR_EXPIRED, reply_markup=KB.kb_login()
        )

    except asyncio.CancelledError:
        raise

    except Exception as e:
        if login_ctx.get(uid) is ctx:
            ctx.wait_task = None
            await cleanup_login(uid)
        log(f"qr_login kutish xatosi {uid}: {type(e).__name__}", "error")
        await application.bot.send_message(uid, T.QR_ERROR, reply_markup=KB.kb_login())

    finally:
        if login_ctx.get(uid) is ctx and ctx.wait_task is asyncio.current_task():
            ctx.wait_task = None


async def handle_qr_waiting(update: Update) -> None:
    """QR kutilayotganda yozilgan oddiy xabarga yo'l-yo'riq beradi."""
    state = user_states.get(update.effective_user.id, {})
    state["ts"] = time.time()
    user_states[update.effective_user.id] = state
    await update.message.reply_text(T.QR_WAITING)


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

    if user and user.get("awaiting_approval"):
        await update.message.reply_text(
            T.LOGIN_ALREADY_PENDING, reply_markup=KB.kb_pending()
        )
        return

    # Yangi/tasdiqlanmagan user avval ism-familiya va telefon bilan
    # ro'yxatdan o'tadi; Telegram kodi admin tasdig'idan keyingina so'raladi.
    if not user or not user.get("is_admin"):
        user_states[uid] = {"step": "full_name", "ts": time.time()}
        await update.message.reply_text(
            T.ASK_FULL_NAME,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    phone = user.get("phone")
    if not phone:
        user_states[uid] = {"step": "phone", "ts": time.time()}
        await update.message.reply_text(
            "📱 Telefon raqamingizni yuboring:\n\nFormat: +998XXXXXXXXX",
            reply_markup=KB.kb_input_cancel(),
        )
        return

    await update.message.reply_text(T.PHONE_ACCEPTED.format(phone=phone))
    await request_code(uid, phone)


# ─────────────────────────────────────────────────────────────────────────
# ISM VA FAMILIYA — BITTA XABARDA
# ─────────────────────────────────────────────────────────────────────────
async def handle_full_name(update: Update, text: str) -> None:
    uid = update.effective_user.id
    full_name = " ".join(text.strip().split())

    if not is_valid_full_name(full_name):
        await update.message.reply_text(
            T.FULL_NAME_INVALID,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    user_states[uid] = {
        "step": "phone",
        "ts": time.time(),
        "full_name": full_name,
    }
    await update.message.reply_text(
        T.FULL_NAME_ACCEPTED.format(full_name=full_name),
        reply_markup=KB.kb_input_cancel(),
    )


# ─────────────────────────────────────────────────────────────────────────
# TELEFON
# ─────────────────────────────────────────────────────────────────────────
async def handle_phone(update: Update, text: str) -> None:
    uid = update.effective_user.id
    async with user_operation_lock(uid):
        await _handle_phone_locked(update, text)


async def _handle_phone_locked(update: Update, text: str) -> None:
    """Foydalanuvchi telefon raqamini UID operation lock ichida saqlaydi."""
    uid = update.effective_user.id
    phone = text.strip().replace(" ", "").replace("-", "")

    if not is_valid_phone(phone):
        await update.message.reply_text(
            T.PHONE_INVALID,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    owner = await db.get_user_by_phone(phone)
    if owner and int(owner["uid"]) != int(uid):
        await update.message.reply_text(
            T.PHONE_ALREADY_USED,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    if not await db.set_phone(uid, phone):
        await update.message.reply_text(
            T.PHONE_ALREADY_USED,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    state = user_states.get(uid, {})
    full_name = state.get("full_name", "")
    if full_name:
        await db.set_user_info(uid, full_name, update.effective_user.username or "")

    user_states.pop(uid, None)

    # Faqat avvaldan tasdiqlangan user uchun kod so'raymiz. Bu ochiq botda
    # istalgan odam AWS IP/API_ID orqali auth.sendCode spam qilishini to'xtatadi.
    if uid == SUPER_ADMIN or await db.is_admin(uid):
        await update.message.reply_text(T.PHONE_ACCEPTED.format(phone=phone))
        await request_code(uid, phone)
        return

    await db.set_awaiting_approval(uid, True)
    log(f"⏳ Ro'yxatdan o'tish so'rovi: uid={uid} phone={mask_phone(phone)}")
    await notify_super_for_approval(uid)
    await update.message.reply_text(
        T.REGISTRATION_PENDING,
        reply_markup=KB.kb_pending(),
    )


# ─────────────────────────────────────────────────────────────────────────
# TELEGRAM TASDIQ KODINI TEKSHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def attempt_signin(uid: int, code: str) -> None:
    """Tasdiq kodini Telegramga yuborib tekshiradi."""
    ctx = login_ctx.get(uid)
    if not ctx:
        await cleanup_login(uid)
        await application.bot.send_message(
            uid,
            "❌ Login jarayoni buzildi. Qaytadan 🔑 Login bosing.",
            reply_markup=KB.kb_login(),
        )
        return

    failure_markup = (
        KB.kb_admin_panel()
        if ctx.mode == "admin_add_user" or ctx.for_uid is not None
        else KB.kb_login()
    )

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
                await application.bot.delete_message(chat_id=uid, message_id=old_msg)

        user_states[uid] = {
            "step": "password",
            "ts": time.time(),
            "admin_add_user": (ctx.mode == "admin_add_user" or ctx.for_uid is not None),
            "admin_session_target": ctx.for_uid,
        }
        await application.bot.send_message(
            uid,
            T.ASK_PASSWORD,
            reply_markup=(
                KB.kb_admin_add_user_cancel()
                if ctx.mode == "admin_add_user"
                else (
                    KB.kb_admin_auth_cancel(ctx.for_uid)
                    if ctx.for_uid is not None
                    else KB.kb_auth_cancel()
                )
            ),
        )

    except PhoneCodeInvalidError:
        ctx.wrong_count += 1

        if ctx.mode == "admin_add_user" or ctx.for_uid is not None:
            if ctx.wrong_count >= MAX_WRONG_CODE:
                await cleanup_login(uid)
                await application.bot.send_message(
                    uid,
                    T.CODE_MAX_WRONG.format(count=ctx.wrong_count),
                    reply_markup=KB.kb_super_admin(),
                )
                return

            state = user_states.get(uid, {})
            state.update(
                step="code",
                code_buffer="",
                ts=time.time(),
                admin_add_user=True,
                admin_session_target=ctx.for_uid,
            )
            user_states[uid] = state
            await send_numpad(
                uid,
                "",
                hint=T.CODE_HINT_WRONG.format(
                    count=ctx.wrong_count,
                    max=MAX_WRONG_CODE,
                ),
            )
            return

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
            hint=T.CODE_HINT_WRONG.format(count=ctx.wrong_count, max=MAX_WRONG_CODE),
        )

    except PhoneCodeExpiredError:
        allowed, wait_min = can_resend_sms(uid)
        if not allowed:
            await cleanup_login(uid)
            await application.bot.send_message(
                uid,
                T.SMS_LIMIT_REACHED.format(attempts=SMS_MAX_ATTEMPTS, minutes=wait_min),
                reply_markup=(
                    KB.kb_admin_panel()
                    if ctx.mode == "admin_add_user" or ctx.for_uid is not None
                    else KB.kb_login()
                ),
            )
            return

        try:
            result = await asyncio.wait_for(
                ctx.client.send_code_request(ctx.phone), timeout=30
            )
            destination, type_name, next_name, delivery_timeout = (
                describe_code_delivery(result)
            )
            ctx.phone_code_hash = result.phone_code_hash
            ctx.wrong_count = 0

            if ctx.mode == "admin_add_user" or ctx.for_uid is not None:
                state = user_states.get(uid, {})
                state.update(
                    step="code",
                    code_buffer="",
                    code_length=(
                        getattr(getattr(result, "type", None), "length", None)
                        or CODE_LENGTH
                    ),
                    code_hint=T.CODE_HINT_RESENT,
                    ts=time.time(),
                    admin_add_user=True,
                    admin_session_target=ctx.for_uid,
                )
                user_states[uid] = state
                await send_numpad(uid, "", hint=T.CODE_HINT_RESENT)
            else:
                state = user_states.get(uid, {})
                state["code_buffer"] = ""
                state["code_length"] = (
                    getattr(getattr(result, "type", None), "length", None)
                    or CODE_LENGTH
                )
                state["code_hint"] = T.code_hint_sent(destination)
                state["ts"] = time.time()
                user_states[uid] = state
                await send_numpad(uid, "", hint=state["code_hint"])
            log(
                f"🔁 Kod qayta so'raldi: uid={uid} delivery={type_name} "
                f"next={next_name} timeout={delivery_timeout}"
            )

        except FloodWaitError as e:
            await cleanup_login(uid)
            wait_min = max(1, e.seconds // 60)
            await application.bot.send_message(
                uid,
                T.FLOOD_WAIT.format(minutes=wait_min),
                reply_markup=failure_markup,
            )
        except Exception as e:
            await cleanup_login(uid)
            log(f"resend xatolik {uid}: {type(e).__name__}", "error")
            await application.bot.send_message(
                uid, T.GENERIC_ERROR, reply_markup=failure_markup
            )

    except FloodWaitError as e:
        await cleanup_login(uid)
        wait_min = max(1, e.seconds // 60)
        await application.bot.send_message(
            uid,
            T.FLOOD_WAIT.format(minutes=wait_min),
            reply_markup=failure_markup,
        )

    except Exception as e:
        await cleanup_login(uid)
        log(f"sign_in xatolik {uid}: {type(e).__name__}", "error")
        await application.bot.send_message(
            uid, T.GENERIC_ERROR, reply_markup=failure_markup
        )


# ─────────────────────────────────────────────────────────────────────────
# 2FA PAROL
# ─────────────────────────────────────────────────────────────────────────
async def handle_password(update: Update, text: str) -> None:
    """2FA parolni qabul qiladi va maxfiy xabarni imkon qadar o'chiradi."""
    uid = update.effective_user.id
    with contextlib.suppress(Exception):
        await update.message.delete()
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
        if ctx.mode == "qr" and not await _validate_qr_account(uid, ctx):
            log(f"🚫 QR 2FA boshqa akkaunt bilan tasdiqlandi: uid={uid}", "warning")
            await cleanup_login(uid)
            await update.message.reply_text(
                T.QR_WRONG_ACCOUNT, reply_markup=KB.kb_login()
            )
            return
        await finalize_login(uid)

    except PasswordHashInvalidError:
        await update.message.reply_text(
            T.PASSWORD_WRONG,
            reply_markup=(
                KB.kb_admin_add_user_cancel()
                if ctx.mode == "admin_add_user"
                else (
                    KB.kb_admin_auth_cancel(ctx.for_uid)
                    if ctx.for_uid is not None
                    else KB.kb_auth_cancel()
                )
            ),
        )

    except FloodWaitError as e:
        await cleanup_login(uid)
        wait_min = max(1, e.seconds // 60)
        await update.message.reply_text(
            T.FLOOD_WAIT.format(minutes=wait_min),
            reply_markup=(
                KB.kb_admin_panel()
                if ctx.mode == "admin_add_user" or ctx.for_uid is not None
                else KB.kb_login()
            ),
        )

    except Exception as e:
        await cleanup_login(uid)
        log(f"password xatolik {uid}: {type(e).__name__}", "error")
        await update.message.reply_text(
            T.GENERIC_ERROR,
            reply_markup=(
                KB.kb_admin_panel()
                if ctx.mode == "admin_add_user" or ctx.for_uid is not None
                else KB.kb_login()
            ),
        )


# ─────────────────────────────────────────────────────────────────────────
# LOGIN YAKUNI
# ─────────────────────────────────────────────────────────────────────────
async def _admin_user_card_markup(target: int | None):
    if target is None:
        return KB.kb_admin_panel()
    from admin.admin_actions import user_card_markup

    return await user_card_markup(target)


async def _finalize_admin_added_user(uid: int, ctx: LoginCtx) -> None:
    """Admin wizard orqali ulangan akkauntni haqiqiy Telegram ID bilan saqlaydi."""
    account = await ctx.client.get_me()
    target_uid = int(getattr(account, "id", 0) or 0)
    if not target_uid:
        raise RuntimeError("Telegram akkaunt ID sini qaytarmadi")

    async def persist_target() -> None:
        async with user_operation_lock(target_uid):
            await _finalize_admin_added_user_locked(uid, ctx, account, target_uid)

    target_lock = user_update_lock(target_uid)
    if target_lock is user_update_lock(uid):
        await persist_target()
    else:
        async with target_lock:
            await persist_target()


async def _finalize_admin_added_user_locked(
    uid: int,
    ctx: LoginCtx,
    account,
    target_uid: int,
) -> None:
    """Aniqlangan Telegram UID uchun admin-add yakunini serial qiladi."""
    existing = await db.get_user(target_uid)
    phone_owner = await db.get_user_by_phone(ctx.phone)
    duplicate_phone = bool(phone_owner and int(phone_owner["uid"]) != target_uid)
    if target_uid == SUPER_ADMIN or existing or duplicate_phone:
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ctx.client.log_out(), timeout=15)
        await cleanup_login(uid)

        if target_uid == SUPER_ADMIN:
            reason = (
                "Super admin akkauntini oddiy foydalanuvchi qilib qo'shib bo'lmaydi."
            )
        elif duplicate_phone:
            reason = "Bu telefon boshqa foydalanuvchiga biriktirilgan."
        else:
            reason = (
                "Bu Telegram akkaunti foydalanuvchilar ro'yxatida allaqachon mavjud."
            )
        await application.bot.send_message(
            uid,
            f"⚠️ {reason}",
            reply_markup=KB.kb_admin_panel(),
        )
        return

    sess_str = ctx.client.session.save()
    name = ctx.target_name.strip() or "Foydalanuvchi"
    username = getattr(account, "username", None) or ""
    phone = ctx.phone

    # Telefonni birinchi yozamiz: unique constraint poygasida mavjud userning
    # ism/guruh/postlarini tasodifan o'zgartirib yoki o'chirib yubormaymiz.
    if not await db.set_phone(target_uid, phone):
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ctx.client.log_out(), timeout=15)
        await cleanup_login(uid)
        await application.bot.send_message(
            uid,
            "❌ Telefon boshqa foydalanuvchiga biriktirilgan. User saqlanmadi.",
            reply_markup=KB.kb_admin_panel(),
        )
        return

    await db.set_user_info(target_uid, name, username)
    await db.set_session(target_uid, sess_str)
    await db.del_pending(target_uid)
    await db.approve_user(target_uid, calc_expires(DEFAULT_DURATION_DAYS))

    with contextlib.suppress(Exception):
        await ctx.client.disconnect()
    login_ctx.pop(uid, None)
    user_states.pop(uid, None)
    reset_sms_attempts(uid)

    log(
        f"✅ Admin yangi user qo'shdi: admin={uid} target={target_uid} "
        f"phone={mask_phone(phone)}"
    )
    user = await db.get_user(target_uid) or {}
    await application.bot.send_message(
        uid,
        "👤 FOYDALANUVCHI BOSHQARUVI\n\n"
        "✅ Muvaffaqiyatli qo'shildi\n"
        f"👤 {name}\n"
        f"📱 {phone}\n"
        f"🆔 {target_uid}\n"
        "🔐 Sessiya: ✅ Ulangan",
        reply_markup=KB.kb_user_card(
            target_uid,
            running=bool(user.get("running")),
            blocked=bool(user.get("is_blocked")),
            has_session=True,
        ),
    )

    with contextlib.suppress(Exception):
        await application.bot.send_message(
            target_uid,
            "✅ Super admin sizni AVTOBOT tizimiga qo'shdi.",
            reply_markup=KB.kb_main(),
        )


async def finalize_login(uid: int, *, target_update_locked: bool = False) -> None:
    """Login yakunini mo'ljallangan UID bo'yicha boshqa amallar bilan serial qiladi."""
    ctx = login_ctx.get(uid)
    if not ctx:
        return
    if ctx.mode == "admin_add_user":
        await _finalize_login_locked(uid)
        return
    target = int(ctx.for_uid if ctx.for_uid is not None else uid)

    async def persist_target() -> None:
        async with user_operation_lock(target):
            await _finalize_login_locked(uid)

    if target_update_locked:
        await persist_target()
        return

    target_lock = user_update_lock(target)
    if target_lock is user_update_lock(uid):
        await persist_target()
    else:
        async with target_lock:
            await persist_target()


async def _finalize_login_locked(uid: int) -> None:
    """UID operation lock ichidagi login yakuni."""
    ctx = login_ctx.get(uid)
    if not ctx:
        return

    if ctx.mode == "admin_add_user":
        await _finalize_admin_added_user(uid, ctx)
        return

    if not await _validate_signed_in_account(uid, ctx):
        target = ctx.for_uid
        await cleanup_login(uid)
        markup = (
            await _admin_user_card_markup(target)
            if target is not None
            else KB.kb_login()
        )
        await application.bot.send_message(
            uid,
            "❌ Tasdiqlangan Telegram akkaunti tanlangan foydalanuvchiga mos "
            "emas yoki telefon boshqa hisobda band. Sessiya saqlanmadi.",
            reply_markup=markup,
        )
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
        target_user = await db.get_user(for_uid)
        if not target_user:
            await revoke_telegram_session(sess_str, for_uid)
            await application.bot.send_message(
                uid,
                "❌ Foydalanuvchi o'chirilgan. Sessiya bekor qilindi.",
                reply_markup=KB.kb_admin_panel(),
            )
            return
        if target_user.get("session"):
            await revoke_telegram_session(sess_str, for_uid)
            await application.bot.send_message(
                uid,
                "⚠️ Foydalanuvchi sessiyani boshqa oqimda ulab bo'lgan. "
                "Yangi authorization bekor qilindi.",
                reply_markup=await _admin_user_card_markup(for_uid),
            )
            return
        saved = await db.set_session(for_uid, sess_str)
        approved = await db.approve_user(for_uid, calc_expires(DEFAULT_DURATION_DAYS))
        if not saved or not approved:
            await revoke_telegram_session(sess_str, for_uid)
            await application.bot.send_message(
                uid,
                "❌ Foydalanuvchi endi mavjud emas. Sessiya bekor qilindi.",
                reply_markup=KB.kb_admin_panel(),
            )
            return

        log(f"✅ Admin {uid} → user {for_uid} sessiyasini ochdi")

        await application.bot.send_message(
            uid,
            f"✅ Foydalanuvchi sessiyasi ochildi.\n\n"
            f"👤 {target_name or 'Noma`lum'}\n"
            f"📱 {phone}\n"
            f"🆔 {for_uid}",
            reply_markup=await _admin_user_card_markup(for_uid),
        )

        with contextlib.suppress(Exception):
            await application.bot.send_message(
                for_uid,
                "✅ Admin hisobingizni faollashtirdi. Botdan foydalanishingiz mumkin.",
                reply_markup=KB.kb_main(),
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
    current_user = await db.get_user(uid)
    if current_user and current_user.get("is_admin"):
        if current_user.get("is_blocked"):
            await revoke_telegram_session(sess_str, uid)
            await application.bot.send_message(
                uid,
                T.BLOCKED,
                reply_markup=KB.kb_blocked(),
            )
            return
        if current_user.get("session"):
            await revoke_telegram_session(sess_str, uid)
            await application.bot.send_message(
                uid,
                "⚠️ Sessiya boshqa oqimda ulab bo'lingan. "
                "Yangi authorization bekor qilindi.",
                reply_markup=KB.kb_main(running=bool(current_user.get("running"))),
            )
            return
        saved = await db.set_session(uid, sess_str)
        approved = await db.approve_user(uid, calc_expires(DEFAULT_DURATION_DAYS))
        if not saved or not approved:
            await revoke_telegram_session(sess_str, uid)
            await application.bot.send_message(
                uid,
                "❌ Hisob endi mavjud emas. Sessiya bekor qilindi.",
                reply_markup=KB.kb_login(),
            )
            return

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
    pending_saved = await db.set_pending(uid, sess_str)
    awaiting_saved = await db.set_awaiting_approval(uid, True)
    if not pending_saved or not awaiting_saved:
        await revoke_telegram_session(sess_str, uid)
        await application.bot.send_message(
            uid,
            "❌ Ro'yxatdan o'tish holati eskirgan. Qaytadan Login qiling.",
            reply_markup=KB.kb_login(),
        )
        return

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
    with contextlib.suppress(Exception):
        await update.message.delete()
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
    return state.get("step") in (
        "full_name",
        "phone",
        "code",
        "qr",
        "password",
        "admin_new_user_full_name",
        "admin_new_user_phone",
    )


def get_step(uid: int) -> str | None:
    """Hozirgi login qadamini qaytaradi."""
    state = user_states.get(uid, {})
    return state.get("step")
