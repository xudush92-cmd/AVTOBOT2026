"""
⏰ Vaqt (interval) ni sozlash.

Funksiyalar:
- Boshlash (⏰ Vaqt tugmasi bosilganda)
- Qiymatni qabul qilish
- Tekshirish va saqlash
"""

from __future__ import annotations

import time

from telegram import Update

from bot import action_tokens
from bot import keyboards as KB
from bot import texts as T
from core import database as db
from core.logger import log
from core.utils import (
    edit_text_safe,
    group_label,
    is_valid_interval,
    reply_text_safe,
)


# ─────────────────────────────────────────────────────────────────────────
# BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_set_interval(update: Update) -> None:
    """⏰ Vaqt tugmasi bosilganda.

    Bu oyna ham matnli xabardan, ham inline tugmadan («mg:global»)
    ochilishi mumkin — shuning uchun `reply_text_safe` ishlatiladi.
    """
    uid = update.effective_user.id
    from bot.login import user_states

    current = await db.get_interval(uid)
    user_states[uid] = {"step": "set_interval", "ts": time.time()}

    await reply_text_safe(
        update,
        T.ask_interval(current),
        reply_markup=KB.kb_input_cancel(),
    )


# ─────────────────────────────────────────────────────────────────────────
# QIYMATNI QABUL QILISH
# ─────────────────────────────────────────────────────────────────────────
async def handle_set_interval(update: Update, text: str) -> None:
    """Foydalanuvchi yangi interval qiymatini kiritdi."""
    uid = update.effective_user.id
    value_text = text.strip()

    # Son emasmi?
    try:
        minutes = int(value_text)
    except ValueError:
        await update.message.reply_text(T.INTERVAL_INVALID_NUMBER)
        return

    # Minimal tekshirish
    if not is_valid_interval(minutes):
        await update.message.reply_text(T.interval_invalid_min())
        return

    # Bir kundan oshsa qo'shimcha tasdiq so'raymiz.
    if minutes > 1440:
        # 1 kundan oshsa — tasdiq so'raymiz
        from bot.login import user_states as us

        token = action_tokens.issue(uid, "interval")
        us[uid] = {
            "step": "set_interval_confirm",
            "ts": time.time(),
            "value": minutes,
            "token": token,
        }
        await update.message.reply_text(
            f"⚠️ Siz {minutes} daqiqa (~{minutes // 60} soat) kiritdingiz.\n\n"
            "Bu juda katta qiymat. Davom etamizmi?",
            reply_markup=KB.kb_yes_no(
                f"intv:yes:{token}",
                f"intv:no:{token}",
            ),
        )
        return

    # Saqlash
    await save_interval(uid, minutes, update)


async def save_interval(uid: int, minutes: int, update: Update) -> None:
    """Umumiy intervalni bazaga saqlash va xabar yuborish."""
    from bot.login import user_states

    user_states.pop(uid, None)
    await db.set_interval(uid, minutes)
    log(f"⏰ Umumiy interval: {uid} → {minutes} daqiqa")

    user = await db.get_user(uid)
    running = bool(user and user.get("running")) if user else False

    await update.message.reply_text(
        T.interval_set(minutes),
        reply_markup=await KB.kb_main_for(uid, running=running),
    )


# ─────────────────────────────────────────────────────────────────────────
# GURUHGA ALOHIDA INTERVAL
# ─────────────────────────────────────────────────────────────────────────
async def begin_set_group_interval(update: Update) -> None:
    """Guruhlar menyusidan alohida interval tanlashni boshlaydi."""
    uid = update.effective_user.id
    groups = await db.get_chat_records(uid)
    if not groups:
        from bot import my_groups as MG

        await MG.render_groups_inline(update, uid)
        return

    global_interval = await db.get_interval(uid)
    await update.message.reply_text(
        T.GROUP_INTERVAL_PICK,
        reply_markup=KB.kb_group_interval_picker(groups, global_interval),
    )


async def _show_group_interval_options(
    update: Update,
    uid: int,
    group_id: int,
    note: str = "",
) -> None:
    q = update.callback_query
    group = await db.get_chat_record(uid, group_id)
    if not group:
        await edit_text_safe(q, "❌ Guruh topilmadi yoki o'chirilgan.")
        return

    global_interval = await db.get_interval(uid)
    custom_interval = group.get("interval_min")
    if custom_interval is None:
        selected = f"Umumiy ({global_interval} daqiqa)"
    else:
        selected = f"Alohida ({int(custom_interval)} daqiqa)"
    text = (
        f"⏱ GURUH INTERVALI\n\n"
        f"Guruh: {group_label(group)}\n"
        f"Hozirgi sozlama: {selected}\n"
        f"Umumiy interval: {global_interval} daqiqa\n\n"
        "Kerakli alohida intervalni tanlang yoki umumiy sozlamaga qaytaring."
    )
    if note:
        text = f"{note}\n\n{text}"
    await edit_text_safe(
        q,
        text,
        reply_markup=KB.kb_group_interval_options(group_id, custom_interval),
    )


