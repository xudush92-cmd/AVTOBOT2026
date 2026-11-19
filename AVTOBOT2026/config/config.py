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
# Bir vaqtda ishlaydigan **alohida** (uzun muddatli o'qish) client'lar
# chegarasi — masalan «🔍 Guruhlarni topish» skaneri. Ular posting
# client'idan alohida bo'lgani uchun worker'ni bloklamaydi, lekin
# resurs nazorati uchun chegarasi bor.
MAX_ISOLATED_CLIENTS: int = max(1, _int("MAX_ISOLATED_CLIENTS", 10))

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
MAX_ALBUM_FILES: int = min(10, max(1, _int("MAX_ALBUM_FILES", 4)))
# Video qo'llab-quvvatlanadimi. 0 = video butunlay rad etiladi (faqat surat).
ALLOW_VIDEO_MEDIA: bool = os.getenv("ALLOW_VIDEO_MEDIA", "0") not in {
    "0",
    "false",
    "no",
}
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
# 0 qiymat = cheksiz. Limitlar faqat musbat qiymatda qo'llaniladi, shuning
# uchun paketsiz (eski) foydalanuvchilar hech qanday cheklovga uchramaydi.
PLAN_DEFS: dict[str, dict] = {
    "SINOV": {"label": "🆓 Sinov", "max_groups": 5, "max_posts": 2, "daily_limit": 30},
    "START": {"label": "🥉 START", "max_groups": 20, "max_posts": 10, "daily_limit": 80},
    "PRO": {"label": "🥈 PRO", "max_groups": 60, "max_posts": 0, "daily_limit": 150},
    "BUSINESS": {
        "label": "🥇 BUSINESS",
        "max_groups": 200,
        "max_posts": 0,
        "daily_limit": 400,
    },
}
DEFAULT_PLAN: str = (os.getenv("DEFAULT_PLAN", "") or "").strip().upper()
if DEFAULT_PLAN not in PLAN_DEFS:
    DEFAULT_PLAN = ""  # bo'sh = limitlarsiz (eski xatti-harakat)

# Telegram akkauntini cheklab qo'ymaslik uchun qo'shimcha himoya.
# 0 = o'chirilgan. Soatlar mahalliy (server) vaqtida hisoblanadi.
USER_DAILY_LIMIT_DEFAULT: int = max(0, _int("USER_DAILY_LIMIT_DEFAULT", 0))
ACTIVE_HOURS_DEFAULT: str = (os.getenv("ACTIVE_HOURS_DEFAULT", "") or "").strip()

