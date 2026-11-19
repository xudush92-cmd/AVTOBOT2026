"""Bir foydalanuvchining parallel Telegram updatelarini tartibga solish.

Nima uchun per-UID lock (striped emas):
    Avval lock'lar ``uid % 256`` shaklida taqsimlanardi. Bu **bounded**
    xotira uchun qulay, lekin ikki xil muammo keltiradi:

    1. **Collision** — ``uid=1`` va ``uid=257`` bir xil lock'ni olardi.
       Bitta foydalanuvchi uzoq amal qilsa (masalan, «🔍 Guruhlarni
       topish» skaneri), ikkinchisi **kutib qolardi** — bu «boshqa
       foydalanuvchilar ziyon ko'rmasligi» talabiga qarshi.
    2. **Noto'g'ri tasodif** — har 256 foydalanuvchidan biri boshqasi
       bilan to'qnashadi, statistik ravishda tez-tez.

Endi lock'lar **aybiga** (per-UID) yaratiladi va ``WeakValueDictionary``
bilan saqlanadi — faqat **faol** foydalanuvchilarning lock'i xotirada
qoladi. Shuning uchun xotira yanada bounded, lekin collision yo'q.
"""

from __future__ import annotations

import asyncio
import weakref

# Ikki alohida namespace:
# - update lock — bir foydalanuvchining parallel Bot API updatelarini
#   serial qiladi (javoblar aralashib ketmasligi uchun);
# - operation lock — admin va user fon vazifalarini target UID bo'yicha
#   serial qiladi.
_UPDATE_LOCKS: weakref.WeakValueDictionary[int, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)
_OPERATION_LOCKS: weakref.WeakValueDictionary[int, asyncio.Lock] = (
    weakref.WeakValueDictionary()
)

# Namespace'lar turli bo'lishi kerak — aks holda update va operation
# lock'lari bir-birini kutib qoldiradi.
_UPDATE_NAMESPACE = id(_UPDATE_LOCKS)
_OPERATION_NAMESPACE = id(_OPERATION_LOCKS)


def _get_lock(
    store: weakref.WeakValueDictionary[int, asyncio.Lock],
    uid: int,
) -> asyncio.Lock:
    """UID uchun lock — mavjudini qaytaradi yoki yangisini yaratadi."""
    uid = int(uid)
    lock = store.get(uid)
    if lock is None:
        lock = asyncio.Lock()
        store[uid] = lock
    return lock


def user_update_lock(uid: int) -> asyncio.Lock:
    """Foydalanuvchining update lock'i (faqat o'z amallari uchun)."""
    return _get_lock(_UPDATE_LOCKS, uid)


def user_operation_lock(uid: int) -> asyncio.Lock:
    """Foydalanuvchining operation lock'i (faqat o'z amallari uchun)."""
    return _get_lock(_OPERATION_LOCKS, uid)


def active_lock_count() -> int:
    """Hozirda faol lock'lar soni — testlar va monitoring uchun."""
    return len(_UPDATE_LOCKS) + len(_OPERATION_LOCKS)


def reset() -> None:
    """Barcha lock'larni tozalaydi (faqat testlar uchun)."""
    _UPDATE_LOCKS.clear()
    _OPERATION_LOCKS.clear()
