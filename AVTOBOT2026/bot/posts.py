"""Postlar bilan ishlash.

Imkoniyatlar:
- post qo'shish (matn / rasm / video / fayl / 2–10 ta rasmdan albom);
- postni tahrirlash (eski post o'chirib qayta yozish shart emas);
- post ko'rinishi (preview) va bitta guruhga sinov yuborish;
- post o'chirish va ro'yxatni ko'rsatish.

Albom Telegram tomonidan har bir faylni ALOHIDA xabar qilib yuboradi, shu
sabab ular ``media_group_id`` bo'yicha bir necha soniya davida yig'iladi va
yakunda bitta post sifatida saqlanadi.
"""

from __future__ import annotations

import asyncio
import contextlib
import time

from telegram import (
    InputMediaPhoto,
    InputMediaVideo,
    MessageEntity,
    Update,
)
from telegram.constants import MessageEntityType

from bot import keyboards as KB
from bot import texts as T
from bot.media_ingest import (
    download_message_media,
    entity_to_dict,
    message_text_and_entities,
    post_media_paths,
    remove_media,
    user_media_dir,
)
from config.config import ALBUM_DEBOUNCE_S, MAX_ALBUM_FILES
from core import database as db
from core.logger import log
from core.utils import media_kind_label, truncate

# Eski importlar uchun qayta eksport (main.py/admin shu nomlarni ishlatadi).
__all__ = [
    "begin_add_post",
    "begin_add_post_state",
    "begin_edit_post_state",
    "begin_edit_post",
    "delete_post_by_id",
    "delete_post_by_index",
    "entity_to_dict",
    "finalize_pending_album",
    "handle_add_post",
    "preview_post",
    "send_test_to_group",
    "show_posts",
    "begin_test_picker",
    "sweep_stale_albums",
    "user_media_dir",
    "begin_delete_posts",
]


# ─────────────────────────────────────────────────────────────────────────
# ENTITY KONVERTORLARI
# ─────────────────────────────────────────────────────────────────────────
def dicts_to_ptb_entities(items: list[dict]) -> list[MessageEntity]:
    """DB'dagi entity dict'larini PTB MessageEntity'lariga aylantiradi."""
    from telegram import User

    known = {item.value for item in MessageEntityType}
    out: list[MessageEntity] = []
    for item in items or []:
        entity_type = item.get("type")
        if entity_type not in known:
            continue
        try:
            out.append(
                MessageEntity(
                    type=entity_type,
                    offset=int(item.get("offset", 0)),
                    length=int(item.get("length", 0)),
                    url=item.get("url") or None,
                    language=item.get("language") or None,
                    custom_emoji_id=item.get("custom_emoji_id") or None,
                    user=(
                        User(id=int(item["user_id"]), is_bot=False, username="user")
                        if item.get("user_id")
                        else None
                    ),
                )
            )
        except Exception:
            continue
    return out


def _state(uid: int) -> dict | None:
    """FSM holatini YARATMASDAN o'qiydi (begona holat qoldirmaslik uchun)."""
    from bot.login import user_states

    return user_states.get(uid)


def _ensure_state(uid: int) -> dict:
    """FSM holatini ochish uchun (yo'q bo'lsa yaratadi)."""
    from bot.login import user_states

    return user_states.setdefault(uid, {})


def _clear_state(uid: int) -> None:
    from bot.login import user_states

    user_states.pop(uid, None)


# ─────────────────────────────────────────────────────────────────────────
# POSTLAR RO'YXATI
# ─────────────────────────────────────────────────────────────────────────
async def show_posts(update: Update) -> None:
    """📝 Postlar ro'yxati va amallar menyusini ko'rsatadi."""
    uid = update.effective_user.id
    posts = await db.get_posts(uid)
    limits = await db.get_limits(uid)
    header = _posts_header(len(posts), limits)

    if not posts:
        await update.message.reply_text(
            header + "\n" + T.POSTS_EMPTY, reply_markup=KB.kb_posts_menu()
        )
        return

    lines = [header]
    for index, post in enumerate(posts, 1):
        preview = truncate((post.get("text") or "(media)").strip().replace("\n", " "), 70)
        count = len(post.get("media") or [])
        badge = f" 🖼×{count}" if count > 1 else (" 🖼" if count == 1 else "")
        lines.append(f"{index}. {preview}{badge}")

    text = "\n".join(lines)
    if len(text) > 3800:
        text = "\n".join(lines[:60]) + f"\n... va yana {len(lines) - 60} ta"

    await update.message.reply_text(text, reply_markup=KB.kb_posts_menu())


