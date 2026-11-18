"""Muddat chegaralari (anti-fraud) markaziy qoidalari.

Muammo: jamoa admini (2-daraja) foydalanuvchiga juda uzoq muddat (masalan
1 yil) berib, uddadan olib, botni tark etishi mumkin. Bunday "firibgar"
adminlardan himoya qilish uchun har bir admin darajasi uchun muddat
chegarasi (cap) belgilanadi.

Qoidalar:
  * Super admin  — chegara yo'q (``SUPER_ADMIN_MAX_DAYS = 0``).
  * Jamoa admini — a'zosiga maksimal ``TEAM_MEMBER_MAX_DAYS`` (standart 60) kun.
  * Chegara nolga teng bo'lsa — cheksiz.

Chegara **bir marta beriladigan** muddatga qo'yiladi, ya'ni dastlabki
tasdiqlashda. Keyinchalik muddatni uzaytirish super adminning vazifasi.
"""

from __future__ import annotations

from config.config import (
    DEFAULT_DURATION_DAYS,
    SUPER_ADMIN_MAX_DAYS,
    TEAM_MEMBER_MAX_DAYS,
)


def max_days_for(is_super_admin: bool) -> int:
    """Berilgan admin darajasidagi maksimal muddat (kun).

    ``0`` qaytarilsa — chegara yo'q.
    """
    return SUPER_ADMIN_MAX_DAYS if is_super_admin else TEAM_MEMBER_MAX_DAYS


def clamp_days(days: int | None, is_super_admin: bool) -> int:
    """Muddatni chegara bilan cheklaydi.

    - ``days`` berilmasa yoki noto'g'ri bo'lsa — standart
      ``DEFAULT_DURATION_DAYS`` ishlatiladi.
    - Chegara mavjud bo'lsa — qiymat chegaradan oshmasligi kafolatlanadi.
    - Kamida 1 kun.
    """
    try:
        value = int(days) if days is not None else DEFAULT_DURATION_DAYS
    except (TypeError, ValueError):
        value = DEFAULT_DURATION_DAYS
    value = max(1, value)

    cap = max_days_for(is_super_admin)
    if cap > 0:
        value = min(value, cap)
    return value


def is_over_cap(days: int, is_super_admin: bool) -> bool:
    """Berilgan muddat chegara oshganmi — ``True``/``False``."""
    cap = max_days_for(is_super_admin)
    return cap > 0 and int(days) > cap


def cap_note(is_super_admin: bool) -> str:
    """Chegara haqida qisqa izoh (UI uchun)."""
    cap = max_days_for(is_super_admin)
    if cap <= 0:
        return ""
    return f"⛔️ Maksimal muddat: {cap} kun"


def options_within_cap(options: list[int], is_super_admin: bool) -> list[int]:
    """Chegaraga sig'adigan muddat variantlarini qaytaradi.

    Standart variantlar ichida chegara chegarasi bo'lmasa (masalan
    chegara 60 kun, variantlar 1/7/30/90) — chegaraning o'zi qo'shiladi,
    shunda admin chegarani to'liq ishlatishi mumkin bo'ladi.
    """
    cap = max_days_for(is_super_admin)
    result = [d for d in options if cap <= 0 or d <= cap]
    if cap > 0 and cap not in result:
        result.append(cap)
        result.sort()
    return result
