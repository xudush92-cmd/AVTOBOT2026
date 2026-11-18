"""Jamoa (team) tizimi — jamoa admini va uning foydalanuvchilari.

Oqim:
1. Oddiy foydalanuvchi ro'yxatdan o'tishda jamoani tanlaydi (tanlash
   ixtiyoriy — tanlamasa ham eski tartibda ishlaydi).
2. Tanlangan jamoa adminiga xabar boradi; admin foydalanuvchini tasdiqlab
   muddat (kun) beradi.
3. Jamoa admini faqat o'z jamoasini boshqaradi: tarif berish, bloklash,
   xabar yuborish, statistika ko'rish.
4. Jamoa adminining muddati tugasa — uning jamoasi ham to'xtaydi.

Super admin jamoa adminlarining muddati va sig'imi (limit)ni boshqaradi.
"""

from __future__ import annotations

import contextlib
import time

from telegram import Update

from bot import keyboards as KB
from bot import texts as T
from config.config import (
    BOT_USERNAME,
    DURATION_OPTIONS,
    SUPER_ADMIN,
    TEAM_ADMIN_DEFAULT_DAYS,
    TEAM_LIST_PAGE_SIZE,
    TEAM_MIN_MEMBERS,
)
from core import database as db
from core.logger import log
from core.utils import format_expires

application = None


def set_application(app) -> None:
    global application
    application = app


# ─────────────────────────────────────────────────────────────────────────
# YORDAMCHILAR
# ─────────────────────────────────────────────────────────────────────────
async def _send(chat_id: int, text: str, markup=None) -> bool:
    """Xabar yuborish. ``True`` — yuborildi, ``False`` — yuborilmadi."""
    if not application:
        return False
    try:
        await application.bot.send_message(chat_id, text, reply_markup=markup)
    except Exception:
        return False
    return True


def team_link(team_id: int) -> str:
    """Jamoa referal havolasi."""
    return f"https://t.me/{BOT_USERNAME}?start=team_{team_id}"


def admin_link(admin_uid: int) -> str:
    """Jamoa adminining shaxsiy havolasi."""
    return f"https://t.me/{BOT_USERNAME}?start=adm_{admin_uid}"


async def admin_teams(admin_uid: int) -> list[dict]:
    """Jamoa adminining o'z jamoalari."""
    return await db.get_teams(admin_uid)


async def primary_team(admin_uid: int) -> dict | None:
    """Jamoa adminining birinchi (asosiy) jamoasi."""
    teams = await admin_teams(admin_uid)
    return teams[0] if teams else None


def _expiry_text(value: str | None) -> str:
    if not value:
        return "—"
    return format_expires(value)


async def _is_team_admin(user: dict | None) -> bool:
    return bool(user and user.get("is_team_admin"))


async def _team_admin_active(admin_uid: int) -> bool:
    """Jamoa adminining muddati tugaganmi (jamoasi ham to'xtaydi)."""
    return not await db.team_admin_expired(admin_uid)


# ─────────────────────────────────────────────────────────────────────────
# RO'YXATDAN O'TISH — JAMOA TANLASH
# ─────────────────────────────────────────────────────────────────────────
async def show_team_picker(update: Update, uid: int, page: int = 0) -> None:
    """Jamoa tanlash oynasini ko'rsatadi."""
    teams = await db.get_all_teams()
    if not teams:
        await update.message.reply_text(
            T.TEAM_PICK_EMPTY,
            reply_markup=KB.kb_login(),
        )
        return

    text = T.team_pick_text(teams, page=page, page_size=TEAM_LIST_PAGE_SIZE)
    await update.message.reply_text(
        text,
        reply_markup=KB.kb_team_pick(teams, page=page, page_size=TEAM_LIST_PAGE_SIZE),
    )