def _posts_header(count: int, limits: dict) -> str:
    max_posts = int(limits.get("max_posts") or 0)
    if max_posts > 0:
        return f"📝 POSTLAR ({count}/{max_posts} ta) · {limits.get('label', '')}"
    return f"📝 POSTLAR ({count} ta)"


# ─────────────────────────────────────────────────────────────────────────
# POST QO'SHISH / TAHRIRLASH — BOSHLASH
# ─────────────────────────────────────────────────────────────────────────
async def begin_add_post_state(uid: int) -> str:
    """Callback menyusidan post qo'shish holatini ochadi (matn qaytaradi)."""
    state = _ensure_state(uid)
    state.pop("album", None)
    state.update({"step": "add_post", "mode": "add", "ts": time.time()})
    return T.ASK_ADD_POST


async def begin_add_post(update: Update) -> None:
    """➕ Post qo'shish tugmasi bosilganda."""
    uid = update.effective_user.id
    state = _ensure_state(uid)
    state.update(
        {"step": "add_post", "mode": "add", "album": None, "ts": time.time()}
    )
    state.pop("album", None)
    await update.message.reply_text(
        T.ASK_ADD_POST,
        reply_markup=KB.kb_input_cancel(),
    )


async def begin_edit_post_state(uid: int, post_id: int) -> str:
    """Callback oynasidan tahrirlash holatini ochadi.

    Returns:
        Foydalanuvchiga yuboriladigan matn; post topilmasa bo'sh satr.
    """
    post = await db.get_post(post_id, uid)
    if not post:
        return ""
    state = _ensure_state(uid)
    state.pop("album", None)
    state.update(
        {
            "step": "add_post",
            "mode": "edit",
            "post_id": int(post["id"]),
            "ts": time.time(),
        }
    )
    return T.ask_edit_post(truncate(post.get("text") or "(media)", 120))


async def begin_edit_post(update: Update, post_id: int) -> None:
    """✏️ Postni tahrirlashni boshlaydi (yangi xabar eski postni almashtiradi)."""
    uid = update.effective_user.id
    post = await db.get_post(post_id, uid)
    if not post:
        await update.message.reply_text(T.POST_NOT_FOUND, reply_markup=KB.kb_posts_menu())
        return
    state = _ensure_state(uid)
    state.pop("album", None)
    state.update(
        {
            "step": "add_post",
            "mode": "edit",
            "post_id": int(post["id"]),
            "ts": time.time(),
        }
    )
    await update.message.reply_text(
        T.ask_edit_post(truncate(post.get("text") or "(media)", 120)),
        reply_markup=KB.kb_input_cancel(),
    )


