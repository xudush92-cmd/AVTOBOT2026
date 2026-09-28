"""
Yordamchi funksiyalar.

Bu fayldagi funksiyalar loyihaning turli joyida ishlatiladi.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit


# ─────────────────────────────────────────────────────────────────────────
# VAQT YORDAMCHILARI
# ─────────────────────────────────────────────────────────────────────────
def now_utc() -> datetime:
    """Hozirgi vaqt (UTC)."""
    return datetime.now(timezone.utc)


def now_local() -> datetime:
    """Hozirgi vaqt (mahalliy — server vaqti)."""
    return datetime.now()


def iso_now() -> str:
    """Hozirgi vaqtni ISO formatda qaytaradi."""
    return now_utc().strftime("%Y-%m-%d %H:%M:%S")


def calc_expires(days: int) -> str:
    """
    Bugundan {days} kun keyingi sanani ISO formatda qaytaradi.

    Misol:
        calc_expires(30) -> '2026-10-17 14:30:00'
    """
    return (now_utc() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")


def format_expires(expires_iso: str | None) -> str:
    """
    Muddatni o'qishga qulay formatda ko'rsatadi.

    Misol:
        '2026-10-17 14:30:00' -> '2026-10-17 (30 kun)'
    """
    if not expires_iso:
        return "cheksiz"
    try:
        dt = datetime.strptime(expires_iso, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        days = (dt - now_utc()).days
        return f"{expires_iso[:10]} ({max(0, days)} kun)"
    except Exception:
        return expires_iso[:10]


def is_expired(expires_iso: str | None) -> bool:
    """Muddat tugaganmi? (True/False)"""
    if not expires_iso:
        return False  # muddatsiz = cheksiz
    try:
        dt = datetime.strptime(expires_iso, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        return now_utc() >= dt
    except (TypeError, ValueError):
        # Noto'g'ri saqlangan tarif muddati cheklovni chetlab o'tmasin.
        return True


def is_last_day(expires_iso: str | None) -> bool:
    """
    Bugun muddatning OXIRGI kunimi?

    Faqat shu kun True qaytaradi — boshqa kunlarda False.
    """
    if not expires_iso:
        return False
    try:
        dt = datetime.strptime(expires_iso, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
        delta = dt - now_utc()
        # 0 <= delta <= 1 kun bo'lsa — oxirgi kun
        return timedelta(0) <= delta <= timedelta(days=1)
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────
# TEKSHIRUVLAR
# ─────────────────────────────────────────────────────────────────────────
PHONE_RE = re.compile(r"^\+\d{7,15}$")


def is_valid_phone(phone: str) -> bool:
    """
    Telefon raqamni tekshiradi.

    Format: +998XXXXXXXXX (7 dan 15 gacha raqam)
    """
    if not phone:
        return False
    phone = phone.strip().replace(" ", "").replace("-", "")
    return bool(PHONE_RE.match(phone))


def is_valid_interval(value: int) -> bool:
    """Posting oralig'ini xavfsiz diapazonda tekshiradi."""
    from config.config import MAX_INTERVAL_MIN, MIN_INTERVAL_MIN

    return MIN_INTERVAL_MIN <= value <= MAX_INTERVAL_MIN


def _valid_name_part(part: str) -> bool:
    letters = [char for char in part if char.isalpha()]
    return len(letters) >= 2 and all(
        char.isalpha() or char in "-'’ʻʼ`" for char in part
    )


def is_valid_name(name: str) -> bool:
    """Bitta ism qismini tekshiradi: faqat harf, apostrof va defis."""
    if not name:
        return False
    value = name.strip()
    return 2 <= len(value) <= 64 and _valid_name_part(value)


def is_valid_full_name(name: str) -> bool:
    """Ism va familiya bitta xabarda, kamida ikki to'g'ri qism bo'lishi kerak."""
    if not name:
        return False
    value = " ".join(name.strip().split())
    parts = value.split()
    return (
        3 <= len(value) <= 64
        and len(parts) >= 2
        and all(_valid_name_part(part) for part in parts)
    )


# ─────────────────────────────────────────────────────────────────────────
# TELEGRAM GURUH HAVOLASINI TOZALASH
# ─────────────────────────────────────────────────────────────────────────
_TELEGRAM_HOSTS = {
    "t.me",
    "www.t.me",
    "telegram.me",
    "www.telegram.me",
    "telegram.dog",
    "www.telegram.dog",
}
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,32}$")
_MARKDOWN_LINK_RE = re.compile(r"^\[[^\]]*\]\(([^\s)]+)\)$")


