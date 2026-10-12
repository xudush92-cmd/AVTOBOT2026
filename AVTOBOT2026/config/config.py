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
            f"Environment variable '{name}' topilmadi. .env faylini tekshiring."
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

# ─────────────────────────────────────────────────────────────────────────
# ISHCHI LIMITLARI
# ─────────────────────────────────────────────────────────────────────────
MAX_CONCURRENT_WORKERS: int = _int("MAX_CONCURRENT_WORKERS", 50)
MAX_CLIENT_POOL: int = _int("MAX_CLIENT_POOL", 50)

# ─────────────────────────────────────────────────────────────────────────
# MAXFIY SESSIYALAR / BACKUP
# ─────────────────────────────────────────────────────────────────────────
SESSION_ENCRYPTION_KEY: str = os.getenv("SESSION_ENCRYPTION_KEY", "")
BACKUP_RETENTION: int = max(1, _int("BACKUP_RETENTION", 7))

# ─────────────────────────────────────────────────────────────────────────
# POSTING SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
MIN_INTERVAL_MIN: int = max(1, _int("MIN_INTERVAL_MIN", 5))  # minimal interval (daqiqa)
MAX_INTERVAL_MIN: int = _int("MAX_INTERVAL_MIN", 10080)  # maksimal interval (7 kun)
# Birinchi marta tasdiqlangan user oladigan standart posting oralig'i.
# Har doim MIN/MAX oraliqqa clamp qilinadi.
DEFAULT_INTERVAL_MIN: int = min(
    MAX_INTERVAL_MIN,
    max(MIN_INTERVAL_MIN, _int("DEFAULT_INTERVAL_MIN", 60)),
)
SEND_DELAY_S: int = 5  # guruhlar orasidagi pauza (soniya)
JITTER_S: int = 300  # tasodifiy qo'shimcha vaqt (5 daqiqagacha)
START_JITTER_S: int = 60  # worker birinchi start (1 daqiqagacha)
MAX_GROUP_FAILS: int = 3  # guruh necha xato qilsa o'chiriladi

# ─────────────────────────────────────────────────────────────────────────
# MEDIA (POST SURATLARI / VIDEO)
# ─────────────────────────────────────────────────────────────────────────
# Bitta postga qo'shiladigan fayllar soni (Telegram albom limiti = 10).
MAX_ALBUM_FILES: int = min(10, max(1, _int("MAX_ALBUM_FILES", 10)))
# Bot API orqali yuklab olinadigan bitta faylning maksimal hajmi.
MAX_MEDIA_BYTES: int = max(1024 * 1024, _int("MAX_MEDIA_BYTES", 20 * 1024 * 1024))
# Bir nechta media qatorlarini albom sifatida yig'ib olish uchun kutish.
ALBUM_DEBOUNCE_S: float = float(os.getenv("ALBUM_DEBOUNCE_S", "1.5") or 1.5)
# Bitta foydalanuvchidagi jami media fayllar limiti (diskni himoyalash).
MAX_MEDIA_FILES_PER_USER: int = max(10, _int("MAX_MEDIA_FILES_PER_USER", 200))

# ─────────────────────────────────────────────────────────────────────────
# YUBORISH STATISTIKASI
# ─────────────────────────────────────────────────────────────────────────
# Har bir yuborish send_logs jadvaliga yoziladi; eski yozuvlar tozalanadi.
SEND_LOGS_ENABLED: bool = os.getenv("SEND_LOGS_ENABLED", "1") not in {
    "0",
    "false",
    "no",
}
SEND_LOG_RETENTION_DAYS: int = max(1, _int("SEND_LOG_RETENTION_DAYS", 30))

# ─────────────────────────────────────────────────────────────────────────
# TARIF PAKETLARI VA LIMITLAR
# ─────────────────────────────────────────────────────────────────────────
# Yagona oylik tarif (SINOV/START/PRO/BUSINESS olib tashlangan). Cheklovlar yo'q:
# 0 = cheksiz (guruh, post, kunlik yuborish). Admin individual limit qo'yishi mumkin.
PLAN_DEFS: dict[str, dict] = {
    "OYLIK": {"label": "💳 Oylik obuna", "max_groups": 0, "max_posts": 0, "daily_limit": 0},
}
DEFAULT_PLAN: str = "OYLIK"

# Telegram akkauntini cheklab qo'ymaslik uchun qo'shimcha himoya.
# 0 = o'chirilgan. Soatlar mahalliy (server) vaqtida hisoblanadi.
USER_DAILY_LIMIT_DEFAULT: int = 0  # cheklov yo'q (yagona oylik tarif)
ACTIVE_HOURS_DEFAULT: str = (os.getenv("ACTIVE_HOURS_DEFAULT", "") or "").strip()