# ─────────────────────────────────────────────────────────────────────────
# POST QO'SHISH — YUNDIRUVCHI (message handler)
# ─────────────────────────────────────────────────────────────────────────
async def handle_add_post(
    update: Update,
    *,
    target_uid: int | None = None,
    state_uid: int | None = None,
    allow_album: bool = True,
) -> None:
    """Foydalanuvchi post uchun xabar/media yubordi.

    Args:
        target_uid: admin boshqa foydalanuvchi nomidan post qo'shayotganda —
            post kimga tegishli bo'ladi.
        state_uid: FSM holati qaysi foydalanuvchi ostida yuritiladi (admin
            oqimida bu adminning UID'i).
        allow_album: ``False`` bo'lsa har bir media alohida post bo'ladi
            (admin oqimida albom yig'ish o'chirilgan).
    """
    msg = update.message
    if msg is None:
        return
    uid = target_uid or update.effective_user.id
    owner = state_uid if state_uid is not None else uid
    state = _state(owner)
    if state is None:
        from bot.login import user_states

        state = user_states.setdefault(owner, {})

    # ── 1. Albomni davom ettirish yoki yakunlash ──
    pending = state.get("album")
    group_id = getattr(msg, "media_group_id", None) if allow_album else None

    if pending and pending.get("gid") != group_id:
        # Boshqa guruh media yoki oddiy xabar keldi — yig'ilgan albomni saqlaymiz.
        await finalize_pending_album(uid, msg, owner=owner)
        state = _state(owner) or {}
        pending = None

    if not pending and state.get("step") not in ("add_post", "edit_post"):
        # Holat (timeout yoki boshqa menyu tufayli) yopilgan — jim qaytamiz.
        return

    text, entities = message_text_and_entities(msg)
    has_media = bool(msg.photo or msg.video or msg.document)

    # ── 2. Media yo'q: matnli post yoki albom uchun caption ──
    if not has_media:
        if not text.strip():
            await msg.reply_text(T.POST_EMPTY_ERROR, reply_markup=KB.kb_input_cancel())
            return
        if state.get("album"):
            state["album"]["text"] = text
            state["album"]["entities"] = entities
            state["album"]["generation"] = int(state["album"].get("generation", 0)) + 1
            state["ts"] = time.time()
            await msg.reply_text(
                T.album_caption_saved(len(state["album"]["items"]), text),
                reply_markup=KB.kb_album_done(),
            )
            return
        await _save_post(uid, text, entities, [], state, msg, owner=owner)
        return

    # ── 3. Bitta fayl ──
    if group_id is None:
        if state.get("album"):
            await finalize_pending_album(uid, msg, owner=owner)
            state = _state(owner) or {}
        items, errors = await download_message_media(msg, uid)
        if errors and not items:
            await msg.reply_text("\n".join(errors), reply_markup=KB.kb_input_cancel())
            return
        await _save_post(uid, text, entities, items, state, msg, owner=owner)
        return

    # ── 4. Albom: yig'amiz ──
    album = state.get("album") or {"gid": group_id, "items": [], "generation": 0}
    album["gid"] = group_id
    remaining = MAX_ALBUM_FILES - len(album["items"])
    items, errors = await download_message_media(msg, uid, remaining=remaining)
    album["items"].extend(items)
    if text.strip() and not album.get("text"):
        album["text"] = text
        album["entities"] = entities
    album["generation"] = int(album.get("generation", 0)) + 1
    album["ts"] = time.time()
    album["chat_id"] = msg.chat_id
    state["album"] = album
    state["step"] = state.get("step") or "add_post"
    state["mode"] = state.get("mode") or "add"
    state["ts"] = time.time()

    if errors:
        await msg.reply_text("\n".join(errors))
    if len(album["items"]) >= MAX_ALBUM_FILES:
        await finalize_pending_album(uid, msg, owner=owner)
        return

    await msg.reply_text(
        T.album_collecting(len(album["items"])),
        reply_markup=KB.kb_album_done(),
    )
    _schedule_flush(uid, group_id, album["generation"], owner=owner)


def _schedule_flush(
    uid: int, gid: str, generation: int, *, owner: int | None = None
) -> None:
    """Albom tugadi deb hisoblash uchun qisqa kutish (foydalanuvchi tugmasi shart emas)."""
    if ALBUM_DEBOUNCE_S <= 0:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _flush() -> None:
        await asyncio.sleep(ALBUM_DEBOUNCE_S)
        state = _state(owner if owner is not None else uid) or {}
        album = state.get("album") or {}
        if album.get("gid") == gid and int(album.get("generation", 0)) == generation:
            with contextlib.suppress(Exception):
                await finalize_pending_album(uid, None, owner=owner)

    loop.create_task(_flush(), name=f"album-flush-{uid}")


