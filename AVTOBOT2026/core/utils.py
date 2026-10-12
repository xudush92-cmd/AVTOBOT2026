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
_INVITE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_NUMBER_RE = re.compile(r"^[0-9]+$")
_MARKDOWN_LINK_RE = re.compile(r"^\[[^\]]*\]\(([^\s)]+)\)$")


def _positive_number(value: str) -> bool:
    return bool(len(value) <= 20 and _NUMBER_RE.fullmatch(value) and int(value) > 0)


def normalize_group_reference(value: str) -> str:
    """Faqat to'g'ri formatdagi guruh havolasini canonical ko'rinishga keltiradi.

    Public/post linklar ``@username`` ga, ``t.me/c`` post linklari ``-100...``
    ID'ga, private invite esa ``https://t.me/+hash`` ga aylanadi. Bu funksiya
    Telegram'ga ulanmaydi: mavjudlik, a'zolik va yozish huquqi postingda bilinadi.
    Noto'g'ri format uchun bo'sh satr qaytaradi.
    """
    if not isinstance(value, str) or not value:
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
        return f"@{username}" if _USERNAME_RE.fullmatch(username) else ""

    digits = cleaned.lstrip("-")
    if len(digits) <= 20 and _NUMBER_RE.fullmatch(digits) and cleaned.count("-") <= 1:
        number = int(cleaned)
        return str(number) if number else ""

    lowered = cleaned.lower()
    if any(lowered.startswith(f"{host}/") for host in _TELEGRAM_HOSTS):
        cleaned = f"https://{cleaned}"

    try:
        parsed = urlsplit(cleaned)
        # Noto'g'ri port yoki qavsli hostname formatini ham qabul qilmaymiz.
        if parsed.port not in (None, 80, 443):
            return ""
    except ValueError:
        return ""
    if parsed.scheme.lower() == "tg":
        if parsed.path not in {"", "/"} or parsed.fragment:
            return ""
        query = parse_qs(parsed.query)
        if parsed.netloc.lower() == "resolve":
            username = (query.get("domain") or [""])[0].lstrip("@")
            post = (query.get("post") or [""])[0]
            if post and not _positive_number(post):
                return ""
            return f"@{username}" if _USERNAME_RE.fullmatch(username) else ""
        if parsed.netloc.lower() == "join":
            invite = (query.get("invite") or [""])[0]
            return f"https://t.me/+{invite}" if _INVITE_RE.fullmatch(invite) else ""
        return ""

    if parsed.scheme.lower() not in {"http", "https"}:
        return f"@{cleaned}" if _USERNAME_RE.fullmatch(cleaned) else ""
    if (
        (parsed.hostname or "").lower() not in _TELEGRAM_HOSTS
        or parsed.username is not None
        or parsed.password is not None
    ):
        return ""

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return ""
    if parts[0].lower() == "s":
        parts = parts[1:]
    if not parts:
        return ""

    first = parts[0]
    if first.lower() == "joinchat":
        return (
            f"https://t.me/+{parts[1]}"
            if len(parts) == 2 and _INVITE_RE.fullmatch(parts[1])
            else ""
        )
    if first.startswith("+"):
        return (
            f"https://t.me/{first}"
            if len(parts) == 1 and _INVITE_RE.fullmatch(first[1:])
            else ""
        )
    if first.lower() == "c":
        if (
            len(parts) in {2, 3}
            and _positive_number(parts[1])
            and (len(parts) == 2 or _positive_number(parts[2]))
        ):
            return f"-100{int(parts[1])}"
        return ""

    username = first.lstrip("@")
    if len(parts) > 2 or (len(parts) == 2 and not _positive_number(parts[1])):
        return ""
    return f"@{username}" if _USERNAME_RE.fullmatch(username) else ""


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


def parse_group_lines_with_errors(text: str) -> tuple[list[str], list[str]]:
    """Guruhlarni canonical ko'rinishga keltiradi, noto'g'ri qatorlarni ajratadi."""
    result: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for line in (text or "").replace(",", "\n").splitlines():
        raw = line.strip()
        if not raw:
            continue
        canonical = normalize_group_reference(raw)
        if not canonical:
            invalid.append(raw)
            continue
        key = group_reference_key(canonical)
        if key not in seen:
            seen.add(key)
            result.append(canonical)
    return result, invalid


