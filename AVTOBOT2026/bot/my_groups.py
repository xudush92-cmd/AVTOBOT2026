"""💬 Foydalanuvchining o'z guruhlarini boshqarish oynasi.

Oqim:
1. Asosiy menyudagi ``💬 Guruhlar`` tugmasi bu oynani ochadi.
2. Oynada yuqorida — ``🔍 Guruhlarni topish`` (avtomatik qidiruv) va
   guruh **havolalari** ro'yxati (raqam bilan).
3. Pastda — har bir guruh uchun **faqat** ``🗑 N. guruh`` o'chirish tugmasi.

Interval o'zgartirish alohida oynada — ``⏱ Interval``:
  * ``🌐 Barcha guruhlar uchun`` — umumiy interval;
  * ``⏱ Bitta guruh uchun`` — bitta tanlangan guruh uchun.

Callback prefikslari:
  * ``mg:`` — mening guruhlarim (o'chirish, skaner);
  * ``int:`` — interval oynasi.

Ikkalasi ham super adminning ``uc:`` prefiksidan ajratilgan — admin
boshqa foydalanuvchining guruhini boshqaradi, bu esa **o'z** guruhini.

Muhim: bu modul **faqat** super admin bo'lmagan foydalanuvchilar uchun.
Super admin allaqachon ``uc:`` orqali barcha foydalanuvchilarni
boshqaradi.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import Update
from telethon import TelegramClient
from telethon.sessions import StringSession

from bot import discover_sessions as DS
from bot import keyboards as KB
from bot import texts as T
from config.config import API_HASH, API_ID
from core import database as db
from core.errlog import log_gap
from core.logger import log
from core.utils import is_valid_interval

# Sahifada nechta guruh ko'rsatiladi.
PAGE_SIZE = 10


def _is_super_admin(uid: int) -> bool:
    """Super admin — o'z guruhlarini boshqarish oynasini ishlatmaydi."""
    from config.config import SUPER_ADMIN

    return int(uid) == int(SUPER_ADMIN)


def public_link(value: str) -> str:
    """Guruh uchun ochiq havola (``https://t.me/username``).

    Faqat username bor guruhlarda mavjud. Yopiq guruhlarda
    (``-100...`` marked ID) Telegram ochiq havola bermaydi — u yerda
    bo'sh qaytariladi va havola ro'yxatda chiqarilmaydi.
    """
    raw = (value or "").strip()
    if raw.startswith("@"):
        return f"https://t.me/{raw[1:]}"
    if raw.startswith("https://t.me/"):
        return raw
    return ""


def escape_html(text: str) -> str:
    """Telegram HTML uchun maxsus belgilarni escape qiladi.

    ``_`` — Telegram'ning *italic* belgisi. Username ichida u bo'lsa
    (``taxi_tashkent``) matn noto'g'ri chiziladi, shuning uchun
    ``\\_`` ga almashtiriladi.
    """
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("_", "\\_")
    )


async def _back_markup(uid: int):
    """Orqaga — asosiy menyu klaviaturasi."""
    return await KB.kb_main_for(uid)


def group_label(item: dict) -> str:
    """Guruh uchun ko'rsatiladigan nom.

    Telegram'dagi display name (baza ``title``) afzal — foydalanuvchi
    guruhni nomidan tanib oladi. Nomi yo'q bo'lsa — username.

    Yopiq guruh (marked ID, masalan ``-100123...``) uchun ID **ko'rsatilmaydi** —
    u maxfiy ma'lumot. Nomi bo'lmasa — umumiy matn qo'yiladi.
    """
    title = str(item.get("title") or "").strip()
    value = str(item.get("value") or "").strip()
    if title and title != value:
        return title
    if value.startswith("@"):
        return value
    # Yopiq guruh — ID ko'rsatilmaydi.
    return "Yopiq guruh"


def group_label_with_handle(item: dict) -> str:
    """``🗑`` tugmasi uchun matn: nom + username.

    Telegram tugma matni 64 belgi bilan cheklangan — shuning uchun
    ikkalasi ham qisqartiriladi. Yopiq guruh ID'si ko'rsatilmaydi.
    """
    title = str(item.get("title") or "").strip()
    value = str(item.get("value") or "").strip()
    if title and title != value:
        if value.startswith("@"):
            return f"{title} ({value})"[:60]
        # Yopiq guruh — ID ko'rsatilmaydi.
        return title[:60]
    if value.startswith("@"):
        return value[:60]
    return (title or "Yopiq guruh")[:60]