async def handle_group_interval_callback(update: Update, uid: int, data: str) -> None:
    """Foydalanuvchining guruh intervali inline callback'larini bajaradi."""
    q = update.callback_query
    parts = data.split(":")
    if len(parts) < 2 or parts[0] != "gint":
        return
    action = parts[1]
    from bot.login import user_states

    if (
        action in {"back", "list", "select", "set", "reset"}
        and user_states.get(uid, {}).get("step") == "set_group_interval"
    ):
        user_states.pop(uid, None)

    if action == "back":
        from bot import my_groups as MG

        # ``edit=True`` — inline kontekstda xabarni tahrirlaydi.
        # Aks holda ``update.message.reply_text`` chaqiriladi va
        # inline callback'da ``NoneType.reply_text`` xatosi chiqadi.
        await MG.render_groups_inline(update, uid, edit=True)
        return

    if action == "list":
        try:
            page = max(0, int(parts[2])) if len(parts) > 2 else 0
        except ValueError:
            page = 0
        groups = await db.get_chat_records(uid)
        if not groups:
            await edit_text_safe(q, T.GROUP_INTERVALS_EMPTY)
            return
        await edit_text_safe(
            q,
            T.GROUP_INTERVAL_PICK,
            reply_markup=KB.kb_group_interval_picker(
                groups, await db.get_interval(uid), page
            ),
        )
        return

    if action not in {"select", "set", "reset", "manual"} or len(parts) < 3:
        return
    try:
        group_id = int(parts[2])
    except ValueError:
        await edit_text_safe(q, "❌ Guruh ID noto'g'ri.")
        return

    group = await db.get_chat_record(uid, group_id)
    if not group:
        await edit_text_safe(q, "❌ Guruh topilmadi yoki o'chirilgan.")
        return

    if action == "manual":
        user_states[uid] = {
            "step": "set_group_interval",
            "ts": time.time(),
            "group_id": group_id,
        }
        await edit_text_safe(
            q,
            f"✏️ {group_label(group)} uchun intervalni daqiqada yuboring.",
        )
        # ⚠️ ``reply_text_safe`` — inline kontekstda ham ishlaydi
        # (``q.message`` inline callback'da None bo'ladi).
        await reply_text_safe(
            update,
            f"{T.MIN_INTERVAL_MIN}–{T.MAX_INTERVAL_MIN} daqiqada "
            "butun son kiriting:",
            reply_markup=KB.kb_input_cancel(),
        )
        return

    if action == "reset":
        if not await db.set_chat_interval(uid, group_id, None):
            await edit_text_safe(q, "❌ Guruh sozlamasi saqlanmadi.")
            return
        log(f"⏱ Guruh intervali umumiyga qaytdi: {uid} → {group_id}")
        await _show_group_interval_options(
            update, uid, group_id, "✅ Endi guruh umumiy intervaldan foydalanadi."
        )
        return

    if action == "set":
        if len(parts) != 4:
            return
        try:
            minutes = int(parts[3])
        except ValueError:
            await edit_text_safe(q, T.INTERVAL_INVALID_NUMBER)
            return
        if not is_valid_interval(minutes):
            await edit_text_safe(q, T.interval_invalid_min())
            return
        if not await db.set_chat_interval(uid, group_id, minutes):
            await edit_text_safe(q, "❌ Guruh sozlamasi saqlanmadi.")
            return
        log(f"⏱ Guruh intervali: {uid} → {group_id} = {minutes} daqiqa")
        await _show_group_interval_options(
            update,
            uid,
            group_id,
            f"✅ Alohida interval {minutes} daqiqaga o'rnatildi.",
        )
        return

    await _show_group_interval_options(update, uid, group_id)


async def handle_set_group_interval(update: Update, text: str) -> None:
    """Foydalanuvchi guruh uchun intervalni qo'lda kiritdi."""
    from bot.login import user_states

    uid = update.effective_user.id
    state = user_states.get(uid, {})
    try:
        group_id = int(state.get("group_id"))
    except (TypeError, ValueError):
        user_states.pop(uid, None)
        await update.message.reply_text(
            "❌ Guruh sozlamasi eskirdi. Qaytadan urinib ko'ring.",
            reply_markup=await KB.kb_main_for(uid),
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
            reply_markup=await KB.kb_main_for(uid),
        )
        return

    log(f"⏱ Guruh intervali: {uid} → {group_id} = {minutes} daqiqa")
    await update.message.reply_text(
        f"✅ Guruh intervali {minutes} daqiqaga o'rnatildi.\n"
        "Umumiy interval boshqa guruhlarga o'zgarishsiz ta'sir qiladi.",
        reply_markup=await KB.kb_main_for(uid),
    )