# ─────────────────────────────────────────────────────────────────────────
# ALBOMNI YAKUNLASH
# ─────────────────────────────────────────────────────────────────────────
async def finalize_pending_album(
    uid: int, msg=None, *, owner: int | None = None
) -> tuple[bool, str]:
    """Yig'ilgan albomni bitta post sifatida saqlaydi.

    Returns:
        (saqlandi, xabar_matni)
    """
    owner = owner if owner is not None else uid
    state = _state(owner) or {}
    album = state.get("album") or {}
    items = list(album.get("items") or [])
    text = album.get("text") or ""
    entities = list(album.get("entities") or [])

    if not items:
        if not text.strip():
            state.pop("album", None)
            return False, ""
        state.pop("album", None)
        await _save_post(uid, text, entities, [], state, msg, owner=owner)
        return True, "text"

    state.pop("album", None)
    # Matnsiz albom ham ruxsat etilgan — e'lon faqat rasmlardan iborat bo'ladi.
    await _save_post(uid, text, entities, items, state, msg, owner=owner)
    return True, f"{len(items)} ta media"


async def sweep_stale_albums(max_age_s: float = 120) -> int:
    """Yopilmay qolgan albomlarni janitor orqali saqlab qo'yadi.

    Foydalanuvchi albomni yuborib, tugmani bosmasa va keyingi xabarni ham
    yubormasa — media yo'qolib ketmasligi uchun shu tozalov ishlaydi.
    """
    from bot.login import user_states

    swept = 0
    for uid, state in list(user_states.items()):
        album = state.get("album") if isinstance(state, dict) else None
        if not album or not album.get("items"):
            continue
        if time.time() - float(album.get("ts", 0)) < max_age_s:
            continue
        with contextlib.suppress(Exception):
            await finalize_pending_album(int(uid))
            swept += 1
    return swept


# ─────────────────────────────────────────────────────────────────────────
# SAQLASH (add/update)
# ─────────────────────────────────────────────────────────────────────────
async def _respond(
    msg, text: str, uid: int, chat_id: int | None = None
) -> None:
    """Javobni imkon qadar xabar ustiga, bo'lmasa shaxsiy chatga yuboradi."""
    from bot.login import application
    from bot.menu import worker_manager

    running = bool(worker_manager and worker_manager.is_running(uid))
    markup = KB.kb_main(running=running)
    if msg is not None:
        await msg.reply_text(text, reply_markup=markup)
        return
    if application and chat_id:
        with contextlib.suppress(Exception):
            await application.bot.send_message(chat_id, text, reply_markup=markup)


async def _save_post(
    uid: int,
    text: str,
    entities: list[dict],
    media: list[dict],
    state: dict,
    msg=None,
    *,
    owner: int | None = None,
) -> None:
    """Postni bazaga yozadi (yangi yoki tahrirlash) va natijani xabar qiladi."""
    owner = owner if owner is not None else uid
    mode = state.get("mode") or "add"
    chat_id = (state.get("album") or {}).get("chat_id") or uid

    if mode == "edit" and state.get("post_id"):
        post_id = int(state["post_id"])
        old = await db.get_post(post_id, uid) or {}
        old_paths = post_media_paths(old)
        new_paths = [item["path"] for item in media]
        # Matn berilib yangi media yuborilmasa — eski rasmlar saqlanadi.
        payload = media or old.get("media") or []
        if media:
            remove_media([path for path in old_paths if path not in new_paths])
        ok = await db.update_post(uid, post_id, text, entities, None, payload, None)
        _clear_state(owner)
        if not ok:
            remove_media(new_paths)
            await _respond(msg, T.GENERIC_ERROR, uid, chat_id)
            return
        log(f"✏️ Post tahrirlandi: {uid} (#{post_id})")
        await _respond(
            msg,
            T.POST_UPDATED.format(
                n=await db.count_posts(uid),
                kind=media_kind_label({"media": payload}),
                preview=truncate(text or "(media)", 100),
            ),
            uid,
            chat_id,
        )
        return

    ok, reason, post_id = await db.add_post(uid, text, entities, None, media, True)
    _clear_state(owner)
    if not ok:
        remove_media([item["path"] for item in media])
        message = (
            T.POSTS_LIMIT.format(max_posts=await db.max_posts_for(uid))
            if reason == "limit"
            else T.GENERIC_ERROR
        )
        await _respond(msg, message, uid, chat_id)
        return

    log(f"📝 Post qo'shildi: {uid} (#{post_id}, media={len(media)})")
    await _respond(
        msg,
        T.post_added_text(
            n=await db.count_posts(uid),
            kind=media_kind_label({"media": media}),
            preview=truncate(text or "(media)", 100),
        ),
        uid,
        chat_id,
    )


