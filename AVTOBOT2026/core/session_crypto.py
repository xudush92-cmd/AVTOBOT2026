"""Telethon StringSession qiymatlarini DB ichida shifrlash.

Kalit ``SESSION_ENCRYPTION_KEY`` orqali berilishi mumkin. U berilmasa,
``data/.session.key`` fayli bir marta xavfsiz yaratiladi. Kalitni DB bilan
birga Telegram chatiga yoki Git'ga joylash mumkin emas.
"""

from __future__ import annotations

import contextlib
import os

from cryptography.fernet import Fernet, InvalidToken

from config.config import DATA_DIR, SESSION_ENCRYPTION_KEY

_PREFIX = "enc:v1:"
_KEY_FILE = DATA_DIR / ".session.key"
_fernet: Fernet | None = None


def _load_or_create_key() -> bytes:
    configured = SESSION_ENCRYPTION_KEY.strip()
    if configured:
        return configured.encode("ascii")

    try:
        key = _KEY_FILE.read_bytes().strip()
        with contextlib.suppress(OSError):
            os.chmod(_KEY_FILE, 0o600)
        return key
    except FileNotFoundError:
        pass

    key = Fernet.generate_key()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(_KEY_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        with contextlib.suppress(OSError):
            os.chmod(_KEY_FILE, 0o600)
        return _KEY_FILE.read_bytes().strip()

    with os.fdopen(fd, "wb") as handle:
        handle.write(key + b"\n")
    return key


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_key())
    return _fernet


def ensure_session_cipher() -> None:
    """Startup paytida kalit mavjud va Fernet formatida ekanini tekshiradi."""
    _cipher()


def is_encrypted(value: str | None) -> bool:
    return bool(value and value.startswith(_PREFIX))


def encrypt_session(value: str | None) -> str:
    """StringSession'ni shifrlaydi; bo'sh va oldindan shifrlangan qiymat xavfsiz."""
    if not value:
        return ""
    if is_encrypted(value):
        return value
    token = _cipher().encrypt(value.encode("utf-8")).decode("ascii")
    return _PREFIX + token


def decrypt_session(value: str | None) -> str:
    """DB qiymatini ochadi; eski plaintext sessiyalar migratsiya uchun o'qiladi."""
    if not value:
        return ""
    if not is_encrypted(value):
        return value
    token = value[len(_PREFIX) :]
    try:
        return _cipher().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise RuntimeError(
            "Telegram sessiyasini ochib bo'lmadi. SESSION_ENCRYPTION_KEY "
            "yoki data/.session.key faylini tekshiring."
        ) from exc