def normalize_group_reference(value: str) -> str:
    """Telegram public/private havolasini saqlash uchun barqaror ko'rinishga keltiradi.

    Public linklar ``@username`` ga, public/private post linklari esa guruhning
    o'ziga aylantiriladi. Private invite avtomatik join qilinmaydi; tekshiruvchi
    akkaunt avvaldan a'zo ekanini alohida tekshiradi.
    """
    if not value:
        return ""

    cleaned = value.strip().replace("\u200b", "")
    markdown = _MARKDOWN_LINK_RE.fullmatch(cleaned)
    if markdown:
        cleaned = markdown.group(1)
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()
    cleaned = cleaned.rstrip(".,;")

    if cleaned.startswith("@"):
        username = cleaned[1:].strip().rstrip("/")
        return f"@{username}" if _USERNAME_RE.fullmatch(username) else cleaned

    if cleaned.lstrip("-").isdigit():
        return str(int(cleaned))

    lowered = cleaned.lower()
    if any(lowered.startswith(f"{host}/") for host in _TELEGRAM_HOSTS):
        cleaned = f"https://{cleaned}"

    parsed = urlsplit(cleaned)
    if parsed.scheme.lower() == "tg":
        query = parse_qs(parsed.query)
        if parsed.netloc.lower() == "resolve":
            username = (query.get("domain") or [""])[0].lstrip("@")
            return f"@{username}" if _USERNAME_RE.fullmatch(username) else cleaned
        if parsed.netloc.lower() == "join":
            invite = (query.get("invite") or [""])[0]
            return f"https://t.me/+{invite}" if invite else cleaned
        return cleaned

    if parsed.scheme.lower() not in {"http", "https"}:
        if _USERNAME_RE.fullmatch(cleaned):
            return f"@{cleaned}"
        return cleaned
    if (parsed.hostname or "").lower() not in _TELEGRAM_HOSTS:
        return cleaned

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return cleaned
    if parts[0].lower() == "s" and len(parts) > 1:
        parts = parts[1:]

    first = parts[0]
    if first.lower() == "joinchat" and len(parts) > 1:
        return f"https://t.me/+{parts[1]}"
    if first.startswith("+") and len(first) > 1:
        return f"https://t.me/{first}"
    if first.lower() == "c" and len(parts) > 1 and parts[1].isdigit():
        return f"-100{parts[1]}"

    username = first.lstrip("@")
    return f"@{username}" if _USERNAME_RE.fullmatch(username) else cleaned


def group_reference_key(value: str) -> str:
    """Equivalent public username/linklar uchun dedupe kalitini qaytaradi.

    Telegram username'lari katta-kichik harfga bog'liq emas, invite hash esa
    case-sensitive. Shu sababli faqat ``@username`` canonical qiymati casefold
    qilinadi.
    """
    canonical = normalize_group_reference(value)
    return canonical.casefold() if canonical.startswith("@") else canonical


def clean_group_value(value: str) -> str:
    """Guruh username, link, invite yoki ID qiymatini normalizatsiya qiladi."""
    return normalize_group_reference(value)


def parse_group_lines(text: str) -> list[str]:
    """Yangi qator/verguldagi guruhlarni ajratadi va format bo'yicha dedupe qiladi."""
    if not text:
        return []
    lines = text.replace(",", "\n").split("\n")
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = clean_group_value(line)
        if not cleaned:
            continue
        dedupe_key = group_reference_key(cleaned)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        result.append(cleaned)
    return result


# ─────────────────────────────────────────────────────────────────────────
# XAVFSIZ FAYL O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
def safe_unlink(path: str | None) -> None:
    """Faylni xavfsiz o'chirish (xato bersa ham davom etadi)."""
    if not path:
        return
    import contextlib
    import os

    with contextlib.suppress(Exception):
        if os.path.exists(path):
            os.remove(path)


def wipe_directory(path: str) -> None:
    """Papkani butunlay o'chirish (xato bersa ham davom etadi)."""
    if not path:
        return
    import contextlib
    import os
    import shutil

    with contextlib.suppress(Exception):
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)


# ─────────────────────────────────────────────────────────────────────────
# DAVRIY TOZALASH (JANITOR UCHUN)
# ─────────────────────────────────────────────────────────────────────────
def prune_orphan_media(valid_uids: set[int]) -> int:
    """
    Bazada yo'q foydalanuvchilarning media (rasm) papkalarini o'chiradi.

    Foydalanuvchi o'chirilganda papka darhol tozalanadi; bu funksiya
    kutilmagan to'xtash yoki eski nusxadan qolgan yetim papkalarni
    yig'ishtirib oladi.

    Returns:
        O'chirilgan papkalar soni
    """
    import os

    from config.config import MEDIA_DIR

    try:
        entries = os.listdir(MEDIA_DIR)
    except OSError:
        return 0

    removed = 0
    for name in entries:
        if not name.isdigit():
            continue
        if int(name) in valid_uids:
            continue
        wipe_directory(str(MEDIA_DIR / name))
        removed += 1
    return removed


def prune_old_backups(keep: int, min_age_s: int = 3600) -> int:
    """
    Eski zaxira nusxalarni o'chiradi, oxirgi {keep} tasini qoldiradi.

    Faqat {min_age_s} soniyadan eski fayllar o'chiriladi — shu bilan hozir
    yaratilayotgan eksport/backup fayliga tegib ketish xavfi bo'lmaydi.

    Returns:
        O'chirilgan fayllar soni
    """
    import os
    import time

    from config.config import BACKUP_DIR

    keep = max(0, keep)
    cutoff = time.time() - max(0, min_age_s)
    removed = 0

    for pattern in ("avtobot_backup_*.db", "avtobot_sanitized_*.db"):
        try:
            files = sorted(
                BACKUP_DIR.glob(pattern),
                key=os.path.getmtime,
                reverse=True,
            )
        except OSError:
            continue
        for path in files[keep:]:
            try:
                if os.path.getmtime(path) > cutoff:
                    continue
            except OSError:
                continue
            safe_unlink(str(path))
            removed += 1
    return removed


# ─────────────────────────────────────────────────────────────────────────
# MATN QISQARTIRISH
# ─────────────────────────────────────────────────────────────────────────
def truncate(text: str, max_len: int = 60) -> str:
    """
    Matnni qisqartiradi.

    Misol:
        truncate("Juda uzun matn...", 20) -> "Juda uzun matn..."
    """
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."