# ─────────────────────────────────────────────────────────────────────────
# POST KO'RINISHI (PREVIEW) VA SANOVDAN YUBORISH
# ─────────────────────────────────────────────────────────────────────────
async def preview_post(uid: int, post_id: int) -> tuple[bool, str]:
    """Postni foydalanuvchining shaxsiy chatiga ko'rinish sifatida yuboradi.

    Guruhlarga yuborishni yoqmasdan turib «e'lon qanday ko'rinadi»ni
    tekshirish imkoni. Shablon belgilari ({vaqt}, {kun}) shu yerda ham
    qo'llaniladi, ya'ni foydalanuvchi haqiqiy chiqadigan matnni ko'radi.
    """
    from bot.login import application

    post = await db.get_post(post_id, uid)
    if not post:
        return False, T.POST_NOT_FOUND
    if not application:
        return False, T.GENERIC_ERROR

    from core.utils import render_template

    text, entities = render_template(post.get("text") or "", post.get("entities") or [])
    paths = [
        item["path"]
        for item in (post.get("media") or [])
        if item.get("path")
    ]

    if not paths:
        await application.bot.send_message(
            uid,
            text or "❌ Bo'sh post",
            entities=dicts_to_ptb_entities(entities) or None,
        )
        return True, "text"

    try:
        if len(paths) > 1:
            await application.bot.send_media_group(
                uid,
                media=[_input_media(path) for path in paths[:MAX_ALBUM_FILES]],
            )
            if text.strip():
                await application.bot.send_message(uid, text)
            return True, "album"
        await _send_single(uid, paths[0], text, entities)
        return True, "media"
    except Exception as exc:
        log(f"preview xato {uid}: {type(exc).__name__}", "warning")
        with contextlib.suppress(Exception):
            await application.bot.send_message(
                uid, text or "❌ Ko'rinishni yuborib bo'lmadi."
            )
        return True, "fallback"


def _input_media(path: str):
    """Faylni turiga qarab PTB media obyektiga aylantiradi."""
    lowered = path.lower()
    if lowered.endswith((".mp4", ".mov", ".webm", ".mkv")):
        return InputMediaVideo(media=path)
    return InputMediaPhoto(media=path)


