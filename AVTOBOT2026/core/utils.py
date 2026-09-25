"""
Yordamchi funksiyalar.

Bu fayldagi funksiyalar loyihaning turli joyida ishlatiladi.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


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
# GURUH NOMINI TOZALASH
# ─────────────────────────────────────────────────────────────────────────
def clean_group_value(value: str) -> str:
    """
    Guruh qiymatini tozalaydi.

    Misol:
        ' @guruh1 ' -> '@guruh1'
        'https://t.me/guruh2\n' -> 'https://t.me/guruh2'
    """
    if not value:
        return ""
    return value.strip()


def parse_group_lines(text: str) -> list[str]:
    """
    Ko'p qatorli matndan guruhlar ro'yxatini ajratadi.

    Misol:
        '@guruh1\\n@guruh2\\n\\n@guruh3' -> ['@guruh1', '@guruh2', '@guruh3']
    """
    if not text:
        return []
    lines = text.replace(",", "\n").split("\n")
    result: list[str] = []
    seen: set[str] = set()
    for line in lines:
        cleaned = clean_group_value(line)
        if not cleaned:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
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