async def build_groups_window(
    uid: int,
    note: str = "",
    page: int = 0,
) -> tuple[str, object]:
    """``💬 Guruhlar`` oynasining matni va klaviaturasini qaytaradi.

    ``render_groups_inline`` va boshqa joylar (masalan, skaner natijasi
    qo'shilgandan keyin) bir xil oynani ko'rsatishi kerak — shuning uchun
    matn/markup yig'ish mantiği bitta joyga chiqarilgan.
    """
    groups = await db.get_chat_records(uid)

    # ⚠️ Skanerda topilgan, lekin hali qo'shilmagan guruhlar.
    # Foydalanuvchi ularni ✅ bilan belgilab, "Tanlanganlarni qo'shish"
    # tugmasini bosmasdan oyna yopsa — ular yo'qolib qoladi. Shuning uchun
    # bo'sh oynada ham, to'ldirilgan oynada ham bu holat ko'rsatiladi va
    # "qo'shish" tugmasi beriladi.
    pending = DS.get_session(uid)
    pending_selected = 0
    pending_found = 0
    if pending is not None and getattr(pending, "groups", None):
        pending_found = len(pending.groups)
        pending_selected = len(getattr(pending, "selected", set()) or set())

    if not groups:
        text = T.GROUPS_PENDING_NONE
        if pending_found:
            if pending_selected:
                text += "\n\n" + T.GROUPS_PENDING_SELECTED.format(
                    found=pending_found,
                    selected=pending_selected,
                )
            else:
                text += "\n\n" + T.GROUPS_PENDING_NOT_SELECTED.format(
                    found=pending_found,
                )
        if note:
            text = f"{note}\n\n{text}"
        return text, KB.kb_my_groups([], 0, pending_selected=pending_selected)

    max_page = max(0, (len(groups) - 1) // PAGE_SIZE)
    page = min(max(page, 0), max_page)

    # Guruh havolalari — raqam bilan. Yopiq guruhlarda havola yo'q.
    # Guruhlar ro'yxati — nom (Telegram display name) va ochiq havola.
    # Nomi yo'q bo'lsa — username ko'rsatiladi.
    lines: list[str] = []
    for idx, item in enumerate(groups, start=1):
        label = escape_html(group_label(item)[:50])
        link = public_link(str(item.get("value") or ""))
        if link:
            lines.append(f"{idx}. {label} — {escape_html(link)}")
        else:
            lines.append(f"{idx}. {label}")
    links_block = ""
    if lines:
        links_block = "\n\n<b>🔗 Guruh havolalari:</b>\n\n" + "\n".join(lines)

    text = (
        "💬 <b>GURUHLAR</b>\n\n"
        f"Guruhlar soni: {len(groups)} ta"
        f"{links_block}\n\n"
        "Quyidagi <b>🗑</b> tugmalari orqali guruhni o'chirish mumkin."
    )
    if pending_selected:
        # ⚠️ Tanlangan guruhlar hali qo'shilmagan — ogohlantirish.
        text += "\n\n" + T.GROUPS_PENDING_SELECTED.format(
            found=pending_found,
            selected=pending_selected,
        )
    if note:
        text = f"{note}\n\n{text}"
    return text, KB.kb_my_groups(
        groups, page, pending_selected=pending_selected
    )


async def render_groups_inline(
    update: Update,
    uid: int,
    edit: bool = False,
    note: str = "",
    page: int = 0,
) -> None:
    """``💬 Guruhlar`` inline oynasini ko'rsatadi (xabar yoki tahrirlash).

    Eski ``kb_groups_menu()`` o'rniga ishlatiladi — foydalanuvchiga
    eski tugmalar (qo'shish/tekshirish/guruh intervali) ko'rinmaydi,
    faqat yangi bitta boshqaruv oynasi: havolalar + ``🗑 N. guruh``.
    """
    text, markup = await build_groups_window(uid, note=note, page=page)
    if edit and update.callback_query is not None:
        with contextlib.suppress(Exception):
            await update.callback_query.edit_message_text(
                text, parse_mode="HTML", reply_markup=markup
            )
            return
    await update.message.reply_text(
        text, parse_mode="HTML", reply_markup=markup
    )

# «Qo'lda kiritish» uchun state step nomi.
STEP_MANUAL_INTERVAL = "my_group_interval_manual"

# Bir foydalanuvchi uchun nom to'ldirish fon tasklari (takrorlanmasligi uchun).
_title_fill_tasks: dict[int, asyncio.Task] = {}


async def _fetch_group_title(client, reference: str) -> str:
    """Telegram'dan guruh nomini oladi (bo'sh bo'lsa — topilmadi)."""
    from bot.groups import GroupResolveError, resolve_group_entity

    try:
        entity = await asyncio.wait_for(
            resolve_group_entity(client, reference), timeout=20
        )
    except GroupResolveError:
        return ""
    except Exception as exc:  # noqa: BLE001 — nom ixtiyoriy
        log(
            f"guruh nomi olinmadi {reference}: {type(exc).__name__}",
            "warning",
        )
        return ""
    return str(getattr(entity, "title", "") or "").strip()


async def _fill_missing_titles(uid: int) -> None:
    """Nomi yo'q guruhlar uchun Telegram'dan nom so'raydi va saqlaydi.

    Fon task sifatida ishlaydi — foydalanuvchi kutmaydi.
    """
    try:
        session = await db.get_session(uid)
        if not session:
            return
        groups = await db.get_chat_records(uid)
        missing = [
            item
            for item in groups
            if not str(item.get("title") or "").strip()
        ]
        if not missing:
            return

        client = TelegramClient(StringSession(session), API_ID, API_HASH)
        await asyncio.wait_for(client.connect(), timeout=20)
        try:
            me = await asyncio.wait_for(client.get_me(), timeout=15)
            if me is None:
                return
            for item in missing:
                title = await _fetch_group_title(client, str(item.get("value") or ""))
                if not title:
                    continue
                await db.set_chat_title(
                    uid, int(item["id"]), title
                )
                log(
                    f"📝 Guruh nomi saqlandi: {uid} → "
                    f"{item.get('value')} = {title}"
                )
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 — fon task, xato jim qoldiriladi
        log(f"guruh nomi to'ldirilmadi {uid}: {type(exc).__name__}", "warning")
    finally:
        _title_fill_tasks.pop(uid, None)


def schedule_title_fill(uid: int) -> None:
    """Nomi yo'q guruhlar uchun fon task ishga tushiradi.

    Xavfsiz: bir foydalanuvchi uchun faqat **bitta** task ishlaydi.
    """
    if not uid or uid in _title_fill_tasks:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:  # pragma: no cover — loop yo'q
        return
    task = loop.create_task(
        _fill_missing_titles(uid), name=f"group-title-fill-{uid}"
    )
    _title_fill_tasks[uid] = task
    task.add_done_callback(lambda _t: _title_fill_tasks.pop(uid, None))


async def show_my_groups(
    update: Update,
    uid: int,
    page: int = 0,
    note: str = "",
) -> None:
    """Foydalanuvchining guruhlarini inline ro'yxat ko'rinishida ko'rsatadi."""
    if _is_super_admin(uid):
        # Super admin uchun bu oyna kerak emas — admin paneli ishlaydi.
        await update.message.reply_text(
            "\U0001f5a5 Super admin uchun guruhlar foydalanuvchi kartasidan boshqariladi.",
        )
        return

    # ✅ Nomi yo'q guruhlar uchun nom fon task'da to'ldiriladi.
    schedule_title_fill(uid)
    await render_groups_inline(update, uid, edit=False, note=note, page=page)


async def show_group_interval(
    update: Update,
    uid: int,
    group_id: int,
    note: str = "",
) -> None:
    """Bitta guruhning alohida intervalini tanlash oynasi."""
    q = update.callback_query
    group = await db.get_chat_record(uid, group_id)
    if not group:
        with contextlib.suppress(Exception):
            await q.edit_message_text("❌ Guruh topilmadi yoki o'chirilgan.")
        return

    global_interval = await db.get_interval(uid)
    custom_interval = group.get("interval_min")
    if custom_interval is None:
        selected = f"Umumiy ({global_interval} daqiqa)"
    else:
        selected = f"Alohida ({int(custom_interval)} daqiqa)"
    text = (
        "⏱ <b>GURUH INTERVALI</b>\n\n"
        f"Guruh: {group['value']}\n"
        f"Hozirgi sozlama: {selected}\n"
        f"Umumiy interval: {global_interval} daqiqa\n\n"
        "Alohida intervalni tanlang yoki umumiy intervalga qaytaring."
    )
    if note:
        text = f"{note}\n\n{text}"
    with contextlib.suppress(Exception):
        await q.edit_message_text(
            text,
            parse_mode="HTML",
            reply_markup=KB.kb_my_group_interval(
                group_id, custom_interval
            ),
        )


async def handle_interval_choice_callback(
    update: Update,
    uid: int,
    data: str,
) -> None:
    """``int:`` prefiksi — ⏱ Interval oynasi.

    Action'lar:
      * ``int:global`` — umumiy intervalni o'zgartirish;
      * ``int:one`` — bitta guruh uchun alohida interval;
      * ``int:back`` — asosiy menyuga qaytish.
    """
    q = update.callback_query
    action = data.split(":")[1] if ":" in data else ""

    if action == "noop":
        await q.answer()
        return

    if action == "back":
        await q.answer()
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                "⬅️ Asosiy menyu",
                reply_markup=await _back_markup(uid),
            )
        return

    if action == "global":
        # Umumiy interval — an'anaviy oqim (raqamni qo'lda kiritish).
        await q.answer()
        from bot import timer as Tm

        await Tm.begin_set_interval(update)
        return

    if action == "one":
        # Bitta guruh uchun — guruhni tanlash oynasi.
        await q.answer()
        groups = await db.get_chat_records(uid)
        if not groups:
            with contextlib.suppress(Exception):
                await q.edit_message_text(
                    "💬 Guruhlar yopiq. Avval guruh qo'shing.",
                    reply_markup=KB.kb_my_groups([], 0),
                )
            return
        global_interval = await db.get_interval(uid)
        text = (
            "⏱ <b>GURUH INTERVALI</b>\n\n"
            f"Umumiy interval: {global_interval} daqiqa\n\n"
            "Intervalni o'zgartirmoqchi guruhni tanlang."
        )
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=KB.kb_group_interval_picker(
                    groups, global_interval
                ),
            )
        return

    await q.answer()


