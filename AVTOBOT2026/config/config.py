"""
Konfiguratsiya — .env faylidan o'qiladi va konstantalar.
Butun loyiha shu fayldan foydalanadi.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# .env faylini loyiha ildizidan yuklash
BASE_DIR = Path(__file__).parent.parent.resolve()
ENV_FILE = BASE_DIR / ".env"
load_dotenv(ENV_FILE)


def _require(name: str) -> str:
    """Majburiy env o'zgaruvchini o'qish."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(
            f"Environment variable '{name}' topilmadi. "
            f".env faylini tekshiring."
        )
    return value


def _int(name: str, default: int | None = None) -> int:
    """Int env o'zgaruvchini o'qish."""
    value = os.getenv(name)
    if value is None or value == "":
        if default is None:
            raise RuntimeError(f"Environment variable '{name}' topilmadi.")
        return default
    try:
        return int(value)
    except ValueError:
        raise RuntimeError(f"'{name}' butun son bo'lishi kerak: {value}")


# ─────────────────────────────────────────────────────────────────────────
# TELEGRAM API
# ─────────────────────────────────────────────────────────────────────────
API_ID: int = _int("API_ID")
API_HASH: str = _require("API_HASH")
BOT_TOKEN: str = _require("BOT_TOKEN")
SUPER_ADMIN: int = _int("ADMIN_ID")

BOT_USERNAME: str = os.getenv("BOT_USERNAME", "avtoelon_el_uzbot").lstrip("@")
ADMIN_CONTACT_PHONE: str = os.getenv("ADMIN_CONTACT_PHONE", "+998938670592")

# ─────────────────────────────────────────────────────────────────────────
# HEALTH SERVER
# ─────────────────────────────────────────────────────────────────────────
HEALTH_HOST: str = os.getenv("HEALTH_HOST", "0.0.0.0")
HEALTH_PORT: int = _int("HEALTH_PORT", 8080)
# Bo'sh bo'lsa — himoyasiz (ochiq tarmoqda to'ldirish tavsiya etiladi!)
# So'rov: /health?token=... yoki Authorization: Bearer <token>
HEALTH_TOKEN: str = os.getenv("HEALTH_TOKEN", "")

# ─────────────────────────────────────────────────────────────────────────
# ISHCHI LIMITLARI
# ─────────────────────────────────────────────────────────────────────────
MAX_CONCURRENT_WORKERS: int = _int("MAX_CONCURRENT_WORKERS", 50)
MAX_CLIENT_POOL: int = _int("MAX_CLIENT_POOL", 50)

# ─────────────────────────────────────────────────────────────────────────
# POSTING SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
MIN_INTERVAL_MIN: int = 5          # minimal interval (5 daqiqa)
SEND_DELAY_S: int = 5              # guruhlar orasidagi pauza (soniya)
POST_SEND_TIMEOUT_S: int = 20      # bitta matnli post timeout (soniya)
PHOTO_SEND_TIMEOUT_S: int = 120    # rasmli post timeout (upload uzoq!)
JITTER_S: int = 300                # tasodifiy qo'shimcha vaqt (5 daqiqagacha)
START_JITTER_S: int = 60           # worker birinchi start (1 daqiqagacha)
MAX_GROUP_FAILS: int = 3           # guruh necha xato qilsa o'chiriladi

# ─────────────────────────────────────────────────────────────────────────
# LOGIN SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
LOGIN_TIMEOUT_S: int = 600         # login jarayoni maksimal (10 daqiqa)
SMS_MAX_ATTEMPTS: int = 3          # SMS kod qayta so'rash limiti
SMS_COOLDOWN_MIN: int = 30         # 3 martadan keyin kutish (30 daqiqa)
CODE_LENGTH: int = 5               # SMS kod uzunligi
MAX_CODE_LENGTH: int = 6           # maksimal kod uzunligi
MAX_WRONG_CODE: int = 5            # xato kod kiritish limiti

# ─────────────────────────────────────────────────────────────────────────
# MUDDAT SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
DEFAULT_DURATION_DAYS: int = 30    # standart muddat (30 kun)
WARN_HOUR_LOCAL: int = 9           # ogohlantirish yuboriladigan soat
EXPIRY_CHECK_INTERVAL_S: int = 3600  # muddat tekshirish (har soat)
JANITOR_INTERVAL_S: int = 60       # stale login tozalash (har daqiqa)

# ─────────────────────────────────────────────────────────────────────────
# RATE LIMIT
# ─────────────────────────────────────────────────────────────────────────
RATE_LIMIT_LOGIN: int = 3          # login urinishlari
RATE_LIMIT_COMMAND: int = 30       # buyruqlar
RATE_LIMIT_MESSAGE: int = 40       # xabarlar
RATE_LIMIT_MODIFY: int = 20        # o'zgartirish amallari
RATE_WINDOW_S: int = 60            # oyna vaqti (60 soniya)

# ─────────────────────────────────────────────────────────────────────────
# FAYL YO'LLARI
# ─────────────────────────────────────────────────────────────────────────
DATA_DIR: Path = BASE_DIR / "data"
MEDIA_DIR: Path = BASE_DIR / "media"
LOGS_DIR: Path = BASE_DIR / "logs"
DB_PATH: Path = DATA_DIR / "avtobot.db"
LOG_FILE: Path = LOGS_DIR / "avtobot.log"

# Papkalarni yaratish
DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────
# BROADCAST (ommaviy xabar)
# ─────────────────────────────────────────────────────────────────────────
BROADCAST_DELAY_S: float = 0.05    # xabarlar orasidagi pauza (flood oldini oladi)

# ─────────────────────────────────────────────────────────────────────────
# MUDDAT TUGMALARI (admin uchun tez tugmalar)
# ─────────────────────────────────────────────────────────────────────────
DURATION_OPTIONS: list[int] = [1, 7, 30, 90]