# ─────────────────────────────────────────────────────────────────────────
# REFERAL MUKOFOTI VA ANTI-FRAUD
# ─────────────────────────────────────────────────────────────────────────
# Har bir FAOL (kriteriyani bosgan) referal uchun referrerga qo'shiladigan kun.
# 0 = bonus kunlari umuman berilmaydi (referal faqat statistika uchun).
REFERRAL_BONUS_DAYS: int = max(0, _int("REFERRAL_BONUS_DAYS", 0))
# Bir oyda beriladigan maksimal bonus kun (firibgarlik ta'sirini cheklash).
REFERRAL_BONUS_MONTHLY_CAP_DAYS: int = max(
    REFERRAL_BONUS_DAYS, _int("REFERRAL_BONUS_MONTHLY_CAP_DAYS", 30)
)
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
# JAMOALAR (TEAMS) — jamoa admini va uning foydalanuvchilari
# ─────────────────────────────────────────────────────────────────────────
# Jamoa admini uchun standart muddat (kun). Super admin alohida belgilaydi.
TEAM_ADMIN_DEFAULT_DAYS: int = max(1, _int("TEAM_ADMIN_DEFAULT_DAYS", 30))
# Jamoadagi minimal foydalanuvchi soni (bitta jamoa kamida shuncha user).
TEAM_MIN_MEMBERS: int = max(1, _int("TEAM_MIN_MEMBERS", 2))
# ─────────────────────────────────────────────────────────────────────────
# MUDDAT CHEGARASI (anti-fraud)
# ─────────────────────────────────────────────────────────────────────────
# Jamoa admini (2-daraja) a'zosiga beradigan MAXIMAL muddat (kun).
# Chegara 0 = cheksiz. Bu chegara foydalanuvchiga beriladigan bir marta
# muddatga qo'yiladi — super admin cheklovsiz, jamoa admini cheklangan.
TEAM_MEMBER_MAX_DAYS: int = max(0, _int("TEAM_MEMBER_MAX_DAYS", 60))
# Super admin beradigan maksial muddat (kun). 0 = cheksiz.
SUPER_ADMIN_MAX_DAYS: int = max(0, _int("SUPER_ADMIN_MAX_DAYS", 0))
# Jamoa adminining sig'imi (0 = cheksiz, faqat super admin belgilaydi).
TEAM_DEFAULT_MAX_USERS: int = max(0, _int("TEAM_DEFAULT_MAX_USERS", 0))
# Ro'yxatdan o'tishda jamoa tanlash uchun maksimal ko'rsatiladigan jamoalar.
TEAM_LIST_PAGE_SIZE: int = max(1, _int("TEAM_LIST_PAGE_SIZE", 10))

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
# TELEGRAM API SOZLAMALARI
# ─────────────────────────────────────────────────────────────────────────
# Telegram Bot API ulanishlari. Standart qiymatlar mos kelmaydi:
#   connection_pool_size = 1  → long-polling connection'i butun botni
#     band qiladi (javoblar "pool timeout" bilan uziladi);
#   read_timeout = 5s        → getUpdates 10 soniya kutsa, timeout beradi
#     va polling loop tez-tez to'xtaydi ("Exception happened while polling").
# Shu sabab ulanishlar kengaytiriladi va timeout'lar oshiriladi.
TELEGRAM_CONNECTION_POOL_SIZE: int = max(
    4, _int("TELEGRAM_CONNECTION_POOL_SIZE", 20)
)
TELEGRAM_READ_TIMEOUT: float = max(
    10.0, float(os.getenv("TELEGRAM_READ_TIMEOUT", "30") or 30)
)
TELEGRAM_WRITE_TIMEOUT: float = max(
    10.0, float(os.getenv("TELEGRAM_WRITE_TIMEOUT", "30") or 30)
)
TELEGRAM_CONNECT_TIMEOUT: float = max(
    5.0, float(os.getenv("TELEGRAM_CONNECT_TIMEOUT", "15") or 15)
)
TELEGRAM_POOL_TIMEOUT: float = max(
    5.0, float(os.getenv("TELEGRAM_POOL_TIMEOUT", "30") or 30)
)
# getUpdates — serverda 10 soniya kutadi, shuning uchun read timeout
# undan uzun bo'lishi kerak.
TELEGRAM_GET_UPDATES_READ_TIMEOUT: float = max(
    20.0, float(os.getenv("TELEGRAM_GET_UPDATES_READ_TIMEOUT", "40") or 40)
)
TELEGRAM_GET_UPDATES_POOL_TIMEOUT: float = max(
    5.0, float(os.getenv("TELEGRAM_GET_UPDATES_POOL_TIMEOUT", "30") or 30)
)


# ─────────────────────────────────────────────────────────────────────────
# GURUHLARNI SKANERLASH TEZLIGI
# ─────────────────────────────────────────────────────────────────────────
# «🔍 Guruhlarni topish» skaneri bir necha yuz guruhni tekshirishi mumkin.
# Har bir guruh uchun alohida RPC (get_permissions) qilinsa — skaner
# juda uzoq davom etadi va foydalanuvchi "kutib qoladi" deb hisoblaydi.
#
# Yechim: huquqlar tekshiruvi **parallel batch**'lar bilan bajariladi.
#   DISCOVER_BATCH_SIZE — bir vaqtda tekshiriladigan guruhlar soni.
#     Katta qiymat tezroq, lekin Telegram FloodWait xavfi oshadi.
#   DISCOVER_BATCH_PAUSE_S — batch'lar orasidagi pauza (soniya).
#     Bu Telegram'ga "odam tezligi" signalini beradi.
#   DISCOVER_PERMISSION_TIMEOUT_S — bitta guruh tekshiruvining limiti.
DISCOVER_BATCH_SIZE: int = max(
    1, min(20, _int("DISCOVER_BATCH_SIZE", 8))
)
DISCOVER_BATCH_PAUSE_S: float = max(
    0.0, min(10.0, float(os.getenv("DISCOVER_BATCH_PAUSE_S", "0.4") or 0.4))
)
DISCOVER_PERMISSION_TIMEOUT_S: float = max(
    5.0, min(60.0, float(os.getenv("DISCOVER_PERMISSION_TIMEOUT_S", "20") or 20))
)
# Progress xabari qancha guruhdan keyin yangilanadi.
DISCOVER_PROGRESS_EVERY: int = max(
    1, min(50, _int("DISCOVER_PROGRESS_EVERY", 10))
)


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
DURATION_OPTIONS: list[int] = [1, 7, 30, 90, 180, 365]


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