async def handle_my_groups_callback(
    update: Update,
    uid: int,
    data: str,
) -> None:
    """``mg:`` prefiksi bilan kelgan inline callback'lar."""
    if _is_super_admin(uid):
        # Super admin boshqa foydalanuvchilarning guruhlarini boshqaradi
        # (``uc:`` orqali) — bu oyna faqat oddiy foydalanuvchilar uchun.
        with contextlib.suppress(Exception):
            await update.callback_query.answer(
                "Super admin uchun bu oyna kerak emas."
            )
        return

    q = update.callback_query
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "noop":
        await q.answer()
        return

    if action == "apply":
        # ⚠️ Skanerda tanlangan, lekin hali qo'shilmagan guruhlarni
        # to'g'ridan-to'g'ri qo'shamiz. Foydalanuvchi "Tanlanganlarni
        # qo'shish" tugmasini skaner oynasida topib bosmasdan, bu
        # oynadan ham qo'shishi mumkin bo'ladi.
        from bot import groups as G

        session = DS.get_session(uid)
        if session is None:
            await q.answer(T.DISCOVER_PICK_EXPIRED, show_alert=True)
            return
        selected = session.selected_groups()
        if not selected:
            await q.answer(T.DISCOVER_APPLY_NONE, show_alert=True)
            return
        # Javob ``apply_selected_groups`` ichida beriladi — bu yerda
        # ``q.answer()`` qo'shimcha chaqirilmaydi (Telegram bitta javobga
        # ruxsat beradi).
        await G.apply_selected_groups(update, uid, selected)
        return

    if action == "back":
        await q.answer()
        # ✅ Oyna yopilganda eskirgan "yopildi" xabari qolmasligi kerak —
        # aks holda foydalanuvchi guruhlar yo'q deb o'ylaydi.
        # Xabar o'chiriladi; asosiy menyu alohida xabarda ochiladi.
        deleted = False
        with contextlib.suppress(Exception):
            await q.delete_message()
            deleted = True
        if not deleted:
            with contextlib.suppress(Exception):
                await q.edit_message_reply_markup(reply_markup=None)
        from bot.menu import show_home

        await show_home(update, uid)
        return

    if action == "page":
        try:
            page = max(0, int(parts[2]))
        except (ValueError, IndexError):
            return
        await q.answer()
        # ✅ Sahifa almashganda ham to'liq oyna ko'rsatiladi —
        # guruhlar ro'yxati va havolalari yo'qolmasligi kerak.
        text, markup = await build_groups_window(uid, page=page)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
            )
        return

    if action == "find":
        # Avtomatik qidiruv — alohida oqim (🔍 Guruhlarni topish).
        await q.answer()
        from bot import groups as G

        await G.discover_groups(update)
        return

    if action == "global":
        # Umumiy interval — an'anaviy oqim.
        from bot import timer as Tm

        await q.answer()
        await Tm.begin_set_interval(update)
        return

    if action == "del":
        try:
            group_id = int(parts[2])
        except (ValueError, IndexError):
            return
        group = await db.get_chat_record(uid, group_id)
        if not group:
            await q.answer("Bu guruh topilmadi", show_alert=True)
            log_gap(uid, "Guruh topilmadi yoki o'chirilgan", action=data)
            return
        removed = await db.remove_chat_by_id(uid, group_id)
        if removed:
            # O'chirish izi logga yoziladi — keyin "guruhlar yo'q" holatida
            # nima bo'lganini tekshirish mumkin bo'ladi.
            log(f"🗑 {uid} guruh o'chirildi (foydalanuvchi): {group['value']}")
        await q.answer(
            f"🗑 O'chirildi: {group['value']}" if removed else "❌ O'chirilmadi",
            show_alert=True,
        )
        groups = await db.get_chat_records(uid)
        if not groups:
            with contextlib.suppress(Exception):
                await q.edit_message_text(
                    "💬 Guruhlar yopildi. Endi guruh yo'q.",
                    reply_markup=await _back_markup(uid),
                )
            return
        # ✅ Oyna to'liq yangilanadi — guruhlar ro'yxati va havolalari
        # ham ko'rinib turishi kerak (avval faqat sarlavha qolardi).
        text, markup = await build_groups_window(uid)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                text,
                parse_mode="HTML",
                reply_markup=markup,
            )
        return

    if action == "gint":
        try:
            group_id = int(parts[2])
        except (ValueError, IndexError):
            return
        await q.answer()
        await show_group_interval(update, uid, group_id)
        return

    if action == "set":
        if len(parts) < 4:
            return
        try:
            group_id = int(parts[2])
            minutes = int(parts[3])
        except (ValueError, IndexError):
            await q.answer("❌ Noto'g'ri qiymat", show_alert=True)
            return
        if not is_valid_interval(minutes):
            await q.answer(
                T.interval_invalid_min(), show_alert=True
            )
            return
        saved = await db.set_chat_interval(uid, group_id, minutes)
        if not saved:
            await q.answer("❌ Saqlanmadi", show_alert=True)
            return
        log(f"⏱ Guruh intervali: {uid} → {group_id} = {minutes} daqiqa")
        await q.answer(f"✅ {minutes} daqiqa", show_alert=True)
        await show_group_interval(
            update, uid, group_id, f"✅ {minutes} daqiqaga o'rnatildi."
        )
        return

    if action == "reset":
        try:
            group_id = int(parts[2])
        except (ValueError, IndexError):
            return
        saved = await db.set_chat_interval(uid, group_id, None)
        if not saved:
            await q.answer("❌ Saqlanmadi", show_alert=True)
            return
        await q.answer("↩️ Umumiy intervalga qaytarildi", show_alert=True)
        await show_group_interval(
            update, uid, group_id, "✅ Endi umumiy intervaldan foydalanadi."
        )
        return

    if action == "manual":
        try:
            group_id = int(parts[2])
        except (ValueError, IndexError):
            return
        from bot.login import user_states

        user_states[uid] = {
            "step": STEP_MANUAL_INTERVAL,
            "ts": time.time(),
            "group_id": group_id,
        }
        await q.answer()
        group = await db.get_chat_record(uid, group_id)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                f"✏️ {group['value'] if group else 'Guruh'} uchun "
                "intervalni daqiqada kiriting."
            )
        await update.message.reply_text(
            f"{T.MIN_INTERVAL_MIN}–{T.MAX_INTERVAL_MIN} daqiqada "
            "butun son kiriting:",
            reply_markup=KB.kb_input_cancel(),
        )
        return