# ─────────────────────────────────────────────────────────────────────────
# REFERAL MUKOFOTI VA ANTI-FRAUD
# ─────────────────────────────────────────────────────────────────────────
# Har bir FAOL (kriteriyani bosgan) do'st uchun referrerga qo'shiladigan kun.
# Har bir do'st uchun bir marta beriladi; do'stlar soniga cheklov yo'q.
REFERRAL_BONUS_DAYS: int = max(0, _int("REFERRAL_BONUS_DAYS", 15))
# Oylik maksimal bonus kun. 0 = cheklovsiz (standart).
REFERRAL_BONUS_MONTHLY_CAP_DAYS: int = max(0, _int("REFERRAL_BONUS_MONTHLY_CAP_DAYS", 0))
# Mukofot uchun referal kamida shuncha marta muvaffaqiyatli post yuborishi kerak.
REFERRAL_QUALIFY_MIN_SENDS: int = max(1, _int("REFERRAL_QUALIFY_MIN_SENDS", 1))
# Kunlik shunchadan ortiq referal → anomaliya deb adminga xabar.
REFERRAL_DAILY_ALERT: int = max(1, _int("REFERRAL_DAILY_ALERT", 10))

# ─────────────────────────────────────────────────────────────────────────
# TEZ TASDIQLASH (AUTO-APPROVE)
# ─────────────────────────────────────────────────────────────────────────
# O'chirilgan holatda admin tasdig'i kutiladi (eski xatti-harakat).
AUTO_APPROVE_ENABLED: bool = os.getenv("AUTO_APPROVE_ENABLED", "0") not in {
    "0",
    "false",
    "no",
}
# Shu ball yoki undan past risk avto-tasdiqlanadi (0 = o'chirilgan filtr).
AUTO_APPROVE_MAX_RISK: int = max(0, _int("AUTO_APPROVE_MAX_RISK", 2))
AUTO_APPROVE_CHECK_INTERVAL_S: int = max(
    15, _int("AUTO_APPROVE_CHECK_INTERVAL_S", 60)
)
AUTO_APPROVE_BATCH: int = max(1, _int("AUTO_APPROVE_BATCH", 5))

# ─────────────────────────────────────────────────────────────────────────
# TO'LOV (A REJA: QO'LDA TASDIQLASH + KVITANSIYA)
# ─────────────────────────────────────────────────────────────────────────
# O'chirilgan holatda (standart) 💳 tugmalari ko'rinmaydi va hech narsa
# o'zgarmaydi. Yoqish uchun PAYMENTS_ENABLED=1 va MONTHLY_PRICE to'ldiriladi.
PAYMENTS_ENABLED: bool = os.getenv("PAYMENTS_ENABLED", "0") not in {
    "0",
    "false",
    "no",
    "",
}


# Oylik obuna narxi (so'm). 0 yoki bo'sh = to'lov tugmalari ko'rinmaydi.
MONTHLY_PRICE: int = max(0, _int("MONTHLY_PRICE", 0))
PLAN_PRICES: dict[str, int] = {"OYLIK": MONTHLY_PRICE} if MONTHLY_PRICE > 0 else {}
# Karta rekvizitlari (kvitansiya shu kartaga yuboriladi)
PAY_CARD: str = (os.getenv("PAY_CARD", "") or "").strip()
PAY_BANK: str = (os.getenv("PAY_BANK", "") or "").strip()
PAY_HOLDER: str = (os.getenv("PAY_HOLDER", "") or "").strip()
# Bir to'lov necha kunga uzaytiradi
PAYMENT_DAYS: int = max(1, _int("PAYMENT_DAYS", 30))
# Kvitansiya yuborilmagan so'rov shundan keyin bekor (expired) bo'ladi
PAYMENT_REQUEST_TTL_MIN: int = max(5, _int("PAYMENT_REQUEST_TTL_MIN", 120))
# Muddat tugashidan necha kun oldin bir marta eslatma yuborilsin
PAYMENT_REMIND_DAYS: int = max(0, _int("PAYMENT_REMIND_DAYS", 3))
# Kvitansiya rasmi qaror qabul qilingach shuncha kun saqlanadi, so'ng o'chadi
PAYMENT_PROOF_RETENTION_DAYS: int = max(1, _int("PAYMENT_PROOF_RETENTION_DAYS", 14))
# Kutayotgan (kvitansiyali) so'rovlar shuncha bo'lsa adminga ogohlantirish
PAYMENT_QUEUE_ALERT: int = max(1, _int("PAYMENT_QUEUE_ALERT", 10))
# Izoh kodi boshlanishi: AVTO-<uid>-<PAKET>
PAY_REF_PREFIX: str = (os.getenv("PAY_REF_PREFIX", "AVTO") or "AVTO").strip().upper()



