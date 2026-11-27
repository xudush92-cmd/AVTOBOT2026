"""
Markaziy xato va kamchilik yozuvchisi.

Vazifa: foydalanuvchi tugma bosganda (yoki matn yuborganda) xatolik yuz
bersa — **kim**, **qaysi tugma/bosqich**, **qanday xato** va **to'liq
traceback** bitta joyda yoziladi.

Nima uchun alohida modul:
- Barcha handler'lar bir xil formatda yozadi — logda «qaysi tugma
  xato berdi» degan savolga bir qarashda javob topiladi;
- «Kamchilik» (xato emas, lekin kutilgan natija chiqmedi — masalan
  bo'sh ro'yxat, topilmagan foydalanuvchi, bekor qilingan amal) ham
  yoziladi — ``warning`` darajasida;
- Traceback har doim bir xil ko'rinishda saqlanadi.

Muhim: kamchilik yozuvi **faqat gapsiz natija** holatlariga qo'yiladi.
Normal oqimga (muvaffaqiyatli tugma bosish) yozilmaydi — aks holda log
shovqin bilan to'ladi va haqiqiy xatolar yashirinib qoladi.

Foydalanish:
    from core.errlog import log_error, log_gap, log_event

    log_error(uid, "Jamoa statistikasi", exc, action="tadm:stats")
    log_gap(uid, "Foydalanuvchi topilmadi", action="tadm:member:123")
"""

from __future__ import annotations

import contextlib
import re
import traceback

from core.logger import log

# ─────────────────────────────────────────────────────────────────────────
# KONSTANTA MATNLAR
# ─────────────────────────────────────────────────────────────────────────
SEP = " │ "

# ─────────────────────────────────────────────────────────────────────────
# MAXFIY MA'LUMOT REDAKSIYASI
# ─────────────────────────────────────────────────────────────────────────
# Foydalanuvchi maxfiy ma'lumot kiritadigan bosqichlar. Bu bosqichlarda
# kiritilgan matn (2FA parol, Telegram tasdiqlash kodi, telefon raqam)
# logga yozilmasligi kerak.
SECRET_STEPS = frozenset({"password", "code", "phone", "full_name"})

# Redaksiya qilinadigan kalitlar (kichik harf bilan).
_SECRET_KEYS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "code",
    "token",
    "session",
    "phone",
    "hash",
    "auth_key",
)

# ``key=value`` ko'rinishidagi maxfiy qiymatlar.
_KV_RE = re.compile(
    r"(?i)\b(" + "|".join(_SECRET_KEYS) + r")\b\s*[:=]\s*"
    r"(\"[^\"]*\"|'[^']*'|[^\s,;}\]]+)"
)


def redact(text: str | None) -> str:
    """Matndagi maxfiy qiymatlarni yopadi.

    ``"password=secret"`` → ``"password=***"``

    Maqsad: log faylida foydalanuvchining paroli yoki kodi **hali ham
    ko'rinmasligi** kerak — hatto keyinchalik tekshirilganda ham.
    """
    if not text:
        return ""
    return _KV_RE.sub(lambda m: f"{m.group(1)}=***", text)


def redact_exc(exc: BaseException) -> str:
    """Xatoning matnini redaksiya qilib beradi.

    Xato matni maxfiy qiymatni o'z ichiga olishi mumkin
    (masalan, Telethon ``PhoneCodeInvalidError`` xabari).
    """
    try:
        return redact(str(exc))
    except Exception:  # noqa: BLE001 — redaksiya hech qachon xato bermasligi kerak
        return f"<{type(exc).__name__}>"


def _fmt(uid: int | None, action: str | None, extra: str | None) -> str:
    """Log sarlavhasini yig'adi: kim │ nima │ qo'shimcha."""
    parts: list[str] = []
    parts.append(f"uid={uid}" if uid else "uid=?")
    if action:
        parts.append(f"action={redact(action)}")
    if extra:
        parts.append(redact(extra))
    return SEP.join(parts)


def _tb(exc: BaseException) -> str:
    """To'liq traceback (redaksiya qilingan holda).

    Traceback manba kodini o'z ichiga oladi — u ichida maxfiy qiymat
    bo'lsa (masalan, xato matnida parol), u ham yopilishi kerak.
    """
    try:
        raw = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        ).rstrip()
    except Exception:  # noqa: BLE001 — traceback formati hech qachon xato bermasligi kerak
        return f"<traceback {type(exc).__name__}>"
    return redact(raw)


# ─────────────────────────────────────────────────────────────────────────
# ASOSIY YOZUVCHILAR
# ─────────────────────────────────────────────────────────────────────────
def log_error(
    uid: int | None,
    context: str,
    exc: BaseException,
    *,
    action: str | None = None,
    extra: str | None = None,
) -> None:
    """Xatoni (to'liq traceback bilan) yozadi.

    ``context`` — xato qayerda bo'lganini qisqa aytadi
    (masalan: «Jamoa statistikasi»).

    Log yozish o'zi xato bersa — bot ishlashda davom etsin
    (yozuvchi hech qachan asosiy oqimni to'xtatmasligi kerak).

    ⚠️ **Maxfiylik:** xato matni va sarlavha redaksiyadan o'tadi —
    foydalanuvchining paroli yoki kodi logga tushmaydi.
    """
    try:
        head = _fmt(uid, action, extra)
        log(
            f"💥 XATO: {redact(context)} │ {head} │ "
            f"{type(exc).__name__}: {redact_exc(exc)}\n{_tb(exc)}",
            "error",
        )
    except Exception:  # noqa: BLE001 — yozuvchi hech qachon xato bermasligi kerak
        with contextlib.suppress(Exception):
            log(f"💥 XATO (batafsil yozib bo'lmadi): {redact(context)}", "error")


def log_gap(
    uid: int | None,
    reason: str,
    *,
    action: str | None = None,
    extra: str | None = None,
) -> None:
    """Kamchilikni yozadi — xato emas, lekin kutilgan natija chiqmedi.

    Masalan:
    - foydalanuvchi topilmadi yoki boshqa jamoaga tegishli;
    - bo'sh ro'yxat ko'rsatildi;
    - eskirgan oyna (state) bilan tugma bosildi;
    - bekor qilingan amal.
    """
    try:
        head = _fmt(uid, action, extra)
        log(f"⚠️ KAMCHILIK: {redact(reason)} │ {head}", "warning")
    except Exception:  # noqa: BLE001
        pass


def log_event(
    uid: int | None,
    event: str,
    *,
    action: str | None = None,
    extra: str | None = None,
) -> None:
    """Muhim, lekin xato emas — oddiy voqeani yozadi (INFO daraja)."""
    try:
        head = _fmt(uid, action, extra)
        log(f"ℹ️ {redact(event)} │ {head}", "info")
    except Exception:  # noqa: BLE001
        pass
