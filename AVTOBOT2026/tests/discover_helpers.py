"""🧪 Test yordamchilari — guruh tanlash oqimi.

``disc:apply`` endi **ikki bosqichli**: birinchi bosilishda tasdiqlash
so'raladi («💾 Tanlanganlarni saqlash»), ikkinchisida («✅ Ha, saqla»)
guruhlar bazaga yoziladi.

Testlar uchun yordamchi funksiyalar.
"""

from __future__ import annotations


async def apply_and_confirm(
    groups_module,
    update,
    uid: int,
    data: str = "disc:apply",
) -> None:
    """Tasdiqlash oqimini to'liq bajaradi.

    1) «💾 Tanlanganlarni saqlash» — tasdiqlash oynasi ochiladi;
    2) «✅ Ha, saqla» — guruhlar bazaga yoziladi.
    """
    await groups_module.handle_discover_callback(update, uid, data)
    await groups_module.handle_discover_callback(update, uid, "disc:apply:yes")


async def apply_and_cancel(
    groups_module,
    update,
    uid: int,
    data: str = "disc:apply",
) -> None:
    """Tasdiqlash oqimini bekor qilish bilan bajaradi."""
    await groups_module.handle_discover_callback(update, uid, data)
    await groups_module.handle_discover_callback(update, uid, "disc:apply:no")