async def handle_team_pick_callback(update: Update, uid: int, data: str) -> None:
    """Jamoa tanlash callback'lari."""
    q = update.callback_query
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "noop":
        return

    if action == "back":
        await q.edit_message_text(
            "🎯 Jamoa tanlash bekor qilindi.\n\nDavom etish uchun 🔑 Login bosing.",
            reply_markup=KB.kb_login(),
        )
        return

    if action == "skip":
        # Foydalanuvchi jamoasiz davom etmoqchi — ro'yxatdan o'tishga o'tadi.
        await q.edit_message_text(
            T.TEAM_PICK_SKIPPED,
            reply_markup=KB.kb_login(),
        )
        from bot.login import begin_login

        await begin_login(update)
        return

    if action == "page":
        try:
            page = max(0, int(parts[2]))
        except (ValueError, IndexError):
            page = 0
        teams = await db.get_all_teams()
        await q.edit_message_text(
            T.team_pick_text(teams, page=page, page_size=TEAM_LIST_PAGE_SIZE),
            reply_markup=KB.kb_team_pick(
                teams, page=page, page_size=TEAM_LIST_PAGE_SIZE
            ),
        )
        return

    if action == "pick":
        try:
            team_id = int(parts[2])
        except (ValueError, IndexError):
            return
        team = await db.get_team(team_id)
        if not team:
            await q.answer("Jamoa topilmadi", show_alert=True)
            return

        # Jamoada joy bormi?
        if not await db.team_has_free_slot(team_id):
            await q.answer(T.TEAM_PICK_FULL, show_alert=True)
            return

        owner_uid = int(team.get("owner_admin_uid") or 0)
        if owner_uid and owner_uid != SUPER_ADMIN:
            # Admin muddati tugagan bo'lsa — jamoa qabul qilmaydi.
            if not await _team_admin_active(owner_uid):
                await q.answer(T.TEAM_ADMIN_EXPIRED_SHORT, show_alert=True)
                return

        saved = await db.set_team_pending(
            uid,
            team_id,
            owner_uid,
            name=update.effective_user.full_name or "",
            username=update.effective_user.username or "",
        )
        if not saved:
            await q.answer("Jamoani biriktirib bo'lmadi", show_alert=True)
            return

        name = team.get("name") or "Noma'lum"
        await q.edit_message_text(
            T.TEAM_SELECTED.format(name=name),
            reply_markup=KB.kb_login(),
        )

        # Adminga xabar: tasdiqlashi kerak.
        user = await db.get_user(uid) or {}
        user_name = user.get("name") or "Yangi foydalanuvchi"
        await _send(
            owner_uid,
            f"🔔 YANGI ARIZA\n\n"
            f"👤 {user_name}\n"
            f"🆔 {uid}\n"
            f"📋 Jamoa: {name}\n\n"
            "Tasdiqlash va muddat berish uchun admin panelidan foydalaning.",
        )
        log(f"👥 Jamoa ariza: {uid} → jamoa #{team_id} (admin {owner_uid})")
        return