async def handle_manual_interval(update: Update, uid: int, text: str) -> None:
    """Foydalanuvchi qo'lda interval kiritdi (``mg:manual`` dan keyin)."""
    from bot.login import user_states

    state = user_states.get(uid, {})
    try:
        group_id = int(state.get("group_id"))
    except (TypeError, ValueError):
        user_states.pop(uid, None)
        await update.message.reply_text(
            "❌ Guruh sozlamasi eskirdi. Qaytadan urinib ko'ring.",
            reply_markup=await _back_markup(uid),
        )
        return

    try:
        minutes = int(text.strip())
    except ValueError:
        await update.message.reply_text(T.INTERVAL_INVALID_NUMBER)
        return
    if not is_valid_interval(minutes):
        await update.message.reply_text(T.interval_invalid_min())
        return

    saved = await db.set_chat_interval(uid, group_id, minutes)
    user_states.pop(uid, None)
    if not saved:
        await update.message.reply_text(
            "❌ Guruh topilmadi yoki sozlama saqlanmadi.",
            reply_markup=await _back_markup(uid),
        )
        return

    log(f"⏱ Guruh intervali (qo'lda): {uid} → {group_id} = {minutes} daqiqa")
    await update.message.reply_text(
        f"✅ Guruh intervali {minutes} daqiqaga o'rnatildi.\n"
        "Umumiy interval boshqa guruhlarga o'zgarishsiz ta'sir qiladi.",
        reply_markup=await _back_markup(uid),
    )