def parse_group_lines(text: str) -> list[str]:
    """Yangi qator/verguldagi to'g'ri guruhlarni canonical, dedupe qilib oladi."""
    return parse_group_lines_with_errors(text)[0]


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


# ─────────────────────────────────────────────────────────────────────────
# YUBORISH OYNASI (TUNGI TANAFFUS) VA KUNLIK LIMIT
# ─────────────────────────────────────────────────────────────────────────
_ACTIVE_HOURS_RE = re.compile(
    r"^\s*(\d{1,2}):(\d{2})\s*[-–—]\s*(\d{1,2}):(\d{2})\s*$"
)


def parse_active_hours(value: str | None) -> tuple[int, int] | None:
    """``"08:00-23:00"`` ni daqiqa juftligiga aylantiradi.

    Bo'sh, noto'g'ri yoki to'liq kunlik (00:00-24:00) qiymat ``None``
    qaytaradi — ya'ni cheklov yo'q. Tungi ko'chma oynalar (masalan
    ``22:00-06:00``) ham qo'llab-quvvatlanadi.
    """
    if not value:
        return None
    match = _ACTIVE_HOURS_RE.match(value)
    if not match:
        return None
    start_h, start_m, end_h, end_m = (int(part) for part in match.groups())
    if start_h > 23 or end_h > 24 or start_m > 59 or end_m > 59:
        return None
    start = start_h * 60 + start_m
    end = end_h * 60 + end_m
    if start == end:
        return None
    if end == 24 * 60:
        end = 0  # kun oxirigacha
    if start == 0 and end == 0:
        return None
    return (start, end)


def in_active_window(active_hours: str | None, when: datetime | None = None) -> bool:
    """Hozir yuborish oynasimi? Cheklov bo'lmasa har doim True."""
    window = parse_active_hours(active_hours)
    if window is None:
        return True
    current = when or now_local()
    minutes = current.hour * 60 + current.minute
    start, end = window
    if start < end:
        return start <= minutes < end
    return minutes >= start or minutes < end  # tungi ko'chma oyna


def seconds_until_window_open(
    active_hours: str | None, when: datetime | None = None
) -> int:
    """Oyna ochilgunicha qancha soniya qoldi (cheklov bo'lmasa 0)."""
    window = parse_active_hours(active_hours)
    if window is None:
        return 0
    current = when or now_local()
    start, _ = window
    minutes_now = current.hour * 60 + current.minute + current.second / 60
    delta = start - minutes_now
    if delta <= 0:
        delta += 24 * 60
    return max(0, int(delta * 60) + (0 if current.second == 0 else 1))


def start_of_local_day_ts(when: datetime | None = None) -> float:
    """Mahalliy yarim tun epoch vaqti — kunlik hisoblar uchun chegara."""
    current = when or now_local()
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    if midnight.tzinfo is None:
        # Naif vaqt mahalliy hisoblanadi: timestamp() shuni hisobga oladi.
        return midnight.timestamp()
    return midnight.timestamp()


# ─────────────────────────────────────────────────────────────────────────
# POST SHABLONI: {sana} {vaqt} {kun} va { variant | lar }
# ─────────────────────────────────────────────────────────────────────────
_TEMPLATE_RE = re.compile(r"\{([^{}]{1,80})\}")
_WEEKDAYS_UZ = (
    "Yakshanba",
    "Dushanba",
    "Seshanba",
    "Chorshanba",
    "Payshanba",
    "Juma",
    "Shanba",
)


def _template_values(when: datetime | None = None) -> dict[str, str]:
    current = when or now_local()
    return {
        "sana": current.strftime("%d.%m.%Y"),
        "vaqt": current.strftime("%H:%M"),
        "soat": current.strftime("%H:%M"),
        "kun": _WEEKDAYS_UZ[_weekday_index(current)],
        "yil": current.strftime("%Y"),
        "oy": current.strftime("%m"),
        "kun_kuni": current.strftime("%d"),
    }


def _weekday_index(current: datetime) -> int:
    """Python weekday() (0=Dushanba) → bizning ro'yxat (0=Yakshanba)."""
    return (current.weekday() + 1) % 7