# ─────────────────────────────────────────────────────────────────────────
# ADMIN BO'LISH (jamoa yaratish)
# ─────────────────────────────────────────────────────────────────────────
# ─────────────────────────────────────────────────────────────────────────
# DO'ST QO'SHISH (telefon raqam bilan)
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_friend(update: Update, admin_uid: int) -> None:
    """Jamoa admini do'st qo'shish oynasini ochadi (telefon kiritish)."""
    from bot.login import user_states

    user = await db.get_user(admin_uid) or {}
    if not await _is_team_admin(user):
        await update.message.reply_text(
            "❌ Bu oynadan foydalanish huquqingiz yo'q.",
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    team = await primary_team(admin_uid)
    if not team:
        await update.message.reply_text(
            T.TEAM_ADMIN_NO_TEAM,
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    user_states[admin_uid] = {"step": "team_add_friend", "ts": time.time()}
    await update.message.reply_text(
        T.TEAM_ADD_FRIEND_ASK,
        reply_markup=KB.kb_input_cancel(),
    )


async def handle_add_friend_phone(update: Update, admin_uid: int, text: str) -> None:
    """Admin do'stning telefon raqamini kiritadi — jamoaga biriktiriladi."""
    from bot.login import user_states
    from core.utils import is_valid_phone, normalize_phone

    raw = (text or "").strip()
    phone = normalize_phone(raw)
    if not phone or not is_valid_phone(phone):
        await update.message.reply_text(
            T.TEAM_ADD_FRIEND_INVALID,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    team = await primary_team(admin_uid)
    if not team:
        user_states.pop(admin_uid, None)
        await update.message.reply_text(
            T.TEAM_ADMIN_NO_TEAM,
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    # Sig'im tekshiruvi — jamoa to'lgan bo'lsa yangi do'st qo'shilmaydi.
    if not await db.team_has_free_slot(int(team["id"])):
        user_states.pop(admin_uid, None)
        await update.message.reply_text(
            "🚫 Jamoa sig'imi to'lgan. Super admin limitni oshirishi kerak.",
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    # Allaqachon boshqa jamoaga biriktirilganmi?
    existing = await db.get_team_invite(phone, kind="member")
    if existing and int(existing.get("owner_admin_uid") or 0) != int(admin_uid):
        old_team = await db.get_team(int(existing.get("team_id") or 0))
        user_states.pop(admin_uid, None)
        await update.message.reply_text(
            T.TEAM_ADD_FRIEND_EXISTS.format(
                phone=phone,
                team=(old_team or {}).get("name") or "boshqa jamoa",
            ),
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    await db.add_team_invite(
        phone, admin_uid, team_id=int(team["id"]), kind="member"
    )
    user_states.pop(admin_uid, None)

    await update.message.reply_text(
        T.TEAM_ADD_FRIEND_DONE_WITH_ADMIN_LINK.format(
            phone=phone,
            team=team.get("name") or "Jamoangiz",
            link=team_link(int(team["id"])),
            admin_link=admin_link(admin_uid),
        ),
        reply_markup=await KB.kb_main_for(admin_uid),
    )
    log(f"➕ Do'st qo'shildi: admin {admin_uid} → {phone}")


async def show_team_invites(
    update: Update, admin_uid: int, edit: bool = False
) -> None:
    """Admin qo'shgan do'stlar ro'yxatini ko'rsatadi.

    ``edit=True`` — inline xabar holati (callback dan chaqirilganda).
    """
    team = await primary_team(admin_uid)
    if not team:
        text = T.TEAM_ADMIN_NO_TEAM
        markup = await KB.kb_main_for(admin_uid)
        invites = []
    else:
        invites = await db.get_team_invites(admin_uid)
        if not invites:
            text = T.TEAM_INVITES_EMPTY
            markup = KB.kb_team_admin_panel()
        else:
            text = T.TEAM_INVITES_TEXT.format(total=len(invites)) + (
                f"\n🔗 {team_link(int(team['id']))}"
            )
            markup = KB.kb_team_invites(invites)

    if edit:
        q = update.callback_query
        if q is not None:
            with contextlib.suppress(Exception):
                await q.edit_message_text(text, reply_markup=markup)
                return
    await update.message.reply_text(text, reply_markup=markup)


async def begin_team_admin_register(update: Update, uid: int) -> None:
    """Admin bo'lish oqimini boshlaydi (foydalanuvchi raqam kiritadi)."""
    from bot.login import user_states

    user = await db.get_user(uid) or {}
    if await _is_team_admin(user):
        await update.message.reply_text(
            "✅ Siz allaqachon jamoa adminisiz.",
            reply_markup=await KB.kb_main_for(uid),
        )
        return

    existing = await admin_teams(uid)
    if existing:
        await update.message.reply_text(
            f"✅ Sizning jamoangiz mavjud: {existing[0].get('name')}\n\n"
            "«👥 Jamoam» orqali boshqaring.",
            reply_markup=await KB.kb_main_for(uid),
        )
        return

    user_states[uid] = {"step": "team_admin_size", "ts": time.time()}
    await update.message.reply_text(
        T.TEAM_ADMIN_ASK_SIZE.format(min_users=TEAM_MIN_MEMBERS),
        reply_markup=KB.kb_input_cancel(),
    )


async def handle_team_admin_size(update: Update, uid: int, text: str) -> None:
    """Admin jamoasining sig'imini (user soni) kiritadi."""
    from bot.login import user_states

    raw = (text or "").strip()
    if not raw.isdigit():
        await update.message.reply_text(
            T.TEAM_ADMIN_SIZE_INVALID.format(min_users=TEAM_MIN_MEMBERS),
            reply_markup=KB.kb_input_cancel(),
        )
        return

    size = int(raw)
    if size < TEAM_MIN_MEMBERS:
        await update.message.reply_text(
            T.TEAM_ADMIN_SIZE_INVALID.format(min_users=TEAM_MIN_MEMBERS),
            reply_markup=KB.kb_input_cancel(),
        )
        return

    user_states[uid] = {
        "step": "team_admin_name",
        "ts": time.time(),
        "team_size": size,
    }
    await update.message.reply_text(
        T.TEAM_ADMIN_ASK_NAME,
        reply_markup=KB.kb_input_cancel(),
    )


async def handle_team_admin_name(update: Update, uid: int, text: str) -> None:
    """Admin jamoasining nomini kiritadi va jamoani yaratadi."""
    from bot.login import user_states

    name = " ".join((text or "").split())
    if not (2 <= len(name) <= 40):
        await update.message.reply_text(
            T.TEAM_ADMIN_NAME_INVALID,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    state = user_states.get(uid, {})
    size = int(state.get("team_size") or TEAM_MIN_MEMBERS)

    existing = await db.get_team_by_name(uid, name)
    if existing:
        await update.message.reply_text(
            T.TEAM_ADMIN_NAME_TAKEN,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    expires = _admin_expiry(TEAM_ADMIN_DEFAULT_DAYS)
    team = await db.create_team(name, uid, max_users=size, expires_at=expires)
    if not team:
        await update.message.reply_text(
            "❌ Jamoani yaratib bo'lmadi. Qaytadan urinib ko'ring.",
            reply_markup=KB.kb_input_cancel(),
        )
        return

    # Admin rolini beriladi: jamoa egasi.
    await db.set_team_admin(
        uid,
        int(team["id"]),
        max_users=size,
        admin_expires_at=expires,
    )
    # Jamoa admini ham o'z jamoasining a'zosi — lekin u allaqachon
    # tasdiqlangan (jamoani o'ziga yaratgan admin ustiga tasdiq kutilmaydi).
    await db.set_team_pending(uid, int(team["id"]), uid)
    await db.set_awaiting_approval(uid, False)
    # Jamoa admini ham oddiy foydalanuvchi kabi posting qila oladi.
    if not (await db.get_user(uid) or {}).get("is_admin"):
        await db.approve_user(uid, expires)

    user_states.pop(uid, None)
    log(f"👑 Yangi jamoa admini: {uid} — {name} (max {size})")

    # Super admin'ni xabardor qilamiz — muddat va sig'imni nazorat qilishi uchun.
    await notify_super_team_admin(uid, name, size)

    await update.message.reply_text(
        T.TEAM_ADMIN_REGISTERED.format(
            name=name,
            max_users=size,
            expires=_expiry_text(expires),
            link=team_link(int(team["id"])),
        ),
        reply_markup=await KB.kb_main_for(uid),
    )


async def notify_super_team_admin(uid: int, name: str, size: int) -> None:
    """Super admin'ga yangi jamoa admini haqida xabar beradi.

    Xabar muvaffaqiyatli bo'lmasa ham oqim buzilmaydi — xabarlar
    ehtimoliy yetkazib borilmagan deb hisoblanadi.
    """
    import contextlib

    try:
        from config.config import SUPER_ADMIN

        user = await db.get_user(uid) or {}
        display = user.get("name") or f"@{user.get('username') or uid}"
        text = (
            "👑 <b>Yangi jamoa admini ro'yxatdan o'tdi</b>\n\n"
            f"👤 Admin: {display}\n"
            f"📋 Jamoa: {name}\n"
            f"👥 Sig'im: {size} ta foydalanuvchi\n\n"
            "Muddatni va sig'imni tasdiqlash uchun: "
            "«Jamoa adminlari» bo'limiga o'ting."
        )
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                SUPER_ADMIN, text, parse_mode="HTML"
            )
    except Exception as exc:  # pragma: no cover - xabar yetkazish ixtisosiy
        log(f"⚠️ Super admin'ga jamoa admini xabari yuborilmadi: {exc}", "warning")


def _admin_expiry(days: int) -> str:
    """``days`` kunlik muddat sanasi (bazadagi muddat formati)."""
    from core.utils import calc_expires

    return calc_expires(max(1, int(days)))


# ─────────────────────────────────────────────────────────────────────────
# JAMOA ADMINI PANELI
# ─────────────────────────────────────────────────────────────────────────
async def show_team_admin_panel(update: Update, admin_uid: int) -> None:
    """Jamoa admini panelining asosiy oynasi."""
    team = await primary_team(admin_uid)
    if not team:
        await update.message.reply_text(
            T.TEAM_ADMIN_NO_TEAM,
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    members = await db.count_team_members(int(team["id"]))
    expires = await db.get_user(admin_uid) or {}

    # Muddati tugagan jamoa admini — ogohlantiriladi.
    if await db.team_admin_expired(admin_uid):
        await update.message.reply_text(
            T.TEAM_ADMIN_EXPIRED.format(
                expires=_expiry_text(expires.get("admin_expires_at"))
            ),
            reply_markup=await KB.kb_main_for(admin_uid),
        )
        return

    await update.message.reply_text(
        T.team_admin_menu_text(
            team,
            members=members,
            expires=_expiry_text(expires.get("admin_expires_at") or team.get("expires_at")),
        ),
        reply_markup=KB.kb_team_admin_panel(),
    )


async def _stop_member_worker(uid: int) -> None:
    """A'zoning e'lon yuborishini darhol to'xtatadi (bloklashda)."""
    with contextlib.suppress(Exception):
        from bot.menu import worker_manager

        if worker_manager:
            await worker_manager.stop_worker(uid)
    with contextlib.suppress(Exception):
        await db.set_running(uid, False)


async def show_team_member_panel(update: Update, uid: int) -> None:
    """Oddiy jamoa a'zosi uchun jamoa kartasi va chiqish tugmasi."""
    user = await db.get_user(uid) or {}
    team_id = int(user.get("team_id") or 0)

    if not team_id:
        await update.message.reply_text(
            T.TEAM_ADMIN_NO_TEAM,
            reply_markup=await KB.kb_main_for(uid),
        )
        return

    team = await db.get_team(team_id)
    if not team:
        # Jamoa bazadan o'chirilgan — foydalanuvchini tozalaymiz.
        await db.leave_team(uid)
        await update.message.reply_text(
            "ℹ️ Jamoangiz endi mavjud emas.\n\n"
            "👑 «Admin bo'lish» tugmasi orqali yangi jamoa yaratishingiz mumkin.",
            reply_markup=await KB.kb_main_for(uid),
        )
        return

    await update.message.reply_text(
        T.TEAM_MEMBER_INFO.format(
            name=team.get("name") or "Jamoa",
            expires=_expiry_text(user.get("tariff_expires_at")),
        ),
        reply_markup=KB.kb_team_member_self_card(),
    )


async def handle_team_member_callback(update: Update, uid: int, data: str) -> None:
    """Oddiy jamoa a'zosi callback'lari — jamoadan chiqish."""
    q = update.callback_query
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    user = await db.get_user(uid) or {}
    team_id = int(user.get("team_id") or 0)
    if not team_id:
        await q.answer(
            "Siz jamoada emassingiz", show_alert=True
        )
        return

    team = await db.get_team(team_id)
    team_name = (team or {}).get("name") or "Jamoa"

    if action == "leaveask":
        await q.edit_message_text(
            T.TEAM_MEMBER_LEAVE_CONFIRM.format(name=team_name),
            reply_markup=KB.kb_team_leave_confirm(),
        )
        return

    if action == "leavecancel":
        await q.edit_message_text(
            T.TEAM_MEMBER_LEAVE_CANCELLED,
            reply_markup=KB.kb_team_member_self_card(),
        )
        return

    if action == "leaveconfirm":
        # Jamoa admini o'z jamoasidan chiqmaydi.
        if user.get("is_team_admin"):
            await q.answer(
                "Jamoa egasi jamoasidan chiqmaydi", show_alert=True
            )
            return

        # Jamoa adminiga xabar — a'zo ketdi.
        owner_uid = int(user.get("owner_admin_uid") or 0)
        result = await db.leave_team(uid)
        if not result:
            await q.answer(
                "Jamoadan chiqib bo'lmadi", show_alert=True
            )
            return

        # E'lon yuborish to'xtatiladi — muddat ham tugadi.
        await db.set_running(uid, False)

        if owner_uid:
            with contextlib.suppress(Exception):
                await application.bot.send_message(
                    owner_uid,
                    f"👋 A'zo ketdi: <b>{user.get('name') or uid}</b>\n\n"
                    f"📋 Jamoa: {team_name}\n"
                    "ℹ️ Uning muddati ham tugdi.",
                    parse_mode="HTML",
                )

        await q.edit_message_text(
            T.TEAM_MEMBER_LEFT.format(name=team_name),
            reply_markup=await KB.kb_main_for(uid),
        )
        log(f"👋 {uid} jamoadan chiqdi: {team_name}")
        return


async def handle_team_admin_callback(update: Update, uid: int, data: str) -> None:
    """Jamoa admini paneli callback'lari."""
    q = update.callback_query
    parts = data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    user = await db.get_user(uid) or {}
    if not await _is_team_admin(user):
        await q.answer("Bu oynadan foydalanish huquqingiz yo'q", show_alert=True)
        return

    if action == "noop":
        return

    if action == "back":
        await show_team_admin_panel(update, uid)
        return

    if action == "addfriend":
        await begin_add_friend(update, uid)
        return

    if action == "invites":
        await show_team_invites(update, uid, edit=True)
        return

    if action == "delinvite":
        phone = parts[2] if len(parts) > 2 else ""
        invite = await db.get_team_invite(phone, kind="member")
        if not invite or int(invite.get("owner_admin_uid") or 0) != uid:
            await q.answer(
                "Bu taklif sizning jamoangizga tegishli emas", show_alert=True
            )
            return
        await db.delete_team_invite(phone, kind="member")
        await q.answer(f"🗑 {phone} bekor qilindi", show_alert=True)
        await show_team_invites(update, uid, edit=True)
        return

    if action == "link":
        team = await primary_team(uid)
        if not team:
            await q.answer(T.TEAM_ADMIN_NO_TEAM, show_alert=True)
            return
        await q.edit_message_text(
            "🔗 <b>Jamoangiz havolalari</b>\n\n"
            "Do'stlaringizga yuboring — ular avtomatik sizning jamoangizga "
            "birikadi va siz tasdiqlaysiz.\n\n"
            f"🔗 Jamoa havolasi:\n{team_link(int(team['id']))}\n\n"
            f"🔗 Shaxsiy havolangiz:\n{admin_link(uid)}",
            parse_mode="HTML",
            reply_markup=KB.kb_team_admin_panel(),
        )
        return

    if action == "users":
        try:
            page = max(0, int(parts[2]))
        except (ValueError, IndexError):
            page = 0
        team = await primary_team(uid)
        if not team:
            await q.answer(T.TEAM_ADMIN_NO_TEAM, show_alert=True)
            return
        members = await db.get_team_members(int(team["id"]))
        await q.edit_message_text(
            T.team_members_text(members),
            reply_markup=KB.kb_team_members(members, page=page),
        )
        return

    if action == "member":
        try:
            target = int(parts[2])
        except (ValueError, IndexError):
            return
        member = await db.get_user(target)
        if not member:
            await q.answer("Foydalanuvchi topilmadi", show_alert=True)
            return
        # Faqat o'z jamoasining a'zosiga murojaat qila oladi.
        if int(member.get("owner_admin_uid") or 0) != uid:
            await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
            return
        await q.edit_message_text(
            T.TEAM_ADMIN_MEMBER_INFO.format(
                name=member.get("name") or "Noma'lum",
                uid=target,
                team=(await primary_team(uid) or {}).get("name") or "—",
                expires=_expiry_text(member.get("tariff_expires_at")),
                status=_member_status(member),
            ),
            reply_markup=KB.kb_team_member_card(
                target, awaiting=bool(member.get("awaiting_approval"))
            ),
        )
        return

    if action == "term":
        try:
            target = int(parts[2])
        except (ValueError, IndexError):
            return
        member = await db.get_user(target)
        if not member or int(member.get("owner_admin_uid") or 0) != uid:
            await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
            return

        # Chegara: faqat chegaragacha muddat ko'rsatiladi.
        from core.duration_policy import cap_note, options_within_cap

        options = options_within_cap(DURATION_OPTIONS, is_super_admin=False)
        note = cap_note(is_super_admin=False)
        text = T.TEAM_ADMIN_GIVE_TERM.format(
            name=member.get("name") or "Noma'lum",
            uid=target,
        )
        if note:
            text += f"\n\n{note}"
        await q.edit_message_text(
            text,
            reply_markup=KB.kb_team_term_options(target, options),
        )
        return

    if action == "setterm":
        try:
            target = int(parts[2])
            days = int(parts[3])
        except (ValueError, IndexError):
            return
        member = await db.get_user(target)
        if not member or int(member.get("owner_admin_uid") or 0) != uid:
            await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
            return

        # Chegara: jamoa admini a'zosiga belgilangan maksimal muddatdan
        # ko'p kun bera olmaydi (firibgar adminlardan himoya).
        from core.duration_policy import clamp_days, is_over_cap, max_days_for

        if is_over_cap(days, is_super_admin=False):
            cap = max_days_for(is_super_admin=False)
            await q.answer(
                f"⛔️ Maksimal muddat {cap} kun. Super admin bilan bog'laning.",
                show_alert=True,
            )
            return

        days = clamp_days(days, is_super_admin=False)
        expires = _admin_expiry(days)
        await db.set_user_limits(target, tariff_expires_at=expires)
        await db.approve_user(target, expires)
        team = await primary_team(uid)
        await q.edit_message_text(
            T.TEAM_ADMIN_TERM_SET.format(
                name=member.get("name") or "Noma'lum",
                expires=_expiry_text(expires),
                team=(team or {}).get("name") or "—",
            ),
            reply_markup=KB.kb_team_member_card(target),
        )
        await _send(
            target,
            T.TEAM_APPROVED.format(
                name=(team or {}).get("name") or "Jamoangiz",
                expires=_expiry_text(expires),
            ),
        )
        log(f"📅 Muddat berildi: admin {uid} → user {target} ({days} kun)")
        return

    if action == "block":
        try:
            target = int(parts[2])
        except (ValueError, IndexError):
            return
        member = await db.get_user(target)
        if not member or int(member.get("owner_admin_uid") or 0) != uid:
            await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
            return
        await db.set_user_limits(target, is_blocked=1)
        # E'lon yuborish darhol to'xtatiladi.
        await _stop_member_worker(target)
        await q.answer("🚫 Foydalanuvchi bloklandi", show_alert=True)
        await _send(target, T.BLOCKED)
        return

    if action == "unblock":
        try:
            target = int(parts[2])
        except (ValueError, IndexError):
            return
        member = await db.get_user(target)
        if not member or int(member.get("owner_admin_uid") or 0) != uid:
            await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
            return
        await db.set_user_limits(target, is_blocked=0)
        await q.answer("✅ Blokdan chiqarildi", show_alert=True)
        await _send(target, "✅ Blokdan chiqarildingiz. Botdan foydalanishingiz mumkin.")
        return

    if action == "kick":
        try:
            target = int(parts[2])
        except (ValueError, IndexError):
            return
        member = await db.get_user(target)
        if not member or int(member.get("owner_admin_uid") or 0) != uid:
            await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
            return
        # Jamoa egasi jamoasidan chiqarilmaydi.
        if member.get("is_team_admin"):
            await q.answer("Jamoa egasi jamoasidan chiqarilmaydi", show_alert=True)
            return

        team = await primary_team(uid)
        team_name = (team or {}).get("name") or "Jamoangiz"
        result = await db.leave_team(target)
        if not result:
            await q.answer("Jamoadan chiqarib bo'lmadi", show_alert=True)
            return

        await _stop_member_worker(target)
        await q.answer(
            f"🚪 {member.get('name') or target} jamoadan chiqarildi",
            show_alert=True,
        )
        await q.edit_message_text(
            f"🚪 <b>{member.get('name') or target}</b> jamoadan chiqarildi.\n\n"
            f"📋 Jamoa: {team_name}\n"
            "ℹ️ Uning jamoa muddati ham tugdi.",
            parse_mode="HTML",
            reply_markup=KB.kb_team_admin_panel(),
        )
        with contextlib.suppress(Exception):
            await _send(
                target,
                f"🚪 Siz <b>{team_name}</b> jamoasidan chiqarildingiz.\n\n"
                "ℹ️ Jamoa muddati ham tugdi.",
            )
        log(f"🚪 Admin {uid} → a'zoni jamoadan chiqardi: {target}")
        return

    if action == "stats":
        team = await primary_team(uid)
        if not team:
            await q.answer(T.TEAM_ADMIN_NO_TEAM, show_alert=True)
            return
        members = await db.get_team_members(int(team["id"]))
        stats = {
            "total": len(members),
            "running": sum(1 for m in members if m.get("running")),
            "waiting": sum(1 for m in members if m.get("awaiting_approval")),
            "blocked": sum(1 for m in members if m.get("is_blocked")),
            "groups": sum(await db.count_chats(int(m["uid"])) for m in members),
            "posts": sum(await db.count_posts(int(m["uid"])) for m in members),
        }
        await q.edit_message_text(
            T.TEAM_ADMIN_STATS.format(**stats),
            reply_markup=KB.kb_team_admin_panel(),
        )
        return

    if action == "message":
        from bot.login import user_states

        team = await primary_team(uid)
        if not team:
            await q.answer(T.TEAM_ADMIN_NO_TEAM, show_alert=True)
            return
        user_states[uid] = {"step": "team_admin_message", "ts": time.time()}
        await q.edit_message_text(
            T.TEAM_ADMIN_MESSAGE,
            reply_markup=KB.kb_input_cancel(),
        )
        return

    if action == "approve":
        try:
            target = int(parts[2])
        except (ValueError, IndexError):
            return
        # Avval muddatni tanlash — keyin tasdiqlash.
        from core.duration_policy import cap_note, options_within_cap

        options = options_within_cap(DURATION_OPTIONS, is_super_admin=False)
        note = cap_note(is_super_admin=False)
        text = "📅 Muddatni tanlang — foydalanuvchiga qancha kun beriladi?"
        if note:
            text += f"\n{note}"
        await q.edit_message_text(
            text,
            reply_markup=KB.kb_team_approve_term_options(target, options),
        )
        return

    if action == "approveterm":
        try:
            target = int(parts[2])
            days = int(parts[3])
        except (ValueError, IndexError):
            return
        await approve_team_member(update, uid, target, days=days)
        return


def _member_status(member: dict) -> str:
    if member.get("awaiting_approval"):
        return "⏳ Tasdiq kutilmoqda"
    if member.get("is_blocked"):
        return "🚫 Bloklangan"
    if T.member_expired(member):
        return "⌛ Muddati tugagan"
    if member.get("running"):
        return "🟢 Ishlamoqda"
    return "⚪ To'xtatilgan"


async def approve_team_member(
    update: Update,
    admin_uid: int,
    target: int,
    days: int | None = None,
) -> None:
    """Jamoa admini o'z jamoasidagi foydalanuvchini tasdiqlaydi.

    ``days`` — beriladigan muddat (kun). Berilmasa standart
    Standart muddat ishlatiladi (chegara bilan cheklangan).
    """
    q = update.callback_query
    member = await db.get_user(target)
    if not member:
        await q.answer("Foydalanuvchi topilmadi", show_alert=True)
        return

    # Faqat o'z jamoasining a'zosini tasdiqlaydi.
    if int(member.get("owner_admin_uid") or 0) != admin_uid:
        await q.answer("Bu foydalanuvchi sizning jamoangizda emas", show_alert=True)
        return

    if not member.get("awaiting_approval"):
        await q.answer("Ariya allaqachon ko'rib chiqilgan", show_alert=True)
        return

    # Jamoa sig'imi to'lgan bo'lsa — yangi a'zo qabul qilinmaydi.
    team_id = int(member.get("team_id") or 0)
    team = await db.get_team(team_id) if team_id else None
    if team:
        limit = int(team.get("max_users") or 0)
        members = await db.get_team_members(team_id)
        if limit and len(members) > limit:
            await q.answer(
                f"🚫 Jamoa sig'imi to'lgan ({limit} ta)", show_alert=True
            )
            return

    # Beriladigan muddat (kun). Jamoa admini uchun chegara bor —
    # firibgar adminlardan himoya.
    from core.duration_policy import clamp_days

    duration_days = clamp_days(days, is_super_admin=False)
    expires = _admin_expiry(duration_days)
    await db.approve_user(target, expires)

    team_name = (team or {}).get("name") or "Jamoangiz"
    await q.edit_message_text(
        T.TEAM_ADMIN_TERM_SET.format(
            name=member.get("name") or "Noma'lum",
            expires=_expiry_text(expires),
            team=team_name,
        ),
        reply_markup=KB.kb_team_member_card(target),
    )
    await _send(
        target,
        T.TEAM_APPROVED.format(
            name=team_name,
            expires=_expiry_text(expires),
        ),
    )
    log(f"✅ Jamoa admini tasdiqladi: {admin_uid} → user {target}")


async def send_team_message(update: Update, uid: int, text: str) -> None:
    """Jamoa admini jamoasiga xabar yuboradi."""
    from bot.login import user_states

    user_states.pop(uid, None)
    team = await primary_team(uid)
    if not team:
        await update.message.reply_text(T.TEAM_ADMIN_NO_TEAM)
        return

    members = await db.get_team_members(int(team["id"]))
    sent = 0
    for member in members:
        target = int(member["uid"])
        if target == uid:
            continue
        if await _send(target, text):
            sent += 1

    await update.message.reply_text(
        T.TEAM_ADMIN_MESSAGE_SENT.format(count=sent),
        reply_markup=await KB.kb_main_for(uid),
    )
    log(f"📨 Jamoa xabari: admin {uid} → {sent} ta foydalanuvchi")