async def _send_single(uid: int, path: str, text: str, entities: list[dict]) -> None:
    """Bitta faylni turiga qarab yuboradi (fayl tutqichi har doim yopiladi)."""
    from bot.login import application

    lowered = path.lower()
    caption_entities = dicts_to_ptb_entities(entities) or None
    kwargs = {"caption": text or None, "entities": caption_entities}
    with open(path, "rb") as handle:
        if lowered.endswith((".mp4", ".mov", ".webm", ".mkv")):
            await application.bot.send_video(uid, video=handle, **kwargs)
        elif lowered.endswith((".mp3", ".m4a", ".ogg")):
            await application.bot.send_audio(uid, audio=handle, **kwargs)
        elif lowered.endswith(
            (".pdf", ".txt", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx")
        ):
            await application.bot.send_document(uid, document=handle, **kwargs)
        else:
            await application.bot.send_photo(uid, photo=handle, **kwargs)


async def send_test_to_group(uid: int, post_id: int, group_id: int) -> tuple[bool, str]:
    """Bitta postni BITTA guruhga sinov uchun yuboradi (postingni ishga tushirmasdan)."""
    from worker.worker import client_pool, send_post

    if not client_pool:
        return False, T.START_BUSY

    user = await db.get_user(uid)
    if not user or not user.get("session"):
        return False, "❌ Sessiya topilmadi. Qaytadan 🔑 Login qiling."

    post = await db.get_post(post_id, uid)
    record = await db.get_chat_record(uid, group_id)
    if not post or not record:
        return False, "❌ Post yoki guruh topilmadi."

    from worker.client_pool import PoolBusyError, SessionInvalidError

    try:
        client = await client_pool.acquire(uid, user["session"])
    except SessionInvalidError:
        return False, T.START_SESSION_INVALID
    except PoolBusyError:
        return False, T.START_BUSY
    try:
        await asyncio.wait_for(send_post(client, str(record["value"]), post), timeout=30)
    except Exception as exc:
        await db.log_send(uid, False, group_id=group_id, post_id=post_id, error=type(exc).__name__)
        return False, T.test_send_failed(type(exc).__name__)
    finally:
        await client_pool.release(uid)

    await db.log_send(uid, True, group_id=group_id, post_id=post_id)
    await db.touch_last_active(uid)
    log(f"🧪 Sinov yuborildi: {uid} → {record['value']}")
    return True, T.test_send_done(str(record["value"]))


# ─────────────────────────────────────────────────────────────────────────
# POST O'CHIRISH
# ─────────────────────────────────────────────────────────────────────────
async def begin_delete_posts(update: Update) -> None:
    """🗑 Post o'chirish tugmasi bosilganda."""
    uid = update.effective_user.id
    posts = await db.get_posts(uid)
    if not posts:
        await update.message.reply_text(T.POSTS_EMPTY)
        return
    await update.message.reply_text(
        T.ASK_DEL_POST, reply_markup=KB.kb_posts_delete(posts)
    )


async def begin_edit_picker(update: Update) -> None:
    """✏️ Tahrirlash uchun post tanlash oynasi."""
    uid = update.effective_user.id
    posts = await db.get_posts(uid)
    if not posts:
        await update.message.reply_text(T.POSTS_EMPTY, reply_markup=KB.kb_posts_menu())
        return
    await update.message.reply_text(
        T.ASK_EDIT_POST, reply_markup=KB.kb_posts_edit(posts)
    )


async def begin_test_picker(update: Update) -> None:
    """🧪 Sinov yuborish uchun post tanlash oynasi."""
    uid = update.effective_user.id
    posts = await db.get_posts(uid)
    if not posts:
        await update.message.reply_text(
            T.POSTS_EMPTY, reply_markup=KB.kb_posts_menu()
        )
        return
    if not await db.get_chats(uid):
        await update.message.reply_text(
            T.GROUPS_EMPTY_HINT, reply_markup=KB.kb_groups_menu()
        )
        return
    await update.message.reply_text(
        T.ASK_TEST_PICK, reply_markup=KB.kb_posts_test(posts)
    )


async def begin_preview_picker(update: Update) -> None:
    """👁 Ko'rinishni ko'rsatish uchun post tanlash oynasi."""
    uid = update.effective_user.id
    posts = await db.get_posts(uid)
    if not posts:
        await update.message.reply_text(T.POSTS_EMPTY, reply_markup=KB.kb_posts_menu())
        return
    await update.message.reply_text(
        T.ASK_PREVIEW_POST, reply_markup=KB.kb_posts_preview(posts)
    )


async def delete_post_by_id(uid: int, post_id: int) -> tuple[bool, str]:
    """UID va barqaror post ID bo'yicha o'chiradi."""
    post = await db.remove_post_by_id(uid, post_id)
    if not post:
        return False, ""
    remove_media(post_media_paths(post))
    text = (post.get("text") or "").strip().replace("\n", " ")
    preview = truncate(text or "(media)", 80)
    log(f"🗑 Post o'chirildi: {uid} post_id={post_id}")
    return True, preview


async def delete_post_by_index(uid: int, index: int) -> tuple[bool, str]:
    """Eski chaqiruvlar uchun indeksni UID-scope qilingan ID'ga aylantiradi."""
    posts = await db.get_posts(uid)
    if not 0 <= index < len(posts):
        return False, ""
    return await delete_post_by_id(uid, int(posts[index]["id"]))
