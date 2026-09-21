"""
Rate limiter — anti-spam himoya.

Har bir foydalanuvchi uchun amallar sonini kuzatadi.
Belgilangan limitdan oshsa — vaqtincha bloklaydi.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field

from config.config import (
    RATE_LIMIT_COMMAND,
    RATE_LIMIT_LOGIN,
    RATE_LIMIT_LOGIN_WINDOW_S,
    RATE_LIMIT_MESSAGE,
    RATE_LIMIT_MODIFY,
    RATE_WINDOW_S,
)


# ─────────────────────────────────────────────────────────────────────────
# AMAL LIMITLARI
# ─────────────────────────────────────────────────────────────────────────
LIMITS: dict[str, int] = {
    "login": RATE_LIMIT_LOGIN,       # login urinishlari
    "command": RATE_LIMIT_COMMAND,   # /start va h.k.
    "message": RATE_LIMIT_MESSAGE,   # oddiy xabarlar
    "modify": RATE_LIMIT_MODIFY,     # guruh/post o'zgartirish
}

WINDOWS: dict[str, int] = {
    "login": RATE_LIMIT_LOGIN_WINDOW_S,  # Telegram auth: 3 marta / soat
    "command": RATE_WINDOW_S,
    "message": RATE_WINDOW_S,
    "modify": RATE_WINDOW_S,
}


# ─────────────────────────────────────────────────────────────────────────
# HAR BIR FOYDALANUVCHI UCHUN YOZUV
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class UserRecord:
    """Bitta foydalanuvchining amallari vaqtlari."""
    # action -> [timestamp, timestamp, ...]
    timestamps: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add(self, action: str, now: float) -> None:
        """Yangi amal qo'shadi."""
        self.timestamps[action].append(now)

    def count(self, action: str, since: float) -> int:
        """Berilgan vaqtdan keyingi amallar soni."""
        return sum(1 for ts in self.timestamps[action] if ts >= since)

    def cleanup(self, action: str, since: float) -> None:
        """Eski yozuvlarni tozalaydi."""
        self.timestamps[action] = [
            ts for ts in self.timestamps[action] if ts >= since
        ]


# ─────────────────────────────────────────────────────────────────────────
# RATE LIMITER
# ─────────────────────────────────────────────────────────────────────────
class RateLimiter:
    """
    Har bir foydalanuvchi uchun amallar sonini kuzatadi.

    Misol:
        rl = RateLimiter()

        if rl.is_allowed(uid, "login"):
            # ruxsat
        else:
            wait = rl.get_wait_time(uid, "login")
            print(f"{wait} daqiqa kuting")
    """

    def __init__(self, window_s: int | None = None) -> None:
        # Testlar/maxsus holatlar uchun berilgan window barcha actionlarga
        # qo'llanadi. Standart holatda login oynasi alohida — 1 soat.
        self._custom_window_s = window_s
        self.window_s = window_s if window_s is not None else RATE_WINDOW_S
        self._records: dict[int, UserRecord] = {}

    def _window_for(self, action: str) -> int:
        if self._custom_window_s is not None:
            return self._custom_window_s
        return WINDOWS.get(action, RATE_WINDOW_S)

    # ─────────────────────────────────────────────────────────────
    # ASOSIY TEKSHIRUV
    # ─────────────────────────────────────────────────────────────
    def is_allowed(self, uid: int, action: str) -> bool:
        """
        Foydalanuvchi bu amalni bajarishi mumkinmi?

        Returns:
            True  — ruxsat
            False — bloklangan
        """
        limit = LIMITS.get(action)
        if limit is None:
            return True  # noma'lum amal — cheklov yo'q

        now = time.time()
        since = now - self._window_for(action)

        record = self._records.get(uid)
        if record is None:
            record = UserRecord()
            self._records[uid] = record

        # Eski yozuvlarni tozalash
        record.cleanup(action, since)

        # Limitdan oshganmi?
        if record.count(action, since) >= limit:
            return False

        # Yangi amalni yozish
        record.add(action, now)
        return True

    # ─────────────────────────────────────────────────────────────
    # KUTISH VAQTI
    # ─────────────────────────────────────────────────────────────
    def get_wait_time(self, uid: int, action: str) -> int:
        """
        Necha DAQIQA kutish kerak (soniya emas — daqiqa!).

        Returns:
            Daqiqada yumaloqlangan kutish vaqti (minimum 1)
        """
        record = self._records.get(uid)
        if record is None:
            return 1

        now = time.time()
        window_s = self._window_for(action)
        since = now - window_s
        timestamps = [ts for ts in record.timestamps.get(action, []) if ts >= since]

        if not timestamps:
            return 1

        # Eng eski amal + oyna - hozirgi vaqt
        oldest = min(timestamps)
        wait_seconds = (oldest + window_s) - now
        if wait_seconds <= 0:
            return 1

        # Daqiqaga yumaloqlash (yuqoriga)
        return max(1, int(wait_seconds // 60) + (1 if wait_seconds % 60 else 0))

    # ─────────────────────────────────────────────────────────────
    # STATISTIKA (admin uchun)
    # ─────────────────────────────────────────────────────────────
    def stats(self) -> dict:
        """
        Umumiy statistika.

        Returns:
            {
                'tracked_users': int,     # kuzatilayotgan foydalanuvchilar
                'currently_blocked': int, # hozir bloklanganlar
                'total_actions': int,     # jami amallar
            }
        """
        now = time.time()
        tracked = len(self._records)
        blocked = 0
        total = 0

        for uid, record in self._records.items():
            for action, limit in LIMITS.items():
                since = now - self._window_for(action)
                count = record.count(action, since)
                total += count
                if count >= limit:
                    blocked += 1

        return {
            "tracked_users": tracked,
            "currently_blocked": blocked,
            "total_actions": total,
        }

    # ─────────────────────────────────────────────────────────────
    # TOZALASH
    # ─────────────────────────────────────────────────────────────
    def reset(self, uid: int) -> None:
        """Bitta foydalanuvchining barcha yozuvlarini o'chirish."""
        self._records.pop(uid, None)

    def cleanup_all(self) -> int:
        """
        Eski yozuvlarni tozalash (janitor uchun).

        Returns:
            O'chirilgan foydalanuvchilar soni
        """
        now = time.time()
        removed = 0

        for uid in list(self._records.keys()):
            record = self._records[uid]
            has_recent = False
            for action in list(record.timestamps.keys()):
                since = now - self._window_for(action)
                record.cleanup(action, since)
                if record.timestamps[action]:
                    has_recent = True
            if not has_recent:
                del self._records[uid]
                removed += 1

        return removed
