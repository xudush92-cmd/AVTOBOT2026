"""
🔍 Guruhlarni topish — qo'lda belgilash bilan.

Oqim:
1. ``🔍 Guruhlarni topish`` bosilganda Telegram'dagi barcha guruhlar
   skanerlanadi, lekin **hech biri botga qo'shilmaydi**.
2. Topilgan guruhlar foydalanuvchiga **ro'yxat qilib ko'rsatiladi**
   (sahifalash, 15 ta/sahifa).
3. Foydalanuvchi kerakli guruhlarni **✅ belgilaydi**.
4. «✅ Tanlanganlarni qo'shish (N)» bosilganda **faqat belgilangan**
   guruhlar botga qo'shiladi va e'lon yuborishni boshlaydi.

Belgilanmagan guruhlar hech qachon botga qo'shilmaydi.

Sessiya vaqtinchalik — ``DISCOVER_SELECTION_TTL_S`` soniyadan keyin
foydalanuvchining tanlovi va ro'yxati tozalanadi (jarayon qayta ishga
tushsa ham eski ma'lumot qolmaydi).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.logger import log
from core.utils import group_reference_key

# Sahifada nechta guruh ko'rsatiladi.
GROUPS_PAGE_SIZE = 15

# Tanlov sessiyasining umriga (soniya).
DISCOVER_SELECTION_TTL_S = 30 * 60

# Maksimal saqlanadigan guruhlar soni (xavfsizlik).
DISCOVER_MAX_STORED = 1000


@dataclass
class DiscoveredGroup:
    """Topilgan bitta guruh."""

    reference: str
    """Bazada saqlanadigan canonical reference (``@username`` yoki ID)."""

    title: str
    """Guruh nomi (ko'rsatish uchun)."""

    members: int = 0
    """A'zolar soni (taxminiy)."""

    kind: str = "guruh"
    """``guruh`` yoki ``megaguruh``."""

    key: str = ""
    """Dedupe kaliti (``group_reference_key``)."""

    def display(self) -> str:
        """Ro'yxatda ko'rsatiladigan matn."""
        name = self.title or self.reference
        if len(name) > 40:
            name = name[:39] + "…"
        icon = "📢" if self.kind == "megaguruh" else "👥"
        extra = f" · {self.members} a'zo" if self.members else ""
        return f"{icon} {name}{extra}"


def build_key(reference: str) -> str:
    """Guruh uchun barqaror dedupe kaliti.

    ``group_reference_key`` ba'zi username'lar uchun bo'sh qaytadi
    (``@g0`` — raqam bilan tugaydigan username rad etiladi). Bo'sh kalit
    bo'lsa, **fallback** ishlatiladi — aks holda bir nechta guruh bir xil
    kalit olib, tanlash/bekor qilish noto'g'ri ishlaydi.
    """
    key = group_reference_key(reference)
    if key:
        return key
    return f"ref:{reference.strip().casefold()}" if reference else ""


@dataclass
class DiscoverSession:
    """Foydalanuvchining guruh tanlov sessiyasi."""

    groups: list[DiscoveredGroup] = field(default_factory=list)
    """Topilgan barcha guruhlar (tartibda)."""

    selected: set[str] = field(default_factory=set)
    """Belgilangan guruhlar kalitlari (``key``)."""

    created_at: float = field(default_factory=time.time)
    """Sessiya yaratilgan vaqti."""

    updated_at: float = field(default_factory=time.time)
    """Oxirgi yangilanish vaqti."""

    def is_expired(self, ttl_s: int = DISCOVER_SELECTION_TTL_S) -> bool:
        """Sessiya muddati tugaganmi."""
        return (time.time() - self.updated_at) > ttl_s

    def page_count(self, page_size: int = GROUPS_PAGE_SIZE) -> int:
        """Sahifalar soni."""
        if not self.groups:
            return 1
        return max(1, (len(self.groups) + page_size - 1) // page_size)

    def page_groups(
        self, page: int = 0, page_size: int = GROUPS_PAGE_SIZE
    ) -> list[DiscoveredGroup]:
        """Sahifadagi guruhlar."""
        page = max(page, 0)
        start = page * page_size
        return self.groups[start : start + page_size]

    def selected_groups(self) -> list[DiscoveredGroup]:
        """Belgilangan guruhlar (ro'yxat tartibida)."""
        return [g for g in self.groups if g.key in self.selected]

    def toggle(self, key: str) -> bool:
        """Belgini almashtiradi. Qaytaradi: endi belgilanganmi."""
        if key in self.selected:
            self.selected.discard(key)
            now_selected = False
        else:
            self.selected.add(key)
            now_selected = True
        self.updated_at = time.time()
        return now_selected

    def is_selected(self, key: str) -> bool:
        """Guruh belgilanganmi."""
        return key in self.selected

    def find(self, key: str) -> DiscoveredGroup | None:
        """Kalit bo'yicha guruhni topadi."""
        for group in self.groups:
            if group.key == key:
                return group
        return None


# Foydalanuvchi UID → sessiya
_sessions: dict[int, DiscoverSession] = {}


def get_session(uid: int) -> DiscoverSession | None:
    """Foydalanuvchining aktiv sessiyasini qaytaradi (muddati tugagan bo'lsa None)."""
    session = _sessions.get(int(uid))
    if session is None:
        return None
    if session.is_expired():
        _sessions.pop(int(uid), None)
        return None
    return session


def start_session(
    uid: int, groups: list[DiscoveredGroup]
) -> DiscoverSession:
    """Yangi tanlov sessiyasini boshlaydi (eski tanlov tozalanadi)."""
    session = DiscoverSession(groups=groups[:DISCOVER_MAX_STORED])
    _sessions[int(uid)] = session
    log(
        f"🔍 Guruh tanlash sessiyasi: {uid} — {len(session.groups)} ta guruh topildi"
    )
    return session


def clear_session(uid: int) -> None:
    """Sessiyani tozalaydi."""
    _sessions.pop(int(uid), None)


def reset() -> None:
    """Barcha sessiyalarni tozalaydi (testlar uchun)."""
    _sessions.clear()