# ─────────────────────────────────────────────────────────────────────────
# LOGIN SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
LOGIN_TIMEOUT_S: int = 300  # login jarayoni maksimal (5 daqiqa)
SMS_MAX_ATTEMPTS: int = 1  # muddati o'tgan kodni faqat 1 marta qayta so'rash
SMS_COOLDOWN_MIN: int = 30  # keyingi qayta so'rovgacha kutish
CODE_LENGTH: int = 5  # SMS kod uzunligi
MAX_CODE_LENGTH: int = 6  # maksimal kod uzunligi
MAX_WRONG_CODE: int = 5  # xato kod kiritish limiti

# ─────────────────────────────────────────────────────────────────────────
# MUDDAT SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
DEFAULT_DURATION_DAYS: int = max(1, _int("DEFAULT_DURATION_DAYS", 30))
EXPIRY_CHECK_INTERVAL_S: int = max(30, _int("EXPIRY_CHECK_INTERVAL_S", 60))
JANITOR_INTERVAL_S: int = 60  # stale login tozalash (har daqiqa)
# Davriy tozalash: yetim media, eski backup, WAL/statistika (standart 30 daqiqa)
CLEANUP_INTERVAL_S: int = max(300, _int("CLEANUP_INTERVAL_S", 1800))

# ─────────────────────────────────────────────────────────────────────────
# RATE LIMIT
# ─────────────────────────────────────────────────────────────────────────
RATE_LIMIT_LOGIN: int = 3  # login urinishlari (UID bo'yicha)
RATE_LIMIT_PHONE_CODE: int = 3  # bitta telefon uchun kod so'rovlari
RATE_LIMIT_PHONE_CODE_WINDOW_S: int = 3600  # telefon kod limiti oynasi (1 soat)
RATE_LIMIT_COMMAND: int = 30  # buyruqlar
RATE_LIMIT_MESSAGE: int = 40  # xabarlar
RATE_LIMIT_MODIFY: int = 20  # o'zgartirish amallari
RATE_WINDOW_S: int = 60  # oddiy amallar oynasi (60 soniya)
RATE_LIMIT_LOGIN_WINDOW_S: int = 3600  # login: 3 marta / 1 soat

# ─────────────────────────────────────────────────────────────────────────
# FAYL YO'LLARI
# ─────────────────────────────────────────────────────────────────────────
DATA_DIR: Path = BASE_DIR / "data"
MEDIA_DIR: Path = BASE_DIR / "media"
LOGS_DIR: Path = BASE_DIR / "logs"
DB_PATH: Path = DATA_DIR / "avtobot.db"
LOG_FILE: Path = LOGS_DIR / "avtobot.log"
_backup_dir_value = Path(os.getenv("BACKUP_DIR", "backups")).expanduser()
BACKUP_DIR: Path = (
    _backup_dir_value
    if _backup_dir_value.is_absolute()
    else BASE_DIR / _backup_dir_value
)

# Papkalarni yaratish
DATA_DIR.mkdir(exist_ok=True)
MEDIA_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(parents=True, exist_ok=True)

# ─────────────────────────────────────────────────────────────────────────
# MUDDAT TUGMALARI (admin uchun tez tugmalar)
# ─────────────────────────────────────────────────────────────────────────
DURATION_OPTIONS: list[int] = [1, 7, 30, 90]


# ─────────────────────────────────────────────────────────────────────────
# PAKET YORDAMCHILARI
# ─────────────────────────────────────────────────────────────────────────
UNLIMITED = 0  # 0 = cheksiz


def plan_limits(plan: str | None) -> dict:
    """Paket nomi bo'yicha limitlar. Noma'lum/bo'sh paket = cheksiz.

    0 qiymat cheksiz degani — shuning uchun paketsiz (eski) foydalanuvchilar
    hech qanday cheklovga uchramaydi.
    """
    key = (plan or "").strip().upper()
    definition = PLAN_DEFS.get(key)
    if not definition:
        return {
            "plan": "",
            "label": "📦 Limitlarsiz",
            "max_groups": UNLIMITED,
            "max_posts": UNLIMITED,
            "daily_limit": USER_DAILY_LIMIT_DEFAULT,
        }
    return {
        "plan": key,
        "label": definition["label"],
        "max_groups": int(definition.get("max_groups", UNLIMITED)),
        "max_posts": int(definition.get("max_posts", UNLIMITED)),
        "daily_limit": int(definition.get("daily_limit", USER_DAILY_LIMIT_DEFAULT)),
    }


def format_plan_price() -> str:
    """Admin/yordam matnida ishlatiladigan paketlar ro'yxati."""
    lines = []
    for name, definition in PLAN_DEFS.items():
        groups = definition["max_groups"] or "∞"
        posts = definition["max_posts"] or "∞"
        daily = definition["daily_limit"] or "∞"
        lines.append(
            f"{definition['label']}: 💬 {groups} guruh · 📝 {posts} post · "
            f"📤 kuniga {daily}"
        )
    return "\n".join(lines)
