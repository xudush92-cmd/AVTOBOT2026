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

import contextlib
import time

from telegram import Update

from bot import keyboards as KB
from bot import texts as T
from core import database as db
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
    groups = await db.get_chat_records(uid)

    if not groups:
        text = (
            "💬 <b>GURUHLAR</b>\n\n"
            "Sizda hali guruh yo'q.\n\n"
            "«🔍 Guruhlarni topish» tugmasi orqali Telegram'dagi "
            "guruhlaringizni avtomatik toping va qo'shing."
        )
        if note:
            text = f"{note}\n\n{text}"
        markup = KB.kb_my_groups([], 0)
        if edit and update.callback_query is not None:
            with contextlib.suppress(Exception):
                await update.callback_query.edit_message_text(
                    text, parse_mode="HTML", reply_markup=markup
                )
                return
        await update.message.reply_text(
            text, parse_mode="HTML", reply_markup=markup
        )
        return

    max_page = max(0, (len(groups) - 1) // PAGE_SIZE)
    page = min(max(page, 0), max_page)

    # Guruh havolalari — raqam bilan. Yopiq guruhlarda havola yo'q.
    links: list[str] = []
    for item in groups:
        link = public_link(str(item.get("value") or ""))
        if link:
            links.append(link)
    links_block = ""
    if links:
        numbered = "\n".join(
            f"{idx}. {escape_html(link)}"
            for idx, link in enumerate(links, start=1)
        )
        links_block = f"\n\n<b>🔗 Guruh havolalari:</b>\n\n{numbered}"

    text = (
        "💬 <b>GURUHLAR</b>\n\n"
        f"Guruhlar soni: {len(groups)} ta"
        f"{links_block}\n\n"
        "Quyidagi <b>🗑</b> tugmalari orqali guruhni o'chirish mumkin."
    )
    if note:
        text = f"{note}\n\n{text}"
    markup = KB.kb_my_groups(groups, page)
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

    if action == "back":
        await q.answer()
        with contextlib.suppress(Exception):
            await q.edit_message_text("💬 Guruhlar yopildi.")
        from bot.menu import show_home

        await show_home(update, uid)
        return

    if action == "page":
        try:
            page = max(0, int(parts[2]))
        except (ValueError, IndexError):
            return
        await q.answer()
        groups = await db.get_chat_records(uid)
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                "💬 <b>GURUHLAR</b>",
                parse_mode="HTML",
                reply_markup=KB.kb_my_groups(groups, page),
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
            return
        removed = await db.remove_chat_by_id(uid, group_id)
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
        with contextlib.suppress(Exception):
            await q.edit_message_text(
                "💬 <b>GURUHLAR</b>",
                parse_mode="HTML",
                reply_markup=KB.kb_my_groups(groups, 0),
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