def render_template(
    text: str,
    entities: list[dict] | None = None,
    *,
    when: datetime | None = None,
    rng=None,
) -> tuple[str, list[dict]]:
    """``{sana}``, ``{vaqt}``, ``{kun}`` va ``{A|B|C}`` larni almashtiradi.

    Entity offsetlari qayta hisoblanadi: agar shablon oralig'i entity ichiga
    to'liq tushsa — uzunalik moslashadi, chegarani kesib o'tsa — entity
    tashlab yuboriladi (formatlangan matn buzilmasligi uchun).

    Returns:
        (yangi_matn, yangi_entities)
    """
    if not text:
        return text or "", list(entities or [])

    import random

    chooser = rng or random
    values = _template_values(when)
    spans: list[tuple[int, int, str]] = []
    for match in _TEMPLATE_RE.finditer(text):
        inner = match.group(1).strip()
        if "|" in inner:
            options = [option for option in inner.split("|") if option.strip()]
            if len(options) > 1:
                spans.append((match.start(), match.end(), chooser.choice(options)))
            continue
        value = values.get(inner)
        if value is not None:
            spans.append((match.start(), match.end(), value))

    if not spans:
        return text, list(entities or [])

    new_parts: list[str] = []
    cursor = 0
    for start, end, replacement in spans:
        new_parts.append(text[cursor:start])
        new_parts.append(replacement)
        cursor = end
    new_parts.append(text[cursor:])
    new_text = "".join(new_parts)

    kept: list[dict] = []
    for entity in entities or []:
        try:
            offset = int(entity.get("offset", 0))
            length = int(entity.get("length", 0))
        except (TypeError, ValueError):
            continue
        start, end = offset, offset + length
        if length <= 0 or start < 0 or end > len(text):
            continue

        crossing = False
        delta_before = 0
        delta_inside = 0
        for span_start, span_end, replacement in spans:
            delta = len(replacement) - (span_end - span_start)
            if span_end <= start:
                delta_before += delta
            elif span_start >= end:
                continue
            elif span_start >= start and span_end <= end:
                delta_inside += delta
            else:
                crossing = True
                break
        if crossing:
            continue
        new_offset = start + delta_before
        new_length = length + delta_inside
        if new_length <= 0 or new_offset < 0:
            continue
        updated = dict(entity)
        updated["offset"] = new_offset
        updated["length"] = new_length
        kept.append(updated)

    return new_text, kept


def has_template_markers(text: str) -> bool:
    """Matnda qo'llab-quvvatlanadigan shablon belgisi bormi?"""
    if not text:
        return False
    for match in _TEMPLATE_RE.finditer(text):
        inner = match.group(1).strip()
        if "|" in inner:
            return True
        if inner in _template_values():
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# MEDIA RO'YXATI (ALBOM) YORDAMCHILARI
# ─────────────────────────────────────────────────────────────────────────
def normalize_media(post: dict | None) -> list[dict]:
    """``posts.media`` JSON'ini ro'yxatga aylantiradi (eski ``photo`` ham)."""
    if not post:
        return []
    raw = post.get("media")
    items: list[dict] = []
    if raw:
        import json

        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = []
        else:
            parsed = raw
        if isinstance(parsed, dict):
            parsed = [parsed]
        for item in parsed or []:
            if isinstance(item, str):
                items.append({"path": item, "kind": "photo"})
            elif isinstance(item, dict) and item.get("path"):
                items.append(
                    {
                        "path": str(item["path"]),
                        "kind": str(item.get("kind") or "photo"),
                    }
                )
    if not items and post.get("photo"):
        items.append({"path": str(post["photo"]), "kind": "photo"})
    return items


def existing_media_paths(post: dict | None) -> list[str]:
    """Faqat diskda mavjud bo'lgan media yo'llari (albom yuborish uchun)."""
    import os

    paths = []
    for item in normalize_media(post):
        path = item["path"]
        if path and os.path.exists(path) and path not in paths:
            paths.append(path)
    return paths


def media_kind_label(post: dict | None) -> str:
    """Post turi haqida qisqa matn (foydalanuvchi xabari uchun)."""
    paths = normalize_media(post or {})
    count = len(paths)
    kinds = {item.get("kind") for item in paths}
    if count > 1:
        return f"🖼 Albom ({count} ta media)"
    if count == 1:
        kind = next(iter(kinds), "photo")
        return {"video": "🎬 Video", "document": "📎 Fayl"}.get(kind, "🖼 Rasm")
    return "📝 Matn"
